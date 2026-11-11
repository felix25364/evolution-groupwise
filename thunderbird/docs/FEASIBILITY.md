# Thunderbird native account feasibility

## Target and evidence

Runtime tested during development: Debian GNU/Linux 13 amd64, Mozilla Thunderbird
153.6.0esr (`Services.appinfo.version`: 153.6.0). No Thunderbird 160 binary is
provided by this distribution. The XPI intentionally admits 153.* only; future
versions require testing, not just increasing the manifest limit.

Source reference: Thunderbird `THUNDERBIRD_153_6_0esr_RELEASE`, commit
`966cd5d9e595c000854553773d8851eb0169f620` in
<https://github.com/thunderbird/thunderbird-desktop>. All source links below are
relative to that tag. Early investigation of master uncovered incompatible IDL
changes; the implementation was corrected against the release tag and runtime.

## Account and folders

- `mailnews/base/src/nsMsgAccountManager.cpp`, `createKeyedServer` / incoming
  server creation: constructs `@mozilla.org/messenger/server;1?type=TYPE`, sets
  key/type/username/hostname, and obtains the root folder. Dynamic registration
  through `nsIComponentRegistrar.registerFactory` is viable in an Experiment.
- `mailnews/base/src/MsgIncomingServer.sys.mjs`: reusable JS base implements
  preferences, server URI, local path, password-related methods and root lookup.
  A derived `groupwise` server supplies its own storage type and protocol info.
- `mailnews/base/src/FolderLookupService.cpp`: resolves
  `@mozilla.org/mail/folder-factory;1?name=SCHEME` and enforces object identity.
- `mailnews/jsaccount/src/{components.conf,JaMsgFolder.cpp}`: shipped generic
  `@mozilla.org/jacppmsgfolderdelegator;1` supplies a real C++ `nsMsgDBFolder`,
  database creation and `msgIOverride` forwarding to JS. We delegate only named
  overridden methods; the C++ implementation remains the owner of real folders.
- `mailnews/jsaccount/test/unit/resources/testJaBaseMsgFolder.sys.mjs` and
  `testJaBaseIncomingServer.sys.mjs`: upstream test patterns for JS-backed native
  accounts. No proprietary extension code is used.
- `mailnews/base/public/{nsIMsgIncomingServer,nsIMsgProtocolInfo,nsIMsgFolder}.idl`:
  generic folder requires `incomingServerType`, `getDBFolderInfoAndDB`, message
  URI generation and folder refresh. Registration alone supplies none of these.
  153 uses `name` (not obsolete `prettyName`) and `GetMessageHeader(key)` (not
  master's renamed `getMsgHdr`). A real folder backing path and summary DB are
  needed even though MIME is cached separately.
- `mailnews/db/msgdb/public/nsIMsgDatabase.idl`: actual headers are created using
  `createNewHdr`, inserted with `addNewHdrToDB`, and persisted through `commit`.
  Remote IDs live in a header property; Thunderbird numeric keys remain stable.
  Notification and summary-count paths use the native folder/database machinery.

## MIME, Native Messaging and lifecycle

- `mailnews/base/public/nsIMsgMessageService.idl` in **153** retains `nsIMsgWindow`
  parameters removed on master. `loadMessage(uri, docShell, msgWindow, listener,
  charset)` and `streamMessage(uri, consumer, msgWindow, listener, convert,
  additionalHeader, localOnly)` must match exactly.
- `mailnews/local/src/nsMailboxService.cpp`, `FetchMessage`: accepts standalone
  `file:` MIME input, internally runs the mailbox protocol with `number=0` and
  the file size. The GroupWise message service uses that renderer for authentic
  downloaded MIME. This creates no local mail account, IMAP bridge or fabricated
  inbox. GroupWise folders and headers remain their own native account objects.
- `chrome/toolkit/content/extensions/parent/ext-runtime.js` and
  `modules/NativeMessaging.sys.mjs` shipped in `omni.ja`: `connectNative` creates
  a persistent stdio native host. Correlation/timeouts live in extension code.
- Experiment parent startup registers contracts before account restoration;
  `getAPI` initializes idempotently. Backend script is loaded through an owned
  chrome registration: directly loading a jar URI fails Thunderbird's trusted
  script policy. Shutdown unregisters owned factories/chrome entries and rejects
  pending operations without deleting account data.
- Official documentation: <https://developer.thunderbird.net/add-ons/mailextensions>,
  <https://developer.thunderbird.net/add-ons/mailextensions/experiments>,
  <https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging>.

Official Experiment documentation was also read from its maintained source at
<https://raw.githubusercontent.com/thunderbird/developer-docs/master/add-ons/mailextensions/experiments.md>.
The documentation website itself was denied by the cloud network policy; the
official GitHub source was accessible. Its startup/shutdown event guidance and
startup-cache invalidation requirement are implemented. Runtime testing found
that cached `Cc` properties survive factory unregistration: lifecycle checks
use the registrar's actual state and creation behavior, not JavaScript membership.
Existing folder delegates are rebound on re-enable and startup requests queue
until the background Native Messaging listener is attached.

## Modern Exchange reference and recommendation

The release's `mailnews/protocols/exchange/src/components.conf` registers EWS and
Graph incoming servers, protocol info, folders, URLs, protocol handlers and
message services. `ExchangeIncomingServer.cpp`, `ExchangeFolder.cpp`,
`ExchangeService.cpp` and `ExchangeMessageChannel.cpp` show that server registration
alone is insufficient: message identity, database state, network channels,
notifications and async loading are separate obligations. This implementation
uses the existing JSAccount C++ folder plus built-in MIME renderer to avoid a
Thunderbird fork or custom binary XPCOM ABI. No Thunderbird compilation is needed.

Recommendation: proceed with a version-limited experimental XPI and separate C
host. Keep writes conservative until mock-backed UI, restart and failure tests
pass. Native sending would need an independently verified outgoing-server/send
interface and MIME-to-GroupWise translation; exposing a composer without that
integration would misrepresent support. See TEST_REPORT.md and TASKS.md for the
actual verification state; this document does not equate API feasibility with a
production-ready mail client.
