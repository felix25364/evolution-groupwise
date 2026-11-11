# Thunderbird GroupWise engineering instructions

## Mission and boundaries
Implement a real Linux Thunderbird `groupwise` mail account using the existing
GroupWise SOAP core. Preserve working Evolution functionality and existing
contributions. Do not substitute an IMAP bridge, Evolution intermediary, fake
inbox, local dummy account, or standalone mail reader. Target Arch Linux and a
supported Thunderbird release (160 when available). No macOS/Windows packaging.
Use the existing isolated checkout; do not create worktrees unless requested.

## Organization
- `extension/`: installable XPI, Experiment APIs, XPCOM integration and setup UI.
- `native/`: standalone C Native Messaging host, CMake build.
- `packaging/linux/`: per-user installation/removal; platform-specific details.
- `packaging/arch/`: optional Arch packaging.
- `tests/`: automated tests and fixtures, reusing `../../tests/mock`.
- `docs/`: FEASIBILITY.md, ARCHITECTURE.md, TEST_REPORT.md and limitations.
- `TASKS.md`: ordered, continuously maintained M0–M8 checklist and remaining work.
Reuse `src/libegroupwise` in place. Do not duplicate SOAP code. The host must not
link Camel, EDS or Evolution. Shared CMake changes must be minimal, documented,
and backward compatible. Do not modify unrelated Evolution implementation.
Keep Linux integration independent of the shared protocol for future portability.

## API and implementation discipline
Read version-appropriate Thunderbird source and official documentation. Record
versions, source paths, symbols and URLs in docs/FEASIBILITY.md. Never invent API
signatures or assume historical extension interfaces still work. Verify account
creation, real folders, databases, stable IDs, headers, MIME rendering, flags,
notifications, account persistence and sending separately. Contract registration
or XPI creation alone is not proof of a working account. Evaluate modern native
EWS/Graph backends and JS helpers. Do not copy proprietary ExQuilla code.
Use Experiment APIs only where necessary, never overwrite built-in contracts,
and unregister only owned factories. Initialize and shut down components cleanly.
Disable/removal must retain mail data. Avoid UI-thread blocking, unhandled async
failures, shutdown races and unnecessary dependencies. Prefer maintainable, clear
module boundaries and ordinary installable XPIs. A Thunderbird fork needs an
explicitly documented technical justification; investigate alternatives first.

## Security
Never hardcode or log credentials/session tokens/private message content. Use
Thunderbird credential facilities where supported. No secrets in Git, docs,
fixtures or diagnostics; public mock account constants are test fixtures only.
TLS verification is mandatory by default; do not weaken package integrity or
certificate verification to make tests pass. Do not expose unauthenticated HTTP
APIs. Validate all JSON types and operation arguments; bound input/output,
downloads and batches. Implement native-endian length-prefixed stdio framing,
partial reads/writes, malformed input, disconnects and process shutdown safely.
Reserve stdout for protocol frames; sanitized diagnostics go to stderr. Runtime
must work without root. Prefer per-user installation. Uninstall must be
idempotent and never delete mail, profiles, unrelated configuration or secrets.
Do not let server-controlled content become executable code or HTML UI markup.

## Testing and status
Implement before checking tasks complete. Distinguish implemented, compiled,
automatically tested, runtime verified, partial, blocked, skipped and untested.
Update TASKS.md after each subsystem, failure, blocker, resolution and test run;
retain failed/infeasible tasks with evidence. Reuse the mock POA; never require
private credentials for automated tests. Cover malformed framing/JSON, size
limits, partial I/O, shutdown, missing host, timeout, disconnect, failed auth,
network errors, expired sessions and invalid folder/message IDs. Build all
relevant new targets and rerun relevant Evolution regression tests. Investigate
failures and fix project-scope defects. Record exact commands and real outcomes
in docs/TEST_REPORT.md; never invent results or suppress failures. Test an actual
Thunderbird binary with an isolated disposable profile and Xvfb where available:
Experiment startup/shutdown, registration/unregistration, native messaging,
account creation, normal folder/message UI, persistence/restart and MIME opening.
Never use a user's real profile or real mail for destructive tests. No claim of
runtime success without execution. If an API blocks the integration, identify
the exact source/runtime limitation and continue independent feasible work.

## Delivery and Git
Maintain README.md and docs/{ARCHITECTURE,FEASIBILITY,TEST_REPORT}.md, synchronized
with code. Include build, XPI packaging, Arch install/test/uninstall commands and
unsupported features. Work on `feat/thunderbird-groupwise-linux-mvp` or a distinct
non-conflicting feature branch, never main. Keep changes reviewable and respect
upstream licenses/copyrights. Commit all intended source/tests/docs/build files
with meaningful messages; exclude generated artifacts, profiles and credentials.
Review diff/status, execute final relevant tests, and leave a clean committed
working tree. Never force-push or merge into the default branch. Push when
permitted; report actual branch, commits, tests, remaining limitations, and real
push/PR outcomes. A scaffold or a compiled extension does not satisfy the MVP.
