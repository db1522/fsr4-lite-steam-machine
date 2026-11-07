# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Steam Machine Life
"""FSR 4.1 Lite's one method: OptiScaler in the game's exe folder, set up the way the FSR 4.1 Lite widget for Windows
sets it up (github.com/db1522/fsr4-lite-rog-ally): the game's upscaler goes through FidelityFX, FSR 4 is forced onto
the INT8 Lite model, frame generation stays off, and OptiScaler's log tells whether Lite ran.

Everything here is plain file work on the game's folder, recorded in a manifest so an uninstall puts back exactly
what was there."""
import hashlib
import json
import os
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

# Games the OptiScaler community has a setup for: the loader name they need (the widget's GameRules)
LOADER_RULES = {"rdr2.exe": "winmm.dll", "enshrouded.exe": "winmm.dll"}
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


def pick_proxy(exe_dir, exe_name, tried=()):
    """The loader name for this game: its rule, else the first name free in the folder (and not tried yet)."""
    rule = LOADER_RULES.get((exe_name or "").lower())
    order = ([rule] if rule else []) + [n for n in PROXY_NAMES if n != rule]
    for name in order:
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


def install(exe_dir, exe_name, package_dir, fsr4_files, settings, proxy=None):
    """Copies OptiScaler (OptiScaler.dll under the proxy name), the FSR 4 files into its subfolder and the settings.
    Returns the manifest: created files, backed-up files, proxy name. Rolls back on failure."""
    proxy = proxy or pick_proxy(exe_dir, exe_name)
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
        set_ini(ini, ini_settings(**settings))
        _save(meta, manifest)
    except OSError as e:
        try:
            uninstall(exe_dir, manifest)
        except OSError:
            pass
        raise InstallError(f"Couldn't copy OptiScaler into the game folder ({e.strerror or e}).") from e
    return manifest


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
        set_ini(ini, ini_settings(**settings))


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


def verdict(log):
    """(verdict, detail) from one session's OptiScaler.log:
    lite: the Lite model was hooked; fsr4: FSR 4 loaded but Lite wasn't confirmed; fsr3: the upscaler ran without
    FSR 4; unsupported: OptiScaler says FSR 4 can't run; waiting: OptiScaler ran but the game's upscaler didn't start;
    none: no log (OptiScaler didn't load)."""
    if not log:
        return "none", "OptiScaler didn't load. The game may need a different loader name; play once more."
    if "ffxProvider_FSR4Lite_Int8" in log:
        return "lite", "FSR 4.1 Lite ran last session."
    if "can't run any FSR 4 model" in log or "doesn't support FSR 4" in log:
        return "unsupported", "OptiScaler reports FSR 4 can't run here."
    low = log.lower()
    if DX12_FSR4 in low or VK_FSR4 in low:
        return "fsr4", "FSR 4 loaded, but the log doesn't show the Lite model."
    if re.search(r"(render|output|display).{0,40}\d{3,5}\s*x\s*\d{3,5}", low):
        return "fsr3", "The upscaler ran on FSR 3, not FSR 4. Pick FSR, DLSS or XeSS in the game's settings."
    return "waiting", "OptiScaler loaded, but the game's upscaler didn't start. Pick an upscaler in its settings."
