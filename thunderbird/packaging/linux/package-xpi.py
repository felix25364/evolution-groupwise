#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Deterministic, dependency-free XPI packaging; never include profiles or secrets."""
import json
import pathlib
import sys
import zipfile

source, output = map(pathlib.Path, sys.argv[1:])
manifest = json.loads((source / 'manifest.json').read_text())
assert manifest['manifest_version'] == 2
assert manifest['browser_specific_settings']['gecko']['id'] == 'groupwise@evolution-groupwise.org'
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob('*')):
        if path.is_file():
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
print(output)
