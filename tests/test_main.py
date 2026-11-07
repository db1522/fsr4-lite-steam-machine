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
        for task in list(self.p._watchers.values()):
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
        self.run_(self.p.session_started(42))
        touch(os.path.join(self.game, "OptiScaler.log"), b"ffxProvider_FSR4Lite_Int8")
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
        touch(os.path.join(wrong, "OptiScaler.log"), b"CheckQuirks Game's Exe: PBZ.exe\nffxProvider_FSR4Lite_Int8\n")
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
        touch(os.path.join(self.game, "OptiScaler.log"), b"NVSDK_NGX_D3D12_CreateFeature\nRender Resolution: 1280x720, "
                                                         b"Display Resolution 2560x1440\nffxProvider_FSR4Lite_Int8\n")
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
        self.assertEqual(again._game(4115450)["exe_dir"], game_dir)
        self.assertEqual(again.launchers, {"4115450": ["steam/PBZ.exe"]})
        # the report lists every other OptiScaler.log in the folder
        touch(os.path.join(launcher_dir, "OptiScaler.log"), b"the launcher's own log line\n")
        with open(self.run_(self.p.save_report(4115450))["saved"], encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Ruled out as launchers: steam/PBZ.exe", text)
        self.assertIn("-- steam/OptiScaler.log", text)
        self.assertIn("the launcher's own log line", text)

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
        with open(ini, encoding="utf-8") as f:
            self.assertIn("OptiDllPath=", f.read())

    def test_anticheat_is_refused(self):
        touch(os.path.join(self.game, "BattlEye", "BEClient_x64.dll"))
        self.run_(self.p.scan_games())
        r = self.run_(self.p.enable_game(42, ""))
        self.assertFalse(r["ok"])
        self.assertIn("BattlEye", r["error"])
        self.assertFalse(os.path.exists(os.path.join(self.game, "dxgi.dll")))


if __name__ == "__main__":
    unittest.main()
