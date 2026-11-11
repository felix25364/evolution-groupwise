#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Register an already installed host for this user; never alter Thunderbird profiles."""
import argparse
import json
import os
import pathlib
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--prefix', type=pathlib.Path, default=pathlib.Path.home()/'.local/opt/thunderbird-groupwise')
a = p.parse_args()
host = (a.prefix/'bin/groupwise-host').resolve(strict=True)
if not os.access(host, os.X_OK):
    p.error('groupwise-host is not executable; run cmake --install first')
manifest = {'name':'org.evolution_groupwise.host', 'description':'GroupWise SOAP Native Messaging host',
            'path':str(host), 'type':'stdio', 'allowed_extensions':['groupwise@evolution-groupwise.org']}
folder = pathlib.Path.home()/'.mozilla/native-messaging-hosts'
folder.mkdir(mode=0o700, parents=True, exist_ok=True)
path = folder/'org.evolution_groupwise.host.json'
if path.exists():
    old = json.loads(path.read_text())
    if old.get('name') != manifest['name'] or old.get('allowed_extensions') != manifest['allowed_extensions']:
        p.error('refusing to overwrite an unrelated native host manifest')
fd, tmp = tempfile.mkstemp(dir=folder)
try:
    with os.fdopen(fd, 'w') as f:
        json.dump(manifest, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
print(path)
