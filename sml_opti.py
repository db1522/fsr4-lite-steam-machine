# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Steam Machine Life
"""FSR 4.1 Lite's one method: OptiScaler in the game's exe folder, set up the way the FSR 4.1 Lite widget for Windows
sets it up (github.com/db1522/fsr4-lite-rog-ally): the game's upscaler goes through FidelityFX, FSR 4 is forced onto
the INT8 Lite model, frame generation stays off, and OptiScaler's log tells whether Lite ran.

Everything here is plain file work on the game's folder, recorded in a manifest so an uninstall puts back exactly
what was there."""
import functools
import hashlib
import json
import os
import posixpath
import re
import shutil

# ---- what the widget writes into OptiScaler.ini (InstallConfig.Base) ----
INI_BASE = [
    ("Upscalers", "Dx12Upscaler", "ffx"),
    ("Upscalers", "Dx11Upscaler", "ffx_12"),
    ("Upscalers", "VulkanUpscaler", "ffx_12"),  # Vulkan through OptiScaler's DX12 bridge: its DX12 list puts FSR 4 first
    ("FSR", "Fsr4GpuSupport", "4"),  # INT8 Lite support on RDNA 3 (the Z1 and the Steam Machine alike)
    ("FSR", "Fsr4Model", "3"),  # the INT8 Lite model
    ("FrameGen", "Enabled", "false"),  # upscaling only
    ("Log", "LogToFile", "true"),  # OptiScaler.log next to the exe, fresh each session: how Lite is confirmed
    ("Log", "LogLevel", "2"),
    ("Menu", "DisableSplash", "true"),
]


# OptiScaler's overlay, sized for a TV across the room: each size is a share of the game's output height, a step
# larger than the Windows widget's handheld sizes. The pinned OptiScaler build draws the overlay with its menu font, so
# FontSize sets the text size itself (sharp at any size) and FpsScale only grows it further.
OVERLAY_SIZES = {"small": 0.022, "medium": 0.028, "large": 0.035, "xlarge": 0.045, "huge": 0.058}
OVERLAY_POSITIONS = {"topleft": "0", "topright": "1", "bottomleft": "2", "bottomright": "3"}
DEFAULT_HEIGHT = 2160  # a 4K TV, until OptiScaler's log tells the game's real output height


def overlay_look(size, height):
    """(FontSize, FpsScale) for an overlay size on a game drawing at height pixels."""
    share = OVERLAY_SIZES.get(size, OVERLAY_SIZES["large"])
    target = share * min(max(int(height or DEFAULT_HEIGHT), 480), 4320)
    font = min(max(round(target), 14), 64)
    scale = min(max(round(target / font, 2), 1.0), 3.0)
    return str(font), f"{scale:.2f}"


def ini_settings(watermark=False, overlay=False, overlay_size="large", overlay_pos="topleft", height=None):
    values = list(INI_BASE) + [("FSR", "Fsr4EnableWatermark", "true" if watermark else "false")]
    # OptiScaler's FPS overlay, "Simple" layout: FPS with the upscaler ("FSR3 -> FSR 4.1.2") and render -> output
    font, scale = overlay_look(overlay_size, height)
    values += [
        ("Menu", "ShowFps", "true" if overlay else "auto"),
        ("Menu", "FpsOverlayType", "1" if overlay else "auto"),
        ("Menu", "FpsOverlayShowRatio", "true" if overlay else "auto"),
        ("Menu", "FpsOverlayHorizontal", "false" if overlay else "auto"),
        ("Menu", "FpsOverlayPos", OVERLAY_POSITIONS.get(overlay_pos, "0") if overlay else "auto"),
        ("Menu", "FpsScale", scale if overlay else "auto"),
        ("Menu", "FontSize", font if overlay else "auto"),
    ]
    return values


def display_height(log):
    """The game's output height from its OptiScaler.log, or None before it has run with OptiScaler."""
    found = re.findall(r"color_out extents \((\d+),(\d+),(\d+),(\d+)\)", log)
    if found:
        return int(found[-1][3])
    found = re.findall(r"Display Resolution:?\s*(\d+)x(\d+)", log)
    return int(found[-1][1]) if found else None


# ---- game analysis (the widget's GameAnalyzer) ----
UPSCALER_DLLS = {
    "amd_fidelityfx_dx12.dll": "FSR 3.1", "amd_fidelityfx_upscaler_dx12.dll": "FSR 3.1",
    "amd_fidelityfx_loader_dx12.dll": "FSR 3.1", "amd_fidelityfx_vk.dll": "FSR 3.1",
    "ffx_fsr2_api_x64.dll": "FSR 2", "ffx_fsr2_api_dx12_x64.dll": "FSR 2", "ffx_fsr2_api_vk_x64.dll": "FSR 2",
    "nvngx_dlss.dll": "DLSS", "sl.dlss.dll": "DLSS", "libxess.dll": "XeSS", "libxess_dx11.dll": "XeSS",
}
ANTICHEAT_DIRS = {"easyanticheat": "Easy Anti-Cheat", "easyanticheat_eos": "Easy Anti-Cheat", "battleye": "BattlEye",
                  "eaanticheat": "EA Javelin anti-cheat", "gameguard": "nProtect GameGuard", "xigncode": "XIGNCODE3",
                  "anticheatexpert": "Anti-Cheat Expert (ACE)", "equ8": "EQU8"}
