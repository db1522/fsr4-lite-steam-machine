# SPDX-License-Identifier: BSD-3-Clause
"""FSR 4.1 Lite's OptiScaler method (sml_opti): game analysis, install and exact uninstall, settings, launch options,
and reading a session from OptiScaler.log."""
import json
import os
import shutil
import unittest

import _harness  # noqa: F401
from _tmp import temp_dir  # noqa: E402
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
        self.root = temp_dir(self)

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
        t = temp_dir(self)
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
        d = temp_dir(self)
        exe = os.path.join(d, "g.exe")
        touch(exe, pe_importing(["KERNEL32.dll", "WINMM.dll"], delayed=["d3d11.dll"]))
        self.assertEqual(O.exe_imports(exe), {"kernel32.dll", "winmm.dll", "d3d11.dll"})

    def test_anything_else_gives_nothing(self):
        d = temp_dir(self)
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

    def test_crimson_desert_says_to_change_settings_with_lite_off(self):
        tip = O.tips("CrimsonDesert.exe", ["DLSS", "FSR 3.1", "XeSS"], "Crimson Desert Enhanced")
        self.assertIn("Turn FSR 4.1 Lite off, change your settings, then turn it back on", tip)

    def setUp(self):
        t = temp_dir(self)
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


class GameIni(unittest.TestCase):
    def setUp(self):
        t = temp_dir(self)
        self.pkg, self.game = os.path.join(t, "pkg"), os.path.join(t, "game")
        touch(os.path.join(self.pkg, "OptiScaler.dll"), b"opti")
        touch(os.path.join(self.pkg, "OptiScaler.ini"),
              b"[Menu]\r\nOverlayMenu=auto\r\nShowFps=auto\r\n[Spoofing]\r\nDxgi=auto\r\n")
        touch(os.path.join(self.game, "ACBlackFlag.exe"), b"game")
        touch(os.path.join(self.game, "upc_r2_loader64.dll"), b"ubisoft connect")

    def test_black_flag_gets_the_overlay_and_spoofing_off_and_keeps_them_on_refresh(self):
        self.assertTrue(O.analyze(self.game)["ubisoft"])
        O.install(self.game, "ACBlackFlag.exe", self.pkg, [], {"overlay": True})
        ini = os.path.join(self.game, "OptiScaler.ini")
        self.assertIn("OverlayMenu=false", read(ini))
        self.assertIn("Dxgi=false", read(ini))
        O.set_ini(ini, [("Menu", "OverlayMenu", "auto")])
        O.apply_settings(self.game, {"overlay": True})  # the plugin's settings refresh, at load or a settings change
        self.assertIn("OverlayMenu=false", read(ini))
        tip = O.tips("ACBlackFlag.exe", ["FSR 3.1"], "Assassin's Creed Black Flag Resynced", True)
        self.assertIn("pick FSR", tip)
        self.assertIn("Ubisoft Connect games", tip)

    def test_any_ubisoft_connect_game_gets_the_overlay_off_but_keeps_spoofing(self):
        os.rename(os.path.join(self.game, "ACBlackFlag.exe"), os.path.join(self.game, "ACShadows.exe"))
        os.rename(os.path.join(self.game, "upc_r2_loader64.dll"), os.path.join(self.game, "UPLAY_R1_LOADER64.DLL"))
        O.install(self.game, "ACShadows.exe", self.pkg, [], {})
        ini = read(os.path.join(self.game, "OptiScaler.ini"))
        self.assertIn("OverlayMenu=false", ini)
        self.assertIn("Dxgi=auto", ini)

    def test_other_games_keep_the_overlay(self):
        os.rename(os.path.join(self.game, "ACBlackFlag.exe"), os.path.join(self.game, "game.exe"))
        os.remove(os.path.join(self.game, "upc_r2_loader64.dll"))
        self.assertFalse(O.analyze(self.game)["ubisoft"])
        O.install(self.game, "game.exe", self.pkg, [], {})
        self.assertIn("OverlayMenu=auto", read(os.path.join(self.game, "OptiScaler.ini")))
        self.assertNotIn("Ubisoft", O.tips("game.exe", ["FSR 3.1"], "Game", False))


