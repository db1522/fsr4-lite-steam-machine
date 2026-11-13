# SPDX-License-Identifier: BSD-3-Clause
"""The Steam freeze catcher (sml_watch) against a fake Steam debugger: one that answers, one that hangs, one whose
background page is stuck in a plugin's script."""
import json
import socket
import socketserver
import struct
import threading
import time
import unittest
from unittest import mock

import _harness  # noqa: F401
from _tmp import temp_dir  # noqa: E402,F401
import sml_watch


class FakeDebugger(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, mode):
        self.mode, self.got = mode, []
        super().__init__(("127.0.0.1", 0), Handler)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()


class Handler(socketserver.BaseRequestHandler):
    def _exact(self, n):
        out = b""
        while len(out) < n:
            chunk = self.request.recv(n - len(out))
            if not chunk:
                raise ConnectionError
            out += chunk
        return out

    def _frame(self):
        b1, b2 = self._exact(2)
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._exact(2))[0]
        mask = self._exact(4)
        return json.loads(bytes(b ^ mask[i % 4] for i, b in enumerate(self._exact(n))))

    def _send(self, obj):
        data = json.dumps(obj).encode()
        n = len(data)
        head = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + struct.pack(">H", n)
        self.request.sendall(head + data)

    def handle(self):
        server = self.server
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.request.recv(4096)
        path = head.split(b" ", 2)[1].decode()
        if path == "/json":
            if server.mode == "debugger hung":
                time.sleep(3)
                return
            body = json.dumps([{"title": "SharedJSContext",
                                "webSocketDebuggerUrl": f"ws://127.0.0.1:{server.port}/devtools/page/1"}]).encode()
            self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                                 + str(len(body)).encode() + b"\r\n\r\n" + body)
            return
        self.request.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
        try:
            while True:
                m = self._frame()
                server.got.append(m["method"])
                if server.mode == "ok" and m["method"] == "Runtime.evaluate":
                    self._send({"id": m["id"], "result": {"result": {"type": "number", "value": 2}}})
                elif server.mode == "stuck" and m["method"] == "Debugger.enable":
                    self._send({"method": "Debugger.scriptParsed", "params": {
                        "scriptId": "7", "url": "http://127.0.0.1:1337/plugins/Some Plugin/dist/index.js"}})
                    self._send({"id": m["id"], "result": {}})
                elif server.mode == "stuck" and m["method"] == "Debugger.pause":
                    self._send({"method": "Debugger.paused", "params": {"callFrames": [
                        {"functionName": "spin", "location": {"scriptId": "7", "lineNumber": 41, "columnNumber": 9}},
                        {"functionName": "", "location": {"scriptId": "7", "lineNumber": 99, "columnNumber": 0}}]}})
                # "hung" and "stuck" never answer Runtime.evaluate
        except (ConnectionError, OSError, ValueError):
            pass


class Watch(unittest.TestCase):
    def fake(self, mode):
        server = FakeDebugger(mode)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        patch = mock.patch.object(sml_watch, "DEBUGGER", f"http://127.0.0.1:{server.port}/json")
        patch.start()
        self.addCleanup(patch.stop)
        return server

    def test_a_page_that_answers_is_ok(self):
        self.fake("ok")
        self.assertEqual(sml_watch.ping(2), "ok")

    def test_a_page_that_never_answers_is_hung(self):
        self.fake("hung")
        start = time.monotonic()
        self.assertEqual(sml_watch.ping(1), "hung")
        self.assertLess(time.monotonic() - start, 2.5, "gives up after the timeout")

    def test_a_debugger_that_never_lists_its_pages_is_hung_too(self):
        self.fake("debugger hung")
        self.assertEqual(sml_watch.ping(1), "debugger hung")

    def test_no_debugger_at_all_is_off_not_a_freeze(self):
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        with mock.patch.object(sml_watch, "DEBUGGER", f"http://127.0.0.1:{port}/json"):
            self.assertEqual(sml_watch.ping(5), "off")  # Windows takes ~2 s to report a refused connection

    def test_a_stuck_page_names_the_script_and_line_and_is_resumed(self):
        server = self.fake("stuck")
        self.assertEqual(sml_watch.ping(1), "hung")
        lines = sml_watch.stack(3)
        self.assertEqual(lines[0], "spin  http://127.0.0.1:1337/plugins/Some Plugin/dist/index.js:42:10")
        self.assertTrue(lines[1].startswith("(anonymous)"))
        time.sleep(0.3)
        self.assertIn("Debugger.resume", server.got, "the page is let go again")

    def test_system_lines_never_fail_without_steam(self):
        lines = sml_watch.system_lines(temp_dir(self))
        self.assertIn("== Steam: console_log.txt (end) ==", lines)
        self.assertIn("(no console_log.txt)", lines)


if __name__ == "__main__":
    unittest.main()