ANTICHEAT_FILES = {
    "easyanticheat_x64.dll": "Easy Anti-Cheat", "easyanticheat_eos_setup.exe": "Easy Anti-Cheat",
    "start_protected_game.exe": "Easy Anti-Cheat", "beclient_x64.dll": "BattlEye", "beservice_x64.exe": "BattlEye",
    "beservice.exe": "BattlEye", "eaanticheat.gameservicelauncher.exe": "EA Javelin anti-cheat",
    "eaanticheat.installer.exe": "EA Javelin anti-cheat", "randgrid.sys": "Ricochet anti-cheat",
    "gamemon.des": "nProtect GameGuard", "x3.xem": "XIGNCODE3", "ace-base.sys": "Anti-Cheat Expert (ACE)",
    "mhyprot2.sys": "HoYoverse anti-cheat", "mhyprot3.sys": "HoYoverse anti-cheat",
    "hoyokprotect.sys": "HoYoverse anti-cheat", "pbsvc.exe": "PunkBuster", "pbcl.dll": "PunkBuster",
    "cs2.exe": "Valve Anti-Cheat", "dota2.exe": "Valve Anti-Cheat", "cod.exe": "Ricochet anti-cheat",
    "blackops6.exe": "Ricochet anti-cheat", "modernwarfare.exe": "Ricochet anti-cheat",
    # anti-cheat that lives outside the game folder, recognised by the game's exe (the widget's list)
    "valorant-win64-shipping.exe": "Riot Vanguard", "league of legends.exe": "Riot Vanguard",
    "overwatch.exe": "Blizzard anti-cheat", "genshinimpact.exe": "HoYoverse anti-cheat",
    "starrail.exe": "HoYoverse anti-cheat", "zenlesszonezero.exe": "HoYoverse anti-cheat",
}
NOT_GAME_EXE = ("crashreport", "crashhandler", "crashpad", "unrealcefsubprocess", "cefprocess", "unitycrashhandler",
                "uninst", "setup", "vc_redist", "vcredist", "dxsetup", "ue4prereq", "ueprereq", "easyanticheat",
                "start_protected_game", "redist", "installer", "dotnet", "battleye", "beservice", "launcher")
SKIP_DIRS = {"_commonredist", "__redist", "redist", "redistributables", "directx", "support", "prerequisites",
             "optiscaler", ".fsr4lite", "paks", "movies", "content"}
MAX_DEPTH = 8
# Unreal keeps DLSS, Streamline and FSR plugin DLLs deep in Plugins folders, e.g.
# Engine/Plugins/Marketplace/Nvidia/DLSS/Source/Binaries/ThirdParty/Win64 (Phantom Blade Zero). Like the widget's
# GameAnalyzer: a Plugins folder within 3 levels of the game folder is searched 7 folders further down.
PLUGINS_DIR, PLUGINS_WITHIN, PLUGINS_DEPTH = "plugins", 3, 7

# Games the OptiScaler community has a setup for: the loader name they need and a tip (the widget's GameRules)
LOADER_RULES = {"rdr2.exe": "winmm.dll", "enshrouded.exe": "winmm.dll"}
GAME_TIPS = {
    # OptiScaler wiki: works as winmm.dll with FSR 2 inputs on DirectX 12; Vulkan, the game's default, crashes
    "rdr2.exe": "In Red Dead Redemption 2, set Graphics API to DirectX 12 (Vulkan crashes with OptiScaler), then pick "
                "FSR 2 as the upscaler.",
    # OptiScaler's Compatibility List: DLSS input; the game only lists DLSS after a restart with its upscaler off
    "enshrouded.exe": "In Enshrouded, pick DLSS as the upscaler. If DLSS isn't listed, turn the upscaler off, restart "
                      "the game, then pick DLSS.",
}
# Capcom RE Engine games where OptiScaler needs REFramework (hooks the engine early, past Capcom's integrity checks):
# the "Requires REFramework" rows of OptiScaler's community Compatibility List
# (github.com/optiscaler/OptiScaler/wiki/Compatibility-List), copied on 2026-11-07. The widget reads the live list;
# the plugin pins it like its downloads. Plus the widget's exe rule for Dragon's Dogma 2 (its row says "Check Wiki").
REFRAMEWORK_GAMES = ("Monster Hunter Wilds", "Onimusha: Way of the Sword", "PRAGMATA", "Resident Evil 9 Requiem",
                     "Devil May Cry 5", "Resident Evil 2 (2019)", "Resident Evil 3 (2020)", "Resident Evil 4 (2023)",
                     "Resident Evil 7 Biohazard", "Resident Evil 8 Village")
REFRAMEWORK_EXES = {"dd2.exe"}
REFRAMEWORK_TIP = "This game needs REFramework, so the plugin adds it too."
REFRAMEWORK_CONFIG = "re2_fw_config.txt"  # the same name in every game
NO_UPSCALER_TIP = ("No upscaler files found. Many games build FSR 2 or 3 into the game itself, so the plugin tells "
                   "OptiScaler to search for it (the game loads a little slower). Install, restart the game and turn on "
                   "FSR in its settings. FSR 1 can't be upgraded.")
