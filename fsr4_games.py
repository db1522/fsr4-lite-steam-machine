# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk
# Copyright (c) 2026 Steam Machine Life (changes)

"""Finding installed games that can take the FSR4 upgrade: Steam games and Windows games added to Steam as shortcuts.

A game qualifies when it ships AMD's FidelityFX API loader as a separate DLL (FSR 3.1+ / FSR4 through the FFX API):
that is the only path the driver-side upgrade hooks into. The directory holding that DLL is where our two DLLs go.
"""

import os
import re

FFX_DLLS = ("amd_fidelityfx_dx12.dll", "amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_loader_dx12.dll")
# Lower-case name fragments of anti-cheat files and folders: EAC, BattlEye, XIGNCODE, nProtect GameGuard,
# PunkBuster, EQU8. Online games without any of these are caught by the panel through Steam's store categories.
# Not "vanguard": Riot's lives outside game folders, and the word names game files (Mass Effect's Vanguard class).
ANTICHEAT = ("easyanticheat", "battleye", "beservice", "start_protected_game.exe", "eac_launcher",
             "xigncode", "gameguard", "npgamemon", "punkbuster", "pbsvc", "equ8")
MAX_DEPTH = 9
# Big folders that never hold the FFX DLL; skipping them keeps the deeper walk fast.
SKIP_DIRS = {"paks", "movies", "_commonredist", "__pycache__", ".git", "shadercache", "videos"}
EXE_SUBDIRS = {"win64", "wingdk", "x64", "binaries", "bin", "bin64"}

_KV = re.compile(r'"([^"]+)"\s+"([^"]*)"')


def _values(text, key):
    return [v for k, v in _KV.findall(text) if k.lower() == key]


