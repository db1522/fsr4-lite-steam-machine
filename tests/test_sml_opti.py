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

    def test_upscalers_deep_in_unreal_plugins_folders_are_found(self):
        # UE5 games keep DLSS, Streamline and FSR plugin DLLs deep inside Plugins folders (Phantom Blade Zero),
        # deeper than the general search goes: the widget's GameAnalyzer looks 7 folders into any Plugins folder
        # within 3 levels of the game folder.
        win64 = os.path.join(self.root, "Game", "Binaries", "Win64")
        touch(os.path.join(win64, "Game-Win64-Shipping.exe"))
        deep = ("Binaries", "ThirdParty", "Win64")
        touch(os.path.join(self.root, "Engine", "Plugins", "Marketplace", "Nvidia", "DLSS", "Source", *deep,
                           "nvngx_dlss.dll"))
        touch(os.path.join(self.root, "Game", "Plugins", "Runtime", "AMD", "FSR3", "Source", *deep,
                           "amd_fidelityfx_dx12.dll"))
        self.assertEqual(O.analyze(self.root)["upscalers"], ["DLSS", "FSR 3.1"])

    def test_the_deep_search_stays_inside_plugins_folders(self):
        touch(os.path.join(self.root, "game.exe"))
        touch(os.path.join(self.root, *"abcdefghi", "nvngx_dlss.dll"))  # 9 folders down, not under Plugins
        self.assertEqual(O.analyze(self.root)["upscalers"], [])

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

    def test_the_name_that_worked_last_time_comes_first(self):
        # the widget's LoaderMemory: after the game is set up again, the name OptiScaler loaded under is tried first
        self.assertEqual(O.pick_proxy(self.game, "game.exe", remembered="dbghelp.dll"), "dbghelp.dll")
        self.assertEqual(O.pick_proxy(self.game, "game.exe", remembered="evil.dll"), "dxgi.dll")  # only real names
        os.remove(os.path.join(self.game, "winmm.dll"))
        self.assertEqual(O.pick_proxy(self.game, "RDR2.exe", remembered="version.dll"), "winmm.dll")  # rule first

    def test_after_a_skipped_name_the_ones_the_exe_imports_go_first(self):
        # the widget's OrderForExe: Windows loads imported DLLs from the game folder at startup
        touch(os.path.join(self.game, "game.exe"), pe_importing(["KERNEL32.dll", "VERSION.dll"]))
        self.assertEqual(O.pick_proxy(self.game, "game.exe", ["dxgi.dll"]), "version.dll")
        self.assertEqual(O.pick_proxy(self.game, "game.exe"), "dxgi.dll")  # a first install keeps the usual order

    def test_a_game_without_upscaler_files_gets_optiscalers_pattern_search(self):
        O.install(self.game, "game.exe", self.pkg, self.fsr4, {"watermark": False, "overlay": False}, upscalers=[])
        ini = read(os.path.join(self.game, "OptiScaler.ini"))
        self.assertIn("Fsr2Pattern=true", ini)
        self.assertIn("Fsr3Pattern=true", ini)

    def test_fsr2_inputs_follow_the_exes_graphics_api(self):
        touch(os.path.join(self.game, "dx11.exe"), pe_importing(["d3d11.dll"], delayed=["dxgi.dll"]))
        touch(os.path.join(self.game, "vk.exe"), pe_importing(["vulkan-1.dll"]))
        touch(os.path.join(self.game, "dx12.exe"), pe_importing(["d3d12.dll", "d3d11.dll"]))
        self.assertEqual(O.game_inputs(self.game, "dx11.exe", ["FSR 2"]), [("Inputs", "UseFsr2Dx11Inputs", "true")])
        self.assertEqual(O.game_inputs(self.game, "vk.exe", ["FSR 2"]), [("Inputs", "UseFsr2VulkanInputs", "true")])
        self.assertEqual(O.game_inputs(self.game, "dx12.exe", ["FSR 2"]), [])  # OptiScaler's default
        self.assertEqual(O.game_inputs(self.game, "dx11.exe", ["DLSS"]), [])  # only FSR 2 games
        self.assertEqual(O.game_inputs(self.game, "game.exe", ["FSR 2"]), [])  # not a PE file: nothing guessed


