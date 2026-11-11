# Architecture

`setup page → background transport → connectNative → groupwise-host → libegroupwise → POA`

The Experiment also provides native `groupwise` server and generic JSAccount
folder objects. Folder refresh and message services request SOAP work through an
Experiment event, the background correlates native responses, and the Experiment
updates Thunderbird's actual databases. Message display downloads original MIME
to a private cache and invokes Thunderbird's built-in MIME service.

## Dependencies and reuse

The existing `src/libegroupwise/CMakeLists.txt` is included **in place** by the
standalone `thunderbird/CMakeLists.txt`. It builds the same shared library with
GLib/GObject/GIO, libsoup 3 and libxml2. The C host adds json-glib. No Camel,
Evolution or evolution-data-server headers/libraries are required by this build.
The root CMake build and all Evolution source files remain unchanged.

Core functions used (signatures are authoritative in `e-gw-connection.h` and
`e-gw-folder.h`):

- `e_gw_connection_new(host, guint16 port, gboolean use_ssl)`;
- `e_gw_connection_login_sync(cnc, user, password, cancellable, error)`;
- `e_gw_connection_get_folder_list_sync(cnc, parent, recurse, cancellable, error)`;
- `e_gw_connection_foreach_item_sync(cnc, container, view, filter_xml, page_size,
  callback, data, cancellable, error)` for cursors and the core's query fallback;
- `e_gw_connection_get_items_sync(cnc, container, view, filter_xml, count,
  cancellable, error)` is available but cursor iteration is preferred;
- `e_gw_connection_get_item_sync(cnc, id, view, cancellable, error)`;
- `e_gw_connection_download_sync(cnc, id, as_mime, output, cancellable, error)`;
- `e_gw_connection_mark_read_sync`, `move_items_sync`, `remove_items_sync`.
- `e_gw_connection_send_item_sync(cnc, item_xml, cancellable, error)` exists but
  does not convert arbitrary composed MIME to GroupWise item XML.

The reused core retains its existing SOAP client application label.
The core owns session renewal, TLS validation, user CA support, folder parsing,
cursors and XML helpers. Camel metadata/MIME code is Evolution-specific: it uses
Camel InternetAddress, message info and MIME objects and is **not** linked or
copied into the host. Original `Mime.822` attachments are preferred; otherwise the
core's full-item RFC-822 endpoint is used. Unsupported shared-item MIME rebuilding
is a documented limitation, not silently replaced with Camel.

## Wire contract

Native byte order uint32 length, then UTF-8 JSON. Requests contain string `id`
(maximum 128 bytes), `op`, and operation fields. Replies contain the same `id`,
`ok`, and `result` or a sanitized `{code,message}` error. Malformed framing exits
2; malformed JSON receives an error and the host can continue. EOF exits 0.
Stdout contains frames only. One host owns one account session; each account has
its own native port. SOAP work is serialized in the helper, away from the UI.

Operations: `ping`, `login` (`host`, `port`, `username`, `password`, `tls`), `logout`,
`listFolders`, `listMessages` (`folderId`, `offset`, `limit`), `getMessage`
(`messageId`, `offset`, `limit`), `markRead` (`messageId`, `read`),
`deleteMessages` (`messageId`, `folderId`), `moveMessages` / `copyMessages`
(`messageId`, `folderId` for move, `destinationId`). Mutations intentionally act
on one item per request. There is no raw SOAP endpoint.

Input cap 256 KiB; output cap 1 MiB; 200 headers per page; 128 KiB binary MIME
chunks encoded as base64; one cached MIME message per host, hard download cap
16 MiB enforced during writes. Listing offsets rescan a server cursor and are
not snapshot tokens: concurrent mailbox changes can shift offsets. Query folders
inherit POA/core server result limits. JSON framing bounds do not change the
shared core's existing XML response allocation behavior.

## Storage and safety

Account preferences and login-manager entries belong to Thunderbird. Passwords
are not extension storage values. Folder URI components use encoded remote IDs;
remote names are display labels. Database headers retain full remote IDs; local
numeric keys are stable across refresh/restart. MIME filenames hash remote IDs
under the server's private profile directory. Uninstall only unregisters the
native host; mail databases and account data remain.

New work must follow AGENTS.md. Automatic tests use the existing public mock POA
account and disposable profiles, never a user's profile or real mailbox.
Existing license: LGPL-2.1-or-later, copyright bond Software Entwicklung GmbH;
shared source/license notices are preserved. New implementation files carry the
same SPDX identifier. Mozilla references are inspected, not vendored.