# Names OptiScaler can load under, in order of preference (OptiScaler's own setup script order)
PROXY_NAMES = ("dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "d3d12.dll", "wininet.dll", "winhttp.dll")
SKIP_PACKAGE_FILES = {"setup_windows.bat", "setup_linux.sh", "remove optiscaler.bat", "remove_optiscaler.bat",
                      "streamlined_fetcher_windows.bat"}
SUBFOLDER = "OptiScaler"  # v10 reads the FSR 4 files from here, next to the exe
META = ".fsr4lite"  # next to the exe: backups of anything an install replaced
DX12_FSR4, VK_FSR4 = "amdxcffx64.dll", "amdvkffx64.dll"


def _walk(root):
    base = root.rstrip(os.sep).count(os.sep)
    seen = set()
    limits = {}  # folder -> how deep (from root) the search may go below it, raised inside Unreal's Plugins folders
    for dirpath, dirs, files in os.walk(root, followlinks=True):
        real = os.path.realpath(dirpath)
        if real in seen:
            dirs[:] = []
            continue
        seen.add(real)
        depth = dirpath.count(os.sep) - base
        limit = limits.pop(dirpath, MAX_DEPTH)
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
        if depth >= limit:
            dirs[:] = []
        for d in dirs:
            deeper = depth + 1 + PLUGINS_DEPTH if d.lower() == PLUGINS_DIR and depth + 1 <= PLUGINS_WITHIN else 0
            limits[os.path.join(dirpath, d)] = max(limit, deeper)
        yield dirpath, dirs, files


def blocked_message(anticheat):
    """The FSR 4.1 Lite widget's words for a game with anti-cheat."""
    return f"{anticheat} found. Injecting OptiScaler could get your account banned, so installs are blocked."


def _is_game_exe(name):
    low = name.lower()
    return low.endswith(".exe") and not any(p in low for p in NOT_GAME_EXE)


def analyze(install_dir, exe_path=None):
    """{exe_dir, exe_name, unreal, upscalers, anticheat, manual_optiscaler} for one game, or None without an exe."""
    upscalers, anticheat, candidates = set(), None, []
    for dirpath, dirs, files in _walk(install_dir):
        for d in dirs:
            anticheat = anticheat or ANTICHEAT_DIRS.get(d.lower())
        for f in files:
            low = f.lower()
            if low in UPSCALER_DLLS:
                upscalers.add(UPSCALER_DLLS[low])
            anticheat = anticheat or ANTICHEAT_FILES.get(low)
            if _is_game_exe(f):  # (an exe listed above, cs2.exe say, was matched on the line before)
                candidates.append((dirpath, f))
    if exe_path and os.path.isfile(exe_path):
        exe_dir, exe_name = os.path.dirname(exe_path), os.path.basename(exe_path)
    else:
        if not candidates:
            return None
        # Unreal: the root exe only launches <Project>/Binaries/Win64/<Project>-Win64-Shipping.exe, which is where
        # OptiScaler has to go. Otherwise the shallowest real exe, largest first (launchers are small).
        def rank(c):
            path = os.path.join(*c)
            parts = c[0].lower().split(os.sep)
            unreal = parts[-2:] in (["binaries", "win64"], ["binaries", "wingdk"])
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            return (not ("shipping" in c[1].lower() and unreal), not unreal, c[0].count(os.sep), -size)
        exe_dir, exe_name = min(candidates, key=rank)
    anticheat = anticheat or ANTICHEAT_FILES.get(exe_name.lower())
    parts = exe_dir.lower().split(os.sep)
    return {
        "exe_dir": exe_dir, "exe_name": exe_name,
        "unreal": parts[-2:] in (["binaries", "win64"], ["binaries", "wingdk"]),
        "upscalers": sorted(upscalers), "anticheat": anticheat or "",
        "manual_optiscaler": _manual_optiscaler(exe_dir),
    }


def _manual_optiscaler(exe_dir):
    """OptiScaler already there from somewhere else (not our install): left alone."""
    if os.path.isfile(os.path.join(exe_dir, META, "manifest.json")):
        return False
    return os.path.isfile(os.path.join(exe_dir, "OptiScaler.ini"))


_ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}
_EDITIONS = ("directors cut", "director's cut", "ultimate edition", "definitive edition", "complete edition",
             "deluxe edition", "game of the year edition", "goty edition", "remastered", "enhanced edition",
             "anniversary edition", "standard edition", "gold edition", "premium edition")


def name_key(name):
    """The widget's CompatList.Key: letters and digits only, lower case, Roman numerals II to IX as numbers."""
    import unicodedata
    s = re.sub(r"\b(ix|viii|vii|vi|iv|v|iii|ii)\b", lambda m: _ROMAN[m.group(0)], name.lower())
    return "".join(c for c in unicodedata.normalize("NFKD", s) if c.isalnum())


def base_key(name):
    """The widget's CompatList.BaseKey: no edition words, years in brackets or trademark signs."""
    s = re.sub(r"\((19|20)\d\d\)", " ", name.lower().replace("’", "'"))
    for w in _EDITIONS:
        s = s.replace(w, " ")
    return name_key(re.sub("[™®©]", " ", s))


@functools.lru_cache(maxsize=4)
def _name_index(names):
    """Lookup tables for find_name, built once per list: exact keys, loose keys, and names with exactly one number
    keyed without it ("Resident Evil 9 Requiem" -> "residentevilrequiem", "9")."""
    exact, loose, no_number = {}, {}, {}
    for n in names:
        exact.setdefault(name_key(n), n)
        b = base_key(n)
        if len(b) >= 4:
            loose.setdefault(b, n)
        numbers = re.findall(r"\b\d+\b", n)
        if len(numbers) == 1:
            k = base_key(re.sub(r"\b\d+\b", " ", n))
            if len(k) >= 6:
                no_number.setdefault(k, []).append((n, numbers[0]))
    return exact, loose, no_number


def find_name(names, game_name, exe_name=None):
    """The widget's CompatList.Find over a tuple of list names: an exact or loose name match, or a store name without
    the list's number ("Resident Evil Village") when that number is in the exe (re8.exe), so "Forza Horizon 5" never
    finds "Forza Horizon 6". The list's name, or None."""
    key = name_key(game_name or "")
    if not key:
        return None
    exact, loose, no_number = _name_index(names)
    if key in exact:
        return exact[key]
    b = base_key(game_name)
    if len(b) >= 4 and b in loose:
        return loose[b]
    if not exe_name or len(b) < 6 or any(c.isdigit() for c in b) or len(no_number.get(b, [])) != 1:
        return None
    name, number = no_number[b][0]
    return name if number in re.findall(r"\d+", os.path.splitext(exe_name)[0]) else None


def needs_reframework(game_name, exe_name):
    """The widget's CompatList.NeedsREFramework over the pinned REFramework games, or the exe rule."""
    return (exe_name or "").lower() in REFRAMEWORK_EXES or find_name(REFRAMEWORK_GAMES, game_name, exe_name) is not None


# ---- OptiScaler's community Compatibility List: the snapshot in compat.json (scripts/compat.py, each release) ----

COMPAT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compat.json")