def pe_importing(dlls, delayed=()):
    """A minimal 64-bit PE: one section holding an import table for dlls and a delay-load table for delayed."""
    import struct
    sec_rva, sec_raw, size = 0x1000, 0x200, 0x400
    body = bytearray(size)
    names, at = {}, 0x100
    for n in list(dlls) + list(delayed):
        names[n] = sec_rva + at
        body[at:at + len(n)] = n.encode()
        at += len(n) + 1
    for i, n in enumerate(dlls):  # 20-byte import descriptors at the section start, then a zero one
        struct.pack_into("<IIIII", body, i * 20, 0, 0, 0, names[n], 0)
    delay_at = 0x80
    for i, n in enumerate(delayed):  # 32-byte delay-load descriptors
        struct.pack_into("<IIIIIIII", body, delay_at + i * 32, 1, names[n], 0, 0, 0, 0, 0, 0)
    head = bytearray(sec_raw)
    head[0:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x40)
    head[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", head, 0x44, 0x8664, 1, 0, 0, 0, 240, 0x22)
    opt = 0x58
    struct.pack_into("<H", head, opt, 0x20B)
    dirs = opt + 112
    struct.pack_into("<II", head, dirs + 1 * 8, sec_rva, 20 * (len(dlls) + 1))
    if delayed:
        struct.pack_into("<II", head, dirs + 13 * 8, sec_rva + delay_at, 32 * (len(delayed) + 1))
    struct.pack_into("<8sIIIIIIHHI", head, opt + 240, b".idata", size, sec_rva, size, sec_raw, 0, 0, 0, 0, 0)
    return bytes(head) + bytes(body)


class ExeImports(unittest.TestCase):
    def test_imports_and_delay_loads_are_read(self):
        d = tempfile.mkdtemp()
        exe = os.path.join(d, "g.exe")
        touch(exe, pe_importing(["KERNEL32.dll", "WINMM.dll"], delayed=["d3d11.dll"]))
        self.assertEqual(O.exe_imports(exe), {"kernel32.dll", "winmm.dll", "d3d11.dll"})

    def test_anything_else_gives_nothing(self):
        d = tempfile.mkdtemp()
        for name, data in (("a.exe", b""), ("b.exe", b"MZ" + b"\xff" * 100), ("c.exe", b"not a program at all")):
            touch(os.path.join(d, name), data)
            self.assertEqual(O.exe_imports(os.path.join(d, name)), set())
        self.assertEqual(O.exe_imports(os.path.join(d, "missing.exe")), set())


class REFramework(unittest.TestCase):
    def test_games_that_need_it_are_matched_like_the_widget(self):
        yes = [("Monster Hunter Wilds", "MonsterHunterWilds.exe"), ("RESIDENT EVIL 2", "re2.exe"),
               ("Resident Evil 4", "re4.exe"), ("RESIDENT EVIL 7 biohazard Gold Edition", "re7.exe"),
               ("Resident Evil Village", "re8.exe"), ("Resident Evil Requiem", "re9.exe"),
               ("Devil May Cry 5", "DevilMayCry5.exe"), ("PRAGMATA", "PRAGMATA.exe"),
               ("Onimusha: Way of the Sword", "Onimusha.exe"), ("Dragon's Dogma 2", "DD2.exe")]
        no = [("Resident Evil Village", "village.exe"), ("Resident Evil 5", "re5dx9.exe"), ("Forza Horizon 5", "fh5.exe"),
              ("Monster Hunter World", "MonsterHunterWorld.exe"), ("", "game.exe")]
        for name, exe in yes:
            self.assertTrue(O.needs_reframework(name, exe), name)
        for name, exe in no:
            self.assertFalse(O.needs_reframework(name, exe), name)
        self.assertIn("REFramework", O.tips("re4.exe", ["DLSS", "FSR 3.1"], "Resident Evil 4"))

    def setUp(self):
        t = tempfile.mkdtemp()
        self.pkg, self.game = os.path.join(t, "pkg"), os.path.join(t, "game")
        touch(os.path.join(self.pkg, "OptiScaler.dll"), b"opti")
        self.ref = os.path.join(t, "dinput8.dll")
        touch(self.ref, b"reframework")
        touch(os.path.join(self.game, "re4.exe"), b"game")

    def test_added_with_its_menu_closed_and_everything_it_made_removed(self):
        touch(os.path.join(self.game, "re4_fw_log.txt"), b"the player's earlier REFramework log")
        m = O.install(self.game, "re4.exe", self.pkg, [], {}, reframework=self.ref)
        self.assertTrue(m["reframework"])
        self.assertEqual(read(os.path.join(self.game, "dinput8.dll"), "rb"), b"reframework")
        config = read(os.path.join(self.game, "re2_fw_config.txt"))
        self.assertIn("REFrameworkConfig_MenuOpen=false", config)
        self.assertIn("REFrameworkConfig_RememberMenuState=true", config)
        # what REFramework makes while the game runs
        touch(os.path.join(self.game, "reframework", "plugins", "x.dll"))
        touch(os.path.join(self.game, "re2_framework_log.txt"))
        O.uninstall(self.game)
        self.assertEqual(sorted(os.listdir(self.game)), ["re4.exe", "re4_fw_log.txt"])

    def test_a_dinput8_the_game_already_has_is_left_alone(self):
        touch(os.path.join(self.game, "dinput8.dll"), b"the player's own mod")
        m = O.install(self.game, "re4.exe", self.pkg, [], {}, reframework=self.ref)
        self.assertNotIn("reframework", m)
        self.assertFalse(os.path.exists(os.path.join(self.game, "re2_fw_config.txt")))
        O.uninstall(self.game)
        self.assertEqual(read(os.path.join(self.game, "dinput8.dll"), "rb"), b"the player's own mod")


class REFrameworkDownload(unittest.TestCase):
    def fake_download(self, members):
        def download(url, dest, limit, sha256, **kw):
            import sml_assets
            self.assertEqual((url, limit, sha256), (sml_assets.REFRAMEWORK["url"], sml_assets.REFRAMEWORK["size"],
                                                    sml_assets.REFRAMEWORK["sha256"]))  # only the pinned build
            import zipfile
            with zipfile.ZipFile(dest, "w") as z:
                for name, data in members.items():
                    z.writestr(name, data)
        return download

    def test_only_dinput8_is_kept_and_older_builds_go(self):
        from unittest import mock
        import sml_assets
        data = tempfile.mkdtemp()
        touch(os.path.join(data, "reframework-01000", "dinput8.dll"))
        with mock.patch("dk_net.download", self.fake_download({"dinput8.dll": b"ref", "VR/openvr_api.dll": b"vr",
                                                               "VR/dinput8.dll": b"vr build"})):
            path = sml_assets.fetch_reframework(data)
        self.assertEqual(read(path, "rb"), b"ref")
        self.assertEqual(sorted(os.listdir(data)), [sml_assets.REFRAMEWORK["folder"]])
        self.assertEqual(os.listdir(os.path.dirname(path)), ["dinput8.dll"])

    def test_a_zip_without_dinput8_is_refused(self):
        from unittest import mock
        import sml_assets
        with mock.patch("dk_net.download", self.fake_download({"readme.txt": b"no dll"})):
            with self.assertRaises(RuntimeError):
                sml_assets.fetch_reframework(tempfile.mkdtemp())


class RealExe(unittest.TestCase):
    """Phantom Blade Zero: an Unreal folder, but Steam runs platform/steam/PBZ.exe, not Binaries/Win64/8za_v2.exe."""
    def setUp(self):
        t = tempfile.mkdtemp()
        self.root = os.path.join(t, "steamapps", "common", "PBZ")
        self.real = os.path.join(self.root, "platform", "steam", "PBZ.exe")
        touch(self.real, b"game" * 1000)
        touch(os.path.join(self.root, "PBZLauncher.exe"), b"small")
        touch(os.path.join(self.root, "ProjectPBZ", "Binaries", "Win64", "8za_v2.exe"), b"tool" * 2000)
        self.proc = os.path.join(t, "proc")

    def process(self, pid, *args):
        touch(os.path.join(self.proc, str(pid), "cmdline"), b"\0".join(a.encode() for a in args) + b"\0")

    def test_the_folder_guess_is_the_wrong_exe(self):
        self.assertEqual(O.analyze(self.root)["exe_name"], "8za_v2.exe")

    def test_the_running_exe_is_found_in_the_process_list(self):
        self.process(100, "/usr/bin/python3", "/proton", "waitforexitandrun",
                     "/home/deck/.local/share/Steam/steamapps/common/PBZ/PBZLauncher.exe")
        self.process(101, "S:\\steamapps\\common\\PBZ\\PLATFORM\\steam\\PBZ.exe", "-dx12")  # any letter case
        self.process(102, "C:\\windows\\system32\\steam.exe")
        self.process(103, "Z:\\other\\steamapps\\common\\Other Game\\game.exe")
        os.makedirs(os.path.join(self.proc, "self"))
        self.assertEqual(O.running_exe(self.root, self.proc), self.real)  # the game, not the small launcher

    def test_nothing_running_or_no_proc(self):
        os.makedirs(self.proc)
        self.assertIsNone(O.running_exe(self.root, self.proc))
        self.assertIsNone(O.running_exe(self.root, os.path.join(self.proc, "missing")))
        self.process(1, "S:\\steamapps\\common\\PBZ\\..\\..\\evil.exe")
        self.assertIsNone(O.running_exe(self.root, self.proc))

    def test_optiscalers_log_names_the_exe(self):
        log = "[13:25:07.284454] [I] CheckQuirks Game's Exe: PBZ.exe\n[13:25:07.284461] [I] CheckQuirks Game Name: x\n"
        self.assertEqual(O.logged_exe(log), "PBZ.exe")
        self.assertEqual(O.find_exe(self.root, "pbz.EXE"), self.real)
        self.assertIsNone(O.find_exe(self.root, "missing.exe"))

    def test_a_missing_fsr4_file_is_fsr3_not_fsr4(self):
        log = ("CheckQuirks Game's Exe: PBZ.exe\n`anonymous-namespace'::LoadDriverDll Failed to load amdxcffx64.dll\n"
               "IFeature::SetInitParameters Render Resolution: 1280x720, Display Resolution 3840x2160\n")
        self.assertEqual(O.verdict(log), ("fsr3", O.NO_FSR4_FILE))


class Tips(unittest.TestCase):
    def test_the_widgets_card_lines(self):
        self.assertIn("No upscaler files found", O.tips("game.exe", []))
        self.assertIn("pick DLSS or XeSS", O.tips("game.exe", ["DLSS", "XeSS"]))
        self.assertEqual(O.tips("game.exe", ["DLSS", "FSR 3.1"]), "")
        self.assertIn("DirectX 12", O.tips("RDR2.exe", ["FSR 2"]))


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
