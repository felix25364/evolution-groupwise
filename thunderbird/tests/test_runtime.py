#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Mock-backed Thunderbird 153 integration. Creates and removes its own HOME/profile.
Run under ../../tests/mock/run-with-mock.py; requires an installed Thunderbird and Xvfb.
"""
import argparse
import json
import os
import pathlib
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from marionette import Marionette
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'tests/mock'))
from mock_poa import USER, PASSWORD, MAIL2

PRELUDE = '''
const {MailServices}=ChromeUtils.importESModule("resource:///modules/MailServices.sys.mjs");
const {ExtensionParent}=ChromeUtils.importESModule("resource://gre/modules/ExtensionParent.sys.mjs");
const extension=ExtensionParent.GlobalManager.getExtension("groupwise@evolution-groupwise.org");
const api=extension?.apiManager.getAPI("groupwise",extension,"addon_parent");
const server=[...MailServices.accounts.allServers].find(s=>s.type==="groupwise");
const inbox=server?.rootFolder.getFolderWithFlags(Ci.nsMsgFolderFlags.Inbox);
'''


class Runtime:
    def __init__(self, root, binary):
        self.root, self.binary = root, binary
        self.profile = root/'profile'
        self.profile.mkdir()
        self.log = None
        self.proc = None
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            self.port = s.getsockname()[1]
        prefs = {'marionette.port':self.port, 'mail.provider.suppress_dialog_on_startup':True,
                 'mail.shell.checkDefaultClient':False, 'extensions.experiments.enabled':True,
                 'xpinstall.signatures.required':False, 'mail.spotlight.firstRunDone':True,
                 'extensions.autoDisableScopes':0, 'mailnews.start_page.enabled':False}
        (self.profile/'user.js').write_text(''.join(f'user_pref({json.dumps(k)},{json.dumps(v)});\n' for k,v in prefs.items()))

    def start(self):
        self.log = (self.root/'thunderbird.log').open('a')
        env = dict(os.environ, HOME=str(self.root))
        self.proc = subprocess.Popen(['xvfb-run','-a',self.binary,'--no-remote','--profile',str(self.profile),
                                      '--marionette','--remote-allow-system-access'],
                                     env=env, stdout=self.log, stderr=self.log, start_new_session=True)
        self.m = Marionette(self.port)
        self.m.call('WebDriver:SetTimeouts', {'script':60000})
        return self

    def script(self, code, args=None, async_=False):
        value = self.m.script(PRELUDE+code, args or [], async_)
        result = value.get('value')
        if isinstance(result, dict) and 'testError' in result:
            raise AssertionError(result)
        return result

    def wait(self, code, seconds=15):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            result = self.script(code)
            if result:
                return result
            time.sleep(.1)
        raise AssertionError('Runtime readiness condition timed out: '+code+' '+str(self.script('return {error:server?.getStringValue("groupwiseLastError"),logs:Services.console.getMessageArray().map(m=>m.message).filter(s=>/backend.js|experiment.js/.test(s))};')))

    def stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                self.m.script('Services.prefs.savePrefFile(null); Services.startup.quit(Ci.nsIAppStartup.eAttemptQuit); return true;')
                self.proc.wait(timeout=15)
            except (OSError, EOFError, RuntimeError, subprocess.TimeoutExpired):
                if self.proc.poll() is None:
                    os.killpg(self.proc.pid,signal.SIGTERM)
                    self.proc.wait(timeout=10)
        self.log.close()
        self.proc = None


SNAPSHOT = '''return {key:server.key, count:server.rootFolder.descendants.length,
  headers:[...inbox.messages].map(h=>({key:h.messageKey,id:h.getStringProperty("groupwiseId"),read:h.isRead})),
  flags:inbox.flags,unread:inbox.getNumUnread(false)};'''
ASYNC = 'const done=arguments[arguments.length-1];\n'
CATCH = '.catch(e=>done({testError:String(e),stack:e.stack}));'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xpi',type=pathlib.Path,required=True)
    p.add_argument('--host',type=pathlib.Path,required=True)
    p.add_argument('--thunderbird',default='thunderbird')
    args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='groupwise-thunderbird-test-') as directory:
        root=pathlib.Path(directory)
        native=root/'.mozilla/native-messaging-hosts'
        native.mkdir(parents=True)
        manifest=native/'org.evolution_groupwise.host.json'
        manifest.write_text(json.dumps({'name':'org.evolution_groupwise.host','description':'Isolated GroupWise test',
            'path':str(args.host.resolve()),'type':'stdio','allowed_extensions':['groupwise@evolution-groupwise.org']}))
        runtime=Runtime(root,args.thunderbird)
        try:
            runtime.start()
            version=runtime.script('return Services.appinfo.version;')
            assert version.startswith('153.'), version
            runtime.m.call('Addon:Install',{'path':str(args.xpi.resolve()),'temporary':False})
            runtime.wait('return Components.manager.QueryInterface(Ci.nsIComponentRegistrar).isContractIDRegistered("@mozilla.org/messenger/server;1?type=groupwise");')
            settings={'host':'127.0.0.1','port':int(os.environ['GW_MOCK_PORT']),
                      'username':USER,'password':PASSWORD,'tls':False}
            created=runtime.script(ASYNC+'''api.scope.Backend.createAccount(arguments[0])
                .then(c=>api.scope.Backend.sync(c.serverKey).then(()=>done(c)))'''+CATCH,[settings],True)
            first=runtime.script(SNAPSHOT)
            assert first['count']==10 and len(first['headers'])==2,first
            assert first['flags']&4096 and first['unread']==1,first
            print('PASS native account, real nested folders, special flags, real header database and unread count',flush=True)
            second_created=runtime.script(ASYNC+'api.scope.Backend.createAccount(arguments[0]).then(done)'+CATCH,[settings],True)
            assert second_created==created
            runtime.script(ASYNC+'api.scope.Backend.sync(server.key).then(done)'+CATCH,async_=True)
            assert runtime.script(SNAPSHOT)==first
            print('PASS idempotent setup and refresh; stable message keys',flush=True)

            result=runtime.script(ASYNC+'''
              const h=[...inbox.messages].find(h=>h.subject==="Test message");
              const uri=inbox.getUriForMsg(h),service=MailServices.messageServiceFromURI(uri);
              let bytes="";
              service.streamMessage(uri,{QueryInterface:ChromeUtils.generateQI(["nsIStreamListener"]),
                onStartRequest(){},onDataAvailable(req,stream,off,count){
                  const b=Cc["@mozilla.org/binaryinputstream;1"].createInstance(Ci.nsIBinaryInputStream);
                  b.setInputStream(stream);bytes+=b.readBytes(count);
                },onStopRequest(req,status){done({status,size:bytes.length,original:bytes.includes("X-Original-MIME: yes")});}
              },null,null,false,"",false);
            ''',async_=True)
            assert result=={'status':0,'size':int(os.environ.get('GW_RUNTIME_MIME_SIZE','276')),'original':True},result
            headers=runtime.script(ASYNC+'''
              const h=[...inbox.messages].find(h=>h.subject==="Test message");
              let bytes="";
              MailServices.messageServiceFromURI(inbox.getUriForMsg(h)).streamHeaders(inbox.getUriForMsg(h),{
                QueryInterface:ChromeUtils.generateQI(["nsIStreamListener"]),onStartRequest(){},
                onDataAvailable(req,stream,off,count){const b=Cc["@mozilla.org/binaryinputstream;1"].createInstance(Ci.nsIBinaryInputStream);b.setInputStream(stream);bytes+=b.readBytes(count);},
                onStopRequest(req,status){done({status,header:bytes.includes("X-Original-MIME: yes"),hasBody:bytes.includes("Hello,")});}
              },null,false);
            ''',async_=True)
            assert headers=={'status':0,'header':True,'hasBody':False},headers
            permissions=runtime.script(ASYNC+'''api.scope.Backend.ensureMime([...inbox.messages].find(h=>h.subject==="Test message")).then(f=>done(f.permissions&0o777))'''+CATCH,async_=True)
            assert permissions==0o600,permissions
            saved=runtime.script(ASYNC+'''
              const h=[...inbox.messages].find(h=>h.subject==="Test message");
              const file=Cc["@mozilla.org/file/local;1"].createInstance(Ci.nsIFile);file.initWithPath(arguments[0]);
              MailServices.messageServiceFromURI(inbox.getUriForMsg(h)).saveMessageToDisk(inbox.getUriForMsg(h),file,false,{
                OnStartRunningUrl(){},OnStopRunningUrl(url,status){done(status);}
              },false,null);
            ''',[str(root/'saved.eml')],True)
            assert saved==0 and (root/'saved.eml').stat().st_size==int(os.environ.get('GW_RUNTIME_MIME_SIZE','276'))
            print('PASS actual Thunderbird message service streams original mock-backed MIME',flush=True)

            result=runtime.script('''
              const w=Services.wm.getMostRecentWindow("mail:3pane");
              const pane=w.document.getElementById("tabmail").currentAbout3Pane;
              pane.displayFolder(inbox);return !!pane.folderPane.getRowForFolder(inbox.URI);
            ''')
            assert result
            runtime.wait('''const pane=Services.wm.getMostRecentWindow("mail:3pane").document.getElementById("tabmail").currentAbout3Pane;
              return pane.gDBView?.rowCount===2;''')
            runtime.script('''const pane=Services.wm.getMostRecentWindow("mail:3pane").document.getElementById("tabmail").currentAbout3Pane;
              pane.selectMessage([...inbox.messages].find(h=>h.subject==="Test message"));return true;''')
            runtime.wait('''const pane=Services.wm.getMostRecentWindow("mail:3pane").document.getElementById("tabmail").currentAbout3Pane;
              const msg=pane.messageBrowser.contentWindow;
              return msg.msgLoaded && msg.getMessagePaneBrowser().contentDocument?.body?.textContent?.includes("Hello,");''')
            if os.environ.get('GW_RUNTIME_HTML'):
                runtime.wait('''const pane=Services.wm.getMostRecentWindow("mail:3pane").document.getElementById("tabmail").currentAbout3Pane;
                  const msg=pane.messageBrowser.contentWindow;
                  return !!msg.getMessagePaneBrowser().contentDocument?.querySelector("#groupwise-html") &&
                    msg.currentAttachments.some(a=>a.name==="proof.txt" || a.displayName==="proof.txt");''')
                print('PASS HTML alternative and attachment in Thunderbird MIME UI',flush=True)
            print('PASS normal folder tree, two-row message list and completed MIME rendering in the normal message pane',flush=True)

            # UI read state goes through the native helper before the database changes.
            runtime.script('inbox.markMessagesRead([...inbox.messages],true);return true;')
            runtime.wait('return [...inbox.messages].every(h=>h.isRead);')
            state=urllib.request.urlopen(f'http://127.0.0.1:{settings["port"]}/_test/read?id={MAIL2}').read()
            assert state==b'1'
            print('PASS native read-state write-through from Thunderbird',flush=True)

            # Removing the test-only manifest must produce a useful missing-host error.
            hidden=manifest.with_suffix('.disabled')
            manifest.rename(hidden)
            try:
                result=runtime.script(ASYNC+'api.request("missing-host-test","ping").then(()=>done("unexpected success"),e=>done(String(e)));',async_=True)
                assert 'HOST_DISCONNECTED' in result,result
            finally:
                hidden.rename(manifest)
            print('PASS real missing-native-host error',flush=True)
            # Verify disable removes owned factories while files remain.
            result=runtime.script(ASYNC+'''const {AddonManager}=ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
              AddonManager.getAddonByID("groupwise@evolution-groupwise.org").then(a=>a.disable()).then(()=>done(true))'''+CATCH,async_=True)
            assert result
            state=runtime.script('const r=Components.manager.QueryInterface(Ci.nsIComponentRegistrar);try {Cc["@mozilla.org/messenger/server;1?type=groupwise"].createInstance(Ci.nsIMsgIncomingServer);return {registered:r.isContractIDRegistered("@mozilla.org/messenger/server;1?type=groupwise"),created:true};}catch(e){return {registered:r.isContractIDRegistered("@mozilla.org/messenger/server;1?type=groupwise"),created:false};}')
            assert not state['created'],state
            assert list((runtime.profile/'GroupWise').rglob('*.msf'))
            runtime.script(ASYNC+'''const {AddonManager}=ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
              AddonManager.getAddonByID("groupwise@evolution-groupwise.org").then(a=>a.enable()).then(()=>done(true))'''+CATCH,async_=True)
            runtime.wait('return Components.manager.QueryInterface(Ci.nsIComponentRegistrar).isContractIDRegistered("@mozilla.org/messenger/server;1?type=groupwise");')
            runtime.script('server.setStringValue("groupwiseLastError","pending test refresh"); server.getNewMessages(server.rootFolder,null,null);return true;')
            runtime.wait('return server.getStringValue("groupwiseLastError")==="";')
            print('PASS disable/unregister, mail-data retention and re-enable',flush=True)
            before_restart=runtime.script(SNAPSHOT)
            runtime.stop()
            runtime.start()
            runtime.wait('return !!server && !!inbox;')
            after_restart=runtime.script(SNAPSHOT)
            assert before_restart==after_restart,(before_restart,after_restart)
            runtime.script(ASYNC+'api.scope.Backend.sync(server.key).then(done)'+CATCH,async_=True)
            assert runtime.script(SNAPSHOT)==after_restart
            print('PASS installed XPI and native account survive real Thunderbird restart; fresh host uses saved credentials',flush=True)
            errors=runtime.script('return Services.console.getMessageArray().map(m=>m.message).filter(s=>/JavaScript Error/.test(s)&&/groupwise|backend.js|experiment.js/i.test(s));')
            assert errors==[],errors
            print('PASS no GroupWise JavaScript exceptions in final runtime',flush=True)
        finally:
            runtime.stop()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