@functools.lru_cache(maxsize=1)
def _compat(path=COMPAT_PATH):
    """{list name: (status, inputs)} and the names as a tuple; empty when the file is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            games = json.load(f).get("games", [])
        table = {g[0]: (g[1], tuple(g[2])) for g in games
                 if isinstance(g, list) and len(g) == 3 and isinstance(g[0], str) and isinstance(g[2], list)}
    except (OSError, ValueError, AttributeError, TypeError):
        table = {}
    return table, tuple(table)


def compat_text(game_name, exe_name, path=COMPAT_PATH):
    """The widget's card line from the Compatibility List: a warning for "not working" or "mixed", else the upscaler
    inputs the community found working; "" for a game the list doesn't have."""
    table, names = _compat(path)
    name = find_name(names, game_name, exe_name) if names else None
    if not name:
        return ""
    state, inputs = table[name]
    if state == "not_working":
        return "OptiScaler community: not working in this game."
    if state == "mixed":
        return "OptiScaler community: mixed reports for this game."
    return "Works with: " + ", ".join(inputs) if inputs else ""


def reframework_artifacts(exe_dir):
    """REFramework's runtime files next to the exe: its reframework folder and *_fw_config / *_fw_log files."""
    try:
        names = os.listdir(exe_dir)
    except OSError:
        return []
    return sorted(n for n in names if n.lower() == "reframework" or
                  re.match(r"^(re\d*_?framework.*|[a-z0-9]+_fw_(config|log).*)\.(txt|log|json)$", n, re.I))


def tips(exe_name, upscalers, game_name=""):
    """The widget's game card lines: no upscaler files, DLSS/XeSS-only games, REFramework, and the game's own rule."""
    parts = []
    if not upscalers:
        parts.append(NO_UPSCALER_TIP)
    elif not any(u.startswith("FSR") for u in upscalers):
        parts.append(f"In this game, pick {' or '.join(upscalers)} in its graphics settings: if it also has an FSR "
                     "option, that one is built into the game and may not switch to FSR 4.1 Lite.")
    if needs_reframework(game_name, exe_name):
        parts.append(REFRAMEWORK_TIP)
    if GAME_TIPS.get((exe_name or "").lower()):
        parts.append(GAME_TIPS[(exe_name or "").lower()])
    return " ".join(parts)


def exe_imports(path):
    """DLL names a Windows exe imports or delay-loads, lower case (the widget's ExeImports). Read with seeks, so a
    150 MB Unreal exe isn't loaded whole. Never raises: an unreadable or odd file gives an empty set."""
    out = set()
    try:
        with open(path, "rb") as f:
            def at(off, n):
                f.seek(off)
                return f.read(n)

            def u32(b, i):
                return int.from_bytes(b[i:i + 4], "little")

            head = at(0, 64)
            if len(head) < 64 or head[:2] != b"MZ":
                return out
            pe = u32(head, 0x3C)
            hdr = at(pe, 24)
            if len(hdr) < 24 or hdr[:4] != b"PE\0\0":
                return out
            sections, opt_size = int.from_bytes(hdr[6:8], "little"), int.from_bytes(hdr[20:22], "little")
            opt = pe + 24
            dirs = opt + (112 if at(opt, 2) == b"\x0b\x02" else 96)
            table = at(opt + opt_size, 40 * min(sections, 96))
            secs = [(u32(s, 12), max(u32(s, 8), u32(s, 16)), u32(s, 20))
                    for s in (table[i:i + 40] for i in range(0, len(table) - 39, 40))]

            def offset(rva):
                return next((rva - va + raw for va, size, raw in secs if va <= rva < va + size), -1)

            entries = at(dirs, 14 * 8)
            # regular imports: 20-byte descriptors, name RVA at 12; delay-load: 32-byte descriptors, name RVA at 4
            for index, size, name_at in ((1, 20, 12), (13, 32, 4)):
                rva = u32(entries, index * 8)
                start = offset(rva) if rva else -1
                for n in range(512 if start >= 0 else 0):
                    desc = at(start + n * size, size)
                    name_rva = u32(desc, name_at) if len(desc) == size else 0
                    if not name_rva:
                        break
                    o = offset(name_rva)
                    raw = at(o, 256) if o >= 0 else b""
                    end = raw.find(b"\0")
                    if end > 0:
                        out.add(raw[:end].decode("ascii", "replace").lower())
    except (OSError, ValueError, OverflowError):
        pass
    return out


def game_inputs(exe_dir, exe_name, upscalers):
    """Extra OptiScaler input settings from what the scan found (the widget's InstallConfig.Fsr2Inputs):
    no upscaler files at all: Fsr2Pattern/Fsr3Pattern, OptiScaler searches the exe for built-in FSR 2 and 3 (loads a
    little slower, so only for these games); an FSR 2 DLL in a DX11 or Vulkan game: that API's FSR 2 inputs, as
    OptiScaler hooks DX12 FSR 2 by default. The widget reads the API from the running game; the plugin installs before
    the game runs, so it reads it from the exe's imports (no answer when the exe loads its renderer at runtime)."""
    if not upscalers:
        return [("Inputs", "Fsr2Pattern", "true"), ("Inputs", "Fsr3Pattern", "true")]
    if "FSR 2" not in upscalers or not exe_name:
        return []
    imports = exe_imports(os.path.join(exe_dir, exe_name))
    if "d3d12.dll" in imports:
        return []
    if "vulkan-1.dll" in imports:
        return [("Inputs", "UseFsr2VulkanInputs", "true")]
    if "d3d11.dll" in imports:
        return [("Inputs", "UseFsr2Dx11Inputs", "true")]
    return []


