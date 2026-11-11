# SPDX-License-Identifier: LGPL-2.1-or-later
"""Local-only Marionette client for isolated Thunderbird tests, no third-party deps."""
import json
import socket
import time


class Marionette:
    def __init__(self, port):
        self.sequence = 0
        deadline = time.monotonic() + 20
        while True:
            try:
                self.sock = socket.create_connection(('127.0.0.1', port), timeout=2)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Thunderbird Marionette did not start')
                time.sleep(.1)
        self.sock.settimeout(65)
        self.read()  # Protocol handshake.
        self.call('WebDriver:NewSession', {'capabilities':{}})
        self.call('Marionette:SetContext', {'value':'chrome'})

    def read_exact(self, size):
        data = bytearray()
        while len(data) < size:
            part = self.sock.recv(size-len(data))
            if not part:
                raise EOFError('Marionette disconnected')
            data.extend(part)
        return bytes(data)

    def read(self):
        prefix = bytearray()
        while True:
            char = self.read_exact(1)
            if char == b':':
                break
            prefix.extend(char)
            if len(prefix) > 10 or not char.isdigit():
                raise RuntimeError('Invalid Marionette frame')
        size = int(prefix)
        if size > 16*1024*1024:
            raise RuntimeError('Oversized Marionette frame')
        return json.loads(self.read_exact(size))

    def call(self, name, args=None):
        self.sequence += 1
        data = json.dumps([0, self.sequence, name, args or {}]).encode()
        self.sock.sendall(str(len(data)).encode()+b':'+data)
        response = self.read()
        if response[2]:
            raise RuntimeError(response[2])
        return response[3]

    def script(self, script, args=None, async_=False):
        return self.call('WebDriver:ExecuteAsyncScript' if async_ else 'WebDriver:ExecuteScript', {
            'script':script, 'args':args or [], 'newSandbox':False,
            'sandbox':'system', 'scriptTimeout':60000,
        })