def libraries(steam_root):
    """Steam library roots, the main one first."""
    roots = [steam_root]
    try:
        with open(os.path.join(steam_root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return roots
    for path in _values(text, "path"):
        path = path.replace("\\\\", "\\")
        if os.path.realpath(path) not in map(os.path.realpath, roots):
            roots.append(path)
    return roots


def library_apps(steam_root):
    """Library root -> the app ids Steam lists in it ("apps" in libraryfolders.vdf), by real path. When a game's
    manifest is in two libraries (moved to an SD card, with the old one left behind), this says which one Steam runs
    it from. Empty when the file can't be read."""
    try:
        with open(os.path.join(steam_root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {}
    out = {}
    # each library block: "path" "<root>" ... "apps" { "<appid>" "<size>" ... }
    for block in re.split(r'(?=^\s*"path"\s)', text, flags=re.M)[1:]:
        path = _values(block, "path")
        apps = re.search(r'"apps"\s*\{([^}]*)\}', block, re.I)
        if path and apps:
            out[os.path.realpath(path[0].replace("\\\\", "\\"))] = {k for k, _ in _KV.findall(apps.group(1))
                                                                    if k.isdigit()}
    return out


def _find_ffx(install_dir):
    """(directory with the FFX DLL, its name, anti-cheat seen) for one game.

    Steam Machine fork: walks deeper (Unreal games keep FSR 3.1 under Engine/Plugins/.../Binaries/ThirdParty/Win64),
    follows symlinked folders with a loop guard, and when a game ships more than one copy of the DLL prefers the one
    sitting next to an .exe (the folder the game actually loads from), else the shallowest.
    """
    hits, exe_dirs, anticheat, visited = [], [], False, set()
    base_depth = install_dir.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(install_dir, followlinks=True):
        real = os.path.realpath(root)
        if real in visited:
            dirs[:] = []
            continue
        visited.add(real)
        names = [n.lower() for n in dirs + files]
        if any(marker in n for n in names for marker in ANTICHEAT):
            anticheat = True
        exes = [f.lower() for f in files if f.lower().endswith(".exe") and "crash" not in f.lower()
                and not any(m in f.lower() for m in ANTICHEAT)]
        if exes:
            parts = root.lower().split(os.sep)
            exe_dirs.append((root, any("shipping" in e for e in exes), parts[-2:] in (["binaries", "win64"], ["binaries", "wingdk"])))
        hit = next((f for f in files if f.lower() in FFX_DLLS), None)
        if hit:
            has_exe = any(f.lower().endswith(".exe") for f in files)
            hits.append((not has_exe, root.count(os.sep), root, hit))
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
        if root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
    if not hits:
        return (None, None, anticheat)
    no_exe, _, root, hit = min(hits)
    if no_exe and exe_dirs:
        # Our amdxc64.dll is found through the game's DLL search order, which starts at the .exe's folder, not at the
        # FFX DLL's. When the FFX DLL sits elsewhere (an Unreal plugin folder), our files go next to the game's .exe:
        # an Unreal *-Shipping.exe first, then any .exe under Binaries/Win64 (or WinGDK), then the shallowest .exe.
        root = min(exe_dirs, key=lambda e: (not e[1], not e[2], e[0].count(os.sep)))[0]
    return (root, hit, anticheat)


def _game_root(exe_dir):
    """A shortcut's .exe often sits in Binaries/Win64 while the FFX DLL lives elsewhere in the game: start higher."""
    d = os.path.normpath(exe_dir)
    for _ in range(3):
        if os.path.basename(d).lower() in EXE_SUBDIRS and os.path.dirname(d) != d:
            d = os.path.dirname(d)
        else:
            break
    if d != os.path.normpath(exe_dir) and os.path.dirname(d) != d:
        d = os.path.dirname(d)  # Unreal: <Root>/<Project>/Binaries/Win64 -> <Root>, so Engine/Plugins is covered
    return d


def _binary_map(data, i):
    """One map of Steam's binary VDF (shortcuts.vdf) from offset i: (dict with lower-case keys, offset after it)."""
    out = {}
    while data[i] != 0x08:
        kind, end = data[i], data.index(b"\0", i + 1)
        key, i = data[i + 1:end].decode("utf-8", "replace").lower(), end + 1
        if kind == 0x00:
            out[key], i = _binary_map(data, i)
        elif kind == 0x01:
            end = data.index(b"\0", i)
            out[key], i = data[i:end].decode("utf-8", "replace"), end + 1
        elif kind == 0x02:
            # read unsigned: Steam's client and its app ids for shortcuts are the unsigned 32-bit value
            out[key], i = int.from_bytes(data[i:i + 4], "little"), i + 4
        else:
            raise ValueError(f"binary VDF type {kind}")
    return out, i + 1


def shortcuts(steam_root):
    """Windows games added to Steam ("Add a Non-Steam Game"), for every Steam user: [(appid, name, exe)]."""
    found = []
    userdata = os.path.join(steam_root, "userdata")
    try:
        users = os.listdir(userdata)
    except OSError:
        return found
    for user in users:
        try:
            with open(os.path.join(userdata, user, "config", "shortcuts.vdf"), "rb") as f:
                entries = _binary_map(f.read(), 0)[0].get("shortcuts", {})
        except (OSError, ValueError, IndexError, RecursionError):
            continue
        for e in entries.values() if isinstance(entries, dict) else ():
            if not isinstance(e, dict) or not isinstance(e.get("appid"), int) or not isinstance(e.get("exe"), str):
                continue
            exe = e["exe"].strip().strip('"')
            # Proton runs only .exe shortcuts; Linux launchers (Heroic, Lutris, scripts) would point the walk at
            # their own folders or the home directory
            if os.path.isabs(exe) and exe.lower().endswith(".exe"):
                name = e.get("appname") if isinstance(e.get("appname"), str) else ""
                found.append((e["appid"], name or os.path.splitext(os.path.basename(exe))[0], exe))
    return found


def scan(steam_root, keep=()):
    """Installed games with an FFX API DLL, sorted by name; keep: app ids with FSR 4 on."""
    games = []
    for lib in libraries(steam_root):
        apps = os.path.join(lib, "steamapps")
        try:
            manifests = [n for n in os.listdir(apps) if n.startswith("appmanifest_") and n.endswith(".acf")]
        except OSError:
            continue
        for name in manifests:
            try:
                with open(os.path.join(apps, name), encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            appid, title, installdir = (_values(text, k) for k in ("appid", "name", "installdir"))
            if not (appid and installdir) or not appid[0].isdigit():
                continue
            # installdir is a folder name in steamapps/common; anything path-like could lead out of the library
            # (a symlinked game folder is fine: it is still that name)
            if installdir[0] in ("", ".", "..") or "/" in installdir[0] or "\\" in installdir[0]:
                continue
            install_dir = os.path.join(apps, "common", installdir[0])
            if not os.path.isdir(install_dir):
                continue
            target, ffx, anticheat = _find_ffx(install_dir)
            if target:
                games.append({"appid": int(appid[0]), "name": title[0] if title else installdir[0],
                              "install_dir": install_dir, "target_dir": target, "ffx_dll": ffx,
                              "anticheat": anticheat})
    # A shortcut is searched from its .exe's folder down. One game folder belongs to one entry: two app ids
    # over the same files would undo each other's setup. A shortcut with FSR 4 on (keep) holds its folder, else
    # the one whose .exe is deepest, i.e. closest to the game: a launcher's shortcut (Ubisoft Connect, whose games
    # sit below it) gets only games that have no shortcut of their own.
    seen = {os.path.realpath(g["target_dir"]) for g in games}
    ids = {g["appid"] for g in games}
    order = lambda s: (s[0] not in keep, -os.path.normpath(os.path.dirname(s[2])).count(os.sep))
    for appid, title, exe in sorted(shortcuts(steam_root), key=order):
        install_dir = _game_root(os.path.dirname(exe))
        if appid in ids or not os.path.isdir(install_dir):
            continue
        target, ffx, anticheat = _find_ffx(install_dir)
        if target and os.path.realpath(target) not in seen:
            seen.add(os.path.realpath(target))
            ids.add(appid)
            games.append({"appid": appid, "name": title, "install_dir": install_dir, "target_dir": target,
                          "ffx_dll": ffx, "anticheat": anticheat})
    return sorted(games, key=lambda g: g["name"].lower())
