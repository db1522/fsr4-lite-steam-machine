# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Steam Machine Life

"""Catches Steam's interface freezing, while it's frozen.

Steam's interface (Gaming Mode, the Quick Access menu and every Decky plugin's panel) runs as pages of steamwebhelper,
which answer on the debugger port Decky uses (127.0.0.1:8080). The backend runs apart from them, so it still works
when they hang. ping() asks the background page (SharedJSContext, where plugin panels and Steam's own scripts run)
for 1+1. When it stops answering, stack() pauses that page for a moment and reads where its JavaScript is: the script
URLs name the code (a plugin's dist/index.js, Decky, or Steam's own), which a restart would otherwise erase.

Seen 2026-11-13 on the Steam Machine: after Cyberpunk 2077 closed, every Steam page stopped answering within five
seconds and steamwebhelper sat at 50% CPU; a minute later the debugger itself stopped answering, so the moment to read
the stack is right away. No third-party package: a minimal WebSocket client over a plain socket."""

import base64
import json
import os
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request

DEBUGGER = "http://127.0.0.1:8080/json"
PAGE = "SharedJSContext"


class Cdp:
    """One page's DevTools connection (text frames only, which is all Chrome's protocol sends)."""

    def __init__(self, url, timeout):
        host, path = url[len("ws://"):].split("/", 1)
        name, port = host.split(":")
        self.sock = socket.create_connection((name, int(port)), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("the debugger closed the connection")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("the debugger refused the connection")
        self.next_id = 0
        self.events = []

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _send(self, obj):
        data = json.dumps(obj).encode()
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n)
                                if n < 1 << 16 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _exact(self, n):
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise ConnectionError("the debugger closed the connection")
            out += chunk
        return out

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._exact(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            if b2 & 0x80:  # a masked frame (servers don't send them, but read it right if one comes)
                mask = self._exact(4)
                msg += bytes(b ^ mask[i % 4] for i, b in enumerate(self._exact(n)))
            else:
                msg += self._exact(n)
            if b1 & 0x80:
                if b1 & 0x0F == 0x8:
                    raise ConnectionError("the debugger closed the connection")
                if b1 & 0x0F in (0x9, 0xA):  # ping / pong
                    msg = b""
                    continue
                return json.loads(msg)

    def call(self, method, params=None, deadline=None):
        """A command's reply; events that arrive first are kept in self.events. TimeoutError past deadline."""
        self.next_id += 1
        mine = self.next_id
        self._send({"id": mine, "method": method, "params": params or {}})
        while True:
            if deadline is not None:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(method)
                self.sock.settimeout(left)
            m = self.recv()
            if m.get("id") == mine:
                return m
            self.events.append(m)


def _page_url(timeout):
    """The background page's debugger address; raises OSError when the debugger can't be reached."""
    with urllib.request.urlopen(DEBUGGER, timeout=timeout) as r:
        pages = json.load(r)
    for p in pages:
        if str(p.get("title", "")).startswith(PAGE) and p.get("webSocketDebuggerUrl"):
            return p["webSocketDebuggerUrl"]
    raise ConnectionError("no SharedJSContext page")


def ping(timeout=10):
    """ "ok" when Steam's background page answers within timeout seconds, "hung" when it doesn't, "debugger hung"
    when even the debugger's page list doesn't come, "off" when nothing listens (Steam starting, or no debugger)."""
    start = time.monotonic()
    try:
        url = _page_url(timeout)
    except (socket.timeout, TimeoutError):
        return "debugger hung"
    except urllib.error.URLError as e:
        return "debugger hung" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "off"
    except (OSError, ValueError):
        return "off"
    cdp = None
    try:
        cdp = Cdp(url, timeout)
        r = cdp.call("Runtime.evaluate", {"expression": "1+1", "returnByValue": True}, start + timeout)
        return "ok" if r.get("result", {}).get("result", {}).get("value") == 2 else "hung"
    except (socket.timeout, TimeoutError):
        return "hung"
    except (OSError, ValueError):
        return "off"
    finally:
        if cdp:
            cdp.close()


def stack(timeout=10):
    """Where the background page's JavaScript is right now: one line per call frame (function, script, line), read by
    pausing the page and resuming it at once. A list of lines saying why when it can't be read."""
    deadline = time.monotonic() + timeout
    cdp = None
    try:
        cdp = Cdp(_page_url(timeout), timeout)
        cdp._send({"id": 900001, "method": "Debugger.enable", "params": {}})
        cdp._send({"id": 900002, "method": "Debugger.pause", "params": {}})
        scripts, frames = {}, None
        while frames is None:
            left = deadline - time.monotonic()
            if left <= 0:
                return ["(the page didn't pause in time: Steam's process itself may be stuck, not a script)"]
            cdp.sock.settimeout(left)
            m = cdp.recv()
            if m.get("method") == "Debugger.scriptParsed":
                scripts[m["params"].get("scriptId")] = m["params"].get("url", "")
            elif m.get("method") == "Debugger.paused":
                frames = m["params"].get("callFrames", [])
        lines = []
        for f in frames[:30]:
            loc = f.get("location", {})
            url = scripts.get(loc.get("scriptId")) or f.get("url", "") or "(no script name)"
            lines.append(f'{f.get("functionName") or "(anonymous)"}  {url}:{loc.get("lineNumber", 0) + 1}:'
                         f'{loc.get("columnNumber", 0) + 1}')
        cdp._send({"id": 900003, "method": "Debugger.resume", "params": {}})
        cdp._send({"id": 900004, "method": "Debugger.disable", "params": {}})
        return lines or ["(paused, but no call frames: the page was idle when it paused)"]
    except (socket.timeout, TimeoutError):
        return ["(the debugger didn't answer in time)"]
    except (OSError, ValueError) as e:
        return [f"(couldn't read it: {e})"]
    finally:
        if cdp:
            time.sleep(0.2)  # let the resume go out before the socket closes
            cdp.close()


def _run(cmd, limit=6000):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, errors="replace").stdout
    except (OSError, subprocess.SubprocessError) as e:
        return f"({cmd[0]} couldn't run: {e})"
    return out[-limit:]


def _tail(path, lines=40):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(f.tell() - 64 * 1024, 0))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return f"(no {os.path.basename(path)})"
    return "\n".join(text.splitlines()[-lines:])


def system_lines(home):
    """What the system was doing: the busiest processes, the last minute of the system log, Steam's own logs."""
    steam_logs = os.path.join(home, ".local", "share", "Steam", "logs")
    return [
        "== Busiest processes ==",
        "\n".join(line[:220] for line in
                  _run(["ps", "-eo", "pid,etimes,pcpu,rss,stat,args", "--sort=-pcpu"], 200000).splitlines()[:16]),
        "", "== System log, last minute ==",
        _run(["journalctl", "-b", "--no-pager", "-o", "short-iso", "--since", "-60s"], 12000),
        "", "== Steam: console_log.txt (end) ==", _tail(os.path.join(steam_logs, "console_log.txt")),
        "", "== Steam: gameprocess_log.txt (end) ==", _tail(os.path.join(steam_logs, "gameprocess_log.txt")),
        "", "== Steam: webhelper.txt (end) ==", _tail(os.path.join(steam_logs, "webhelper.txt"), 20),
    ]
