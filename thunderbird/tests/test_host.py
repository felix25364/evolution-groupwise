#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
import json
import os
import struct
import subprocess
import sys
import unittest

HOST = sys.argv.pop(1)


def frame(value):
    data = json.dumps(value).encode() if not isinstance(value, bytes) else value
    return struct.pack('=I', len(data)) + data


class Client:
    def __init__(self):
        self.process = subprocess.Popen([HOST], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.seq = 0

    def call(self, op, **args):
        self.seq += 1
        request = dict(id=str(self.seq), op=op, **args)
        self.process.stdin.write(frame(request))
        self.process.stdin.flush()
        size = struct.unpack('=I', self.process.stdout.read(4))[0]
        assert size <= 1024 * 1024
        response = json.loads(self.process.stdout.read(size))
        assert response['id'] == request['id'], response
        return response

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        assert self.process.returncode == 0
        self.process.stdout.close()
        assert self.process.stderr.read() == b''
        self.process.stderr.close()


class Framing(unittest.TestCase):
    def run_raw(self, data):
        p = subprocess.run([HOST], input=data, capture_output=True, timeout=5)
        self.assertEqual(p.stderr, b'')
        return p

    def test_empty(self):
        p = self.run_raw(b'')
        self.assertEqual((p.returncode, p.stdout), (0, b''))

    def test_ping_and_multiple_requests(self):
        c = Client()
        for _ in range(3):
            r = c.call('ping')
            self.assertTrue(r['ok'])
            self.assertEqual(r['result']['protocolVersion'], 1)
        self.assertEqual(c.call('nonsense')['error']['code'], 'UNSUPPORTED_OPERATION')
        self.assertEqual(c.call('listFolders')['error']['code'], 'NOT_LOGGED_IN')
        c.close()

    def test_bad_json_and_requests(self):
        for data in [b'{', b'[]', b'null', b'"x"', b'{"id":"a"}\x00', b'\xff']:
            p = self.run_raw(frame(data))
            self.assertEqual(p.returncode, 0)
            response = json.loads(p.stdout[4:])
            self.assertFalse(response['ok'])
        for req in [{}, {'id': 1}, {'id': []}, {'id': 'a'}, {'id': 'a', 'op': 'login'},
                    {'id': 'a', 'op': 'login', 'host': 'x', 'username': 'u', 'password': 'p', 'tls': 'false'},
                    {'id': 'a', 'op': 'login', 'host': 'x', 'username': 'u', 'password': 'p', 'port': 1.5}]:
            p = self.run_raw(frame(req))
            self.assertFalse(json.loads(p.stdout[4:])['ok'])

    def test_truncated_zero_and_oversized(self):
        for data in [b'\x01', struct.pack('=I', 20) + b'{}', struct.pack('=I', 0),
                     struct.pack('=I', 262145), struct.pack('>I', 256)]:
            p = self.run_raw(data)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(p.stdout, b'')

    def test_recover_after_invalid_json(self):
        p = self.run_raw(frame(b'{') + frame({'id':'next','op':'ping'}))
        self.assertEqual(p.returncode,0)
        size=struct.unpack('=I',p.stdout[:4])[0]
        self.assertFalse(json.loads(p.stdout[4:4+size])['ok'])
        self.assertTrue(json.loads(p.stdout[8+size:])['ok'])

    def test_no_evolution_linkage(self):
        import re
        result=subprocess.run(['ldd',HOST],capture_output=True,text=True,check=True)
        self.assertIsNone(re.search(r'^\s*(libcamel|libedata|libebackend|libebook|libecal|libevolution)',result.stdout,re.M))

    def test_partial_reads(self):
        c = Client()
        for b in frame({'id': 'partial', 'op': 'ping'}):
            c.process.stdin.write(bytes([b]))
            c.process.stdin.flush()
        size = struct.unpack('=I', c.process.stdout.read(4))[0]
        self.assertTrue(json.loads(c.process.stdout.read(size))['ok'])
        c.close()

    def test_disconnected_reader(self):
        c = Client()
        c.process.stdout.close()
        c.process.stdin.write(frame({'id': 'broken', 'op': 'ping'}))
        c.process.stdin.close()
        self.assertEqual(c.process.wait(timeout=5), 0)
        self.assertEqual(c.process.stderr.read(), b'')
        c.process.stderr.close()


if __name__ == '__main__':
    unittest.main()
