/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Thunderbird-specific objects. SOAP and native stdio remain outside this process. */
var Backend = (() => {
  const registrar = Components.manager.QueryInterface(Ci.nsIComponentRegistrar);
  const roleFlags = {inbox:Ci.nsMsgFolderFlags.Inbox, sent:Ci.nsMsgFolderFlags.SentMail,
    drafts:Ci.nsMsgFolderFlags.Drafts, trash:Ci.nsMsgFolderFlags.Trash, junk:Ci.nsMsgFolderFlags.Junk};
  function register(contract, cidText, create) {
    if (registrar.isContractIDRegistered(contract)) throw new Error("GroupWise contract already registered");
    const cid = Components.ID(cidText);
    const factory = {QueryInterface:ChromeUtils.generateQI(["nsIFactory"]),
      createInstance(iid) { return create().QueryInterface(iid); }};
    registrar.registerFactory(cid, "GroupWise Native", contract, factory);
    api.factories.push({cid, factory});
  }
  class Server extends MsgIncomingServer {
    constructor() { super(); this.canHaveFilters = false; this._refresh = sync; }
    get wrappedJSObject() { return this; }
    get localStoreType() { return "groupwise"; }
    get localDatabaseType() { return "mailbox"; }
    get canSearchMessages() { return true; }
    get offlineSupportLevel() { return 0; }
    get supportsDiskSpace() { return false; }
    get sortOrder() { return 100000000; }
    getNewMessages(...args) { this._refresh(this.key).catch(() => this.setStringValue("groupwiseLastError","Refresh failed")); }
    performBiff() { this.getNewMessages(); }
    closeCachedConnections() {}
    shutdown() {}
  }
  class ProtocolInfo {
    QueryInterface = ChromeUtils.generateQI(["nsIMsgProtocolInfo"]);
    get defaultLocalPath() {
      const file = Services.dirsvc.get("ProfD", Ci.nsIFile); file.append("GroupWise");
      if (!file.exists()) file.create(Ci.nsIFile.DIRECTORY_TYPE, 0o700);
      return file;
    }
    get serverIID() { return Ci.nsIMsgIncomingServer; }
    requiresUsername = true;
    preflightPrettyNameWithEmailAddress = false;
    canDelete = true;
    canLoginAtStartUp = false;
    canDuplicate = true;
    canGetMessages = true;
    canGetIncomingMessages = true;
    defaultDoBiff = false;
    showComposeMsgLink = false;
    foldersCreatedAsync = false;
    getDefaultServerPort() { return 7191; }
  }
  function folderFactory() {
    const folder = Cc["@mozilla.org/jacppmsgfolderdelegator;1"].createInstance(Ci.msgIOverride);
    bindFolder(folder);
    return folder;
  }
  function bindFolder(folder) {
    const base = folder.cppBase.QueryInterface(Ci.nsIMsgFolder);
    const delegate = {
      QueryInterface: ChromeUtils.generateQI(["nsIMsgFolder"]),
      getDBFolderInfoAndDB(info) { const db = base.msgDatabase; info.value = db.dBFolderInfo; return db; },
      get incomingServerType() { return "groupwise"; },
      get baseMessageURI() { return base.URI.replace(/^groupwise:/, "groupwise-message:"); },
      generateMessageURI(key) { return this.baseMessageURI + "#" + key; },
      getUriForMsg(header) { return this.generateMessageURI(header.messageKey); },
      updateFolder() { sync(base.server.key).then(() => base.NotifyFolderEvent("FolderLoaded")).catch(() => base.NotifyFolderEvent("FolderLoaded")); },
      getNewMessages() { this.updateFolder(); },
      markMessagesRead(headers,read) {
        const server = base.server;
        serialized(server.key, async () => {
          await login(server);
          for (const header of headers) await api.request(server.key,"markRead",{messageId:header.getStringProperty("groupwiseId"),read});
          base.markMessagesRead(headers,read);
          server.setStringValue("groupwiseLastError", "");
        }).catch(() => server.setStringValue("groupwiseLastError","Read state update failed"));
      },
      get canFileMessages() { return false; },
      get canDeleteMessages() { return false; },
      get canCreateSubfolders() { return false; },
      get canRename() { return false; },
      get canCompact() { return false; },
    };
    folder.jsDelegate = delegate;
    for (const name of ["GetDBFolderInfoAndDB","GetIncomingServerType","GetBaseMessageURI","GenerateMessageURI","GetUriForMsg","UpdateFolder","GetNewMessages","MarkMessagesRead","GetCanFileMessages","GetCanDeleteMessages","GetCanCreateSubfolders","GetCanRename","GetCanCompact"]) folder.methodsToDelegate.add(name);
  }
  function hierarchy(server, folders) {
    const root = server.rootFolder;
    const byId = new Map();
    for (const f of folders) if (f.role === "root") byId.set(f.id, root);
    let remaining = folders.filter(f => f.role !== "root");
    for (let pass = 0; remaining.length && pass <= folders.length; pass++) {
      const next = [];
      for (const f of remaining) {
        const parent = byId.get(f.parentId) || (!f.parentId ? root : null);
        if (!parent) { next.push(f); continue; }
        // Opaque ID path components make renames and duplicate display names safe.
        const name = encodeURIComponent(f.id);
        let child;
        child = [...parent.subFolders].find(c => c.URI === parent.URI + "/" + encodeURIComponent(name));
        const fresh = !child;
        if (fresh) child = parent.addSubfolder(name);
        const path = child.filePath;
        if (!path.exists()) path.create(Ci.nsIFile.NORMAL_FILE_TYPE,0o600);
        child.name = f.name;
        child.setStringProperty("groupwiseId", f.id);
        const flags = Ci.nsMsgFolderFlags.Mail | (roleFlags[f.role] || 0);
        child.flags = child.flags | flags;
        byId.set(f.id, child);
        if (fresh) {
          MailServices.mailSession.QueryInterface(Ci.nsIFolderListener).onFolderAdded(parent,child);
          MailServices.mfn.notifyFolderAdded(child);
        }
      }
      if (next.length === remaining.length) break;
      remaining = next;
    }
    if (!remaining.length) {
      for (const child of [...root.descendants].reverse()) {
        const id = child.getStringProperty("groupwiseId");
        if (id && byId.get(id) !== child && child.parent) child.parent.propagateDelete(child,false);
      }
    }
    return byId;
  }
  async function createAccount(settings) {
    if (!settings || typeof settings.host !== "string" || !settings.host || /[\s/:@?#\\]/.test(settings.host) || typeof settings.username !== "string" || !settings.username ||
        !Number.isInteger(settings.port) || settings.port < 1 || settings.port > 65535 || typeof settings.tls !== "boolean") throw new Error("Invalid account settings");
    if (settings.password) {
      const origin = "groupwise://" + encodeURIComponent(settings.host) + ":" + settings.port;
      const login = Cc["@mozilla.org/login-manager/loginInfo;1"].createInstance(Ci.nsILoginInfo);
      login.init(origin, null, origin, settings.username, settings.password, "", "");
      const saved = await Services.logins.searchLoginsAsync({origin,httpRealm:origin});
      const previous = saved.find(l=>l.username === settings.username);
      if (previous) await Services.logins.modifyLoginAsync(previous,login);
      else await Services.logins.addLoginAsync(login);
    }
    const existing = [...MailServices.accounts.accounts].find(a=>a.incomingServer?.type === "groupwise" &&
      a.incomingServer.hostname === settings.host && a.incomingServer.username === settings.username && a.incomingServer.port === settings.port);
    if (existing) {
      existing.incomingServer.socketType = settings.tls ? Ci.nsMsgSocketType.SSL : Ci.nsMsgSocketType.plain;
      return {accountKey:existing.key,serverKey:existing.incomingServer.key};
    }
    const server = MailServices.accounts.createIncomingServer(settings.username, settings.host, "groupwise");
    server.port = settings.port;
    server.socketType = settings.tls ? Ci.nsMsgSocketType.SSL : Ci.nsMsgSocketType.plain;
    server.prettyName = "GroupWise — " + settings.username;
    server.valid = true;
    const account = MailServices.accounts.createAccount();
    account.incomingServer = server;
    const identity = MailServices.accounts.createIdentity();
    identity.email = settings.email || "";
    identity.fullName = settings.name || settings.username;
    account.addIdentity(identity);
    server.setStringValue("groupwiseFolders", "[]");
    MailServices.accounts.saveAccountInfo();
    return {accountKey:account.key, serverKey:server.key};
  }
  async function login(server) {
    const origin = "groupwise://" + encodeURIComponent(server.hostname) + ":" + server.port;
    const logins = await Services.logins.searchLoginsAsync({origin, httpRealm:origin});
    const stored = logins.find(l => l.username === server.username);
    if (!stored) throw new Error("No saved GroupWise password; configure the account again");
    return api.request(server.key, "login", {host:server.hostname, port:server.port,
      username:server.username, password:stored.password, tls:server.socketType === Ci.nsMsgSocketType.SSL});
  }
  const queues = new Map();
  function serialized(key, work) {
    const previous = queues.get(key) || Promise.resolve();
    const next = previous.catch(() => {}).then(() => {
      if (!api.factories) throw new Error("GroupWise extension is stopped");
      return work();
    });
    queues.set(key,next);
    next.finally(() => { if (queues.get(key) === next) queues.delete(key); }).catch(() => {});
    return next;
  }
  const jobs = new Map();
  function sync(key) {
    if (jobs.has(key)) return jobs.get(key);
    const job = serialized(key, () => synchronize(key)).then(result=>{
      MailServices.accounts.getIncomingServer(key).setStringValue("groupwiseLastError",""); return result;
    },error=>{
      MailServices.accounts.getIncomingServer(key).setStringValue("groupwiseLastError","Refresh failed; check server, saved password and native host"); throw error;
    }).finally(() => jobs.delete(key)); jobs.set(key, job); return job;
  }
  async function synchronize(key) {
    const server = MailServices.accounts.getIncomingServer(key);
    if (server.type !== "groupwise") throw new Error("Not a GroupWise account");
    await login(server);
    const folders = (await api.request(key, "listFolders")).folders;
    const mapped = hierarchy(server, folders);
    server.setStringValue("groupwiseFolders", JSON.stringify(folders));
    for (const f of folders) {
      if (f.role === "root") continue;
      const folder = mapped.get(f.id);
      if (!folder) continue;
      const db = folder.msgDatabase;
      const existing = new Map([...db.enumerateMessages()].map(h=>[h.getStringProperty("groupwiseId"),h]));
      const seen = new Set();
      let offset = 0, more;
      do {
        const page = await api.request(key, "listMessages", {folderId:f.id, offset, limit:100});
        for (const m of page.messages) {
          seen.add(m.id);
          let header = existing.get(m.id);
          const fresh = !header;
          if (!header) header = db.createNewHdr(0xffffffff);
          const revision = m.modified || JSON.stringify([m.date,m.size,m.subject]);
          const oldRevision = header.getStringProperty("groupwiseRevision");
          if (!fresh && oldRevision && oldRevision !== revision) await IOUtils.remove(cacheFile(header).path,{ignoreAbsent:true});
          header.setStringProperty("groupwiseId", m.id);
          header.setStringProperty("groupwiseRevision",revision);
          header.subject = m.subject; header.author = m.sender; header.recipients = m.recipients;
          header.messageId = "gw-" + encodeURIComponent(m.id) + "@groupwise.invalid";
          header.date = (Date.parse(m.date) || 0) * 1000;
          header.messageSize = Math.max(0, m.size);
          if (fresh) { header.flags = m.read ? Ci.nsMsgMessageFlags.Read : 0; db.addNewHdrToDB(header, true); existing.set(m.id,header); }
          else db.markRead(header.messageKey,m.read,null);
          db.markReplied(header.messageKey,m.replied,null);
        }
        db.summaryValid = true; db.commit(Ci.nsMsgDBCommitType.kLargeCommit);
        folder.updateSummaryTotals(true);
        offset = page.nextOffset; more = page.hasMore;
      } while (more);
      for (const [id,header] of existing) if (f.role !== "query" && !seen.has(id)) db.deleteHeader(header,null,false,true);
      db.commit(Ci.nsMsgDBCommitType.kLargeCommit);
      folder.updateSummaryTotals(true);
      folder.NotifyFolderEvent("FolderLoaded");
    }
    return {folders: mapped.size};
  }
  const downloads = new Map();
  function headerForURI(uri) {
    const match = /^(groupwise-message:\/\/[^#]+)#(\d+)(?:\?.*)?$/.exec(uri);
    if (!match) throw new Error("Invalid GroupWise message URI");
    const folder = MailServices.folderLookup.getOrCreateFolderForURL(match[1].replace(/^groupwise-message:/,"groupwise:"));
    return folder.GetMessageHeader(Number(match[2]));
  }
  function cacheFile(header) {
    const file = header.folder.server.localPath.clone();
    file.append("mime-cache");
    if (!file.exists()) file.create(Ci.nsIFile.DIRECTORY_TYPE,0o700);
    // SHA-256 of remote stable ID avoids path traversal and filesystem length limits.
    const hash = Cc["@mozilla.org/security/hash;1"].createInstance(Ci.nsICryptoHash);
    hash.init(Ci.nsICryptoHash.SHA256);
    const bytes = new TextEncoder().encode(header.getStringProperty("groupwiseId"));
    hash.update(bytes,bytes.length);
    const hex = [...hash.finish(false)].map(c=>c.charCodeAt(0).toString(16).padStart(2,"0")).join("");
    file.append(hex+".eml"); return file;
  }
  function ensureMime(header) {
    const file = cacheFile(header);
    if (file.exists()) return Promise.resolve(file);
    if (downloads.has(file.path)) return downloads.get(file.path);
    const server = header.folder.server;
    const job = serialized(server.key, async () => {
      await login(server);
      const chunks = []; let offset = 0, total = null;
      for (;;) {
        const part = await api.request(server.key,"getMessage",{messageId:header.getStringProperty("groupwiseId"),offset});
        if (!Number.isInteger(part.total) || part.total < 0 || part.total > 16*1024*1024 ||
            (total !== null && total !== part.total) || part.nextOffset < offset || part.nextOffset > part.total) throw new Error("Invalid MIME download");
        total = part.total;
        const raw = atob(part.data);
        if (raw.length > 128*1024 || part.nextOffset !== offset+raw.length || (!part.done && !raw.length)) throw new Error("Invalid MIME chunk");
        chunks.push(Uint8Array.from(raw,c=>c.charCodeAt(0))); offset = part.nextOffset;
        if (part.done) { if (offset !== total) throw new Error("Truncated MIME download"); break; }
      }
      const bytes = new Uint8Array(total); offset = 0;
      for (const chunk of chunks) { bytes.set(chunk,offset); offset += chunk.length; }
      const temporary=file.clone(); temporary.leafName += ".part";
      if (temporary.exists()) temporary.remove(false);
      temporary.create(Ci.nsIFile.NORMAL_FILE_TYPE,0o600);
      try {
        await IOUtils.write(temporary.path,bytes);
        await IOUtils.setPermissions(temporary.path,0o600);
        await IOUtils.move(temporary.path,file.path,{noOverwrite:true});
      } catch (error) {
        await IOUtils.remove(temporary.path,{ignoreAbsent:true});
        throw error;
      }
      return file;
    }).finally(()=>downloads.delete(file.path));
    downloads.set(file.path,job); return job;
  }
  const mailbox = () => Cc["@mozilla.org/messenger/messageservice;1?type=mailbox-message"].getService(Ci.nsIMsgMessageService);
  const fileURI = file => Services.io.newFileURI(file).spec + "?type=application/x-message-display";
  const displayGenerations = new WeakMap();
  class MessageService {
    QueryInterface = ChromeUtils.generateQI(["nsIMsgMessageService"]);
    messageURIToMsgHdr(uri) { return headerForURI(uri); }
    getUrlForUri(uri,msgWindow) {
      const file = cacheFile(headerForURI(uri));
      // 153 messageProgressListener compares this URI with the actual mailbox channel.
      return Services.io.newURI(fileURI(file).replace(/^file:/,"mailbox:") + "&number=0");
    }
    loadMessage(uri,docShell,msgWindow,listener,charset) {
      const header = headerForURI(uri);
      const generation = (displayGenerations.get(docShell) || 0) + 1;
      displayGenerations.set(docShell,generation);
      // The built-in service performs MIME conversion and enforces message display policy.
      ensureMime(header).then(file => {
        if (!api.factories || docShell.isBeingDestroyed() || displayGenerations.get(docShell) !== generation) return;
        mailbox().loadMessage(fileURI(file),docShell,msgWindow,listener,charset);
      }).catch(() => listener?.OnStopRunningUrl(null,Cr.NS_ERROR_FAILURE));
    }
    streamMessage(uri,consumer,msgWindow,listener,convert,additional,localOnly) {
      const header = headerForURI(uri), file = cacheFile(header);
      if (localOnly && !file.exists()) throw Components.Exception("Message is not cached",Cr.NS_ERROR_NOT_AVAILABLE);
      ensureMime(header).then(f => mailbox().streamMessage(fileURI(f),consumer,msgWindow,listener,convert,additional,true))
        .catch(() => { consumer.onStartRequest(null); consumer.onStopRequest(null,Cr.NS_ERROR_FAILURE); });
      return Services.io.newFileURI(file);
    }
    streamHeaders(uri,consumer,listener,localOnly) {
      const header=headerForURI(uri),file=cacheFile(header);
      if (localOnly && !file.exists()) throw Components.Exception("Message is not cached",Cr.NS_ERROR_NOT_AVAILABLE);
      ensureMime(header).then(async f=>{
        const bytes=await IOUtils.read(f.path,{maxBytes:256*1024});
        let end=0;
        for (let i=0;i<bytes.length-1;i++) {
          if (bytes[i]===10 && bytes[i+1]===10) { end=i+2;break; }
          if (i+3<bytes.length && bytes[i]===13 && bytes[i+1]===10 && bytes[i+2]===13 && bytes[i+3]===10) { end=i+4;break; }
        }
        if (!end) throw new Error("Message headers are missing or exceed 256 KiB");
        const parts=[];
        for (let i=0;i<end;i+=16384) parts.push(String.fromCharCode(...bytes.subarray(i,Math.min(end,i+16384))));
        const input=Cc["@mozilla.org/io/string-input-stream;1"].createInstance(Ci.nsIStringInputStream);
        input.setByteStringData(parts.join(""));
        const pump=Cc["@mozilla.org/network/input-stream-pump;1"].createInstance(Ci.nsIInputStreamPump);
        pump.init(input,0,0,true);
        pump.asyncRead({QueryInterface:ChromeUtils.generateQI(["nsIStreamListener"]),
          onStartRequest(request) { listener?.OnStartRunningUrl(Services.io.newFileURI(f)); consumer.onStartRequest(request); },
          onDataAvailable(request,stream,offset,count) { consumer.onDataAvailable(request,stream,offset,count); },
          onStopRequest(request,status) { consumer.onStopRequest(request,status); listener?.OnStopRunningUrl(Services.io.newFileURI(f),status); }
        });
      })
        .catch(()=>{ consumer.onStartRequest(null); consumer.onStopRequest(null,Cr.NS_ERROR_FAILURE); });
      return Services.io.newFileURI(file);
    }
    saveMessageToDisk(uri,file,addEnvelope,listener,canonical,msgWindow) {
      if (addEnvelope || canonical) throw Components.Exception("Mbox appending and line-ending conversion are unsupported",Cr.NS_ERROR_NOT_IMPLEMENTED);
      ensureMime(headerForURI(uri)).then(f=>IOUtils.copy(f.path,file.path)).then(()=>listener?.OnStopRunningUrl(null,Cr.NS_OK))
        .catch(()=>listener?.OnStopRunningUrl(null,Cr.NS_ERROR_FAILURE));
    }
    isMsgInMemCache() { return false; }
    copyMessage() { throw Components.Exception("Copy not supported by the add-on",Cr.NS_ERROR_NOT_IMPLEMENTED); }
    CopyMessages() { throw Components.Exception("Copy not supported by the add-on",Cr.NS_ERROR_NOT_IMPLEMENTED); }
    Search() { throw Components.Exception("Server search not supported",Cr.NS_ERROR_NOT_IMPLEMENTED); }
  }

  function restore() {
    for (const server of MailServices.accounts.allServers) {
      if (server.type === "groupwise") {
        server.wrappedJSObject._refresh = sync;
        for (const folder of [server.rootFolder,...server.rootFolder.descendants]) bindFolder(folder.QueryInterface(Ci.msgIOverride));
        hierarchy(server, JSON.parse(server.getStringValue("groupwiseFolders") || "[]"));
      }
    }
  }
  return {register() {
    register("@mozilla.org/messenger/protocol/info;1?type=groupwise", "{d7baab51-c246-4767-83b1-b5fd1b665ee1}", () => new ProtocolInfo());
    register("@mozilla.org/mail/folder-factory;1?name=groupwise", "{ee364824-abf5-401f-81c5-d74e50bad829}", folderFactory);
    register("@mozilla.org/messenger/server;1?type=groupwise", "{315c4a3d-d786-431e-8689-8f614d1f1c12}", () => new Server());
    register("@mozilla.org/messenger/messageservice;1?type=groupwise-message", "{ad5b38ed-b53d-4477-9dd9-8618f8df7f99}", () => new MessageService());
    register("@mozilla.org/messenger/messageservice;1?type=groupwise", "{12c933e4-e8b5-4fbf-b9ef-52cae9841155}", () => new MessageService());
    restore();
  }, createAccount, sync, ensureMime};
})();
