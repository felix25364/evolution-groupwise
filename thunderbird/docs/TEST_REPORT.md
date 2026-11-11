# Executed validation report

Date: 2026-11-11. Base repository commit:
`f7d27dab8cc4f8261a60b60be4a935e1f9dd52b0`.
Feature branch: `feat/thunderbird-groupwise-linux-mvp`.

## Environment

Debian 13 amd64 containers in the managed Linux environment. GCC 14.2.0,
CMake 3.31.6, Ninja, Python 3.13.5, Node 20.19.2, GLib/GIO 2.84.4,
libsoup 3.6.5, libxml2 2.9.14, json-glib 1.10.6. Full regression image also
has Evolution/evolution-data-server 3.56.2. Actual runtime: Thunderbird
153.6.0esr (`Services.appinfo.version` 153.6.0), launched under Xvfb.

All SOAP tests use the repository's existing mock POA; no private POA or user
profile was accessed. Runtime tests create a temporary HOME, native host manifest
and Thunderbird profile, install the XPI as an actual persistent add-on, perform
real operations, restart Thunderbird and remove their temporary directories.

## Final outcomes

| Check | Result | Evidence |
| --- | --- | --- |
| Standalone C build | PASS | All shared-core and native-host targets compile with host warnings treated as errors |
| native-framing | PASS, 8 Python tests | Ping/sequential requests, JSON/type validation, unknown op, pre-login error, empty input, zero/truncated/oversized/incorrect prefixes, partial reads, invalid-JSON recovery, disconnected reader, clean EOF, no Evolution library linkage |
| native-soap | PASS, 5 Python tests | Actual mock login/folders/headers/MIME, bounded pages, invalid IDs, auth/network errors, TLS trust/rejection, expired session renewal, read/unread, copy/move/delete, 16 MiB cap and exact 1 MiB multi-frame reassembly |
| extension-transport | PASS | Correlation/out-of-order results, structured errors, reconnect, stale disconnect, timeouts, close, UTF-8 size bounds, cancellation of GroupWise-identity sends |
| linux-packaging | PASS, 2 Python tests | Valid deterministic XPI and schema/references; idempotent host registration/removal; unrelated manifests/files protected |
| thunderbird-runtime | PASS | Actual installed Experiment, native factories, account creation, 10 mail folders plus root, nested duplicate names, flags, two Inbox headers, unread count, stable keys across refresh, original MIME and headers streamed, ordinary file save, cache mode 0600, normal folder/message UI, completed text rendering, read state reaches POA, missing-host error, disable/re-enable refresh, data retention, actual restart with saved credentials |
| thunderbird-html-runtime | PASS | Same complete runtime path with generated multipart HTML alternative and binary attachment fixture; normal viewer shows HTML element and attachment; completed load state verified |
| Evolution regression | PASS, 6 CTests | provider-build-tree, connection, camel, utils, contact, calendar |
| Minimal dependency image | PASS, 4 CTests | Clean standalone build/install and framing/SOAP/transport/packaging tests without Evolution, Camel or EDS installed |

The final Thunderbird CTest run executed **6/6 suites, 0 failed, 0 skipped**.
Evolution executed **6/6, 0 failed, 0 skipped**. The independent minimal-image
final run executed **4/4, 0 failed, 0 skipped**. Installed-host framing tests
also passed all eight cases after the final private-prefix installation.

## Exact executed commands

Commands below ran in the selected checkout, `/workspace/evolution-groupwise`,
in the prepared full development container (through `docker exec groupwise-tb-dev`).
The final native release run was:

```sh
cmake -S thunderbird -B build/thunderbird -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_INSTALL_PREFIX=/workspace/evolution-groupwise-env/tb-prefix \
  -DGROUPWISE_RUNTIME_TESTS=ON
cmake --build build/thunderbird --parallel 4
ctest --test-dir build/thunderbird --output-on-failure
cmake --install build/thunderbird
```

The last Evolution regression run was:

```sh
cmake --build build --parallel 4
ctest --test-dir build --output-on-failure
```

`build` was the root Evolution build configured during onboarding with all
modules enabled and private prefix `/workspace/evolution-groupwise-env/prefix`.
No existing Evolution implementation or root build configuration was changed.

Real host registration and transport smoke validation were also executed:

```sh
python3 thunderbird/packaging/linux/install.py \
  --prefix /workspace/evolution-groupwise-env/tb-prefix
node thunderbird/tests/test_transport.js
python3 thunderbird/tests/test_host.py /workspace/evolution-groupwise-env/tb-prefix/bin/groupwise-host
```

Installer/uninstaller idempotence and protection checks run under temporary HOME
directories in `test_packaging.py`. `ldd` verified the installed and build-tree
host's library resolution; the native-framing test rejects Camel/EDS/Evolution
library linkage. The installed executable also successfully ran through native
framing tests during development.

