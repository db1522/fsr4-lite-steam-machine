# SPDX-License-Identifier: BSD-3-Clause
"""FSR 4.1 Lite's OptiScaler method (sml_opti): game analysis, install and exact uninstall, settings, launch options,
and reading a session from OptiScaler.log."""
import os
import tempfile
import unittest

import sml_opti as O


def read(path, mode="r", **kw):
    with open(path, mode, **kw) as f:
        return f.read()


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Analyze(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_unreal_puts_optiscaler_next_to_the_shipping_exe(self):
        touch(os.path.join(self.root, "Game.exe"), b"launcher")
        win64 = os.path.join(self.root, "Game", "Binaries", "Win64")
        touch(os.path.join(win64, "Game-Win64-Shipping.exe"), b"real game" * 100)
        touch(os.path.join(self.root, "Engine", "Plugins", "FSR", "amd_fidelityfx_dx12.dll"))
        touch(os.path.join(win64, "nvngx_dlss.dll"))
        touch(os.path.join(self.root, "Engine", "Binaries", "Win64", "CrashReportClient.exe"))
        a = O.analyze(self.root)
        self.assertEqual(a["exe_dir"], win64)
        self.assertTrue(a["unreal"])
        self.assertEqual(a["upscalers"], ["DLSS", "FSR 3.1"])
        self.assertEqual(a["anticheat"], "")

    def test_anticheat_is_found(self):
        touch(os.path.join(self.root, "game.exe"))
        touch(os.path.join(self.root, "EasyAntiCheat", "EasyAntiCheat_x64.dll"))
        self.assertEqual(O.analyze(self.root)["anticheat"], "Easy Anti-Cheat")

    def test_anticheat_outside_the_game_folder_is_found_by_the_exe(self):
        touch(os.path.join(self.root, "Overwatch.exe"))
        self.assertEqual(O.analyze(self.root)["anticheat"], "Blizzard anti-cheat")
        self.assertIn("installs are blocked", O.blocked_message("Blizzard anti-cheat"))

    def test_a_folder_without_an_exe_is_not_a_game(self):
        touch(os.path.join(self.root, "readme.txt"))
        self.assertIsNone(O.analyze(self.root))


class Install(unittest.TestCase):
    def setUp(self):
        t = tempfile.mkdtemp()
        self.pkg, self.game = os.path.join(t, "pkg"), os.path.join(t, "game")
        touch(os.path.join(self.pkg, "OptiScaler.dll"), b"opti")
        touch(os.path.join(self.pkg, "OptiScaler.ini"), b"[Upscalers]\r\nDx12Upscaler=auto\r\n\r\n[FSR]\r\nFsr4Model=auto\r\n")
        touch(os.path.join(self.pkg, "OptiScaler", "amd_fidelityfx_upscaler_dx12.dll"), b"sdk")
        touch(os.path.join(self.pkg, "setup_linux.sh"), b"script")
        touch(os.path.join(self.pkg, "!! README_EXTRACT ALL FILES TO GAME FOLDER !!.txt"), b"readme")
        self.fsr4 = [os.path.join(t, "amdxcffx64.dll"), os.path.join(t, "amdvkffx64.dll")]
        for p in self.fsr4:
            touch(p, b"amd")
        touch(os.path.join(self.game, "game.exe"), b"game")
        touch(os.path.join(self.game, "winmm.dll"), b"the game's own winmm")

    def test_install_then_uninstall_leaves_the_folder_as_it_was(self):
        before = sorted(os.listdir(self.game))
        m = O.install(self.game, "game.exe", self.pkg, self.fsr4, {"watermark": False, "overlay": False})
        self.assertEqual(m["proxy"], "dxgi.dll")
        self.assertTrue(os.path.isfile(os.path.join(self.game, "dxgi.dll")))
        self.assertTrue(os.path.isfile(os.path.join(self.game, "OptiScaler", "amdxcffx64.dll")))
        self.assertFalse(os.path.exists(os.path.join(self.game, "setup_linux.sh")))
        ini = read(os.path.join(self.game, "OptiScaler.ini"), newline="")
        for line in ("Dx12Upscaler=ffx", "Fsr4GpuSupport=4", "Fsr4Model=3", "Fsr4EnableWatermark=false"):
            self.assertIn(line + "\r\n", ini)
        self.assertNotIn("Dx12Upscaler=auto", ini)
        touch(os.path.join(self.game, "OptiScaler.log"), b"session")
        O.uninstall(self.game)
        self.assertEqual(sorted(os.listdir(self.game)), before)
        self.assertEqual(read(os.path.join(self.game, "winmm.dll"), "rb"), b"the game's own winmm")

    def test_a_named_loader_backs_up_the_games_own_file_and_puts_it_back(self):
        m = O.install(self.game, "game.exe", self.pkg, self.fsr4, {"watermark": True, "overlay": True}, "winmm.dll")
        self.assertEqual(read(os.path.join(self.game, "winmm.dll"), "rb"), b"opti")
        self.assertIn("winmm.dll", m["backups"])
        ini = read(os.path.join(self.game, "OptiScaler.ini"))
        self.assertIn("Fsr4EnableWatermark=true", ini)
        self.assertIn("ShowFps=true", ini)
        O.uninstall(self.game)
        self.assertEqual(read(os.path.join(self.game, "winmm.dll"), "rb"), b"the game's own winmm")

    def test_proxy_order_and_rules(self):
        self.assertEqual(O.pick_proxy(self.game, "game.exe"), "dxgi.dll")
        self.assertEqual(O.pick_proxy(self.game, "game.exe", ["dxgi.dll"]), "version.dll")  # winmm is the game's
        self.assertEqual(O.pick_proxy(self.game, "RDR2.exe"), "dxgi.dll")  # its rule name is taken here


class Overlay(unittest.TestCase):
    def test_tv_sizes_grow_with_the_screen_and_choice(self):
        small, huge = O.overlay_look("small", 2160), O.overlay_look("huge", 2160)
        self.assertLess(int(small[0]) * float(small[1]), int(huge[0]) * float(huge[1]))
        self.assertEqual(O.overlay_look("large", None), O.overlay_look("large", 2160))  # 4K until the log says
        values = dict(((s, k), v) for s, k, v in O.ini_settings(overlay=True, overlay_size="huge", overlay_pos="bottomright",
                                                                height=1440))
        self.assertEqual(values[("Menu", "FpsOverlayPos")], "3")
        self.assertEqual(values[("Menu", "ShowFps")], "true")
        off = dict(((s, k), v) for s, k, v in O.ini_settings(overlay=False))
        self.assertEqual(off[("Menu", "FontSize")], "auto")

    def test_output_height_comes_from_the_log(self):
        self.assertEqual(O.display_height("Display Resolution: 3840x2160"), 2160)
        self.assertEqual(O.display_height("color_out extents (0,0,2560,1440)"), 1440)
        self.assertIsNone(O.display_height("nothing"))


class LaunchOptions(unittest.TestCase):
    def test_added_merged_and_taken_back_out(self):
        self.assertEqual(O.with_override("", "dxgi.dll"), "WINEDLLOVERRIDES=dxgi=n,b %command%")
        self.assertEqual(O.with_override("%command% -dx12", "dxgi.dll"), "WINEDLLOVERRIDES=dxgi=n,b %command% -dx12")
        merged = O.with_override("WINEDLLOVERRIDES=foo=n %command%", "winmm.dll")
        self.assertEqual(merged, "WINEDLLOVERRIDES=foo=n;winmm=n,b %command%")
        self.assertEqual(O.without_override(merged, "winmm.dll"), "WINEDLLOVERRIDES=foo=n %command%")
        self.assertEqual(O.without_override("WINEDLLOVERRIDES=dxgi=n,b %command%", "dxgi.dll", ""), "")


class Verdict(unittest.TestCase):
    def test_reads_the_session(self):
        self.assertEqual(O.verdict("")[0], "none")
        self.assertEqual(O.verdict("... hooking ffxProvider_FSR4Lite_Int8 ...")[0], "lite")
        self.assertEqual(O.verdict("Loaded OptiScaler/amdxcffx64.dll")[0], "fsr4")
        self.assertEqual(O.verdict("FFX upscaler: render 1280x720 output 2560x1440")[0], "fsr3")
        self.assertEqual(O.verdict("OptiScaler v10 started")[0], "waiting")
        self.assertEqual(O.verdict("this GPU can't run any FSR 4 model")[0], "unsupported")


if __name__ == "__main__":
    unittest.main()


class SevenZip(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "the execute bit is POSIX")
    def test_a_non_executable_7zip_is_copied_somewhere_it_can_run(self):
        import stat
        import sml_assets
        d = tempfile.mkdtemp()
        src = os.path.join(d, "plugin", "7zz")
        touch(src, b"#!/bin/sh\n")
        os.chmod(src, 0o644)
        data = os.path.join(d, "data")
        os.makedirs(data)
        os.chmod(os.path.dirname(src), 0o555)  # the plugin folder isn't ours to change
        try:
            got = sml_assets.runnable(src, data)
        finally:
            os.chmod(os.path.dirname(src), 0o755)
        self.assertTrue(os.access(got, os.X_OK))
        self.assertTrue(stat.S_IMODE(os.stat(got).st_mode) & 0o100)