def pick_proxy(exe_dir, exe_name, tried=(), remembered=None):
    """The loader name for this game, the first free in the folder and not tried yet (the widget's PickProxyName):
    the game's rule, then the name that worked last time it was set up (LoaderMemory), then the usual order. When a
    name was already skipped, names the exe imports go first: Windows loads those from the game folder at startup,
    before anything can skip them (the widget's OrderForExe)."""
    order = list(PROXY_NAMES)
    if tried and exe_name:
        imports = exe_imports(os.path.join(exe_dir, exe_name))
        order = [n for n in order if n in imports] + [n for n in order if n not in imports]
    first = [n for n in (LOADER_RULES.get((exe_name or "").lower()), remembered) if n in PROXY_NAMES]
    for name in first + [n for n in order if n not in first]:
        if name in tried:
            continue
        if not os.path.exists(os.path.join(exe_dir, name)):
            return name
    return None


# ---- ini (OptiScaler.ini is CRLF, sections in brackets; keys we set are replaced or added in their section) ----

def set_ini(path, values):
    try:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    nl = "\r\n" if "\r\n" in text or not text else "\n"
    lines = text.splitlines()
    for section, key, value in values:
        start = next((i for i, l in enumerate(lines) if l.strip().lower() == f"[{section.lower()}]"), None)
        if start is None:
            lines += ["", f"[{section}]", f"{key}={value}"]
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        for i in range(start + 1, end):
            if re.match(rf"\s*{re.escape(key)}\s*=", lines[i], re.I):
                lines[i] = f"{key}={value}"
                break
        else:
            lines.insert(end, f"{key}={value}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(nl.join(lines) + nl)


# ---- install / uninstall ----

class InstallError(Exception):
    pass


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install(exe_dir, exe_name, package_dir, fsr4_files, settings, proxy=None, upscalers=None, remembered=None,
            reframework=None):
    """Copies OptiScaler (OptiScaler.dll under the proxy name), the FSR 4 files into its subfolder and the settings,
    plus the game's input settings when its upscalers are given (game_inputs), and REFramework's dinput8.dll when its
    path is given (the widget's AddREFramework; a dinput8.dll the game already has is left alone).
    Returns the manifest: created files, backed-up files, proxy name, and "reframework" true when it was added.
    Rolls back on failure."""
    proxy = proxy or pick_proxy(exe_dir, exe_name, remembered=remembered)
    if not proxy:
        raise InstallError("Every name OptiScaler can load under is already taken in this game's folder.")
    meta = os.path.join(exe_dir, META)
    manifest = {"proxy": proxy, "created": [], "backups": [], "exe_name": exe_name}
    plan = []
    for dirpath, _dirs, files in os.walk(package_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(dirpath, f), package_dir)
            if f.lower() in SKIP_PACKAGE_FILES or f.startswith("!!"):
                continue
            plan.append((os.path.join(dirpath, f), proxy if rel.lower() == "optiscaler.dll" else rel))
    for src in fsr4_files:
        plan.append((src, os.path.join(SUBFOLDER, os.path.basename(src))))
    if reframework and not os.path.lexists(os.path.join(exe_dir, "dinput8.dll")):
        plan.append((reframework, "dinput8.dll"))
        manifest["reframework"] = True
        # REFramework's own files from before (the player's earlier REFramework) are kept at uninstall
        manifest["reframework_preexisting"] = reframework_artifacts(exe_dir)
    try:
        os.makedirs(meta, exist_ok=True)
        for src, rel in plan:
            dst = os.path.join(exe_dir, rel)
            if os.path.lexists(dst):
                backup = os.path.join(meta, "backup", rel)
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.move(dst, backup)
                manifest["backups"].append(rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            manifest["created"].append(rel)
            _save(meta, manifest)
        ini = os.path.join(exe_dir, "OptiScaler.ini")
        if "OptiScaler.ini" not in manifest["created"]:
            manifest["created"].append("OptiScaler.ini")
        set_ini(ini, ini_settings(**settings) + game_values(exe_dir) + (
            game_inputs(exe_dir, exe_name, upscalers) if upscalers is not None else []))
        if manifest.get("reframework") and REFRAMEWORK_CONFIG not in manifest["reframework_preexisting"]:
            # REFramework opens its menu on every launch; with RememberMenuState it starts closed (Insert opens it)
            _set_lines(os.path.join(exe_dir, REFRAMEWORK_CONFIG), {"REFrameworkConfig_RememberMenuState": "true",
                                                                    "REFrameworkConfig_MenuOpen": "false"})
        _save(meta, manifest)
    except OSError as e:
        try:
            uninstall(exe_dir, manifest)
        except OSError:
            pass
        raise InstallError(f"Couldn't copy OptiScaler into the game folder ({e.strerror or e}).") from e
    return manifest


def _set_lines(path, values):
    """key=value lines in a plain config file, replaced or added."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    for key, value in values.items():
        i = next((n for n, line in enumerate(lines) if line.startswith(key + "=")), None)
        if i is None:
            lines.append(f"{key}={value}")
        else:
            lines[i] = f"{key}={value}"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _save(meta, manifest):
    tmp = os.path.join(meta, "manifest.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    os.replace(tmp, os.path.join(meta, "manifest.json"))


def load_manifest(exe_dir):
    try:
        with open(os.path.join(exe_dir, META, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) and isinstance(m.get("created"), list) else None
    except (OSError, ValueError):
        return None


def uninstall(exe_dir, manifest=None):
    """Removes what install created (plus OptiScaler's log), restores backups, removes the meta folder."""
    manifest = manifest or load_manifest(exe_dir) or {"created": [], "backups": []}
    if manifest.get("reframework"):
        # what REFramework made while it ran (its folder, config, logs), unless the game had it before
        keep = set(manifest.get("reframework_preexisting", []))
        for name in reframework_artifacts(exe_dir):
            if name in keep:
                continue
            path = os.path.join(exe_dir, name)
            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except OSError:
                pass
    for path in manifest.get("extra", []):  # FSR 4 files put where OptiScaler looked for them (add_fsr4_copy)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            os.rmdir(os.path.dirname(path))  # the OptiScaler subfolder, when nothing else is in it
        except OSError:
            pass
    for rel in manifest.get("created", []) + ["OptiScaler.log"]:
        path = os.path.join(exe_dir, rel)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
        except OSError:
            pass
    meta = os.path.join(exe_dir, META)
    for rel in manifest.get("backups", []):
        src, dst = os.path.join(meta, "backup", rel), os.path.join(exe_dir, rel)
        try:
            if os.path.lexists(src) and not os.path.lexists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
        except OSError:
            pass
    # empty folders the package created (the OptiScaler subfolder tree), deepest first
    dirs = sorted({os.path.dirname(os.path.join(exe_dir, r)) for r in manifest.get("created", [])},
                  key=lambda d: -d.count(os.sep))
    for d in dirs:
        while d.startswith(exe_dir + os.sep):
            try:
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)
    shutil.rmtree(meta, ignore_errors=True)


def apply_settings(exe_dir, settings):
    ini = os.path.join(exe_dir, "OptiScaler.ini")
    if os.path.isfile(ini):
        set_ini(ini, ini_settings(**settings) + game_values(exe_dir))


# ---- launch options ----

def override_word(proxy):
    return f"WINEDLLOVERRIDES={os.path.splitext(proxy)[0]}=n,b"


def with_override(options, proxy):
    """Steam launch options with OptiScaler's override added (merged into an existing WINEDLLOVERRIDES)."""
    options = (options or "").strip()
    name = os.path.splitext(proxy)[0]
    words = options.split()
    for i, w in enumerate(words):
        if w.startswith("WINEDLLOVERRIDES="):
            value = w.split("=", 1)[1].strip('"')
            if re.search(rf"(^|;){re.escape(name)}=", value):
                return options
            words[i] = f"WINEDLLOVERRIDES={value};{name}=n,b" if value else f"WINEDLLOVERRIDES={name}=n,b"
            return " ".join(words)
    if "%command%" in options:
        return f"{override_word(proxy)} {options}"
    return f"{override_word(proxy)} %command% {options}".strip()


def without_override(options, proxy, original=None):
    """Takes our override back out; returns the user's own options (the original when nothing else changed)."""
    name = os.path.splitext(proxy)[0]
    out = []
    for w in (options or "").split():
        if w.startswith("WINEDLLOVERRIDES="):
            parts = [p for p in w.split("=", 1)[1].strip('"').split(";") if p and p != f"{name}=n,b"]
            if parts:
                out.append("WINEDLLOVERRIDES=" + ";".join(parts))
            continue
        out.append(w)
    result = " ".join(out)
    if original is not None and result.strip() in ("%command%", "") and (original or "").strip() in ("", "%command%"):
        return original
    return result


# ---- the session: OptiScaler.log (the widget's LoadedModules.Check, from the file alone) ----

def read_log(exe_dir, limit=4 * 1024 * 1024):
    try:
        with open(os.path.join(exe_dir, "OptiScaler.log"), "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def log_time(exe_dir):
    try:
        return os.path.getmtime(os.path.join(exe_dir, "OptiScaler.log"))
    except OSError:
        return 0.0


RES = re.compile(r"(\d{3,5})\s*x\s*(\d{3,5})")
NO_FSR4_FILE = ("OptiScaler couldn't load AMD's FSR 4 file, so the game ran FSR 3. When you quit, the plugin puts it "
                "where OptiScaler looks for it.")


def logged_exe(log):
    """The exe OptiScaler says it runs in ("CheckQuirks Game's Exe: PBZ.exe"), or ""."""
    found = re.findall(r"Game's Exe:\s*(\S.*?\.exe)\s*$", log, re.I | re.M)
    return found[-1].strip() if found else ""


RENDER_MARKERS = ("hkD3D12CreateDevice", "hkD3D11CreateDevice", "hkvkCreateDevice", "WrappedIDXGISwapChain",
                  "CreateRenderTargetDx12", "Render Resolution:")


def renders(log):
    """Whether OptiScaler saw the process draw: a graphics device, swapchain or upscaler in its log. The widget only
    counts a process with graphics loaded as the game (GameWatcher); a launcher OptiScaler loaded into ends its log
    after start-up (Phantom Blade Zero's steam/PBZ.exe: "Init done", then nothing)."""
    return any(m in log for m in RENDER_MARKERS)


def game_besides(install_dir, helper):
    """The game when helper (an exe that never drew) turned out to be a launcher: an exe of the same name in an Unreal
    Binaries/Win64 (or WinGDK) folder first (Phantom Blade Zero: steam/PBZ.exe starts ProjectPBZ/Binaries/Win64/
    PBZ.exe), then any other exe of that name, then the folder guess when it's somewhere else. None if none."""
    name = os.path.basename(helper).lower()
    same = [os.path.join(d, f) for d, _dirs, files in _walk(install_dir) for f in files
            if f.lower() == name and os.path.normpath(os.path.join(d, f)) != os.path.normpath(helper)]
    unreal = [p for p in same if [s.lower() for s in p.split(os.sep)[-3:-1]] in (["binaries", "win64"], ["binaries", "wingdk"])]
    if unreal or same:
        return sorted(unreal or same)[0]
    guess = analyze(install_dir)
    if guess and os.path.normpath(guess["exe_dir"]) != os.path.normpath(os.path.dirname(helper)):
        return os.path.join(guess["exe_dir"], guess["exe_name"])
    return None


def all_logs(install_dir):
    """Every OptiScaler.log in the game folder, newest first (for the support report)."""
    found = [os.path.join(d, f) for d, _dirs, files in _walk(install_dir) for f in files if f.lower() == "optiscaler.log"]
    return sorted(found, key=lambda p: -log_time(os.path.dirname(p)))


def find_exe(install_dir, name):
    """The one file called name (any letter case) in the game folder, or None when there's none or several."""
    hits = [os.path.join(d, f) for d, _dirs, files in _walk(install_dir) for f in files if f.lower() == name.lower()]
    return hits[0] if len(hits) == 1 else None


def logged_dll_dir(log):
    """The folder OptiScaler looks for AMD's FSR 4 file in (its OptiScaler subfolder), as a Windows path from
    "Setting DllPath to S:\\steamapps\\common\\PBZ\\platform\\steam", or "". Under Proton it can be the folder Steam
    starts the game in rather than the exe's (Phantom Blade Zero: platform\\steam, exe in ProjectPBZ\\Binaries\\Win64)."""
    found = re.findall(r"Setting DllPath to\s+(\S.*?)\s*$", log, re.M)
    return found[-1] if found else ""


def local_dir(install_dir, win_path):
    """A Windows path inside the game's folder ("S:\\steamapps\\common\\PBZ\\platform\\steam") as the folder on this
    machine, matched from steamapps/common/<game folder>/ down in any letter case; None when outside or absent."""
    marker = "/steamapps/common/" + os.path.basename(install_dir.rstrip("/\\")).lower()
    text = win_path.replace("\\", "/").rstrip("/")
    at = text.lower().find(marker)
    if at < 0 or text.lower()[at + len(marker):at + len(marker) + 1] not in ("", "/"):
        return None
    return _resolve(install_dir, text[at + len(marker):], want_dir=True)


def add_fsr4_copy(exe_dir, target_dir, fsr4_files):
    """AMD's FSR 4 files in target_dir's OptiScaler subfolder too, for a game where OptiScaler looks there. Recorded
    in the manifest ("extra") so uninstall removes them; a file already there that isn't ours is left alone. True when
    anything was added."""
    manifest = load_manifest(exe_dir)
    if not manifest:
        return False
    extra, added = manifest.setdefault("extra", []), False
    for src in fsr4_files:
        dst = os.path.join(target_dir, SUBFOLDER, os.path.basename(src))
        if os.path.lexists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        extra.append(dst)
        added = True
    if added:
        _save(os.path.join(exe_dir, META), manifest)
    return added


def _resolve(root, rel, want_dir=False):
    """root joined with a path from Windows, matching each folder and file name in any letter case; None if absent."""
    path = root
    for part in [p for p in rel.split("/") if p not in ("", ".")]:
        if part == "..":
            return None
        try:
            match = next((n for n in os.listdir(path) if n.lower() == part.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        path = os.path.join(path, match)
    return path if (os.path.isdir(path) if want_dir else os.path.isfile(path)) else None


GAME_MEMORY_MB = 512  # a game's process uses gigabytes; a launcher (Phantom Blade Zero's steam/PBZ.exe) far less


def _memory_mb(proc, pid):
    try:
        with open(os.path.join(proc, pid, "status"), encoding="utf-8", errors="replace") as f:
            found = re.search(r"^VmRSS:\s*(\d+)\s*kB", f.read(), re.M)
        return int(found.group(1)) // 1024 if found else 0
    except (OSError, ValueError):
        return 0


GRAPHICS_DLLS = ("dxgi.dll", "d3d11.dll", "d3d12.dll", "vulkan-1.dll")  # the widget's GameWatcher.GraphicsDlls


def _rendering(proc, pid):
    """The widget's "rendering" test: the process has loaded a graphics DLL (Wine maps them as files)."""
    try:
        with open(os.path.join(proc, pid, "maps"), encoding="utf-8", errors="replace") as f:
            return any(line.rstrip().lower().endswith(GRAPHICS_DLLS) for line in f)
    except OSError:
        return False


def running_exe(install_dir, proc="/proc"):
    """(exe, memory in MB) of the game a running game really is, or (None, 0). The widget installs next to the exe
    that owns the big window on screen (ForegroundGame) and only counts a process with graphics loaded (GameWatcher);
    any other exe from the folder is "a launcher or helper, not the game itself". Proton games have no window to ask,
    so: of the exes from the game's folder with graphics loaded, the one using the most memory. A launcher can load
    graphics for a moment (Phantom Blade Zero's steam/PBZ.exe), but only the game uses gigabytes. Proton starts exes
    with their Windows path ("S:\\steamapps\\common\\PBZ\\ProjectPBZ\\Binaries\\Win64\\PBZ.exe", the drive letter
    depending on the library), so a path is matched from steamapps/common/<game folder>/ down."""
    return pick_game(running_processes(install_dir, proc))


def windows_programs(proc="/proc"):
    """Every running Windows program, for the support report: how it was started (its .exe argument as given), its
    working folder, memory and whether graphics are loaded. Shows how a game was really started when the plugin's
    matching misses it."""
    out = []
    try:
        pids = sorted((p for p in os.listdir(proc) if p.isdigit()), key=int)
    except OSError:
        return out
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as f:
                args = [a.decode("utf-8", "replace") for a in f.read(64 * 1024).split(b"\0")]
        except OSError:
            continue
        exe = next((a for a in args if a.lower().endswith(".exe")), None)
        if not exe or os.path.basename(exe.replace("\\", "/")).lower() in ("steam.exe", "services.exe", "winedevice.exe",
                                                                          "plugplay.exe", "svchost.exe", "explorer.exe",
                                                                          "rpcss.exe", "tabtip.exe", "conhost.exe"):
            continue
        try:
            cwd = os.readlink(os.path.join(proc, pid, "cwd"))
        except OSError:
            cwd = "?"
        out.append({"pid": int(pid), "exe": exe[:300], "cwd": cwd[:300], "mb": _memory_mb(proc, pid),
                    "graphics": _rendering(proc, pid)})
    return out


def game_exes(install_dir):
    """Every .exe in the game folder with its size in MB, for the support report."""
    found = []
    for d, _dirs, files in _walk(install_dir):
        for f in files:
            if f.lower().endswith(".exe"):
                p = os.path.join(d, f)
                try:
                    found.append((os.path.relpath(p, install_dir).replace(os.sep, "/"), os.path.getsize(p) / 2 ** 20))
                except OSError:
                    pass
    return sorted(found)


def pick_game(processes):
    """(exe, memory in MB) of the process from running_processes that is the game: graphics loaded, most memory."""
    drawing = [p for p in processes if p["graphics"]]
    if not drawing:
        return None, 0
    best = max(sorted(drawing, key=lambda p: p["path"]), key=lambda p: p["mb"])
    return best["path"], best["mb"]


def running_processes(install_dir, proc="/proc"):
    """Every running exe from the game's folder: [{path, mb, graphics}], one per exe (its largest process). A path is
    matched from steamapps/common/<game folder>/ down; one given relative to the process's working folder is joined
    to it first."""
    marker = "/steamapps/common/" + os.path.basename(install_dir.rstrip("/\\")).lower() + "/"
    found = {}
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return []
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as f:
                args = f.read(64 * 1024).split(b"\0")
        except OSError:
            continue
        for arg in args:
            text = arg.decode("utf-8", "replace").replace("\\", "/")
            low = text.lower()
            if not low.endswith(".exe"):
                continue
            if marker not in low and not re.match(r"^[a-z]:/|^/", low):  # relative: from the working folder
                try:
                    text = os.readlink(os.path.join(proc, pid, "cwd")).rstrip("/") + "/" + text
                except OSError:
                    continue
                low = text.lower()
            at = low.find(marker)
            if at < 0:
                continue
            # "..\" steps that stay inside the game folder are tidied first: a launcher can start the game as
            # S:\...\PBZ\steam\..\ProjectPBZ\Binaries\Win64\PBZ.exe. A path that leaves the folder stays refused.
            rel = posixpath.normpath(text[at + len(marker):])
            if rel == ".." or rel.startswith("../"):
                continue
            path = _resolve(install_dir, rel)
            if path and _is_game_exe(os.path.basename(path)):
                mb, graphics = _memory_mb(proc, pid), _rendering(proc, pid)
                old = found.get(path)
                if not old or (graphics, mb) > (old["graphics"], old["mb"]):
                    found[path] = {"path": path, "mb": mb, "graphics": graphics}
                break
    return sorted(found.values(), key=lambda p: p["path"])


def opti_dll_path(exe_dir):
    """OptiScaler's OptiDllPath for a game: its OptiScaler folder as a full Windows path. OptiScaler works the folder
    out from its own location, which under Proton can come out as the folder Steam starts the game in, where AMD's
    FSR 4 file isn't (Phantom Blade Zero). Proton maps Z: to /, so the full path always points at the right folder;
    if it ever didn't exist, OptiScaler falls back to its own folder as before."""
    path = os.path.abspath(os.path.join(exe_dir, SUBFOLDER))
    return "Z:" + path.replace("/", "\\") if path.startswith("/") else path


def game_values(exe_dir):
    """The settings every set-up game gets for its folder."""
    return [("Libraries", "OptiDllPath", opti_dll_path(exe_dir))]


MODES = ((1.0, "Native AA"), (1.5, "Quality"), (1.7, "Balanced"), (2.0, "Performance"), (3.0, "Ultra Performance"))


def summary(log):
    """What OptiScaler is doing, for the notification: "DLSS → FSR 4.1.2 Lite, 1280×720 → 3840×2160 (Ultra
    Performance)". The game's upscaler input is named only from the calls OptiScaler logs for it (DLSS's
    CreateFeature, the FidelityFX API's ffxCreateContext, XeSS's CreateContext); the resolutions are the last ones
    OptiScaler set up. "" when the log has neither."""
    if "NVSDK_NGX_D3D12_CreateFeature" in log or "NVSDK_NGX_D3D11_CreateFeature" in log:
        source = "DLSS"
    elif "ffxCreateContext" in log:
        source = "FSR"
    elif re.search(r"xessD3D1[12]CreateContext", log):
        source = "XeSS"
    else:
        source = ""
    found = re.findall(r"Render Resolution:\s*(\d+)x(\d+),\s*Display Resolution\s*(\d+)x(\d+)", log)
    parts = [f"{source} → FSR 4.1.2 Lite" if source else "FSR 4.1.2 Lite"]
    if found:
        rw, rh, dw, dh = (int(v) for v in found[-1])
        ratio = dw / rw if rw else 0
        mode = next((m for r, m in MODES if abs(ratio - r) < 0.06), f"{ratio:.2f}x")
        parts.append(f"{rw}×{rh} → {dw}×{dh} ({mode})")
    return ", ".join(parts)


def verdict(log):
    """(verdict, detail) from one session's OptiScaler.log:
    lite: the Lite model was hooked; fsr4: FSR 4 loaded but Lite wasn't confirmed; fsr3: the upscaler ran without
    FSR 4 (also when OptiScaler couldn't load AMD's FSR 4 file); unsupported: OptiScaler says FSR 4 can't run;
    waiting: OptiScaler ran but the game's upscaler didn't start; none: no log (OptiScaler didn't load)."""
    if not log:
        return "none", "OptiScaler didn't load. The game may need a different loader name; play once more."
    if "ffxProvider_FSR4Lite_Int8" in log:
        return "lite", "FSR 4.1 Lite ran last session."
    if "can't run any FSR 4 model" in log or "doesn't support FSR 4" in log:
        return "unsupported", "OptiScaler reports FSR 4 can't run here."
    low = log.lower()
    if f"failed to load {DX12_FSR4}" in low or f"failed to load {VK_FSR4}" in low:
        return "fsr3", NO_FSR4_FILE
    if DX12_FSR4 in low or VK_FSR4 in low:
        return "fsr4", "FSR 4 loaded, but the log doesn't show the Lite model."
    if re.search(r"(render|output|display).{0,40}\d{3,5}\s*x\s*\d{3,5}", low):
        return "fsr3", "The upscaler ran on FSR 3, not FSR 4. Pick FSR, DLSS or XeSS in the game's settings."
    return "waiting", "OptiScaler loaded, but the game's upscaler didn't start. Pick an upscaler in its settings."
