# Native GroupWise mail for Thunderbird on Linux

Experimental Thunderbird **153 ESR** add-on and standalone C Native Messaging
host. It reuses this repository's GroupWise SOAP library directly. There is no
IMAP bridge or Evolution intermediary, and building this integration does not
require Camel, Evolution or evolution-data-server.

The native account type is `groupwise`: actual Thunderbird folders, message
summary databases, the normal folder tree/message list and Thunderbird's normal
MIME viewer. Tested with the repository's mock POA on Debian 13 and Thunderbird
153.6.0esr. A real GroupWise server and an Arch installation have not been tested.
Thunderbird 160 and other release lines are not admitted by the manifest.

## Build on Arch Linux

```sh
sudo pacman -S --needed base-devel cmake ninja pkgconf glib2 libsoup3 libxml2 json-glib python openssl
cmake -S thunderbird -B build/thunderbird -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_INSTALL_PREFIX="$HOME/.local/opt/thunderbird-groupwise" \
  -DCMAKE_INSTALL_LIBDIR=lib
cmake --build build/thunderbird --parallel 4
ctest --test-dir build/thunderbird --output-on-failure
cmake --install build/thunderbird
python thunderbird/packaging/linux/install.py \
  --prefix "$HOME/.local/opt/thunderbird-groupwise"
```

The products are `build/thunderbird/groupwise-host` and
`build/thunderbird/groupwise.xpi`. CMake installs the executable and shared library
with an RPATH to the selected private prefix. Reconfigure/reinstall when changing
prefixes; do not just move installed binaries. The registration script writes
`~/.mozilla/native-messaging-hosts/org.evolution_groupwise.host.json`, allowing
only extension ID `groupwise@evolution-groupwise.org` to launch the host. It works
without root. Install into a user-writable prefix. An optional Arch PKGBUILD is
not supplied; the native CMake workflow is the supported build path.

Debian equivalents for the standalone build: `build-essential cmake ninja-build
pkgconf libglib2.0-dev libsoup-3.0-dev libxml2-dev libjson-glib-dev python3 openssl`.
No changes to the root Evolution build are needed.

## Install and configure Thunderbird

Install a supported Thunderbird 153 ESR build. In Add-ons Manager, choose
**Install Add-on From File…** and select `build/thunderbird/groupwise.xpi`.
Experiments require privileged add-on support (`extensions.experiments.enabled`
must be true). This add-on has the privileges of Thunderbird itself; install
only code you trust. The test harness permits unsigned XPIs only inside its own
disposable profile; ordinary installation follows Thunderbird's distribution
policy. Restart after installation if prompted.

Open the add-on's preferences, enter the POA hostname (no URL scheme), SOAP port
(default 7191), username and password. TLS is enabled by default and certificate
verification cannot be disabled. Plain HTTP is available only by explicitly
unchecking TLS for a legacy POA. Credentials are validated before account creation
and stored in Thunderbird's login manager, not extension local storage. The
GroupWise account appears in the ordinary folder tree. Re-entering matching
server/port/user settings updates credentials instead of duplicating the account.

Use **Refresh** in add-on preferences or Thunderbird's Get Messages action.
Headers sync in bounded batches; bodies download on demand and are cached in
`<profile>/GroupWise/<server>/mime-cache` with mode 0600. Read/unread changes are
sent to GroupWise before local confirmation. Repeated refresh keeps existing
message keys and reconciles remote removals only after a complete successful
listing. Query-folder listings inherit the POA's limits and are not authoritative
for removals.

GroupWise private CAs can be installed through the SOAP core's existing
`GROUPWISE_CA_DIR` (PEM directory) or system trust configuration. An untrusted
certificate is rejected; there is no accept-all certificate switch.

## Current limits

- This is an experimental mail-access MVP, not a production parity release.
- No native Thunderbird sending. The add-on cancels sends from its identities
  so another account's SMTP server cannot be used accidentally.
- The host exposes tested mark/read, copy/move/delete primitives. Only read state
  is integrated into the Thunderbird UI; copy/move/delete UI is intentionally
  disabled until its transaction, undo and destination semantics are integrated.
