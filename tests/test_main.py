# SPDX-License-Identifier: BSD-3-Clause
"""FSR 4.1 Lite 2.0 backend, end to end on a fake Steam library: scan, install, a session where OptiScaler didn't
load (the next loader name is set up), a session where Lite ran, and an uninstall that leaves the game as it was."""
import asyncio
import os
import tempfile
import time
import unittest
from unittest import mock

import _harness  # noqa: F401
import decky
import main
import sml_assets


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Flow(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        steam = os.path.join(self.home, ".local", "share", "Steam")
        apps = os.path.join(steam, "steamapps")
        touch(os.path.join(apps, "appmanifest_42.acf"),
              b'"AppState"\n{\n"appid" "42"\n"name" "Test Game"\n"installdir" "Test Game"\n}\n')
        touch(os.path.join(steam, "steamapps", "libraryfolders.vdf"), b'"libraryfolders"\n{\n}\n')
        self.game = os.path.join(apps, "common", "Test Game")
        touch(os.path.join(self.game, "game.exe"), b"game" * 50)
        touch(os.path.join(self.game, "nvngx_dlss.dll"))
        self.data = tempfile.mkdtemp()
        pkg = sml_assets.package_dir(self.data)
        touch(os.path.join(pkg, "OptiScaler.dll"), b"opti")
        touch(os.path.join(pkg, "OptiScaler.ini"), b"[FSR]\r\nFsr4Model=auto\r\n")
        for name, spec in sml_assets.FSR4_FILES.items():
            path = os.path.join(self.data, "fsr4", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.truncate(spec["size"])
        self.settings = tempfile.mkdtemp()
        self.patches = [mock.patch.multiple(decky, DECKY_USER_HOME=self.home, DECKY_PLUGIN_SETTINGS_DIR=self.settings,
                                            DECKY_PLUGIN_RUNTIME_DIR=self.data, create=True)]
        for p in self.patches:
            p.start()
        self.loop = asyncio.new_event_loop()
        self.p = main.Plugin()
        self.loop.run_until_complete(self.p._main())
        self.loop.run_until_complete(self.p._scan_task)

    def tearDown(self):
        self.loop.close()
        for p in self.patches:
            p.stop()

    def run_(self, coro):
        return self.loop.run_until_complete(coro)

    def test_scan_install_retry_lite_uninstall(self):
        state = self.run_(self.p.get_state())["state"]
        self.assertTrue(state["assets_ready"])
        self.assertEqual([g["name"] for g in state["games"]], ["Test Game"])
        self.assertEqual(state["games"][0]["upscalers"], ["DLSS"])

        r = self.run_(self.p.enable_game(42, ""))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b %command%")
        self.assertTrue(os.path.isfile(os.path.join(self.game, "dxgi.dll")))
        self.assertTrue(os.path.isfile(os.path.join(self.game, "OptiScaler", "amdxcffx64.dll")))

        # a session with no OptiScaler.log: the game skipped dxgi.dll, so winmm.dll is set up next
        self.run_(self.p.session_started(42))
        self.p.sessions[42] = time.time() + 5
        r = self.run_(self.p.session_ended(42, "WINEDLLOVERRIDES=dxgi=n,b %command%"))
        self.assertEqual(r["retry"], "winmm.dll")
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=winmm=n,b %command%")
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))
        self.assertTrue(os.path.isfile(os.path.join(self.game, "winmm.dll")))

        # a session where OptiScaler hooked the Lite model
        self.run_(self.p.session_started(42))
        touch(os.path.join(self.game, "OptiScaler.log"), b"... ffxProvider_FSR4Lite_Int8 created ...")
        self.assertTrue(self.run_(self.p.session_check(42))["lite"])
        r = self.run_(self.p.session_ended(42, "WINEDLLOVERRIDES=winmm=n,b %command%"))
        self.assertEqual(r["verdict"], "lite")
        self.assertEqual(self.run_(self.p.get_state())["state"]["games"][0]["verdict"], "lite")

        r = self.run_(self.p.disable_game(42, "WINEDLLOVERRIDES=winmm=n,b %command%"))
        self.assertEqual(r["launch_options"], "")
        self.assertEqual(sorted(os.listdir(self.game)), ["game.exe", "nvngx_dlss.dll"])
        self.assertFalse(self.run_(self.p.get_state())["state"]["games"][0]["installed"])

    def test_live_status_on_the_running_game(self):
        self.run_(self.p.session_started(42))
        self.assertEqual(self.run_(self.p.live_status(42))["status"], "off")
        self.run_(self.p.enable_game(42, ""))
        self.assertEqual(self.run_(self.p.live_status(42))["status"], "restart")
        r = self.run_(self.p.session_ended(42, "WINEDLLOVERRIDES=dxgi=n,b %command%"))
        self.assertNotIn("retry", r, "a session the game was set up in is not judged")
        self.assertTrue(os.path.isfile(os.path.join(self.game, "dxgi.dll")))
        self.assertEqual(self.run_(self.p.live_status(42))["status"], "idle")
        self.run_(self.p.session_started(42))
        self.assertEqual(self.run_(self.p.live_status(42))["status"], "starting")
        touch(os.path.join(self.game, "OptiScaler.log"), b"ffxProvider_FSR4Lite_Int8")
        self.assertEqual(self.run_(self.p.live_status(42))["status"], "active")

    def test_anticheat_is_refused(self):
        touch(os.path.join(self.game, "BattlEye", "BEClient_x64.dll"))
        self.run_(self.p.scan_games())
        r = self.run_(self.p.enable_game(42, ""))
        self.assertFalse(r["ok"])
        self.assertIn("BattlEye", r["error"])
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))


if __name__ == "__main__":
    unittest.main()