class OptiPatcher(unittest.TestCase):
    def test_the_tip_says_dlss_is_the_way_only_when_the_game_has_nothing_else(self):
        only = O.tips("Palworld-Win64-Shipping.exe", ["DLSS"], "Palworld")
        self.assertIn("only offers DLSS with OptiPatcher", only)
        self.assertIn("Pick DLSS in the game", only)
        wukong = O.tips("b1-Win64-Shipping.exe", ["DLSS", "FSR 3.1", "XeSS"], "Black Myth: Wukong")
        self.assertNotIn("only offers DLSS", wukong)
        self.assertIn("You don't need it: FSR or XeSS runs FSR 4.1 Lite too.", wukong)
        self.assertIn("FSR runs FSR 4.1 Lite too",
                      O.tips("b1-Win64-Shipping.exe", ["DLSS", "FSR 2"], "Black Myth: Wukong"))

    def test_the_games_the_list_marks_get_it(self):
        self.assertTrue(O.needs_optipatcher("DOOM Eternal", "DOOMEternalx64vk.exe"))
        self.assertFalse(O.needs_optipatcher("Horizon Zero Dawn Complete Edition", "HorizonZeroDawn.exe"))
        self.assertFalse(O.needs_optipatcher("Not Listed", "n.exe"))
        self.assertIn("OptiPatcher", O.tips("DOOMEternalx64vk.exe", ["DLSS"], "DOOM Eternal"))
        # compat.json from before 2.2.25 (three columns) still reads
        path = os.path.join(temp_dir(self), "compat.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"games": [["Old", "working", ["DLSS"]], ["New", "working", ["DLSS"], True]]}, f)
        self.assertFalse(O.needs_optipatcher("Old", "old.exe", path))
        self.assertTrue(O.needs_optipatcher("New", "new.exe", path))
        self.assertEqual(O.compat_text("Old", "old.exe", path), "Works with: DLSS")

    def setUp(self):
        t = temp_dir(self)
        self.pkg, self.game = os.path.join(t, "pkg"), os.path.join(t, "game")
        touch(os.path.join(self.pkg, "OptiScaler.dll"), b"opti")
        touch(os.path.join(self.pkg, "OptiScaler.ini"), b"[Plugins]\r\nPath=auto\r\nLoadAsiPlugins=auto\r\n")
        self.asi = os.path.join(t, "OptiPatcher.asi")
        touch(self.asi, b"MZ patcher")
        touch(os.path.join(self.game, "doom.exe"), b"game")

    def test_added_in_optiscalers_plugins_folder_with_asi_loading_on_and_removed_at_uninstall(self):
        # OptiScaler reads plugins from <OptiDllPath>/plugins, and every setup pins OptiDllPath to OptiScaler/
        O.install(self.game, "doom.exe", self.pkg, [], {})
        self.assertTrue(O.add_optipatcher(self.game, self.asi, "v0.42"))
        self.assertEqual(read(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi"), "rb"), b"MZ patcher")
        self.assertFalse(os.path.exists(os.path.join(self.game, "plugins")))
        self.assertIn("LoadAsiPlugins=true", read(os.path.join(self.game, "OptiScaler.ini")))
        self.assertEqual(O.load_manifest(self.game)["optipatcher"], "v0.42")
        self.assertFalse(O.add_optipatcher(self.game, self.asi, "v0.42"), "already there")
        touch(self.asi, b"MZ newer")
        self.assertTrue(O.add_optipatcher(self.game, self.asi, "v0.43"))
        self.assertEqual(read(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi"), "rb"), b"MZ newer")
        O.uninstall(self.game)
        self.assertEqual(os.listdir(self.game), ["doom.exe"])

    def test_a_players_own_plugins_stay_in_both_folders(self):
        touch(os.path.join(self.game, "plugins", "theirs.asi"), b"theirs")
        O.install(self.game, "doom.exe", self.pkg, [], {})
        O.add_optipatcher(self.game, self.asi, "v0.42")
        touch(os.path.join(self.game, "OptiScaler", "plugins", "mine.asi"), b"mine")
        O.uninstall(self.game)
        self.assertEqual(sorted(os.listdir(self.game)), ["OptiScaler", "doom.exe", "plugins"])
        self.assertEqual(os.listdir(os.path.join(self.game, "plugins")), ["theirs.asi"])
        self.assertEqual(os.listdir(os.path.join(self.game, "OptiScaler", "plugins")), ["mine.asi"])

    def setup_2225(self, players_file=False):
        """A game set up by 2.2.25: OptiPatcher in plugins/ next to the exe."""
        if players_file:
            touch(os.path.join(self.game, "plugins", "theirs.asi"), b"theirs")
        O.install(self.game, "doom.exe", self.pkg, [], {})
        m = O.load_manifest(self.game)
        meta = os.path.join(self.game, O.META)
        O._place(self.game, meta, m, self.asi, os.path.join("plugins", "OptiPatcher.asi"))
        m["optipatcher"] = "v0.42"
        O._save(meta, m)

    def test_a_2225_setup_is_moved_into_optiscalers_plugins_folder(self):
        self.setup_2225()
        self.assertTrue(O.move_old_optipatcher(self.game))
        self.assertEqual(read(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi"), "rb"), b"MZ patcher")
        self.assertFalse(os.path.exists(os.path.join(self.game, "plugins")), "the empty old folder is gone")
        created = O.load_manifest(self.game)["created"]
        self.assertIn(os.path.join("OptiScaler", "plugins", "OptiPatcher.asi"), created)
        self.assertNotIn(os.path.join("plugins", "OptiPatcher.asi"), created)
        self.assertFalse(O.move_old_optipatcher(self.game), "once")
        self.assertFalse(O.add_optipatcher(self.game, self.asi, "v0.42"), "nothing more to do")
        O.uninstall(self.game)
        self.assertEqual(os.listdir(self.game), ["doom.exe"])

    def test_a_players_file_in_the_old_folder_stays_when_moving(self):
        self.setup_2225(players_file=True)
        O.move_old_optipatcher(self.game)
        self.assertEqual(os.listdir(os.path.join(self.game, "plugins")), ["theirs.asi"])
        self.assertTrue(os.path.isfile(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi")))

    def test_repair_and_updates_move_a_2225_setup_too(self):
        self.setup_2225()
        O.repair(self.game, self.pkg, [], {}, optipatcher=self.asi)
        self.assertTrue(os.path.isfile(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi")))
        self.assertFalse(os.path.exists(os.path.join(self.game, "plugins")))
        self.setUp()
        self.setup_2225()
        touch(self.asi, b"MZ newer")
        self.assertTrue(O.add_optipatcher(self.game, self.asi, "v0.43"))
        self.assertEqual(read(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi"), "rb"), b"MZ newer")
        self.assertFalse(os.path.exists(os.path.join(self.game, "plugins")))

    def test_repair_puts_it_back(self):
        O.install(self.game, "doom.exe", self.pkg, [], {})
        O.add_optipatcher(self.game, self.asi, "v0.42")
        os.remove(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi"))
        os.remove(os.path.join(self.game, "OptiScaler.ini"))
        fixed = O.repair(self.game, self.pkg, [], {}, optipatcher=self.asi)
        self.assertIn(os.path.join("OptiScaler", "plugins", "OptiPatcher.asi"), fixed)
        self.assertTrue(os.path.isfile(os.path.join(self.game, "OptiScaler", "plugins", "OptiPatcher.asi")))
        self.assertIn("LoadAsiPlugins=true", read(os.path.join(self.game, "OptiScaler.ini")))

    def test_not_for_a_game_that_isnt_set_up(self):
        self.assertFalse(O.add_optipatcher(self.game, self.asi, "v0.42"))
        self.assertFalse(os.path.exists(os.path.join(self.game, "OptiScaler")))


OP_RELEASES = [
    {"tag_name": "rolling", "published_at": "2026-05-14T18:26:56Z", "assets": [
        {"name": "OptiPatcher.asi", "size": 300, "digest": "sha256:" + "c" * 64,
         "browser_download_url": "https://github.com/optiscaler/OptiPatcher/releases/download/rolling/OptiPatcher.asi"}]},
    {"tag_name": "v0.43", "published_at": "2026-11-01T00:00:00Z", "prerelease": True, "assets": [
        {"name": "OptiPatcher_v0.43.asi", "size": 300,
         "browser_download_url": "https://github.com/optiscaler/OptiPatcher/releases/download/v0.43/OptiPatcher_v0.43.asi"}]},
    {"tag_name": "v0.42", "published_at": "2026-10-18T12:28:51Z", "assets": [
        {"name": "OptiPatcher_v0.42.asi", "size": 200, "digest": "sha256:" + "a" * 64,
         "browser_download_url": "https://github.com/optiscaler/OptiPatcher/releases/download/v0.42/OptiPatcher_v0.42.asi"}]},
    {"tag_name": "evil", "published_at": "2026-12-01T00:00:00Z", "assets": [
        {"name": "OptiPatcher.asi", "size": 200, "browser_download_url": "https://example.com/OptiPatcher.asi"}]},
]


class OptiPatcherDownload(unittest.TestCase):
    def fake_download(self, data, expect):
        def download(url, dest, limit, sha256, **kw):
            self.assertEqual((url, limit, sha256), expect)
            with open(dest, "wb") as f:
                f.write(data)
        return download

    def test_the_newest_published_release_is_used_checked_by_githubs_sha256(self):
        from unittest import mock
        import sml_assets
        self.assertEqual(sml_assets.newest_optipatcher(OP_RELEASES)["tag"], "v0.42")
        data = temp_dir(self)
        with mock.patch("sml_assets._api", return_value=OP_RELEASES), \
                mock.patch("dk_net.download", self.fake_download(b"MZ op", (
                    OP_RELEASES[2]["assets"][0]["browser_download_url"], 200, "a" * 64))):
            path = sml_assets.fetch_optipatcher(data)
        self.assertEqual(read(path, "rb"), b"MZ op")
        self.assertEqual(sml_assets.optipatcher_build(data), "v0.42")

    def test_without_githubs_api_the_pinned_release_is_used(self):
        from unittest import mock
        import dk_net
        import sml_assets
        data = temp_dir(self)
        P = sml_assets.OPTIPATCHER
        with mock.patch("sml_assets._api", side_effect=dk_net.NetError("rate limited")), \
                mock.patch("dk_net.download", self.fake_download(b"MZ op", (P["url"], P["size"], P["sha256"]))):
            sml_assets.fetch_optipatcher(data)
        self.assertEqual(sml_assets.optipatcher_build(data), "v0.42")

    def test_looked_for_once_a_day_and_a_non_dll_is_refused(self):
        from unittest import mock
        import sml_assets
        data = temp_dir(self)
        with mock.patch("sml_assets._api", return_value=OP_RELEASES) as api, \
                mock.patch("dk_net.download", self.fake_download(b"MZ op", mock.ANY)):
            sml_assets.update_optipatcher(data, now=1000)
            self.assertEqual(sml_assets.update_optipatcher(data, now=1000 + 3600), ("v0.42", False))
            self.assertEqual(api.call_count, 1)
        with mock.patch("sml_assets._api", return_value=OP_RELEASES), \
                mock.patch("dk_net.download", self.fake_download(b"<html>", mock.ANY)):
            with self.assertRaises(RuntimeError):
                sml_assets.fetch_optipatcher(temp_dir(self))


REF_RELEASE = {"tag_name": "nightly-01440-abc", "assets": [
    {"name": "REFramework.zip", "size": 1234, "digest": "sha256:" + "a" * 64,
     "browser_download_url": "https://github.com/praydog/REFramework-nightly/releases/download/nightly-01440-abc/"
                             "REFramework.zip"}]}


class REFrameworkDownload(unittest.TestCase):
    def fake_download(self, members, expect):
        def download(url, dest, limit, sha256, **kw):
            self.assertEqual((url, limit, sha256), expect)
            import zipfile
            with zipfile.ZipFile(dest, "w") as z:
                for name, data in members.items():
                    z.writestr(name, data)
        return download

    def test_the_newest_nightly_is_used_checked_by_githubs_sha256_and_only_dinput8_is_kept(self):
        from unittest import mock
        import sml_assets
        data = temp_dir(self)
        touch(os.path.join(data, "reframework-01433", "dinput8.dll"))  # the pinned build from before 2.2.17
        asset = REF_RELEASE["assets"][0]
        with mock.patch("sml_assets._api", return_value=REF_RELEASE), \
                mock.patch("dk_net.download", self.fake_download(
                    {"dinput8.dll": b"ref", "VR/openvr_api.dll": b"vr", "VR/dinput8.dll": b"vr build"},
                    (asset["browser_download_url"], 1234, "a" * 64))):
            path = sml_assets.fetch_reframework(data)
        self.assertEqual(read(path, "rb"), b"ref")
        self.assertEqual(sml_assets.reframework_build(data), "nightly-01440-abc")
        self.assertEqual(sorted(os.listdir(data)), ["reframework"])
        self.assertNotIn("openvr_api.dll", os.listdir(os.path.dirname(path)))

    def test_without_githubs_api_the_pinned_build_is_used(self):
        from unittest import mock
        import dk_net
        import sml_assets
        data = temp_dir(self)
        R = sml_assets.REFRAMEWORK
        with mock.patch("sml_assets._api", side_effect=dk_net.NetError("rate limited")), \
                mock.patch("dk_net.download", self.fake_download({"dinput8.dll": b"ref"},
                                                                 (R["url"], R["size"], R["sha256"]))):
            sml_assets.fetch_reframework(data)
        self.assertEqual(sml_assets.reframework_build(data), R["tag"])

    def test_a_newer_nightly_is_looked_for_once_a_day(self):
        from unittest import mock
        import sml_assets
        data = temp_dir(self)
        with mock.patch("sml_assets._api", return_value=REF_RELEASE) as api, \
                mock.patch("dk_net.download", self.fake_download({"dinput8.dll": b"ref"}, mock.ANY)):
            sml_assets.update_reframework(data, now=1000)
            self.assertEqual(sml_assets.update_reframework(data, now=1000 + 3600), ("nightly-01440-abc", False))
            self.assertEqual(api.call_count, 1)
            sml_assets.update_reframework(data, now=1000 + 25 * 3600)
            self.assertEqual(api.call_count, 2)

    def test_a_zip_without_dinput8_is_refused(self):
        from unittest import mock
        import sml_assets
        with mock.patch("sml_assets._api", return_value=REF_RELEASE), \
                mock.patch("dk_net.download", self.fake_download({"readme.txt": b"no dll"}, mock.ANY)):
            with self.assertRaises(RuntimeError):
                sml_assets.fetch_reframework(temp_dir(self))


class RealExe(unittest.TestCase):
    """Phantom Blade Zero as the reports show it: Steam starts a small launcher, steam/PBZ.exe, which starts the game,
    ProjectPBZ/Binaries/Win64/PBZ.exe, next to 8za_v2.exe (the folder guess)."""
    def setUp(self):
        t = temp_dir(self)
        self.root = os.path.join(t, "steamapps", "common", "PBZ")
        self.launcher = os.path.join(self.root, "steam", "PBZ.exe")
        self.real = os.path.join(self.root, "ProjectPBZ", "Binaries", "Win64", "PBZ.exe")
        touch(self.launcher, b"launcher" * 100)
        touch(self.real, b"game" * 1000)
        touch(os.path.join(self.root, "ProjectPBZ", "Binaries", "Win64", "8za_v2.exe"), b"tool" * 2000)
        os.makedirs(os.path.join(self.root, "platform", "steam"))  # where the 2.2.6 report's DllPath pointed
        self.proc = os.path.join(t, "proc")

    def process(self, pid, *args, mb=0, graphics=False):
        touch(os.path.join(self.proc, str(pid), "cmdline"), b"\0".join(a.encode() for a in args) + b"\0")
        touch(os.path.join(self.proc, str(pid), "status"), f"Name:\tx\nVmRSS:\t  {mb * 1024} kB\n".encode())
        maps = "7f00-7f01 r-xp 0 08:01 1 /pfx/drive_c/windows/system32/kernel32.dll\n"
        if graphics:
            maps += "7f02-7f03 r-xp 0 08:01 2 /proton/lib/wine/x86_64-windows/D3D12.dll\n"
        touch(os.path.join(self.proc, str(pid), "maps"), maps.encode())

    def test_the_folder_guess_is_the_wrong_exe(self):
        self.assertEqual(O.analyze(self.root)["exe_name"], "8za_v2.exe")

    def test_the_folder_guess_takes_a_far_bigger_game_exe(self):
        # as seen on the Steam Machine: Binaries/Win64 holds only a 5 MB tool, the game is platform/steam/PBZ.exe
        real = os.path.join(self.root, "platform", "steam", "PBZ.exe")
        touch(real)
        with open(real, "r+b") as f:
            f.truncate(60 << 20)
        self.assertEqual(os.path.join(O.analyze(self.root)["exe_dir"], "PBZ.exe"), real)

    def test_a_shipping_exe_always_wins_the_folder_guess(self):
        win64 = os.path.dirname(self.real)
        touch(os.path.join(win64, "PBZ-Win64-Shipping.exe"), b"ship")
        big = os.path.join(self.root, "platform", "steam", "Big.exe")
        touch(big)
        with open(big, "r+b") as f:
            f.truncate(60 << 20)
        self.assertEqual(O.analyze(self.root)["exe_name"], "PBZ-Win64-Shipping.exe")

    def test_the_game_is_the_rendering_process_using_the_most_memory(self):
        self.process(100, "/usr/bin/python3", "/proton", "waitforexitandrun",
                     "/home/deck/.local/share/Steam/steamapps/common/PBZ/steam/PBZ.exe")
        self.process(101, "S:\\steamapps\\common\\PBZ\\steam\\PBZ.exe", mb=180, graphics=True)  # the launcher
        self.process(102, "S:\\steamapps\\common\\PBZ\\PROJECTPBZ\\Binaries\\Win64\\PBZ.exe", "-dx12", mb=5400,
                     graphics=True)  # any letter case
        self.process(103, "S:\\steamapps\\common\\PBZ\\ProjectPBZ\\Binaries\\Win64\\8za_v2.exe", mb=9000)  # no graphics
        self.process(104, "Z:\\other\\steamapps\\common\\Other Game\\game.exe", mb=9000, graphics=True)
        os.makedirs(os.path.join(self.proc, "self"))
        self.assertEqual(O.running_exe(self.root, self.proc), (self.real, 5400))

    def test_only_the_launcher_running_is_too_small_to_be_the_game(self):
        self.process(101, "S:\\steamapps\\common\\PBZ\\steam\\PBZ.exe", mb=180, graphics=True)
        path, mb = O.running_exe(self.root, self.proc)
        self.assertEqual(path, self.launcher)
        self.assertLess(mb, O.GAME_MEMORY_MB)  # main.py won't take it

    def test_nothing_running_or_no_proc(self):
        os.makedirs(self.proc)
        self.assertEqual(O.running_exe(self.root, self.proc), (None, 0))
        self.assertEqual(O.running_exe(self.root, os.path.join(self.proc, "missing")), (None, 0))
        self.process(1, "S:\\steamapps\\common\\PBZ\\..\\..\\evil.exe", mb=4000, graphics=True)
        self.assertEqual(O.running_exe(self.root, self.proc), (None, 0))

    def test_a_launcher_log_never_draws(self):
        launcher = "CheckQuirks Game's Exe: PBZ.exe\nInit done\nVulkanSpoofing::hkvkCreateInstance Skipping\n"
        game = "hkD3D12CreateDevice Adapter Desc: AMD Steam Machine\nWrappedIDXGISwapChain4 created\n"
        self.assertFalse(O.renders(launcher))
        self.assertTrue(O.renders(game))
        self.assertTrue(O.renders("IFeature::SetInitParameters Render Resolution: 1280x720, Display Resolution 3840x2160"))

    def test_the_game_besides_a_launcher(self):
        self.assertEqual(O.game_besides(self.root, self.launcher), self.real)  # same name, in Binaries/Win64
        other = os.path.join(self.root, "Other.exe")
        touch(other, b"x")
        self.assertEqual(O.game_besides(self.root, other),
                         os.path.join(os.path.dirname(self.real), "8za_v2.exe"))  # no namesake: the folder guess

    @unittest.skipUnless(os.name == "posix", "a working-folder symlink in a fake /proc")
    def test_a_path_relative_to_the_working_folder(self):
        self.process(105, "..\\ProjectPBZ\\Binaries\\Win64\\PBZ.exe", mb=5000, graphics=True)
        os.symlink(os.path.join(self.root, "steam"), os.path.join(self.proc, "105", "cwd"))
        self.assertEqual(O.running_exe(self.root, self.proc), (self.real, 5000))

    def test_a_game_started_with_a_path_through_its_launchers_folder(self):
        # the launcher in steam\ starts the game as steam\..\ProjectPBZ\...: tidied, and the game is found
        self.process(101, "S:\\steamapps\\common\\PBZ\\steam\\PBZ.exe", mb=304, graphics=True)
        self.process(102, "S:\\steamapps\\common\\PBZ\\steam\\..\\ProjectPBZ\\Binaries\\Win64\\PBZ.exe", mb=6100,
                     graphics=True)
        self.assertEqual(O.running_exe(self.root, self.proc), (self.real, 6100))
        self.process(103, "S:\\steamapps\\common\\PBZ\\steam\\..\\..\\..\\evil.exe", mb=9000, graphics=True)
        self.assertEqual(O.running_exe(self.root, self.proc), (self.real, 6100))  # leaving the folder: refused

    def test_the_report_lists_every_windows_program_and_exe(self):
        self.process(101, "S:\\steamapps\\common\\PBZ\\steam\\PBZ.exe", mb=304, graphics=True)
        self.process(102, "C:\\windows\\system32\\services.exe", mb=10)
        self.process(103, "/usr/bin/bash")
        progs = O.windows_programs(self.proc)
        self.assertEqual([(p["pid"], p["exe"], p["mb"], p["graphics"]) for p in progs],
                         [(101, "S:\\steamapps\\common\\PBZ\\steam\\PBZ.exe", 304, True)])
        self.assertEqual([p for p, _mb in O.game_exes(self.root)],
                         ["ProjectPBZ/Binaries/Win64/8za_v2.exe", "ProjectPBZ/Binaries/Win64/PBZ.exe", "steam/PBZ.exe"])

    def test_the_report_sees_every_process(self):
        self.process(101, "S:\\steamapps\\common\\PBZ\\steam\\PBZ.exe", mb=180, graphics=True)
        self.process(102, "S:\\steamapps\\common\\PBZ\\ProjectPBZ\\Binaries\\Win64\\8za_v2.exe", mb=40)
        seen = O.running_processes(self.root, self.proc)
        self.assertEqual([(os.path.basename(p["path"]), p["mb"], p["graphics"]) for p in seen],
                         [("8za_v2.exe", 40, False), ("PBZ.exe", 180, True)])

    def test_every_optiscaler_log_in_the_folder(self):
        touch(os.path.join(self.root, "steam", "OptiScaler.log"), b"launcher")
        touch(os.path.join(os.path.dirname(self.real), "OptiScaler.log"), b"game")
        self.assertEqual(len(O.all_logs(self.root)), 2)

    def test_optiscalers_folder_is_pinned_to_the_games(self):
        self.assertEqual(O.opti_dll_path("/home/deck/.local/share/Steam/steamapps/common/PBZ/ProjectPBZ/Binaries/Win64"),
                         "Z:\\home\\deck\\.local\\share\\Steam\\steamapps\\common\\PBZ\\ProjectPBZ\\Binaries\\Win64\\OptiScaler"
                         if os.sep == "/" else os.path.abspath(
                             "/home/deck/.local/share/Steam/steamapps/common/PBZ/ProjectPBZ/Binaries/Win64/OptiScaler"))
        exe_dir = os.path.dirname(self.real)
        t = temp_dir(self)
        touch(os.path.join(t, "OptiScaler.dll"), b"opti")
        O.install(exe_dir, "PBZ.exe", t, [], {})
        self.assertIn("OptiDllPath=" + O.opti_dll_path(exe_dir), read(os.path.join(exe_dir, "OptiScaler.ini")))

    def test_optiscalers_log_names_the_exe(self):
        log = "[13:25:07.284454] [I] CheckQuirks Game's Exe: PBZ.exe\n[13:25:07.284461] [I] CheckQuirks Game Name: x\n"
        self.assertEqual(O.logged_exe(log), "PBZ.exe")
        self.assertIsNone(O.find_exe(self.root, "pbz.EXE"))  # two PBZ.exe: the log can't say which
        self.assertEqual(O.find_exe(self.root, "8ZA_V2.exe"), os.path.join(os.path.dirname(self.real), "8za_v2.exe"))
        self.assertIsNone(O.find_exe(self.root, "missing.exe"))

    def test_the_folder_optiscaler_looks_in(self):
        log = "[13:43:42.161952] [I] Setting DllPath to S:\\steamapps\\common\\PBZ\\Platform\\steam\n"
        self.assertEqual(O.logged_dll_dir(log), "S:\\steamapps\\common\\PBZ\\Platform\\steam")
        self.assertEqual(O.local_dir(self.root, O.logged_dll_dir(log)), os.path.join(self.root, "platform", "steam"))
        self.assertEqual(O.local_dir(self.root, "S:\\steamapps\\common\\PBZ"), self.root)
        self.assertIsNone(O.local_dir(self.root, "S:\\steamapps\\common\\PBZ2\\x"))  # another game
        self.assertIsNone(O.local_dir(self.root, "S:\\steamapps\\common\\PBZ\\missing"))
        self.assertIsNone(O.local_dir(self.root, "S:\\steamapps\\common\\PBZ\\..\\..\\x"))
        self.assertEqual(O.logged_dll_dir("no such line"), "")

    def test_fsr4_files_where_optiscaler_looks_go_at_uninstall(self):
        exe_dir = os.path.join(self.root, "ProjectPBZ", "Binaries", "Win64")
        t = temp_dir(self)
        pkg, amd = os.path.join(t, "pkg"), os.path.join(t, "amdxcffx64.dll")
        touch(os.path.join(pkg, "OptiScaler.dll"), b"opti")
        touch(amd, b"amd")
        O.install(exe_dir, "8za_v2.exe", pkg, [amd], {})
        steam = os.path.join(self.root, "platform", "steam")
        before = sorted(os.listdir(steam))
        self.assertTrue(O.add_fsr4_copy(exe_dir, steam, [amd]))
        self.assertEqual(read(os.path.join(steam, "OptiScaler", "amdxcffx64.dll"), "rb"), b"amd")
        self.assertFalse(O.add_fsr4_copy(exe_dir, steam, [amd]))  # already there
        O.uninstall(exe_dir)
        self.assertEqual(sorted(os.listdir(steam)), before)
        self.assertFalse(O.add_fsr4_copy(exe_dir, steam, [amd]))  # nothing installed: nothing added

    def test_a_missing_fsr4_file_is_fsr3_not_fsr4(self):
        log = ("CheckQuirks Game's Exe: PBZ.exe\n`anonymous-namespace'::LoadDriverDll Failed to load amdxcffx64.dll\n"
               "IFeature::SetInitParameters Render Resolution: 1280x720, Display Resolution 3840x2160\n")
        self.assertEqual(O.verdict(log), ("fsr3", O.NO_FSR4_FILE))


class CompatList(unittest.TestCase):
    SAMPLE = (
        "# Compatibility List\n\nSome text.\n\n"
        "| Game | Compatibility | Upscaler <br>Inputs | OptiPatcher <br>Support | Notes | Images |\n"
        "| ---- | :-----------: | :-----------------: | :---: | ----- | :----: |\n"
        "| [Cyberpunk 2077](Cyberpunk-2077) | ✅ | DLSS, FSR3, FSR3.1/4, XeSS |  | Notes | [1](https://x) |\n"
        "| Gears of War: Reloaded | ❌ |  |  | Crashes |  |\n"
        "| [Some Game](Some-Game) | ✅ ❌ | DLSS | ✨ | Depends |  |\n"
        "| Minecraft RTX | ➖ | `DLSS` |  |  |  |\n"
        "| [Resident Evil 8 Village](Resident-Evil-8-Village) | ✅ | DLSS, FSR2 |  | Requires REFramework |  |\n"
        "\n## Another section\n| not | a | row | in | the | table |\n")

    def test_the_release_script_reads_the_table_like_the_widget(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("compat_script", os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "compat.py"))
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        self.assertEqual(script.parse(self.SAMPLE), [
            ["Cyberpunk 2077", "working", ["DLSS", "FSR3", "FSR3.1/4", "XeSS"], False],
            ["Gears of War: Reloaded", "not_working", [], False], ["Some Game", "mixed", ["DLSS"], True],
            ["Minecraft RTX", "partial", ["DLSS"], False], ["Resident Evil 8 Village", "working", ["DLSS", "FSR2"], False]])

    def test_the_card_line(self):
        path = os.path.join(temp_dir(self), "compat.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"games": [["Cyberpunk 2077", "working", ["DLSS", "FSR3.1/4", "XeSS"]],
                                 ["Gears of War: Reloaded", "not_working", []], ["Some Game", "mixed", ["DLSS"]],
                                 ["Resident Evil 8 Village", "working", ["DLSS", "FSR2"]], ["Bare", "working", []]]}, f)
        self.assertEqual(O.compat_text("Cyberpunk 2077", "Cyberpunk2077.exe", path), "Works with: DLSS, FSR3.1/4, XeSS")
        self.assertIn("not working", O.compat_text("Gears of War: Reloaded", "gears.exe", path))
        self.assertIn("mixed reports", O.compat_text("Some Game", "g.exe", path))
        self.assertEqual(O.compat_text("Resident Evil Village", "re8.exe", path), "Works with: DLSS, FSR2")
        self.assertEqual(O.compat_text("Resident Evil Village", "village.exe", path), "")
        self.assertEqual(O.compat_text("Bare", "b.exe", path), "")
        self.assertEqual(O.compat_text("Not Listed", "n.exe", path), "")
        self.assertEqual(O.compat_text("Cyberpunk 2077", "x.exe", os.path.join(path + ".missing")), "")

    def test_the_shipped_snapshot(self):
        self.assertTrue(os.path.isfile(O.COMPAT_PATH), "run python scripts/compat.py")
        self.assertIn("FSR3.1/4", O.compat_text("Cyberpunk 2077", "Cyberpunk2077.exe"))
        self.assertTrue(O.compat_text("PAYDAY 3", "PAYDAY3-Win64-Shipping.exe").startswith("Works with:"))


class Summary(unittest.TestCase):
    def test_what_runs_in_the_notification(self):
        res = "IFeature::SetInitParameters Render Resolution: {}, Display Resolution {}, Quality: 3\n"
        dlss = "NVSDK_NGX_D3D12_CreateFeature ...\n" + res.format("1280x720", "3840x2160")
        self.assertEqual(O.summary(dlss), "DLSS → FSR 4.1.2 Lite, 1280×720 → 3840×2160 (Ultra Performance)")
        fsr = "ffxCreateContext_Dx12 context created\n" + res.format("1920x1080", "3840x2160") + res.format("2560x1440", "3840x2160")
        self.assertEqual(O.summary(fsr), "FSR → FSR 4.1.2 Lite, 2560×1440 → 3840×2160 (Quality)")  # the last one
        xess = "hk_xessD3D12CreateContext\n" + res.format("2259x1271", "3840x2160")
        self.assertEqual(O.summary(xess), "XeSS → FSR 4.1.2 Lite, 2259×1271 → 3840×2160 (Balanced)")
        self.assertEqual(O.summary(res.format("1000x500", "3840x2160")), "FSR 4.1.2 Lite, 1000×500 → 3840×2160 (3.84x)")
        self.assertEqual(O.summary(""), "FSR 4.1.2 Lite")


class HdrSharing(unittest.TestCase):
    """ReShade (RenoDX's loader, from HDR for Every Game or set up by hand) and OptiScaler both load as dxgi.dll. Like
    the widget's HdrInstaller: OptiScaler takes the name and loads ReShade64.dll itself (LoadReshade), and uninstall
    gives ReShade its name back. Special K isn't tested with OptiScaler on SteamOS yet: blocked."""
    RESHADE = b"MZ ... Initializing crosire's ReShade version ..."
    SPECIALK = b"MZ ... Special K by Kaldaien ..."

    def setUp(self):
        t = temp_dir(self)
        self.pkg, self.game = os.path.join(t, "pkg"), os.path.join(t, "game")
        touch(os.path.join(self.pkg, "OptiScaler.dll"), b"MZ OptiScaler build with SpecialK and ReShade options")
        touch(os.path.join(self.pkg, "OptiScaler.ini"), b"[Plugins]\r\nLoadReshade=auto\r\nLoadSpecialK=auto\r\n")
        touch(os.path.join(self.game, "game.exe"), b"game")
        touch(os.path.join(self.game, "renodx-game.addon64"), b"renodx")
        touch(os.path.join(self.game, "ReShade.ini"), b"[GENERAL]\r\n")

    def path(self, *rel):
        return os.path.join(self.game, *rel)

    def test_reshade_is_found_and_optiscaler_is_not_taken_for_it(self):
        self.assertIsNone(O.hdr_tool(self.game))
        touch(self.path("dxgi.dll"), b"MZ a manual OptiScaler, SpecialK and ReShade menus")
        self.assertIsNone(O.hdr_tool(self.game))
        touch(self.path("dxgi.dll"), self.RESHADE)
        self.assertEqual(O.hdr_tool(self.game), ("reshade", "dxgi.dll"))
        self.assertEqual(O.analyze(self.game)["hdr"], "reshade")
        touch(self.path("dxgi.dll"), self.SPECIALK)
        self.assertEqual(O.hdr_tool(self.game), ("specialk", "dxgi.dll"))
        self.assertEqual(O.analyze(self.game)["hdr"], "specialk")

    def test_optiscaler_takes_reshades_name_loads_it_and_uninstall_gives_it_back(self):
        touch(self.path("dxgi.dll"), self.RESHADE)
        before = sorted(os.listdir(self.game))
        m = O.install(self.game, "game.exe", self.pkg, [], {})
        self.assertEqual(m["proxy"], "dxgi.dll")  # the name the launch options already load
        self.assertEqual(m["reshade_from"], "dxgi.dll")
        self.assertNotIn("dxgi.dll", m["backups"])  # moved aside for OptiScaler, not hidden in a backup
        self.assertEqual(read(self.path("ReShade64.dll"), "rb"), self.RESHADE)
        self.assertTrue(read(self.path("dxgi.dll"), "rb").startswith(b"MZ OptiScaler"))
        self.assertIn("LoadReshade=true", read(self.path("OptiScaler.ini")))
        self.assertEqual(O.hdr_tool(self.game), ("reshade", "ReShade64.dll"))  # our own dxgi.dll isn't read
        O.uninstall(self.game)
        self.assertEqual(sorted(os.listdir(self.game)), before)
        self.assertEqual(read(self.path("dxgi.dll"), "rb"), self.RESHADE)

    def test_reshade_under_d3d11_is_shared_while_optiscaler_takes_dxgi(self):
        touch(self.path("d3d11.dll"), self.RESHADE)
        m = O.install(self.game, "game.exe", self.pkg, [], {})
        self.assertEqual((m["proxy"], m["reshade_from"]), ("dxgi.dll", "d3d11.dll"))
        self.assertFalse(os.path.exists(self.path("d3d11.dll")))
        O.uninstall(self.game)
        self.assertEqual(read(self.path("d3d11.dll"), "rb"), self.RESHADE)
        self.assertFalse(os.path.exists(self.path("ReShade64.dll")))

    def test_a_retry_under_another_name_still_shares(self):
        # main.py tries the next loader name when OptiScaler didn't load: uninstall, then install with that name
        touch(self.path("dxgi.dll"), self.RESHADE)
        O.install(self.game, "game.exe", self.pkg, [], {})
        O.uninstall(self.game)
        m = O.install(self.game, "game.exe", self.pkg, [], {}, "winmm.dll")
        self.assertEqual((m["proxy"], m["reshade_from"]), ("winmm.dll", "dxgi.dll"))
        self.assertIn("LoadReshade=true", read(self.path("OptiScaler.ini")))
        O.uninstall(self.game)
        self.assertEqual(read(self.path("dxgi.dll"), "rb"), self.RESHADE)

    def test_a_game_rule_keeps_its_loader_name(self):
        os.rename(self.path("game.exe"), self.path("RDR2.exe"))
        touch(self.path("dxgi.dll"), self.RESHADE)
        m = O.install(self.game, "RDR2.exe", self.pkg, [], {})
        self.assertEqual((m["proxy"], m["reshade_from"]), ("winmm.dll", "dxgi.dll"))

    def test_reshade64_already_there_is_loaded_and_left_alone(self):
        touch(self.path("ReShade64.dll"), self.RESHADE)  # set up for OptiScaler by hand
        m = O.install(self.game, "game.exe", self.pkg, [], {})
        self.assertNotIn("reshade_from", m)
        self.assertIn("LoadReshade=true", read(self.path("OptiScaler.ini")))
        O.uninstall(self.game)
        self.assertEqual(read(self.path("ReShade64.dll"), "rb"), self.RESHADE)

    def test_reshade_twice_is_refused_untouched(self):
        touch(self.path("dxgi.dll"), self.RESHADE)
        touch(self.path("ReShade64.dll"), self.RESHADE + b" older")
        with self.assertRaises(O.InstallError):
            O.install(self.game, "game.exe", self.pkg, [], {})
        self.assertEqual(read(self.path("dxgi.dll"), "rb"), self.RESHADE)
        self.assertFalse(os.path.exists(self.path(O.META)))

    def test_a_failed_install_gives_reshade_its_name_back(self):
        touch(self.path("dxgi.dll"), self.RESHADE)
        touch(os.path.join(self.pkg, "OptiScaler", "sdk.dll"), b"sdk")
        touch(self.path("OptiScaler"), b"a file where OptiScaler needs its folder")  # the copy fails
        with self.assertRaises(O.InstallError):
            O.install(self.game, "game.exe", self.pkg, [], {})
        self.assertEqual(read(self.path("dxgi.dll"), "rb"), self.RESHADE)
        self.assertFalse(os.path.exists(self.path("ReShade64.dll")))

    def test_special_k_blocks_the_install_and_says_why(self):
        touch(self.path("dxgi.dll"), self.SPECIALK)
        with self.assertRaises(O.InstallError) as e:
            O.install(self.game, "game.exe", self.pkg, [], {})
        self.assertIn("Special K", str(e.exception))
        self.assertEqual(read(self.path("dxgi.dll"), "rb"), self.SPECIALK)
        self.assertFalse(os.path.exists(self.path(O.META)))

    def test_repair_keeps_loading_reshade(self):
        touch(self.path("dxgi.dll"), self.RESHADE)
        O.install(self.game, "game.exe", self.pkg, [], {})
        os.remove(self.path("OptiScaler.ini"))
        O.repair(self.game, self.pkg, [], {})
        self.assertIn("LoadReshade=true", read(self.path("OptiScaler.ini")))

    def test_the_card_says_so(self):
        self.assertIn("ReShade is in this game", O.tips("game.exe", ["FSR 3.1"], hdr="reshade"))
        self.assertIn("Special K is in this game", O.tips("game.exe", ["FSR 3.1"], hdr="specialk"))
        self.assertNotIn("ReShade", O.tips("game.exe", ["FSR 3.1"]))


class Tested(unittest.TestCase):
    """The card's "Tested by Steam Machine Life" line, matched on Steam's store names."""

    def test_store_names_match_with_the_upscaler_that_was_picked(self):
        self.assertIn("with DLSS picked", O.tested_text("Palworld / パルワールド", "Palworld-Win64-Shipping.exe"))
        self.assertIn("with DLSS picked", O.tested_text("Control Ultimate Edition", "Control_DX12.exe"))
        self.assertIn("with FSR 2 picked", O.tested_text("UNCHARTED™: Legacy of Thieves Collection", "u4.exe"))
        self.assertIn("with DLSS picked", O.tested_text("STAR WARS Jedi: Survivor™", "JediSurvivor.exe"))
        self.assertIn("DLSS-IV", O.tested_text("Grand Theft Auto IV: The Complete Edition", "dlssiv-helper.exe"))
        self.assertIn("with FSR picked", O.tested_text("Monster Hunter Wilds", "MonsterHunterWilds.exe"))
        self.assertTrue(all(TESTED_PICK for TESTED_PICK in O.TESTED.values()), "every tested game names its pick")

    def test_other_games_and_their_sequels_get_nothing(self):
        for name, exe in (("God of War Ragnarök", "GoWR.exe"), ("Control 2", "Control2.exe"),
                          ("Red Dead Redemption", "RDR.exe"), ("Dying Light", "DyingLightGame.exe"),
                          ("Some Other Game", "game.exe")):
            self.assertEqual(O.tested_text(name, exe), "", name)


class Tips(unittest.TestCase):
    def test_the_widgets_card_lines(self):
        self.assertIn("No upscaler files found", O.tips("game.exe", []))
        self.assertEqual(O.tips("game.exe", ["DLSS", "XeSS"]), "")  # the panel says "pick DLSS or XeSS, not its own FSR"
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

    def test_sizes_match_the_widget_and_leave_the_menu_font_alone(self):
        # the widget's InstallConfig.OverlayLookFor: Large is 2.6% of the height, the font itself up to 48 px
        self.assertEqual(O.overlay_look("large", 1080), ("28", "1.00"))
        self.assertEqual(O.overlay_look("large", 2160), ("48", "1.17"))
        self.assertEqual(O.overlay_look("small", 1080), ("16", "1.01"))
        self.assertEqual(O.overlay_look("max", 2160), ("48", "2.25"))
        sizes = [O.overlay_look(k, 2160) for k in ("small", "medium", "large", "xlarge", "huge", "max")]
        px = [int(f) * float(s) for f, s in sizes]
        self.assertEqual(px, sorted(px))
        # a build without FpsOverlayFontSize: only FpsScale, over the 14 px menu font
        self.assertEqual(O.overlay_look("large", 1080, font_known=False), ("auto", "2.01"))
        on = dict(((s, k), v) for s, k, v in O.ini_settings(overlay=True, overlay_size="large", height=2160))
        self.assertEqual((on[("Menu", "FpsOverlayFontSize")], on[("Menu", "FpsScale")]), ("48", "1.17"))
        self.assertEqual(on[("Menu", "FontSize")], "auto", "OptiScaler's whole menu keeps its own font")

    def test_a_game_set_up_before_gets_its_menu_font_back(self):
        t = temp_dir(self)
        game, pkg = os.path.join(t, "game"), os.path.join(t, "pkg")
        touch(os.path.join(game, "game.exe"), b"game")
        touch(os.path.join(pkg, "OptiScaler.dll"), b"MZ OptiScaler")
        touch(os.path.join(pkg, "OptiScaler.ini"), b"[Menu]\r\nFontSize=auto\r\nFpsScale=auto\r\n"
              b"; FPS Overlay font size in pixels, before FpsScale\r\nFpsOverlayFontSize=auto\r\n")
        O.install(game, "game.exe", pkg, [], {"overlay": True})
        ini = os.path.join(game, "OptiScaler.ini")
        O.set_ini(ini, [("Menu", "FontSize", "64")])  # what 2.2.35 wrote
        self.assertTrue(O.overlay_font_known(game))
        O.apply_settings(game, {"overlay": True, "overlay_size": "large", "height": 1080})
        text = read(ini)
        self.assertIn("FontSize=auto", text)
        self.assertIn("FpsOverlayFontSize=28", text)
        # an ini from an older build (kept through updates): the DLL decides, read once per build
        with open(ini, encoding="utf-8") as f:
            older = f.read().replace("; FPS Overlay font size in pixels, before FpsScale", "")
        with open(ini, "w", encoding="utf-8", newline="") as f:
            f.write(older)
        dll = os.path.join(game, O.load_manifest(game)["proxy"])
        touch(dll, b"MZ OptiScaler FpsOverlayFontSize")
        self.assertTrue(O.overlay_font_known(game), "a newer DLL under an older ini")
        touch(dll, b"MZ OptiScaler")  # same build: the kept answer, the DLL isn't read again
        self.assertTrue(O.overlay_font_known(game))
        m = O.load_manifest(game)
        m["opti_build"] = "OptiScaler_older"  # another build: read again
        O._save(os.path.join(game, O.META), m)
        self.assertFalse(O.overlay_font_known(game))
        O.apply_settings(game, {"overlay": True, "overlay_size": "large", "height": 1080})
        self.assertIn("FpsOverlayFontSize=auto", read(ini))
        self.assertIn("FpsScale=2.01", read(ini))

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
        self.assertEqual(O.verdict(LITE_SESSION)[0], "lite")
        self.assertEqual(O.verdict("Loaded OptiScaler/amdxcffx64.dll")[0], "fsr4")
        self.assertEqual(O.verdict("FFX upscaler: render 1280x720 output 2560x1440")[0], "fsr3")
        self.assertEqual(O.verdict("OptiScaler v10 started")[0], "waiting")
        self.assertEqual(O.verdict("this GPU can't run any FSR 4 model")[0], "unsupported")

    def test_the_lite_name_alone_is_not_proof(self):
        # Newer nightlies name the Lite provider as they load, before any game upscales (DOA6 Last Round: the game
        # never started an upscaler and AMD's file never loaded, yet the old check said Lite ran).
        hooked_only = (HOOK_LINE.replace("amdxcffx64.dll", "amd_fidelityfx_upscaler_dx12.dll")
                       + "[I] Init done\n[W] Config::CheckUpscalerFiles nvngx.dll not found!\n")
        self.assertFalse(O.lite_ran(hooked_only))
        self.assertEqual(O.verdict(hooked_only)[0], "waiting")
        # AMD's file loaded but no upscaler yet: not proven
        self.assertFalse(O.lite_ran(HOOK_LINE + LOADED_LINE))
        # AMD's file failed to load: the resolutions come from FSR 3
        failed = (HOOK_LINE.replace("amdxcffx64.dll", "amd_fidelityfx_upscaler_dx12.dll")
                  + "[E] Failed to load amdxcffx64.dll\n" + RES_LINE)
        self.assertFalse(O.lite_ran(failed))
        self.assertEqual(O.verdict(failed)[0], "fsr3")
        self.assertTrue(O.lite_ran(LITE_SESSION))
        # an older nightly that logged only the driver context
        self.assertTrue(O.lite_ran(HOOK_LINE + "[I] FSR4DriverDll::QueryProvider amdxcffx64.dll provider for 10000: 4.1.2 *\n"
                                   "[I] FSR4DriverProviderDx12::CreateContext Created driver upscaler context, result: The operation was successful.\n"))


# lines from real OptiScaler.logs on the Steam Machine (Resident Evil Requiem, 2026-11-08 nightly)
HOOK_LINE = "[I] FSR4Models::Hook Hooked the support check of ffxProvider_FSR4Lite_Int8 in amdxcffx64.dll\n"
LOADED_LINE = ("[I] `anonymous-namespace'::LoadDriverDll amdxcffx64.dll loaded from Z:\\home\\deck\\.local\\share\\Steam"
               "\\steamapps\\common\\RESIDENT EVIL requiem BIOHAZARD requiem\\OptiScaler\\amdxcffx64.dll\n")
RES_LINE = "[I] IFeature::SetInitParameters Render Resolution: 1920x1080, Display Resolution 3840x2160, Quality: 0\n"
LITE_SESSION = HOOK_LINE + LOADED_LINE + "[I] ffxCreateContext_Dx12 context created: 1EE8\n" + RES_LINE
# 007 First Light (2026-11-09 nightly): this line, thousands of times a second, after the Lite proof
FLOOD = ("[00:50:38.250975] [I] Amdxc64Hooks::hkAmdExtD3DCreateInterface IAmdExtD3DFactory queried, returning custom "
         "AmdExtD3DFactory: 5B1BB270, real: 6FFFE82A3070\n")


class ManualInstall(unittest.TestCase):
    def setUp(self):
        t = temp_dir(self)
        self.game, self.backup = os.path.join(t, "game"), os.path.join(t, "backup")
        touch(os.path.join(self.game, "game.exe"), b"game")
        touch(os.path.join(self.game, "dxgi.dll"), b"MZ" + b"\0" * 5000 + b"OptiScaler v0.7" + b"\0" * 100)
        touch(os.path.join(self.game, "OptiScaler.ini"), b"[Upscalers]\n")
        touch(os.path.join(self.game, "OptiScaler.log"), b"log")
        touch(os.path.join(self.game, "OptiScaler", "amdxcffx64.dll"), b"amd")
        touch(os.path.join(self.game, "nvapi64.dll"), b"MZ fakenvapi")
        # the game's own files, which a manual install also tends to have: they stay
        for own in ("winmm.dll", "libxess.dll", "amd_fidelityfx_dx12.dll", "nvngx_dlss.dll"):
            touch(os.path.join(self.game, own), b"MZ the game's own")

    def test_only_optiscalers_files_move_and_nothing_is_deleted(self):
        self.assertTrue(O.analyze(self.game)["manual_optiscaler"])
        moved = O.remove_manual(self.game, self.backup)
        self.assertEqual(sorted(moved), ["OptiScaler", "OptiScaler.ini", "OptiScaler.log", "dxgi.dll", "nvapi64.dll"])
        self.assertEqual(sorted(os.listdir(self.game)),
                         ["amd_fidelityfx_dx12.dll", "game.exe", "libxess.dll", "nvngx_dlss.dll", "winmm.dll"])
        self.assertTrue(os.path.isfile(os.path.join(self.backup, "OptiScaler", "amdxcffx64.dll")))
        self.assertIn(self.game, read(os.path.join(self.backup, "MOVED-FROM.txt")))
        self.assertFalse(O.analyze(self.game)["manual_optiscaler"])
        with self.assertRaises(O.InstallError):
            O.remove_manual(self.game, self.backup)

    def test_a_leftover_optiscaler_dll_counts_without_its_ini_but_a_lone_log_does_not(self):
        for name in ("OptiScaler.ini", "nvapi64.dll"):
            os.remove(os.path.join(self.game, name))
        shutil.rmtree(os.path.join(self.game, "OptiScaler"))
        self.assertTrue(O.analyze(self.game)["manual_optiscaler"], "dxgi.dll is OptiScaler's")
        os.remove(os.path.join(self.game, "dxgi.dll"))
        self.assertFalse(O.analyze(self.game)["manual_optiscaler"], "only OptiScaler.log is left")
        self.assertEqual(O.manual_files(self.game), ["OptiScaler.log"])

    def test_our_own_setup_is_never_taken_for_a_manual_one(self):
        touch(os.path.join(self.game, O.META, "manifest.json"), b"{}")
        self.assertEqual(O.manual_files(self.game), [])
        with self.assertRaises(O.InstallError):
            O.remove_manual(self.game, self.backup)
        self.assertTrue(os.path.isfile(os.path.join(self.game, "dxgi.dll")))


def pe(machine):
    """A minimal Windows exe header: MZ, the PE offset at 0x3C, then PE\\0\\0 and the machine type."""
    head = bytearray(b"MZ" + b"\0" * 0x7E)
    head[0x3C:0x40] = (0x80).to_bytes(4, "little")
    return bytes(head) + b"PE\0\0" + machine.to_bytes(2, "little") + b"\0" * 200


class Bits32AndHelpers(unittest.TestCase):
    def test_a_32_bit_exe_is_told_apart(self):
        d = temp_dir(self)
        touch(os.path.join(d, "old.exe"), pe(0x14C))
        touch(os.path.join(d, "new.exe"), pe(0x8664))
        touch(os.path.join(d, "text.exe"), b"not an exe")
        self.assertTrue(O.is_32bit(os.path.join(d, "old.exe")))
        self.assertFalse(O.is_32bit(os.path.join(d, "new.exe")))
        self.assertFalse(O.is_32bit(os.path.join(d, "text.exe")))
        self.assertFalse(O.is_32bit(os.path.join(d, "missing.exe")))

    def test_gta_iv_alone_is_blocked_and_with_dlss_iv_set_up_next_to_its_helper(self):
        game = os.path.join(temp_dir(self), "GTAIV")
        touch(os.path.join(game, "GTAIV.exe"), pe(0x14C) + b"\0" * 50000)
        touch(os.path.join(game, "PlayGTAIV.exe"), pe(0x14C))
        alone = O.analyze(game)
        self.assertEqual(alone["exe_name"], "GTAIV.exe")
        self.assertTrue(alone["bits32"])
        # DLSS-IV: its 64-bit helper upscales, and its folder ships the upscalers
        touch(os.path.join(game, "DLSSIV", "dlssiv-helper.exe"), pe(0x8664))
        for dll in ("nvngx_dlss.dll", "amd_fidelityfx_upscaler_dx12.dll", "libxess.dll"):
            touch(os.path.join(game, "DLSSIV", dll))
        modded = O.analyze(game)
        self.assertEqual((modded["exe_dir"], modded["exe_name"]), (os.path.join(game, "DLSSIV"), "dlssiv-helper.exe"))
        self.assertFalse(modded["bits32"])
        self.assertEqual(modded["host"], "DLSS-IV")
        self.assertEqual(modded["upscalers"], ["DLSS", "FSR 3.1", "XeSS"])
        self.assertIn("DLSS-IV's DLSS and FSR both run FSR 4.1.2 Lite", O.tips("dlssiv-helper.exe", modded["upscalers"]))
        # a remembered exe (GTAIV.exe seen running) still goes to the helper
        self.assertEqual(O.analyze(game, os.path.join(game, "GTAIV.exe"))["exe_name"], "dlssiv-helper.exe")

    def test_the_watcher_never_takes_a_32_bit_program_for_the_game(self):
        d = temp_dir(self)
        touch(os.path.join(d, "GTAIV.exe"), pe(0x14C))
        touch(os.path.join(d, "dlssiv-helper.exe"), pe(0x8664))
        seen = [{"path": os.path.join(d, "GTAIV.exe"), "mb": 3000, "graphics": True},
                {"path": os.path.join(d, "dlssiv-helper.exe"), "mb": 300, "graphics": True}]
        self.assertEqual(O.pick_game(seen), (os.path.join(d, "dlssiv-helper.exe"), 300))
        self.assertEqual(O.pick_game(seen[:1]), (None, 0))


class Light(unittest.TestCase):
    """What runs over and over on the Steam Machine stays cheap."""

    def test_an_ini_is_only_written_when_something_changes(self):
        ini = os.path.join(temp_dir(self), "OptiScaler.ini")
        O.set_ini(ini, [("Menu", "ShowFps", "true")])
        before = os.stat(ini).st_mtime_ns
        os.utime(ini, ns=(before - 10**9, before - 10**9))
        O.set_ini(ini, [("Menu", "ShowFps", "true")])
        self.assertEqual(os.stat(ini).st_mtime_ns, before - 10**9, "same values: no write")
        O.set_ini(ini, [("Menu", "ShowFps", "false")])
        self.assertIn("ShowFps=false", read(ini))

    def test_every_running_games_folder_from_one_look_at_the_processes(self):
        proc = temp_dir(self)

        def process(pid, *args, cwd=None):
            touch(os.path.join(proc, str(pid), "cmdline"), "\0".join(args).encode() + b"\0")
            if cwd:
                os.symlink(cwd, os.path.join(proc, str(pid), "cwd"))
        process(100, "S:\\steamapps\\common\\Crimson Desert\\bin64\\CrimsonDesert.exe")
        process(101, "/home/deck/.local/share/Steam/steamapps/common/Palworld/Pal/Binaries/Win64/Palworld.exe", "-x")
        process(102, "/usr/bin/bash")
        if os.name == "posix":
            process(103, "PBZ.exe", cwd="/home/deck/.local/share/Steam/steamapps/common/PBZ/platform/steam")
        found = O.running_folders(proc)
        self.assertIn("crimson desert", found)
        self.assertIn("palworld", found)
        if os.name == "posix":
            self.assertIn("pbz", found)
        self.assertEqual(O.running_folders(os.path.join(proc, "missing")), set())


class FloodedLog(unittest.TestCase):
    def setUp(self):
        self.dir = temp_dir(self)
        self.log = os.path.join(self.dir, "OptiScaler.log")
        O._logs.clear()

    def write(self, text, mode="w"):
        with open(self.log, mode, encoding="utf-8", newline="") as f:
            f.write(text)

    def test_the_lite_proof_is_found_under_a_flood(self):
        self.write("[00:49:15.154621] [I] OptiScaler v10 session 1\n" + LITE_SESSION + FLOOD * 60_000)  # ~8 MB
        self.assertGreater(os.path.getsize(self.log), 4 * 1024 * 1024)
        log = O.read_log(self.dir)
        self.assertEqual(O.verdict(log)[0], "lite")
        self.assertEqual(log.count("hkAmdExtD3DCreateInterface"), O.LOG_REPEATS)
        self.assertIn(f"{60_000 - O.LOG_REPEATS} repeated lines left out", O.log_note(self.dir))
        # later lines are read without starting over
        self.write(FLOOD * 10 + "[00:51:00.000000] [I] later line\n", "a")
        self.assertIn("later line", O.read_log(self.dir))
        self.assertIn(f"{60_010 - O.LOG_REPEATS} repeated", O.log_note(self.dir))

    def test_a_new_session_starts_over(self):
        self.write("[00:49:15.154621] [I] OptiScaler v10 session 1\n" + LITE_SESSION)
        self.assertEqual(O.verdict(O.read_log(self.dir))[0], "lite")
        self.write("[01:12:00.000000] [I] OptiScaler v10 session 2\n" + "[I] Init done\n" * 3)
        self.assertEqual(O.verdict(O.read_log(self.dir))[0], "waiting")

    def test_a_huge_log_is_emptied_and_what_mattered_stays(self):
        self.write("[00:49:15.154621] [I] OptiScaler v10 session 1\n" + LITE_SESSION + FLOOD * 1000)
        self.assertFalse(O.trim_log(self.dir, cap=10 * 1024 * 1024))
        self.assertTrue(O.trim_log(self.dir, cap=64 * 1024))
        self.assertEqual(os.path.getsize(self.log), 0)
        self.write(FLOOD * 5 + "[00:55:00.000000] [I] after the trim\n", "a")  # OptiScaler keeps writing
        log = O.read_log(self.dir)
        self.assertEqual(O.verdict(log)[0], "lite")
        self.assertIn("after the trim", log)
        self.assertIn("so it was emptied here", log)
        self.assertIn("emptied 1 times", O.log_note(self.dir))
        # the next session is its own
        self.write("[02:00:00.000000] [I] OptiScaler v10 session 2\n[I] Init done\n")
        self.assertEqual(O.verdict(O.read_log(self.dir))[0], "waiting")

    def test_a_long_log_keeps_its_start_and_end(self):
        lines = "".join(f"[00:49:15.{i:06d}] [I] line number {i}\n" for i in range(60_000))
        self.write(LITE_SESSION + lines)
        log = O.read_log(self.dir, limit=64 * 1024)
        self.assertLessEqual(len(log), 64 * 1024 + 100)
        self.assertEqual(O.verdict(log)[0], "lite")
        self.assertIn("line number 59999", log)
        self.assertIn("part of the log left out here", log)

    def test_no_log(self):
        self.assertEqual(O.read_log(self.dir), "")
        self.assertFalse(O.trim_log(self.dir))
        self.assertEqual(O.log_note(self.dir), "")


if __name__ == "__main__":
    unittest.main()


class SevenZip(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "the execute bit is POSIX")
    def test_a_non_executable_7zip_is_copied_somewhere_it_can_run(self):
        import stat
        import sml_assets
        d = temp_dir(self)
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


class ExeRunning(unittest.TestCase):
    def test_a_non_steam_exe_is_seen_running_under_proton(self):
        proc = temp_dir(self)
        touch(os.path.join(proc, "100", "cmdline"),
              b"Z:\\home\\deck\\Games\\God Of War\\GoW.exe\0-windowed\0")
        touch(os.path.join(proc, "101", "cmdline"), b"/usr/bin/bash\0")
        self.assertTrue(O.exe_running("/home/deck/Games/God Of War/GoW.exe", proc))
        self.assertTrue(O.exe_running("/home/deck/Games/God of War/gow.exe", proc))
        self.assertFalse(O.exe_running("/home/deck/Games/Other/GoW.exe", proc))
        self.assertFalse(O.exe_running("/home/deck/Games/God Of War", proc))