- No GroupWise events, incremental token sync, offline actions, search backend,
  calendar, contacts, tasks, notes or advanced proxy-account setup.
- MIME is limited to 16 MiB per message; Native Messaging chunks are 128 KiB.
  Original Internet `Mime.822` is preferred; otherwise the POA RFC-822 endpoint
  is used. Shared messages that require rebuilding MIME from SOAP-only parts are
  not supported yet. An unrenderable server item reports failure rather than
  fabricated content. HTML/attachment coverage is described in TEST_REPORT.md.
- Full refresh uses cursor rescans for offsets, not a mailbox snapshot. Large or
  concurrently changing mailboxes need further scalability testing. The core's
  XML response allocation and query-folder POA limits are unchanged.
- Cached MIME is invalidated when the reported modification/metadata revision
  changes. Mail cache quotas/eviction and encrypted offline storage are not added.
- Account deletion, server rename and cross-folder transactions need broader UI
  testing. Disable/uninstall preserves account, header DB and cached mail data.
- Future Thunderbird versions, primary-password workflows and live POAs require
  additional validation. See [TASKS.md](TASKS.md) for precise remaining work.

## Tests

Fast tests need Python and OpenSSL; Node.js enables transport tests:

```sh
sudo pacman -S --needed nodejs
cmake -S thunderbird -B build/thunderbird -DGROUPWISE_RUNTIME_TESTS=OFF
cmake --build build/thunderbird --parallel 4
ctest --test-dir build/thunderbird --output-on-failure
```

The runtime test installs the XPI into a newly created, disposable HOME/profile,
uses the existing local mock POA, and runs a real Thunderbird under Xvfb. It does
not use your profile or credentials. It verifies native accounts, real folders,
headers, MIME rendering, read state, missing-host errors, disable/re-enable and
restart. It requires a **153 ESR** binary (an unsupported Arch rolling-release
version will fail the test, not be treated as compatible):

```sh
sudo pacman -S --needed thunderbird xorg-server-xvfb xorg-xauth
cmake -S thunderbird -B build/thunderbird -DGROUPWISE_RUNTIME_TESTS=ON
cmake --build build/thunderbird --parallel 4
ctest --test-dir build/thunderbird --output-on-failure
```

For Evolution regression checks, use the root README's separate build and
requirements. Exact executed commands and results are in
[docs/TEST_REPORT.md](docs/TEST_REPORT.md).

The minimal container proof excludes all Evolution/Camel/EDS packages:

```sh
docker build --target build -t groupwise-standalone -f thunderbird/tests/Dockerfile .
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/src" -w /src groupwise-standalone sh -c \
  'cmake -S thunderbird -B build/standalone -G Ninja && cmake --build build/standalone --parallel 4 && ctest --test-dir build/standalone --output-on-failure'
```

## Uninstall and troubleshooting

```sh
python thunderbird/packaging/linux/uninstall.py
```

Remove/disable the add-on through Thunderbird's Add-ons Manager. Unregistering is
idempotent and leaves the installed private prefix and all mail data intact.
After unregistering, the private binary/library prefix can be removed separately
if no longer needed. Do not delete the profile's GroupWise directory to uninstall.

If the host is unavailable, check that its manifest points to the installed
executable and only the expected extension ID is allowed. A Flatpak/Snap
Thunderbird may not see host paths; sandboxed packaging is not supported here.
Use `ldd "$HOME/.local/opt/thunderbird-groupwise/bin/groupwise-host"` to check
libraries. Do not run the helper in a terminal expecting text commands: stdin and
stdout are exclusively length-prefixed JSON. Run tests for protocol diagnostics.
Refresh errors are shown in add-on preferences; no password, session token or
message body should be pasted into bug reports.

Implementation and library license: LGPL-2.1-or-later; see the repository's
COPYING and existing copyright notices. The SOAP implementation remains shared
with Evolution. Architecture and versioned API evidence are in `docs/`.