The independent minimal-dependency proof used the committed Dockerfile:

```sh
docker build --target build -t groupwise-standalone \
  -f thunderbird/tests/Dockerfile .
docker run --rm --user 1000:1000 -e HOME=/tmp \
  --mount type=bind,src=/workspace/evolution-groupwise,dst=/src \
  --mount type=bind,src=/workspace/evolution-groupwise-env,dst=/outputs \
  -w /src groupwise-standalone sh -c '
    cmake -S thunderbird -B /outputs/standalone-build -G Ninja \
      -DCMAKE_BUILD_TYPE=Debug -DCMAKE_INSTALL_PREFIX=/outputs/standalone-prefix &&
    cmake --build /outputs/standalone-build --parallel 4 &&
    ctest --test-dir /outputs/standalone-build --output-on-failure &&
    cmake --install /outputs/standalone-build &&
    ldd /outputs/standalone-prefix/bin/groupwise-host'
```

After final source updates, the same minimal image rebuilt the existing
`/outputs/standalone-build`, repeated all four tests and reinstalled successfully.
The Dockerfile's `runtime` target optionally adds Thunderbird/Xvfb, separately
from this dependency proof.

## Failures investigated and fixed

- Directly loading the backend jar URI was rejected as untrusted. Added an owned
  chrome registration and corresponding shutdown cleanup.
- Experiment globals require imported timers and explicit imported DOM globals.
  These were corrected, then tested in the actual application.
- Generic folders need `incomingServerType`, a backing file and delegated
  `getDBFolderInfoAndDB`. Without these, server lookup/summary operations failed.
- `setFlag` treats combined masks as an any-bit test. Using the full flags setter
  made Inbox/Sent/Drafts/Trash/Junk flags correct and persistent.
- Master IDL differs from 153 ESR (`nsIMsgWindow` parameters and
  `GetMessageHeader`). Adapters now match the tagged runtime source.
- 153's standalone-MIME path needs the message-display query before `&number=0`.
  The custom service also returns the actual mailbox channel URL so Thunderbird's
  progress listener accepts headers, attachments and completed-load events.
- Cached `Cc` membership survives unregistration. Actual registrar state and
  factory creation now drive ownership checks. Re-enable rebinds existing native
  folder delegates/server refresh, and pending startup work waits for the
  background listener instead of getting lost.
- IOUtils ignored a proposed write-permissions option. MIME now writes through a
  pre-created 0600 temporary file, explicitly sets permissions, and atomically
  moves it into a private cache. Runtime assertions verify the final mode.
- The first SOAP test expected MIME-Version in a pre-existing fixture that does
  not contain it. The test now checks the original-MIME marker and exact bytes;
  the separate HTML multipart fixture verifies full MIME/attachment handling.

None of these failures remain in the final executed suites. Ordinary runtime
logs include container user-namespace and missing accessibility DBus warnings,
plus an empty initial add-on blocklist database message. Final-runtime assertions
found no GroupWise JavaScript exceptions. Errors intentionally induced for tests
(e.g. missing native host) are distinguished from unhandled application errors.

## Limits of the evidence

- Live GroupWise behavior, Arch Linux installation, Thunderbird 160/other release
  lines, Flatpak/Snap integration and primary-password prompts were not tested.
- Automated runtime setup invokes the actual Experiment backend; the HTML setup
  form itself was not driven by the harness. The background native transport,
  login manager and persistent account are exercised.
- Copy/move/delete are verified host operations, not completed Thunderbird
  transaction/undo UI integration. Native outgoing sending is not implemented;
  only its conservative identity-send guard is tested automatically.
- Events, incremental/offline actions, large-mailbox/concurrent sync stability,
  cache quotas and SOAP-only shared-message MIME reconstruction remain future
  work. Canonical save conversion and mbox appending are explicitly unsupported.
- No publication of a reusable cloud environment is claimed. The earlier cloud
  draft service error is separate from the committed, tested repository workflow.

## Git delivery

Implementation commit: `8cf3630968498a80c1cd2f484887923c371fbe0f`, pushed to
`origin/feat/thunderbird-groupwise-linux-mvp` in `felix25364/evolution-groupwise`.
The default branch was not changed or merged.

A draft PR was attempted using:

```sh
gh pr create --repo felix25364/evolution-groupwise \
  --head feat/thunderbird-groupwise-linux-mvp --base main --draft \
  --title "Add native GroupWise mail accounts for Thunderbird 153 on Linux" \
  --body-file /tmp/groupwise-pr.md
```

Result: `Post "https://api.github.com/graphql": Forbidden`. A subsequent
`curl -I --max-time 20 https://api.github.com/` returned a CONNECT tunnel HTTP
403 from the environment proxy. This blocks PR creation through the available
API route; it is separate from the successful authenticated Git push. No PR URL
is claimed. Final delivery notes are in a separate documentation-only commit.
