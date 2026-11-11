#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
import base64
import json
import os
import sys
import unittest
import urllib.request
from test_host import Client

PORT = int(os.environ['GW_MOCK_PORT'])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../tests/mock'))
sys.path.insert(0, ROOT)
import mock_poa


class Soap(unittest.TestCase):
    def setUp(self):
        self.c = Client()

    def tearDown(self):
        self.c.close()

    def login(self, **kw):
        args = dict(host='127.0.0.1', port=PORT, username=mock_poa.USER, password=mock_poa.PASSWORD, tls=False)
        args.update(kw)
        return self.c.call('login', **args)

    def test_mailbox(self):
        self.assertTrue(self.login()['ok'])
        folders = self.c.call('listFolders')['result']['folders']
        inbox = next(f for f in folders if f['role'] == 'inbox')
        self.assertEqual(inbox['id'], mock_poa.FOLDERS['inbox'])
        first = self.c.call('listMessages', folderId=inbox['id'], limit=1)['result']
        self.assertEqual(len(first['messages']), 1)
        self.assertTrue(first['hasMore'])
        second = self.c.call('listMessages', folderId=inbox['id'], offset=1, limit=1)['result']
        self.assertNotEqual(first['messages'][0]['id'], second['messages'][0]['id'])
        messages = self.c.call('listMessages', folderId=inbox['id'])['result']['messages']
        self.assertTrue(any(m['id'] == mock_poa.MAIL2 for m in messages))
        self.assertEqual(self.c.call('listMessages', folderId='invalid')['error']['code'], 'NOT_FOUND')
        self.assertEqual(self.c.call('listMessages', folderId=inbox['id'], limit=0)['error']['code'], 'INVALID_REQUEST')
        data, offset = bytearray(), 0
        while True:
            part = self.c.call('getMessage', messageId=mock_poa.MAIL2, offset=offset, limit=97)
            self.assertTrue(part['ok'], part)
            part = part['result']
            data.extend(base64.b64decode(part['data']))
            offset = part['nextOffset']
            if part['done']:
                break
        self.assertIn(b'Subject:', data)
        self.assertIn(b'X-Original-MIME: yes', data)
        self.assertEqual(len(data), part['total'])
        self.assertEqual(self.c.call('getMessage', messageId='absent')['ok'], False)
        for read in [False, True]:
            self.assertTrue(self.c.call('markRead', messageId=mock_poa.MAIL1, read=read)['ok'])
            m = self.c.call('listMessages', folderId=inbox['id'])['result']['messages']
            self.assertEqual(next(x for x in m if x['id'] == mock_poa.MAIL1)['read'], read)
        # Core automatically renews one expired session, without exposing tokens.
        urllib.request.urlopen(f'http://127.0.0.1:{PORT}/_test/expire').close()
        self.assertTrue(self.c.call('listFolders')['ok'])
        self.assertTrue(self.c.call('logout')['ok'])
        self.assertEqual(self.c.call('listFolders')['error']['code'], 'NOT_LOGGED_IN')

    def test_mutations(self):
        self.assertTrue(self.login()['ok'])
        inbox, trash = mock_poa.FOLDERS['inbox'], mock_poa.FOLDERS['trash']
        self.assertTrue(self.c.call('copyMessages', messageId=mock_poa.MAIL1, destinationId=trash)['ok'])
        copied = self.c.call('listMessages', folderId=trash)['result']['messages']
        self.assertTrue(any(m['id'].split('@')[0] == mock_poa.MAIL1.split('@')[0] for m in copied))
        self.assertTrue(self.c.call('moveMessages', messageId=mock_poa.MAIL2, folderId=inbox, destinationId=trash)['ok'])
        remaining = self.c.call('listMessages', folderId=inbox)['result']['messages']
        self.assertFalse(any(m['id'] == mock_poa.MAIL2 for m in remaining))
        self.assertTrue(self.c.call('deleteMessages', messageId=mock_poa.MAIL1, folderId=inbox)['ok'])
        urllib.request.urlopen(f'http://127.0.0.1:{PORT}/_test/reset').close()

    def test_large_download_and_hard_limit(self):
        import importlib.util
        import threading
        import pathlib
        from http.server import HTTPServer
        spec=importlib.util.spec_from_file_location('large_mock', pathlib.Path(ROOT)/'run-with-mock.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class Large(module.Handler):
            size=16*1024*1024+1
            def do_GET(self):
                if self.path.startswith('/attachment'):
                    self.send_response(200)
                    self.send_header('Content-Length',str(self.size))
                    self.end_headers()
                    try:
                        remaining=self.size
                        while remaining:
                            n=min(16384,remaining)
                            self.wfile.write(b'x'*n)
                            remaining-=n
                    except (BrokenPipeError,ConnectionResetError):
                        pass
                else:
                    super().do_GET()
        server=HTTPServer(('127.0.0.1',0),Large)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            self.assertTrue(self.login(port=server.server_port)['ok'])
            result=self.c.call('getMessage',messageId=mock_poa.MAIL2)
            self.assertEqual(result['error']['code'],'MESSAGE_TOO_LARGE')
            self.assertTrue(self.c.call('ping')['ok'])
            Large.size=1024*1024
            data,offset=bytearray(),0
            while True:
                part=self.c.call('getMessage',messageId=mock_poa.MAIL2,offset=offset)['result']
                chunk=base64.b64decode(part['data'])
                self.assertLessEqual(len(chunk),128*1024)
                data.extend(chunk)
                offset=part['nextOffset']
                if part['done']: break
            self.assertEqual(data,b'x'*(1024*1024))
            self.assertEqual(part['total'],len(data))
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)

    def test_trusted_tls(self):
        self.c.close()
        old = os.environ.get('GROUPWISE_CA_DIR')
        os.environ['GROUPWISE_CA_DIR'] = os.path.dirname(os.environ['GW_MOCK_CA'])
        try:
            self.c = Client()
        finally:
            if old is None: os.environ.pop('GROUPWISE_CA_DIR', None)
            else: os.environ['GROUPWISE_CA_DIR'] = old
        self.assertTrue(self.login(port=int(os.environ['GW_MOCK_TLS_PORT']), tls=True)['ok'])
        self.assertTrue(self.c.call('listFolders')['ok'])

    def test_auth_network_and_validation(self):
        self.assertEqual(self.login(password='wrong')['error']['code'], 'AUTH_FAILED')
        self.assertEqual(self.login(username='wrong')['error']['code'], 'AUTH_FAILED')
        self.assertEqual(self.login(port=1)['error']['code'], 'NETWORK_ERROR')
        self.assertEqual(self.login(host='http://bad')['error']['code'], 'INVALID_REQUEST')
        # Trusted TLS succeeds through the core's user CA support; untrusted fails.
        tls_port = int(os.environ['GW_MOCK_TLS_PORT'])
        self.assertFalse(self.login(port=tls_port, tls=True)['ok'])


if __name__ == '__main__':
    unittest.main()
