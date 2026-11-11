# Thunderbird implementation progress

Status: mail-access MVP is runtime verified with Thunderbird 153.6.0esr and the
mock POA. All six integration CTests and six original Evolution CTests passed;
a separate image without Evolution/Camel/EDS also built and passed four suites.
Final source review is complete; Git delivery is in progress.
Checkboxes mean implemented and verified as described, not merely files created.

## M0 – Repository analysis
- [x] Inspect root/library CMake, headers, Camel metadata/MIME behavior and mock POA.
- [x] Confirm SOAP core uses GLib/GIO, libsoup and libxml2, independently of EDS.
- [x] Establish baseline: full Evolution build/install and six CTests pass.
- [x] Create feature branch and durable engineering instructions.
- [x] Record dependency/API map and licensing in architecture documentation.
## M1 – Thunderbird API research
- [x] Obtain supported Thunderbird runtime and corresponding source.
- [x] Inspect account manager, incoming server, protocol info and factories.
- [x] Inspect folders, database/storage, headers, MIME/message service and notifications.
- [x] Inspect Native Messaging, Experiment lifecycle, JS helpers and EWS architecture.
- [x] Record versioned evidence and recommendation in FEASIBILITY.md.
## M2 – Account type feasibility proof
- [x] Build installable Experiment XPI and register owned groupwise contracts.
- [x] Create real groupwise account in isolated runtime; show normal account/folder UI.
- [x] Restart and verify account persistence/loading.
- [x] Verify disable/shutdown cleanup without removing mail data.
- [x] Investigate actual failures; document unavailable interfaces and alternatives.
## M3 – Standalone GroupWise native host
- [x] Independent CMake mode without EDS/Camel and real C executable.
- [x] Bounded framing, strict JSON validation, request IDs and structured errors.
- [x] Ping, login/logout, folder hierarchy and metadata batches.
- [x] MIME download with bounded/chunked output and stable IDs.
- [x] Read/unread and other justified mail operations.
- [x] Session/auth/network failures and safe shutdown.
## M4 – Native Messaging
- [x] Async connectNative transport, correlation, timeout, disconnect and reconnect.
- [x] Missing host detection, safe credentials, size limits and cancellation policy.
- [x] Exercise real Thunderbird-to-host requests and transport failure tests.
## M5 – Real Thunderbird mail integration
- [x] Account setup/login validation and credential manager.
- [x] Native GroupWise hierarchy, special flags and duplicate-free refresh.
- [x] Stable message headers/database, unread counts and normal message list.
- [x] Real MIME in normal message viewer and attachments.
- [x] Manual refresh, failed request handling and read/unread synchronization.
- [x] Evaluate delete/move/copy/send, events and offline cache after core works.
## M6 – Build and Linux packaging
- [x] Build host, shared library and deterministic installable XPI.
- [x] Native host manifest, reliable RPATH and idempotent per-user install/uninstall.
- [x] Document accurate Arch dependencies and build/use commands.
## M7 – Automated and runtime testing
- [x] Framing/JSON tests: valid, sequential, invalid, missing, unsupported, empty,
      truncated, oversized, incorrect prefixes, partial I/O, disconnect and shutdown.
- [x] Mock SOAP: login/folders/messages/MIME, invalid auth/IDs, network/lost session.
- [x] Extension manifest/package and transport unit tests.
- [x] Runtime Experiment/XPCOM/native-host tests with temporary profile.
- [x] Account restart/folders/messages/rendering tests where feasible.
- [x] Full Evolution regression build and tests after shared build changes.
- [x] Review results and record exact commands, failures/fixes and limitations.
## M8 – Documentation and final delivery
- [x] README, architecture, feasibility, test report and truthful final checklist.
- [ ] Review code/security, artifacts and final diff; commit all intended files.
- [ ] Verify clean feature branch, push if permitted, report hashes/PR outcome.

## Remaining problems and follow-up scope
- [ ] Native sending and outgoing-server/composer integration: optional beyond the
  mail-access MVP. No verified outgoing adapter exists; GroupWise identity sends
  are canceled rather than routed through another account's SMTP server.
