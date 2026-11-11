#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]


class Packaging(unittest.TestCase):
    def test_deterministic_complete_xpi(self):
        with tempfile.TemporaryDirectory() as d:
            outputs=[pathlib.Path(d)/f'{n}.xpi' for n in [1,2]]
            for path in outputs:
                subprocess.run([sys.executable,str(ROOT/'packaging/linux/package-xpi.py'),str(ROOT/'extension'),str(path)],check=True,capture_output=True)
            self.assertEqual(hashlib.sha256(outputs[0].read_bytes()).digest(),hashlib.sha256(outputs[1].read_bytes()).digest())
            with zipfile.ZipFile(outputs[0]) as z:
                self.assertIsNone(z.testzip())
                manifest=json.loads(z.read('manifest.json'))
                for name in manifest['background']['scripts']+[manifest['options_ui']['page'],'setup.js','backend.js','experiment.js','schema.json']:
                    self.assertIn(name,z.namelist())
                self.assertTrue(all(not p.startswith(('/', '..')) for p in z.namelist()))
                self.assertEqual(manifest['experiment_apis']['groupwise']['parent']['events'],['startup'])
                json.loads(z.read('schema.json'))

    def test_idempotent_registration_and_safe_removal(self):
        with tempfile.TemporaryDirectory() as d:
            home=pathlib.Path(d)
            prefix=home/'prefix'
            (prefix/'bin').mkdir(parents=True)
            host=prefix/'bin/groupwise-host'
            host.write_text('#!/bin/sh\nexit 0\n')
            host.chmod(0o700)
            untouched=prefix/'unrelated-file'
            untouched.write_text('retain')
            env=dict(os.environ,HOME=str(home))
            for _ in range(2):
                subprocess.run([sys.executable,str(ROOT/'packaging/linux/install.py'),'--prefix',str(prefix)],env=env,check=True,capture_output=True)
            path=home/'.mozilla/native-messaging-hosts/org.evolution_groupwise.host.json'
            manifest=json.loads(path.read_text())
            self.assertEqual(manifest['path'],str(host))
            self.assertEqual(manifest['allowed_extensions'],['groupwise@evolution-groupwise.org'])
            for _ in range(2):
                subprocess.run([sys.executable,str(ROOT/'packaging/linux/uninstall.py')],env=env,check=True,capture_output=True)
            self.assertFalse(path.exists())
            self.assertEqual(untouched.read_text(),'retain')
            self.assertTrue(host.exists())
            path.write_text('{"name":"unrelated"}')
            refused=subprocess.run([sys.executable,str(ROOT/'packaging/linux/install.py'),'--prefix',str(prefix)],env=env,capture_output=True)
            self.assertNotEqual(refused.returncode,0)
            refused=subprocess.run([sys.executable,str(ROOT/'packaging/linux/uninstall.py')],env=env,capture_output=True)
            self.assertNotEqual(refused.returncode,0)
            self.assertEqual(json.loads(path.read_text()),{'name':'unrelated'})


if __name__=='__main__':
    unittest.main()
