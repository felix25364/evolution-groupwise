#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Unregister this user's native host. Mail, profiles and installed files are retained."""
import json
import pathlib

path = pathlib.Path.home()/'.mozilla/native-messaging-hosts/org.evolution_groupwise.host.json'
if path.exists():
    manifest = json.loads(path.read_text())
    if manifest.get('name') != 'org.evolution_groupwise.host' or manifest.get('allowed_extensions') != ['groupwise@evolution-groupwise.org']:
        raise SystemExit('Refusing to remove an unrelated manifest')
    path.unlink()
print('Native host unregistered. Remove the add-on in Thunderbird; profile and mail data are retained.')