- [ ] Thunderbird copy/move/delete transaction/undo UI: host operations are tested,
  but their folder UI remains disabled. This is unfinished integration, not an
  external API blocker or a claimed success.
- [ ] Events/incremental sync, cache eviction and offline actions: not implemented.
  Refresh currently rescans cursors; concurrent/large mailboxes need further tests.
- [ ] Shared-item SOAP-to-MIME reconstruction, non-mail item types and advanced
  proxy/calendar/address-book features: not part of this mail-access MVP.
- [ ] Live GroupWise, Arch Linux runtime, Thunderbird 160/other releases, sandboxed
  distributions and primary-password flows: not verified in this environment.
- [ ] Setup form submission is implemented; automated runtime tests currently
  create accounts through the same Experiment backend and exercise real native
  login/credential storage, rather than driving the HTML form itself.
- [ ] Canonical line-ending conversion and mbox appending through saveMessageToDisk
  are explicitly unsupported; ordinary byte-preserving file saving is implemented.
- Cloud onboarding draft persistence previously failed; repository build scripts
  and Dockerfile now carry the reusable workflow independently of that service.

### Development evidence (first host run)
- Standalone build succeeded against GLib/GIO, libsoup, libxml2, json-glib.
- CTest native-framing (6 Python tests) and native-soap (2 tests) passed.
- Initial SOAP test incorrectly expected MIME-Version in the existing original
  Internet fixture. Inspected fixture; test now verifies X-Original-MIME and exact
  byte count instead. No production code weakened.
- TLS untrusted-certificate rejection, expired-session renewal, wrong credentials,
  unreachable port, invalid IDs and chunk assembly exercised.
- Actual Thunderbird: 153.6.0esr (Debian), JSAccount component present at runtime.

### Native account gate progress
- A real groupwise server/account was created in a disposable Thunderbird 153.6
  profile. Background connectNative calls authenticated against the mock POA.
- Ten mail folders (plus root), including a nested duplicate display name, were
  mapped to native JSAccount C++ folder objects. Real message headers populated
  Thunderbird summary DBs. Special flags now persist correctly.
- Fixed trusted script loading, missing Experiment timer imports, generic folder
  database-info delegation, backing files and combined-flag setter behavior.
- Tagged 153 IDL differs from master (nsIMsgWindow arguments and GetMessageHeader);
  runtime tests caught this and adapters now target the release IDL.
- Extended SOAP tests verify copy/move/delete and trusted custom-CA TLS.
- Transport tests pass correlation, errors, reconnect, stale disconnect, timeout,
  shutdown and request bounds. Native mutations are not yet exposed as mail UI.

### End-to-end validation progress
- Text and multipart HTML/attachment variants both passed actual Thunderbird UI
  rendering, including completed load state, folder rows and message lists.
- Header-only streaming and MIME streaming passed through real message services.
- Read state reached the mock POA before local success; complete refresh reconciles
  remote removals, preserves keys, and retains query-folder entries conservatively.
- Tested missing host, disable/unregister, data retention, re-enable refresh and
  genuine restart with the installed XPI and login-manager credentials.
- Fixed stale component membership checks, re-enable delegate binding and startup
  listener races; invalidated the startup cache following official documentation.
- Large-download test verifies 16 MiB rejection and exact 1 MiB chunk reassembly.
- Clean standalone image has no Evolution/Camel/EDS build or runtime dependency.
- Optional advanced features above remain unchecked; the native account gate is
  successful and a Thunderbird fork is unnecessary for the tested release.

### Final review refinements
- Cache permissions are asserted in both runtime variants. A failed assertion
  exposed an ignored IOUtils option; private pre-creation, explicit chmod and
  atomic rename fixed it, and both runtime suites passed again.
- Ordinary file saving, header-only streaming, replied flags, date fallback and
  wrapped original-MIME attachment IDs are handled. No shared protocol source
  was modified to add them.
- Final native release validation: six suites passed; minimal-image rebuild and
  four suites passed. Original Evolution regression remains six passing suites.
