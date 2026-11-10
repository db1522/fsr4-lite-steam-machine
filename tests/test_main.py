# SPDX-License-Identifier: BSD-3-Clause
"""FSR 4.1 Lite 2.0 backend, end to end on a fake Steam library: scan, install, a session where OptiScaler didn't
load (the next loader name is set up), a session where Lite ran, and an uninstall that leaves the game as it was."""
import asyncio
import os
import time
import unittest
from unittest import mock

import _harness  # noqa: F401
from _tmp import temp_dir, small_fsr4  # noqa: E402
import decky
import main
import sml_assets

# a session where Lite really upscaled: AMD's file loaded and an upscaler was created (sml_opti.lite_ran)
LITE_LOG = (b"Hooked the support check of ffxProvider_FSR4Lite_Int8 in amdxcffx64.dll\namdxcffx64.dll loaded from OptiScaler\nRender Resolution: 1280x720, Display Resolution 2560x1440\n")


def binary(path):
    with open(path, "rb") as f:
        return f.read()


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Flow(unittest.TestCase):
    def setUp(self):
        self.home = temp_dir(self)
        steam = os.path.join(self.home, ".local", "share", "Steam")
        apps = os.path.join(steam, "steamapps")
        touch(os.path.join(apps, "appmanifest_42.acf"),
              b'"AppState"\n{\n"appid" "42"\n"name" "Test Game"\n"installdir" "Test Game"\n}\n')
        touch(os.path.join(steam, "steamapps", "libraryfolders.vdf"), b'"libraryfolders"\n{\n}\n')
        self.game = os.path.join(apps, "common", "Test Game")
        touch(os.path.join(self.game, "game.exe"), b"game" * 50)
        touch(os.path.join(self.game, "nvngx_dlss.dll"))
        self.data = temp_dir(self)
        small = small_fsr4()  # placeholders for AMD's files, 64 bytes each, not 158 MB
        small.start()
        self.addCleanup(small.stop)
        pkg = sml_assets.package_dir(self.data)
        touch(os.path.join(pkg, "OptiScaler.dll"), b"opti")
        touch(os.path.join(pkg, "OptiScaler.ini"), b"[FSR]\r\nFsr4Model=auto\r\n")
        for name, spec in sml_assets.FSR4_FILES.items():
            path = os.path.join(self.data, "fsr4", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.truncate(spec["size"])
        self.settings = temp_dir(self)
        self.patches = [mock.patch.multiple(decky, DECKY_USER_HOME=self.home, DECKY_PLUGIN_SETTINGS_DIR=self.settings,
                                            DECKY_PLUGIN_RUNTIME_DIR=self.data, create=True)]
        for p in self.patches:
            p.start()
        self.loop = asyncio.new_event_loop()
        self.p = main.Plugin()
        self.loop.run_until_complete(self.p._main())
        self.loop.run_until_complete(self.p._scan_task)

    def tearDown(self):
        for task in [*self.p._watchers.values(), self.p._updater, self.p._log_guard]:
            task.cancel()
        self.loop.run_until_complete(asyncio.sleep(0))
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
        touch(os.path.join(self.game, "OptiScaler.log"), LITE_LOG)
        self.assertTrue(self.run_(self.p.session_check(42))["lite"])
        r = self.run_(self.p.session_ended(42, "WINEDLLOVERRIDES=winmm=n,b %command%"))
        self.assertEqual(r["verdict"], "lite")
        self.assertEqual(self.run_(self.p.get_state())["state"]["games"][0]["verdict"], "lite")

        r = self.run_(self.p.disable_game(42, "WINEDLLOVERRIDES=winmm=n,b %command%"))
        self.assertEqual(r["launch_options"], "")
        self.assertEqual(sorted(os.listdir(self.game)), ["game.exe", "nvngx_dlss.dll"])
        self.assertFalse(self.run_(self.p.get_state())["state"]["games"][0]["installed"])

    def test_an_old_manual_optiscaler_is_moved_out_and_then_lite_installs(self):
        touch(os.path.join(self.game, "dxgi.dll"), b"MZ OptiScaler")
        touch(os.path.join(self.game, "OptiScaler.ini"), b"[Upscalers]\n")
        self.run_(self.p.scan_games())
        self.assertFalse(self.run_(self.p.enable_game(42, ""))["ok"])
        r = self.run_(self.p.remove_manual(42))
        self.assertTrue(r["ok"], r)
        self.assertEqual(sorted(r["moved"]), ["OptiScaler.ini", "dxgi.dll"])
        self.assertTrue(r["backup"].startswith(os.path.join(self.data, "old-optiscaler", "42-")))
        self.assertFalse(r["state"]["games"][0]["manual_optiscaler"])
        self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        self.assertFalse(self.run_(self.p.remove_manual(42))["ok"], "never on our own setup")

    def test_a_32_bit_game_is_blocked(self):
        exe = os.path.join(self.game, "game.exe")
        head = bytearray(b"MZ" + b"\0" * 0x7E)
        head[0x3C:0x40] = (0x80).to_bytes(4, "little")
        touch(exe, bytes(head) + b"PE\0\0" + (0x14C).to_bytes(2, "little") + b"\0" * 300)
        self.run_(self.p.scan_games())
        game = self.run_(self.p.get_state())["state"]["games"][0]
        self.assertIn("32-bit", game["broken"])
        r = self.run_(self.p.enable_game(42, ""))
        self.assertFalse(r["ok"])
        self.assertIn("only runs in 64-bit games", r["error"])
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))

    def quick_session(self, log, length=10):
        """A session of `length` seconds whose OptiScaler.log is `log`."""
        self.run_(self.p.session_started(42))
        self.p.sessions[42] = time.time() - length
        self.p.registry["42"]["installed_at"] = time.time() - 3600  # set up before this session
        touch(os.path.join(self.game, "OptiScaler.log"), log)
        return self.run_(self.p.session_ended(42, "WINEDLLOVERRIDES=dxgi=n,b %command%"))

    def test_a_game_that_closes_at_launch_twice_is_turned_off(self):
        self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        r = self.quick_session(b"[I] Init done\n")
        self.assertNotIn("turned_off", r)  # once could be the player quitting
        self.assertTrue(os.path.isfile(os.path.join(self.game, "dxgi.dll")))
        r = self.quick_session(b"[I] Init done\n")
        self.assertTrue(r["turned_off"])
        self.assertEqual(r["launch_options"], "")
        self.assertIn("closed right after starting 2 times in a row", r["detail"])
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))
        game = self.run_(self.p.get_state())["state"]["games"][0]
        self.assertFalse(game["installed"])
        self.assertIn("Turn it back on to try again", game["turned_off"])
        self.assertFalse(self.run_(self.p.session_started(42))["managed"])
        self.p.sessions.pop(42, None)
        # turned back on: the note is gone and the count starts over
        self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        game = self.run_(self.p.get_state())["state"]["games"][0]
        self.assertTrue(game["installed"])
        self.assertEqual(game["turned_off"], "")
        self.assertNotIn("turned_off", self.quick_session(b"[I] Init done\n"))

    def test_quick_exits_must_be_in_a_row_and_lite_or_no_optiscaler_never_counts(self):
        self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        self.quick_session(b"[I] Init done\n")
        self.quick_session(b"[I] Init done\n", length=600)  # a real session in between
        self.assertNotIn("turned_off", self.quick_session(b"[I] Init done\n"))
        self.assertNotIn("turned_off", self.quick_session(LITE_LOG))  # Lite ran: the player quit
        self.assertNotIn("turned_off", self.quick_session(b"[I] Init done\n"))
        self.assertTrue(os.path.isfile(os.path.join(self.game, "dxgi.dll")))

    def test_the_card_shows_no_resolution_that_could_be_old(self):
        # OptiScaler logs the resolution only when the game builds its upscaler; The Witcher 3 changes FSR quality
        # without that, so the card would show an old mode. The FPS overlay shows it live.
        self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        self.p.registry["42"]["installed_at"] = time.time() - 3600
        self.run_(self.p.session_started(42))
        touch(os.path.join(self.game, "OptiScaler.log"), LITE_LOG)
        self.assertEqual(self.run_(self.p.live_status(42))["detail"], "FSR 4.1 Lite is running.")
        self.p.sessions[42] = time.time() - 600
        self.assertEqual(self.run_(self.p.session_ended(42, ""))["verdict"], "lite")
        self.assertNotIn("summary", self.run_(self.p.get_state())["state"]["games"][0])

    def test_a_new_optiscaler_nightly_goes_into_games_that_are_not_running(self):
        r = self.run_(self.p.enable_game(42, ""))
        self.assertTrue(r["ok"], r)
        old = sml_assets.current(self.data)
        with mock.patch("sml_assets.update_optiscaler", return_value=(old, False)):
            self.assertEqual(self.run_(self.p.check_optiscaler())["message"],
                             "Up to date: OptiScaler v10.0.0-pre1 (Oct 24, 2026).")
        with open(os.path.join(self.game, "OptiScaler.ini"), encoding="utf-8") as f:
            ini = f.read()
        # a newer nightly arrives
        new = "OptiScaler_v10.0.0-pre2_20261120"
        touch(os.path.join(self.data, "optiscaler", new, "OptiScaler.dll"), b"new build")
        touch(os.path.join(self.data, "optiscaler", new, "OptiScaler.ini"), b"[FSR]\nFsr4Model=auto\n")
        touch(os.path.join(self.data, "optiscaler", new, "D3D12_Optiscaler", "D3D12Core.dll"), b"new file")
        touch(os.path.join(self.data, "optiscaler", "latest.txt"), new.encode())
        emitted = lambda: [e for e in decky.emitted if e[0] == "games_updated"]  # noqa: E731
        before = len(emitted())
        with mock.patch("sml_assets.update_optiscaler", return_value=(new, True)):
            # while the game runs it waits
            self.p.sessions[42] = time.time()
            r = self.run_(self.p.check_optiscaler())
            self.assertEqual(r["message"], "1 running game updates once it's closed.")
            self.assertEqual(binary(os.path.join(self.game, "dxgi.dll")), b"opti")
            # closed: it gets the new build under its loader name, its own settings kept, one notification
            del self.p.sessions[42]
            r = self.run_(self.p.check_optiscaler())
            self.assertEqual(r["message"], "Updated 1 game.")
            self.assertEqual(binary(os.path.join(self.game, "dxgi.dll")), b"new build")
            self.assertTrue(os.path.isfile(os.path.join(self.game, "D3D12_Optiscaler", "D3D12Core.dll")))
            with open(os.path.join(self.game, "OptiScaler.ini"), encoding="utf-8") as f:
                self.assertEqual(f.read(), ini)
            self.assertEqual(len(emitted()), before + 1)
            self.assertIn("1 game now uses OptiScaler v10.0.0-pre2 (Nov 20, 2026)", emitted()[-1][2])
            self.run_(self.p.check_optiscaler())
            self.assertEqual(len(emitted()), before + 1, "one notification per build")
        self.assertEqual(self.run_(self.p.diagnose(42))["report"]["opti_build"],
                         "OptiScaler v10.0.0-pre2 (Nov 20, 2026)")
        # uninstalling still leaves the game as it was
        self.run_(self.p.disable_game(42, "WINEDLLOVERRIDES=dxgi=n,b %command%"))
        self.assertEqual(sorted(os.listdir(self.game)), ["game.exe", "nvngx_dlss.dll"])

    def test_a_non_steam_shortcut_running_under_its_games_steam_id_is_found_by_its_exe(self):
        # God of War added as a non-Steam game: Steam runs it as app 1593500 (its steam_appid.txt), not the shortcut
        exe = os.path.join(self.home, "Games", "God Of War", "GoW.exe")
        touch(exe, b"game" * 50)
        touch(os.path.join(os.path.dirname(exe), "nvngx_dlss.dll"))
        self.p.games.append({"appid": 2725409646, "name": "GoW.exe", "install_dir": os.path.dirname(exe),
                             "nonsteam": True, "launch_exe": exe, "exe_dir": os.path.dirname(exe),
                             "exe_name": "GoW.exe", "upscalers": ["DLSS"], "anticheat": "",
                             "manual_optiscaler": False, "unreal": False})
        with mock.patch("sml_opti.exe_running", side_effect=lambda path: path == exe):
            self.assertEqual(self.run_(self.p.resolve_running(1593500))["appid"], 2725409646)
            self.assertEqual(self.run_(self.p.session_started(1593500))["appid"], 2725409646)
        self.assertIn(2725409646, self.p.sessions)
        with mock.patch("sml_opti.exe_running", return_value=False):  # the exe has quit by the time the session ends
            self.run_(self.p.session_ended(1593500, ""))
        self.assertNotIn(2725409646, self.p.sessions)
        self.assertEqual(self.run_(self.p.resolve_running(42))["appid"], 42)  # a game the scan knows is itself

    def test_files_a_game_update_removed_are_put_back_with_one_notification(self):
        self.run_(self.p.enable_game(42, ""))
        dxgi = os.path.join(self.game, "dxgi.dll")
        amd = os.path.join(self.game, "OptiScaler", "amdxcffx64.dll")
        os.remove(dxgi)
        os.remove(amd)
        told = lambda: [e for e in decky.emitted if e[0] == "game_repaired"]  # noqa: E731
        before = len(told())
        self.run_(self.p._repair_games())
        self.assertEqual(binary(dxgi), b"opti")
        self.assertTrue(os.path.isfile(amd))
        self.assertEqual(len(told()), before + 1)
        self.assertEqual(told()[-1][1], "FSR 4.1 Lite set up again in Test Game")
        self.assertIn("next session", told()[-1][2])
        self.run_(self.p._repair_games())  # nothing missing: no second notification
        self.assertEqual(len(told()), before + 1)

    def test_a_game_file_steam_put_back_over_the_loader_is_replaced_at_game_start(self):
        self.run_(self.p.enable_game(42, ""))
        dxgi = os.path.join(self.game, "dxgi.dll")
        touch(dxgi, b"the game's own dxgi.dll from Steam's file check")
        self.run_(self.p.session_started(42))
        self.assertEqual(binary(dxgi), b"opti")
        self.assertIn("restart the game", [e for e in decky.emitted if e[0] == "game_repaired"][-1][2])

    def test_a_running_game_is_left_alone_by_the_repair_check(self):
        self.run_(self.p.enable_game(42, ""))
        os.remove(os.path.join(self.game, "dxgi.dll"))
        self.p.sessions[42] = time.time()
        self.run_(self.p._repair_games())
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))

    def test_two_checks_at_once_run_one_after_the_other(self):
        # the 5-minute check and Check now landing together: the second used to lose its download folder
        import threading
        running, overlapped = [0], []
        lock = threading.Lock()
        old = sml_assets.current(self.data)

        def slow_update(*a, **k):
            with lock:
                running[0] += 1
                overlapped.append(running[0] > 1)
            time.sleep(0.2)
            with lock:
                running[0] -= 1
            return old, False

        async def both():
            return await asyncio.gather(self.p.check_optiscaler(), self.p._check_builds(force=False))
        with mock.patch("sml_assets.update_optiscaler", side_effect=slow_update):
            first, _ = self.run_(both())
        self.assertEqual(overlapped, [False, False])
        self.assertTrue(first["ok"])
        self.assertEqual(first["state"]["opti_note"], "")

    def test_a_new_plugin_release_is_looked_for_hourly_and_told_once(self):
        told = lambda: [e for e in decky.emitted if e[0] == "plugin_update"]  # noqa: E731
        before = len(told())
        newer = {"ok": True, "update_available": True, "latest_version": "9.9.9"}
        with mock.patch.object(self.p.updates, "check", return_value=newer) as check:
            self.run_(self.p._check_release(now=1000))
            self.assertEqual(len(told()), before + 1)
            self.assertEqual(told()[-1][1], "FSR 4.1 Lite 9.9.9 is out")
            self.run_(self.p._check_release(now=1000 + 1800))  # within the hour: GitHub isn't asked
            self.assertEqual(check.call_count, 1)
            self.run_(self.p._check_release(now=1000 + 3600))  # asked again, same version: no second notice
            self.assertEqual(check.call_count, 2)
            self.assertEqual(len(told()), before + 1)
        with mock.patch.object(self.p.updates, "check", return_value={"ok": True, "update_available": False}):
            self.run_(self.p._check_release(now=1000 + 14 * 3600))
        self.assertEqual(len(told()), before + 1)

    def test_with_automatic_updates_off_games_keep_their_build(self):
        self.run_(self.p.enable_game(42, ""))
        self.run_(self.p.set_setting("auto_update", False))
        new = "OptiScaler_v10.0.0-pre2_20261120"
        touch(os.path.join(self.data, "optiscaler", new, "OptiScaler.dll"), b"new build")
        touch(os.path.join(self.data, "optiscaler", "latest.txt"), new.encode())
        with mock.patch("sml_assets.update_optiscaler", return_value=(new, True)):
            self.run_(self.p.check_optiscaler())
        self.assertEqual(binary(os.path.join(self.game, "dxgi.dll")), b"opti")

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
        touch(os.path.join(self.game, "OptiScaler.log"), LITE_LOG)
        self.assertEqual(self.run_(self.p.live_status(42))["status"], "active")

    def test_a_game_without_upscaler_files_can_still_be_set_up(self):
        # like the widget: many games build FSR in, so OptiScaler is told to search the exe for it
        os.remove(os.path.join(self.game, "nvngx_dlss.dll"))
        self.run_(self.p.scan_games())
        g = self.run_(self.p.get_state())["state"]["games"][0]
        self.assertEqual(g["upscalers"], [])
        self.assertIn("No upscaler files found", g["tip"])
        r = self.run_(self.p.enable_game(42, ""))
        self.assertTrue(r["ok"], r)
        with open(os.path.join(self.game, "OptiScaler.ini"), encoding="utf-8") as f:
            self.assertIn("Fsr2Pattern=true", f.read())

    def test_the_loader_that_worked_is_used_when_set_up_again(self):
        self.run_(self.p.enable_game(42, ""))
        self.p.registry["42"]["proxy"] = "version.dll"  # as if OptiScaler had moved to version.dll
        os.rename(os.path.join(self.game, "dxgi.dll"), os.path.join(self.game, "version.dll"))
        with mock.patch("sml_opti.repair", return_value=[]):  # the rename above is a stand-in, not a game update
            self.run_(self.p.session_started(42))
        touch(os.path.join(self.game, "OptiScaler.log"), LITE_LOG)
        self.run_(self.p.session_ended(42, "WINEDLLOVERRIDES=version=n,b %command%"))
        self.assertEqual(self.p.loaders, {"game.exe": "version.dll"})
        self.assertTrue(os.path.isfile(os.path.join(self.settings, "loaders.json")))
        os.rename(os.path.join(self.game, "version.dll"), os.path.join(self.game, "dxgi.dll"))
        self.p.registry["42"]["proxy"] = "dxgi.dll"
        self.run_(self.p.disable_game(42, "WINEDLLOVERRIDES=dxgi=n,b %command%"))
        r = self.run_(self.p.enable_game(42, ""))
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=version=n,b %command%")

    def test_an_re_engine_game_gets_reframework_and_its_launch_option(self):
        apps = os.path.join(self.home, ".local", "share", "Steam", "steamapps")
        touch(os.path.join(apps, "appmanifest_2246340.acf"),
              b'"AppState"\n{\n"appid" "2246340"\n"name" "Monster Hunter Wilds"\n"installdir" "MHWilds"\n}\n')
        mhw = os.path.join(apps, "common", "MHWilds")
        touch(os.path.join(mhw, "MonsterHunterWilds.exe"), b"game" * 50)
        touch(os.path.join(mhw, "amd_fidelityfx_dx12.dll"))
        ref = os.path.join(self.data, "ref", "dinput8.dll")
        touch(ref, b"reframework")
        self.run_(self.p.scan_games())
        with mock.patch("sml_assets.fetch_reframework", return_value=ref) as fetch:
            r = self.run_(self.p.enable_game(2246340, ""))
        self.assertTrue(r["ok"], r)
        fetch.assert_called_once()
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b;dinput8=n,b %command%")
        self.assertTrue(os.path.isfile(os.path.join(mhw, "dinput8.dll")))
        r = self.run_(self.p.disable_game(2246340, "WINEDLLOVERRIDES=dxgi=n,b;dinput8=n,b %command%"))
        self.assertEqual(r["launch_options"], "")
        self.assertEqual(sorted(os.listdir(mhw)), ["MonsterHunterWilds.exe", "amd_fidelityfx_dx12.dll"])

    def test_a_game_the_list_marks_gets_optipatcher_and_loses_it_at_uninstall(self):
        apps = os.path.join(self.home, ".local", "share", "Steam", "steamapps")
        touch(os.path.join(apps, "appmanifest_782330.acf"),
              b'"AppState"\n{\n"appid" "782330"\n"name" "DOOM Eternal"\n"installdir" "DOOMEternal"\n}\n')
        doom = os.path.join(apps, "common", "DOOMEternal")
        touch(os.path.join(doom, "DOOMEternalx64vk.exe"), b"game" * 50)
        touch(os.path.join(doom, "nvngx_dlss.dll"))
        asi = os.path.join(self.data, "op", "OptiPatcher.asi")
        touch(asi, b"MZ patcher")
        self.run_(self.p.scan_games())
        with mock.patch("sml_assets.fetch_optipatcher", return_value=asi) as fetch:
            r = self.run_(self.p.enable_game(782330, ""))
        self.assertTrue(r["ok"], r)
        fetch.assert_called_once()
        self.assertTrue(os.path.isfile(os.path.join(doom, "OptiScaler", "plugins", "OptiPatcher.asi")))
        with open(os.path.join(doom, "OptiScaler.ini"), encoding="utf-8") as f:
            self.assertIn("LoadAsiPlugins=true", f.read())
        self.run_(self.p.disable_game(782330, r["launch_options"]))
        self.assertEqual(sorted(os.listdir(doom)), ["DOOMEternalx64vk.exe", "nvngx_dlss.dll"])

    def test_a_game_set_up_before_gets_optipatcher_with_the_next_update(self):
        apps = os.path.join(self.home, ".local", "share", "Steam", "steamapps")
        touch(os.path.join(apps, "appmanifest_782330.acf"),
              b'"AppState"\n{\n"appid" "782330"\n"name" "DOOM Eternal"\n"installdir" "DOOMEternal"\n}\n')
        doom = os.path.join(apps, "common", "DOOMEternal")
        touch(os.path.join(doom, "DOOMEternalx64vk.exe"), b"game" * 50)
        asi = os.path.join(self.data, "op", "OptiPatcher.asi")
        touch(asi, b"MZ patcher")
        self.run_(self.p.scan_games())
        with mock.patch("sml_assets.fetch_optipatcher", side_effect=OSError("offline")):
            self.assertTrue(self.run_(self.p.enable_game(782330, ""))["ok"], "set up even when it can't download")
        self.assertFalse(os.path.exists(os.path.join(doom, "OptiScaler", "plugins")))
        with mock.patch("sml_assets.fetch_optipatcher", return_value=asi), \
                mock.patch("sml_opti.running_processes", return_value=[]):
            self.run_(self.p._update_games())
        self.assertTrue(os.path.isfile(os.path.join(doom, "OptiScaler", "plugins", "OptiPatcher.asi")))

    def test_a_2225_optipatcher_is_moved_by_the_update_even_while_the_game_runs(self):
        import sml_opti
        game_exe = os.path.join(self.game, "game.exe")
        self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        m = sml_opti.load_manifest(self.game)
        asi = os.path.join(self.data, "op", "OptiPatcher.asi")
        touch(asi, b"MZ patcher")
        sml_opti._place(self.game, os.path.join(self.game, sml_opti.META), m, asi, os.path.join("plugins", "OptiPatcher.asi"))
        m["optipatcher"] = "v0.42"
        sml_opti._save(os.path.join(self.game, sml_opti.META), m)
        with mock.patch("sml_opti.running_processes", return_value=[(game_exe, 900, True)]):
            self.run_(self.p._update_games())
        self.assertTrue(os.path.isfile(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi")))
        self.assertFalse(os.path.exists(os.path.join(self.game, "plugins")))

    def test_other_games_never_download_reframework(self):
        with mock.patch("sml_assets.fetch_reframework") as fetch:
            self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        fetch.assert_not_called()

    def pbz(self):
        apps = os.path.join(self.home, ".local", "share", "Steam", "steamapps")
        touch(os.path.join(apps, "appmanifest_4115450.acf"),
              b'"AppState"\n{\n"appid" "4115450"\n"name" "Phantom Blade Zero"\n"installdir" "PBZ"\n}\n')
        root = os.path.join(apps, "common", "PBZ")
        touch(os.path.join(root, "platform", "steam", "PBZ.exe"), b"game" * 1000)
        touch(os.path.join(root, "ProjectPBZ", "Binaries", "Win64", "8za_v2.exe"), b"tool" * 2000)
        touch(os.path.join(root, "ProjectPBZ", "Plugins", "FSR", "Source", "signedbin", "amd_fidelityfx_dx12.dll"))
        self.run_(self.p.scan_games())
        return root

    def test_a_setup_next_to_the_wrong_exe_moves_to_the_one_the_game_runs(self):
        root = self.pbz()
        wrong, real = (os.path.join(root, "ProjectPBZ", "Binaries", "Win64"), os.path.join(root, "platform", "steam"))
        self.assertEqual(self.p._game(4115450)["exe_dir"], wrong)  # the folder guess
        r = self.run_(self.p.enable_game(4115450, ""))
        self.assertTrue(os.path.isfile(os.path.join(wrong, "dxgi.dll")))
        # OptiScaler loaded from there, but the game runs PBZ.exe and found no FSR 4 file next to it
        self.run_(self.p.session_started(4115450))
        touch(os.path.join(wrong, "OptiScaler.log"), b"CheckQuirks Game's Exe: PBZ.exe\n"
                                                     b"LoadDriverDll Failed to load amdxcffx64.dll\n")
        r = self.run_(self.p.session_ended(4115450, r["launch_options"]))
        self.assertEqual(r["retry"], "dxgi.dll")
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b %command%")
        self.assertIn("PBZ.exe", r["detail"])
        self.assertTrue(os.path.isfile(os.path.join(real, "dxgi.dll")))
        self.assertTrue(os.path.isfile(os.path.join(real, "OptiScaler", "amdxcffx64.dll")))
        self.assertEqual(sorted(os.listdir(wrong)), ["8za_v2.exe"])
        self.assertEqual(self.p.exes, {"4115450": "platform/steam/PBZ.exe"})
        self.run_(self.p.scan_games())  # remembered across scans
        self.assertEqual(self.p._game(4115450)["exe_dir"], real)

    def test_the_running_game_not_its_launcher_is_used_for_a_first_setup(self):
        root = self.pbz()
        launcher = os.path.join(root, "steam", "PBZ.exe")
        real = os.path.join(root, "ProjectPBZ", "Binaries", "Win64", "PBZ.exe")
        touch(launcher, b"launcher")
        touch(real, b"game")
        # the launcher runs first (graphics loaded, little memory), then the game takes over
        def p(path, mb):
            return [{"path": path, "mb": mb, "graphics": True}]
        seen = iter([p(launcher, 180), p(launcher, 190), p(real, 2400), p(real, 5400)] + [[]] * 30)
        with mock.patch("sml_opti.running_processes", side_effect=lambda *a: next(seen)), \
                mock.patch("asyncio.sleep", return_value=None):
            self.run_(self.p.session_started(4115450))
            self.run_(self.p._watchers[4115450])
        self.assertEqual(self.p._game(4115450)["exe_dir"], os.path.dirname(real))
        self.assertEqual(self.p.exes, {"4115450": "ProjectPBZ/Binaries/Win64/PBZ.exe"})
        self.assertTrue(self.run_(self.p.enable_game(4115450, ""))["ok"])
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(real), "dxgi.dll")))
        self.assertFalse(os.path.exists(os.path.join(root, "steam", "dxgi.dll")))

    def test_fsr4_files_go_where_optiscaler_looks_for_them(self):
        # Phantom Blade Zero as it is: PBZ.exe next to 8za_v2.exe, but Steam starts it in platform/steam, where
        # OptiScaler (loaded fine from Binaries/Win64) looks for AMD's FSR 4 file
        root = self.pbz()
        win64, steam = os.path.join(root, "ProjectPBZ", "Binaries", "Win64"), os.path.join(root, "platform", "steam")
        os.remove(os.path.join(steam, "PBZ.exe"))
        touch(os.path.join(win64, "PBZ.exe"), b"game" * 3000)
        self.run_(self.p.scan_games())
        r = self.run_(self.p.enable_game(4115450, ""))
        self.assertEqual(self.p._game(4115450)["exe_dir"], win64)
        self.run_(self.p.session_started(4115450))
        touch(os.path.join(win64, "OptiScaler.log"),
              b"Setting DllPath to S:\\steamapps\\common\\PBZ\\platform\\steam\nCheckQuirks Game's Exe: PBZ.exe\n"
              b"LoadDriverDll Failed to load amdxcffx64.dll\nRender Resolution: 1280x720, Display Resolution 3840x2160\n")
        r = self.run_(self.p.session_ended(4115450, r["launch_options"]))
        self.assertEqual((r["verdict"], r["retry"]), ("unplayed", "dxgi.dll"))
        self.assertIn("platform/steam", r["detail"])
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b %command%")
        for name in ("amdxcffx64.dll", "amdvkffx64.dll"):
            self.assertTrue(os.path.isfile(os.path.join(steam, "OptiScaler", name)))
        self.assertTrue(os.path.isfile(os.path.join(win64, "dxgi.dll")))  # the setup itself stays put
        self.run_(self.p.disable_game(4115450, r["launch_options"]))
        self.assertEqual(os.listdir(steam), [])

    def test_a_working_setup_never_moves(self):
        self.pbz()
        self.run_(self.p.enable_game(4115450, ""))
        wrong = self.p._game(4115450)["exe_dir"]
        self.run_(self.p.session_started(4115450))
        touch(os.path.join(wrong, "OptiScaler.log"), b"CheckQuirks Game's Exe: PBZ.exe\n" + LITE_LOG)
        r = self.run_(self.p.session_ended(4115450, "WINEDLLOVERRIDES=dxgi=n,b %command%"))
        self.assertEqual(r["verdict"], "lite")
        self.assertNotIn("retry", r)

    def test_session_check_says_what_runs_and_why_not_yet(self):
        self.run_(self.p.enable_game(42, ""))
        self.run_(self.p.session_started(42))
        self.p.registry["42"]["installed_at"] = time.time() - 600  # set up before this session
        self.p.sessions[42] = time.time() - 200  # 3 min 20 s into the session
        touch(os.path.join(self.game, "OptiScaler.log"), b"OptiScaler loaded\n")
        r = self.run_(self.p.session_check(42))
        self.assertFalse(r["lite"])
        self.assertIn("Pick an upscaler", r["hint"])
        touch(os.path.join(self.game, "OptiScaler.log"), b"NVSDK_NGX_D3D12_CreateFeature\n" + LITE_LOG)
        r = self.run_(self.p.session_check(42))
        self.assertEqual((r["lite"], r["minutes"]), (True, 3))
        self.assertEqual(r["summary"], "DLSS → FSR 4.1.2 Lite, 1280×720 → 2560×1440 (Performance)")

    def test_a_setup_in_a_launcher_moves_to_the_game_and_the_report_shows_why(self):
        # 2.2.9 as reported: 2.2.8 remembered the launcher steam/PBZ.exe, so the setup sits there; OptiScaler loads in
        # it and its log ends after start-up: no device, no swapchain, no upscaler
        root = self.pbz()
        launcher_dir, game_dir = os.path.join(root, "steam"), os.path.join(root, "ProjectPBZ", "Binaries", "Win64")
        touch(os.path.join(launcher_dir, "PBZ.exe"), b"launcher")
        touch(os.path.join(game_dir, "PBZ.exe"), b"game" * 3000)
        self.p.exes = {"4115450": "steam/PBZ.exe"}
        self.run_(self.p.scan_games())
        self.assertEqual(self.p._game(4115450)["exe_dir"], launcher_dir)
        r = self.run_(self.p.enable_game(4115450, ""))
        self.p.registry["4115450"]["installed_at"] = time.time() - 600
        self.run_(self.p.session_started(4115450))
        self.p.sessions[4115450] = time.time() - 120
        touch(os.path.join(launcher_dir, "OptiScaler.log"),
              b"CheckQuirks Game's Exe: PBZ.exe\nCheckQuirks Game Version: 1.0.0.0\nInit done\n"
              b"VulkanSpoofing::hkvkCreateInstance Skipping because DXVK/VKD3D is creating a D3D device\n"
              b"Amdxc64Hooks::Init amdxc64.dll loaded\n")
        self.p.seen[4115450] = [{"path": os.path.join(launcher_dir, "PBZ.exe"), "mb": 180, "graphics": True}]
        report_before = self.run_(self.p.save_report(4115450))
        with open(report_before["saved"], encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Seen running and remembered: steam/PBZ.exe", text)
        self.assertIn("steam/PBZ.exe: 180 MB, graphics loaded", text)
        r = self.run_(self.p.session_ended(4115450, r["launch_options"]))
        self.assertEqual(r["retry"], self.p.registry["4115450"]["proxy"])
        self.assertTrue(os.path.isfile(os.path.join(game_dir, "OptiScaler.ini")))
        self.assertFalse(os.path.exists(os.path.join(launcher_dir, "OptiScaler.ini")))
        self.assertEqual(self.p.launchers, {"4115450": ["steam/PBZ.exe"]})
        self.assertEqual(self.p.exes, {"4115450": "ProjectPBZ/Binaries/Win64/PBZ.exe"})
        # the launcher is never picked again, even when seen running with lots of memory
        self.run_(self.p._use_exe(4115450, os.path.join(launcher_dir, "PBZ.exe")))
        self.assertEqual(self.p._game(4115450)["exe_dir"], game_dir)
        # and after a reload it stays ruled out
        again = main.Plugin()
        self.run_(again._main())
        self.run_(again._scan_task)
        again._updater.cancel()
        self.assertEqual(again._game(4115450)["exe_dir"], game_dir)
        self.assertEqual(again.launchers, {"4115450": ["steam/PBZ.exe"]})
        # the report lists every other OptiScaler.log in the folder
        touch(os.path.join(launcher_dir, "OptiScaler.log"), b"the launcher's own log line\n")
        with open(self.run_(self.p.save_report(4115450))["saved"], encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Ruled out as launchers: steam/PBZ.exe", text)
        self.assertIn("== Windows programs running ==", text)
        self.assertIn("== Every .exe in the game folder ==", text)
        self.assertIn("  steam/PBZ.exe (", text)
        self.assertIn("-- steam/OptiScaler.log", text)
        self.assertIn("the launcher's own log line", text)

    def test_installing_while_playing_uses_the_game_on_screen_like_the_widget(self):
        root = self.pbz()
        launcher_dir, game_dir = os.path.join(root, "steam"), os.path.join(root, "ProjectPBZ", "Binaries", "Win64")
        touch(os.path.join(launcher_dir, "PBZ.exe"), b"launcher")
        touch(os.path.join(game_dir, "PBZ.exe"), b"game")
        self.run_(self.p.scan_games())
        self.run_(self.p.session_started(4115450))

        def running(*procs):
            return mock.patch("sml_opti.running_processes", return_value=[
                {"path": p, "mb": mb, "graphics": True} for p, mb in procs])
        # only the launcher so far: wait, nothing installed
        with running((os.path.join(launcher_dir, "PBZ.exe"), 180)):
            r = self.run_(self.p.enable_game(4115450, ""))
        self.assertFalse(r["ok"])
        self.assertIn("still starting", r["error"])
        self.assertNotIn("4115450", self.p.registry)
        # the game is up: installed next to its exe straight away
        with running((os.path.join(launcher_dir, "PBZ.exe"), 180), (os.path.join(game_dir, "PBZ.exe"), 5200)):
            r = self.run_(self.p.enable_game(4115450, ""))
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.p.registry["4115450"]["exe_dir"], game_dir)
        self.assertTrue(os.path.isfile(os.path.join(game_dir, "dxgi.dll")))

    def test_a_small_game_still_installs_after_starting(self):
        root = self.pbz()
        small = os.path.join(root, "platform", "steam", "PBZ.exe")
        self.run_(self.p.session_started(4115450))
        self.p.sessions[4115450] = time.time() - 300
        with mock.patch("sml_opti.running_processes", return_value=[{"path": small, "mb": 300, "graphics": True}]):
            self.assertTrue(self.run_(self.p.enable_game(4115450, ""))["ok"])
        self.assertEqual(self.p.registry["4115450"]["exe_dir"], os.path.dirname(small))

    def test_processes_without_graphics_never_block_an_install(self):
        # graphics couldn't be read for anything running: no "still starting", the folder guess installs right away
        root = self.pbz()
        self.run_(self.p.session_started(4115450))
        tool = os.path.join(root, "ProjectPBZ", "Binaries", "Win64", "8za_v2.exe")
        with mock.patch("sml_opti.running_processes", return_value=[{"path": tool, "mb": 5000, "graphics": False}]):
            r = self.run_(self.p.enable_game(4115450, ""))
        self.assertTrue(r["ok"], r)

    def test_nothing_seen_running_falls_back_to_the_folder_guess(self):
        self.run_(self.p.session_started(42))
        with mock.patch("sml_opti.running_processes", return_value=[]):
            self.assertTrue(self.run_(self.p.enable_game(42, ""))["ok"])
        self.assertEqual(self.p.registry["42"]["exe_dir"], self.game)

    def test_a_short_session_never_marks_a_launcher(self):
        root = self.pbz()
        self.run_(self.p.enable_game(4115450, ""))
        exe_dir = self.p._game(4115450)["exe_dir"]
        self.p.registry["4115450"]["installed_at"] = time.time() - 600
        self.run_(self.p.session_started(4115450))
        self.p.sessions[4115450] = time.time() - 20  # quit at the menu
        touch(os.path.join(exe_dir, "OptiScaler.log"), b"Init done\n")
        self.run_(self.p.session_ended(4115450, "WINEDLLOVERRIDES=dxgi=n,b %command%"))
        self.assertEqual(self.p.launchers, {})
        self.assertEqual(self.p._game(4115450)["exe_dir"], exe_dir)

    def test_games_set_up_by_an_older_version_get_the_pinned_folder_at_load(self):
        self.run_(self.p.enable_game(42, ""))
        ini = os.path.join(self.game, "OptiScaler.ini")
        with open(ini, encoding="utf-8") as f:
            old = "".join(line for line in f if not line.startswith("OptiDllPath="))
        with open(ini, "w", encoding="utf-8") as f:
            f.write(old)
        again = main.Plugin()
        self.run_(again._main())
        self.run_(again._scan_task)
        again._updater.cancel()
        with open(ini, encoding="utf-8") as f:
            self.assertIn("OptiDllPath=", f.read())

    def test_anticheat_is_refused(self):
        touch(os.path.join(self.game, "BattlEye", "BEClient_x64.dll"))
        self.run_(self.p.scan_games())
        r = self.run_(self.p.enable_game(42, ""))
        self.assertFalse(r["ok"])
        self.assertIn("BattlEye", r["error"])
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))

    def test_a_game_that_closes_with_optiscaler_on_steamos_is_refused(self):
        os.rename(os.path.join(self.game, "game.exe"), os.path.join(self.game, "DOA6LR.exe"))
        self.run_(self.p.scan_games())
        state = self.run_(self.p.get_state())["state"]
        game = next(g for g in state["games"] if g["appid"] == 42)
        self.assertIn("closes itself", game["broken"])
        r = self.run_(self.p.enable_game(42, ""))
        self.assertFalse(r["ok"])
        self.assertIn("closes itself", r["error"])
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))


if __name__ == "__main__":
    unittest.main()
