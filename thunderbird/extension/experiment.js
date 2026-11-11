/* SPDX-License-Identifier: LGPL-2.1-or-later */
var { ExtensionCommon } = ChromeUtils.importESModule("resource://gre/modules/ExtensionCommon.sys.mjs");
var { MailServices } = ChromeUtils.importESModule("resource:///modules/MailServices.sys.mjs");
var { MsgIncomingServer } = ChromeUtils.importESModule("resource:///modules/MsgIncomingServer.sys.mjs");

var { setTimeout, clearTimeout } = ChromeUtils.importESModule("resource://gre/modules/Timer.sys.mjs");
Components.utils.importGlobalProperties(["IOUtils", "PathUtils", "atob", "TextEncoder"]);

var groupwise = class extends ExtensionCommon.ExtensionAPI {
  onStartup() { this.initialize(); }
  initialize() {
    if (this.factories) return;
    this.factories = [];
    this.pending = new Map();
    this.sequence = 0;
    this.listeners = new Set();
    const api = this;
    this.chromeHandle = Cc["@mozilla.org/addons/addon-manager-startup;1"].getService(Ci.amIAddonManagerStartup).registerChrome(this.extension.rootURI, [["content", "groupwise-native", this.extension.rootURI.spec]]);
    this.scope = { ChromeUtils, Components, Cc, Ci, Cr, Services, MailServices, MsgIncomingServer, IOUtils, PathUtils, atob, TextEncoder, api };
    try {
      Services.scriptloader.loadSubScript("chrome://groupwise-native/content/backend.js", this.scope);
      this.scope.Backend.register();
    } catch (error) { this.onShutdown(false); throw error; }
  }
  request(serverKey, op, args = {}) {
    return new Promise((resolve, reject) => {
      const id = String(++this.sequence);
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("GroupWise request timed out"));
      }, 45000);
      const request = {id, serverKey, op, ...args};
      const fire = this.listeners.values().next().value;
      this.pending.set(id, {resolve, reject, timer, request, sent:!!fire});
      if (fire) fire.async(request);
    });
  }
  onShutdown(isAppShutdown) {
    if (!this.factories) return;
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(new Error("GroupWise stopped")); }
    this.pending.clear(); this.listeners.clear();
    if (!isAppShutdown) {
      const registrar = Components.manager.QueryInterface(Ci.nsIComponentRegistrar);
      for (const {cid, factory} of this.factories.reverse()) registrar.unregisterFactory(cid, factory);
      Services.obs.notifyObservers(null,"startupcache-invalidate");
    }
    this.chromeHandle?.destruct();
    this.factories = null;
    // Account preferences, databases, MIME cache and mail are deliberately retained.
  }
  getAPI(context) {
    this.initialize();
    const api = this;
    return {groupwise: {
      async bootstrap() { return {version: Services.appinfo.version}; },
      async createAccount(settings) { return api.scope.Backend.createAccount(settings); },
      async listAccounts() {
        return [...MailServices.accounts.accounts].filter(a=>a.incomingServer?.type === "groupwise")
          .map(a=>({key:a.incomingServer.key,name:a.incomingServer.prettyName,error:a.incomingServer.getStringValue("groupwiseLastError")}));
      },
      async isGroupwiseIdentity(identityId) {
        return [...MailServices.accounts.accounts].some(a=>a.incomingServer?.type === "groupwise" && [...a.identities].some(i=>i.key === identityId));
      },
      async sync(key) { return api.scope.Backend.sync(key); },
      async answer(id, response) {
        const p = api.pending.get(id);
        if (!p) return;
        clearTimeout(p.timer); api.pending.delete(id);
        if (response.ok) p.resolve(response.result);
        else p.reject(new Error(response.error?.code || "GroupWise failed"));
      },
      onRequest: new ExtensionCommon.EventManager({context, name:"groupwise.onRequest", register(fire) {
        api.listeners.add(fire);
        for (const pending of api.pending.values()) {
          if (!pending.sent) { pending.sent=true; fire.async(pending.request); }
        }
        return () => api.listeners.delete(fire);
      }}).api(),
    }};
  }
};
