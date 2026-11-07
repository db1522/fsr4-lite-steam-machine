# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk
# Copyright (c) 2026 Steam Machine Life (changes)

"""FSR 4.1 Lite by Steam Machine Life: AMD's FSR 4.1.2 Lite model in any game OptiScaler can take over, on the
Steam Machine under Proton. One method for every game, the one the FSR 4.1 Lite widget for Windows uses: OptiScaler
in the game's exe folder (sml_opti), AMD's two FSR 4 files next to it, OptiScaler's log as the proof that Lite ran.

Launch options are applied by the frontend through SteamClient; this backend computes them so they come off exactly.
Every RPC answers {ok, error?, state?} (DeckyKit D2, dk_rpc).
"""

import asyncio
import json
import os
import sys
import time

import decky

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import dk_fs  # noqa: E402
import dk_rpc  # noqa: E402
import dk_update  # noqa: E402
import fsr4_games  # noqa: E402  (Steam library and shortcut parsing)
import sml_assets  # noqa: E402
import sml_opti  # noqa: E402

REPOSITORY = "db1522/fsr4-lite-steam-machine"
SEVENZIP = os.path.join(PLUGIN_DIR, "bin", "7zz")
try:
    with open(os.path.join(PLUGIN_DIR, "plugin.json"), encoding="utf-8") as _f:
        VERSION = json.load(_f)["version"]
except (OSError, ValueError, KeyError):
    VERSION = "0.0.0"
# session_toast: a notification in the game once Lite runs; watermark: AMD's FSR 4 watermark; overlay: OptiScaler's
# FPS line with the upscaler and render -> output resolution.
DEFAULT_SETTINGS = {"session_toast": True, "watermark": False, "overlay": False, "overlay_size": "large",
                    "overlay_pos": "topleft"}
CHOICES = {"overlay_size": tuple(sml_opti.OVERLAY_SIZES), "overlay_pos": tuple(sml_opti.OVERLAY_POSITIONS)}
_ready = asyncio.Event()
rpc = dk_rpc.boundary(decky.logger, _ready)


def _data_dir():
    return getattr(decky, "DECKY_PLUGIN_RUNTIME_DIR", decky.DECKY_PLUGIN_SETTINGS_DIR)


def _home():
    return getattr(decky, "DECKY_USER_HOME", os.path.expanduser("~"))


def _steam_root():
    return os.path.join(_home(), ".local", "share", "Steam")


def _read(path, default):
    try:
        return dk_fs.read_json(path, default, validate=dk_fs.require_object)
    except OSError as e:
        decky.logger.warning(f"{os.path.basename(path)} could not be read ({dk_fs.shown(e)})")
        return default


def scan_library(steam_root):
    """Every Steam game and non-Steam shortcut with a game exe. Games without upscaler files stay in the scan, like
    in the widget (many build FSR 2 or 3 in, which OptiScaler can search for); the panel offers them only while they
    run, not in the library list."""
    games = []
    for lib in fsr4_games.libraries(steam_root):
        apps = os.path.join(lib, "steamapps")
        try:
            names = [n for n in os.listdir(apps) if n.startswith("appmanifest_") and n.endswith(".acf")]
        except OSError:
            continue
        for name in names:
            try:
                with open(os.path.join(apps, name), encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            appid, title, installdir = (fsr4_games._values(text, k) for k in ("appid", "name", "installdir"))
            if not (appid and installdir) or not appid[0].isdigit():
                continue
            if installdir[0] in ("", ".", "..") or "/" in installdir[0] or "\\" in installdir[0]:
                continue
            root = os.path.join(apps, "common", installdir[0])
            if os.path.isdir(root):
                games.append((int(appid[0]), title[0] if title else installdir[0], root, None))
    for appid, name, exe in fsr4_games.shortcuts(steam_root):
        root = os.path.dirname(exe)
        if os.path.isdir(root):
            games.append((appid, name, root, exe))
    out = []
    for appid, name, root, exe in games:
        info = sml_opti.analyze(root, exe)
        if not info:
            continue
        out.append({"appid": appid, "name": name, "install_dir": root, "nonsteam": exe is not None, **info})
    out.sort(key=lambda g: g["name"].lower())
    return out


class Plugin:
    async def _main(self):
        try:
            settings_dir = decky.DECKY_PLUGIN_SETTINGS_DIR
            self.settings_path = os.path.join(settings_dir, "settings.json")
            self.registry_path = os.path.join(settings_dir, "games.json")
            # exe name (lower case) -> the loader name OptiScaler last loaded under in that game (the widget's
            # LoaderMemory), so setting a game up again starts with the name that worked
            self.loaders_path = os.path.join(settings_dir, "loaders.json")
            self.settings = dict(DEFAULT_SETTINGS)
            self.registry = {}  # str(appid) -> {exe_dir, proxy, tried, launch_original, launch_applied, installed_at}
            self.loaders = {}
            self.games, self.scanned, self._scan_task = [], False, None
            self.download = {"state": "idle", "done": 0, "total": sml_assets.TOTAL, "error": ""}
            self.assets_ok = False
            self.lock = asyncio.Lock()
            self._cancel = False
            self.sessions = {}
            self.updates = dk_update.Updates(
                repo=REPOSITORY, folder="FSR4Lite", plugin_name="FSR 4.1 Lite", package_name="fsr4-lite",
                current=VERSION, home=_home(), required=(*dk_update.REQUIRED, "bin/7zz"),
                max_expanded=64 << 20, max_members=512, logger=decky.logger)
            os.makedirs(_data_dir(), exist_ok=True)
            saved = await asyncio.to_thread(_read, self.settings_path, {})
            self.settings = {k: saved[k] if (isinstance(saved.get(k), bool) and isinstance(v, bool)) or
                             saved.get(k) in CHOICES.get(k, ()) else v for k, v in DEFAULT_SETTINGS.items()}
            reg = await asyncio.to_thread(_read, self.registry_path, {})
            self.registry = {k: v for k, v in reg.items() if isinstance(v, dict) and isinstance(v.get("exe_dir"), str)}
            loaders = await asyncio.to_thread(_read, self.loaders_path, {})
            self.loaders = {k: v for k, v in loaders.items() if v in sml_opti.PROXY_NAMES}
            try:
                os.chmod(SEVENZIP, 0o755)
            except OSError:
                pass
            self.assets_ok = await asyncio.to_thread(sml_assets.ready, _data_dir())
            self.legacy = await asyncio.to_thread(self._legacy_entries)
            self._scan_task = asyncio.create_task(self.scan_games())
        finally:
            _ready.set()

    # ---- state ----

    def _legacy_entries(self):
        """Games still set up by FSR 4.1 Lite 1.x (its own DLL, before OptiScaler): they need cleaning first."""
        try:
            data = dk_fs.read_json(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "manifest.json"), {},
                                   validate=dk_fs.require_object)
            return sorted(int(k) for k in (data.get("entries") or {}))
        except (OSError, ValueError, AttributeError):
            return []

    def _save_registry(self):
        dk_fs.write_json(self.registry_path, self.registry)

    def _view(self, g):
        entry = self.registry.get(str(g["appid"]))
        view = {k: g[k] for k in ("appid", "name", "exe_name", "upscalers", "anticheat", "nonsteam",
                                  "manual_optiscaler")}
        view["installed"] = entry is not None
        view["tip"] = sml_opti.tips(g["exe_name"], g["upscalers"])
        view["verdict"], view["detail"] = ("", "")
        if entry:
            view["verdict"], view["detail"] = entry.get("verdict", "unplayed"), entry.get("detail", "")
            view["proxy"] = entry.get("proxy", "")
        return view

    async def _state(self):
        return {
            "version": VERSION, "home": _home(), "assets_ready": self.assets_ok,
            "download": dict(self.download), "settings": dict(self.settings), "scanned": self.scanned,
            "games": [self._view(g) for g in self.games], "legacy": list(self.legacy),
            "optiscaler": sml_assets.OPTISCALER["build"],
        }

    @rpc
    async def get_state(self) -> dict:
        return dk_rpc.ok(await self._state())

    @rpc
    async def scan_games(self) -> dict:
        self.games = await asyncio.to_thread(scan_library, _steam_root())
        self.scanned = True
        return dk_rpc.ok(await self._state())

    # ---- downloads ----

    @rpc
    async def download_assets(self) -> dict:
        if self.download["state"] == "running":
            return dk_rpc.ok(await self._state())
        self.download.update(state="running", done=0, total=sml_assets.TOTAL, error="")
        self._cancel = False

        def progress(done, total):
            self.download.update(done=done, total=total)
        try:
            await asyncio.to_thread(sml_assets.fetch, _data_dir(), SEVENZIP, progress, lambda: self._cancel)
            self.download["state"] = "done"
        except Exception as e:  # noqa: BLE001 - every failure is shown in the panel
            self.download.update(state="error", error="Cancelled." if self._cancel else str(e) or type(e).__name__)
            decky.logger.warning(f"download: {e!r}")
        self.assets_ok = await asyncio.to_thread(sml_assets.ready, _data_dir())
        if self.download["state"] == "error":
            return dk_rpc.fail(self.download["error"], await self._state())
        return dk_rpc.ok(await self._state())

    @rpc
    async def download_progress(self) -> dict:
        return dk_rpc.ok(download=dict(self.download), assets_ready=self.assets_ok)

    @rpc
    async def cancel_download(self) -> dict:
        self._cancel = True
        return dk_rpc.ok(await self._state())

    # ---- games ----

    def _game(self, appid):
        return next((g for g in self.games if g["appid"] == appid), None)

    def _settings_for_ini(self, height=None):
        return {"watermark": self.settings["watermark"], "overlay": self.settings["overlay"],
                "overlay_size": self.settings["overlay_size"], "overlay_pos": self.settings["overlay_pos"],
                "height": height}

    @rpc
    async def enable_game(self, appid: int, launch_options: str) -> dict:
        async with self.lock:
            game = self._game(appid)
            if not game:
                return dk_rpc.fail("This game isn't in the library scan. Rescan and try again.", await self._state())
            if not self.assets_ok:
                return dk_rpc.fail("Download OptiScaler and AMD's FSR 4 files first.", await self._state())
            if game["anticheat"]:
                return dk_rpc.fail(sml_opti.blocked_message(game["anticheat"]), await self._state())
            if game["manual_optiscaler"]:
                return dk_rpc.fail("OptiScaler is already in this game's folder from another install. Remove it "
                                   "first.", await self._state())
            key = str(appid)
            entry = self.registry.get(key, {})
            try:
                manifest = await asyncio.to_thread(
                    sml_opti.install, game["exe_dir"], game["exe_name"], sml_assets.package_dir(_data_dir()),
                    sml_assets.fsr4_paths(_data_dir()), self._settings_for_ini(), entry.get("next_proxy"),
                    game["upscalers"], self.loaders.get(game["exe_name"].lower()))
            except sml_opti.InstallError as e:
                return dk_rpc.fail(str(e), await self._state())
            original = entry.get("launch_original", launch_options)
            new = sml_opti.with_override(launch_options, manifest["proxy"])
            self.registry[key] = {"exe_dir": game["exe_dir"], "proxy": manifest["proxy"],
                                  "tried": sorted(set(entry.get("tried", [])) | {manifest["proxy"]}),
                                  "launch_original": original, "launch_applied": new,
                                  "installed_at": time.time(), "verdict": "unplayed", "detail": ""}
            await asyncio.to_thread(self._save_registry)
            decky.logger.info(f"enabled {appid} in {game['exe_dir']} as {manifest['proxy']}")
            return dk_rpc.ok(await self._state(), launch_options=new)

    async def _disable(self, appid, launch_options, keep_retry=False):
        key = str(appid)
        entry = self.registry.get(key)
        if not entry:
            return launch_options
        await asyncio.to_thread(sml_opti.uninstall, entry["exe_dir"])
        restored = sml_opti.without_override(launch_options, entry["proxy"], entry.get("launch_original"))
        if keep_retry:
            self.registry[key] = {"tried": entry.get("tried", []), "launch_original": entry.get("launch_original"),
                                  "exe_dir": entry["exe_dir"]}
        else:
            del self.registry[key]
        await asyncio.to_thread(self._save_registry)
        return restored

    @rpc
    async def disable_game(self, appid: int, launch_options: str) -> dict:
        async with self.lock:
            restored = await self._disable(appid, launch_options)
            if str(appid) in self.registry and "proxy" not in self.registry[str(appid)]:
                del self.registry[str(appid)]
                await asyncio.to_thread(self._save_registry)
            return dk_rpc.ok(await self._state(), launch_options=restored)

    @rpc
    async def set_setting(self, key: str, value) -> dict:
        ok = key in DEFAULT_SETTINGS and (isinstance(value, bool) if isinstance(DEFAULT_SETTINGS[key], bool)
                                          else value in CHOICES.get(key, ()))
        if not ok:
            return dk_rpc.fail("Unknown setting.", await self._state())
        async with self.lock:
            self.settings[key] = value
            await asyncio.to_thread(dk_fs.write_json, self.settings_path, self.settings)
            if key != "session_toast":
                for entry in self.registry.values():
                    if entry.get("proxy"):
                        await asyncio.to_thread(sml_opti.apply_settings, entry["exe_dir"],
                                                self._settings_for_ini(entry.get("height")))
        return dk_rpc.ok(await self._state())

    # ---- sessions ----

    @rpc
    async def session_started(self, appid: int) -> dict:
        # Every game's start is kept: setting a game up while it runs needs a restart, and the panel says so.
        self.sessions[appid] = time.time()
        return dk_rpc.ok(managed=str(appid) in self.registry)

    @rpc
    async def live_status(self, appid: int) -> dict:
        """The running game's status right now, for the Now playing card:
        active: this session's OptiScaler.log shows the Lite model; restart: set up after the game started;
        starting: running, no answer yet; inactive: running and OptiScaler's log says Lite isn't on (with why);
        idle: the game isn't running (the card shows the last session instead)."""
        started = self.sessions.get(appid)
        entry = self.registry.get(str(appid))
        if not started:
            return dk_rpc.ok(status="idle")
        if not entry or not entry.get("proxy"):
            return dk_rpc.ok(status="off")
        if entry.get("installed_at", 0) > started:
            return dk_rpc.ok(status="restart", detail="Set up while the game was running. Restart the game.")
        exe_dir = entry["exe_dir"]
        if sml_opti.log_time(exe_dir) < started - 2:
            waited = time.time() - started
            return dk_rpc.ok(status="inactive" if waited > 90 else "starting",
                             detail="OptiScaler hasn't loaded. When you quit, the plugin tries the next loader name."
                             if waited > 90 else "Waiting for the game to start its upscaler.")
        log = await asyncio.to_thread(sml_opti.read_log, exe_dir)
        verdict, detail = sml_opti.verdict(log)
        if verdict == "lite":
            return dk_rpc.ok(status="active", detail="FSR 4.1 Lite is running.")
        if verdict == "waiting" and time.time() - started < 120:
            return dk_rpc.ok(status="starting", detail="Waiting for the game to start its upscaler.")
        return dk_rpc.ok(status="inactive", detail=detail)

    @rpc
    async def session_check(self, appid: int) -> dict:
        """While the game runs: whether this session's OptiScaler.log already shows the Lite model."""
        entry = self.registry.get(str(appid))
        started = self.sessions.get(appid)
        if not entry or not entry.get("proxy") or not started or entry.get("installed_at", 0) > started:
            return dk_rpc.ok(lite=False, done=True)
        if sml_opti.log_time(entry["exe_dir"]) < started - 2:
            return dk_rpc.ok(lite=False, done=False)
        log = await asyncio.to_thread(sml_opti.read_log, entry["exe_dir"])
        return dk_rpc.ok(lite="ffxProvider_FSR4Lite_Int8" in log, done=False)

    @rpc
    async def session_ended(self, appid: int, launch_options: str = "") -> dict:
        key = str(appid)
        async with self.lock:
            entry = self.registry.get(key)
            started = self.sessions.pop(appid, None)
            if not entry or not entry.get("proxy"):
                return dk_rpc.ok(managed=False)
            if started and entry.get("installed_at", 0) > started:
                # set up during this session: OptiScaler couldn't load yet, so nothing is judged
                return dk_rpc.ok(managed=True, verdict="unplayed", detail="Set up during this session.")
            exe_dir = entry["exe_dir"]
            fresh = sml_opti.log_time(exe_dir) >= (started or entry.get("installed_at", 0)) - 2
            log = await asyncio.to_thread(sml_opti.read_log, exe_dir) if fresh else ""
            verdict, detail = sml_opti.verdict(log)
            entry["verdict"], entry["detail"] = verdict, detail
            height = sml_opti.display_height(log) if log else None
            if height and height != entry.get("height"):
                entry["height"] = height  # the overlay is sized for what the game really draws at
                await asyncio.to_thread(sml_opti.apply_settings, exe_dir, self._settings_for_ini(height))
            result = {"managed": True, "verdict": verdict, "detail": detail}
            game = self._game(appid)
            exe_key = (game or {}).get("exe_name", "").lower()
            if verdict != "none" and exe_key and self.loaders.get(exe_key) != entry["proxy"]:
                self.loaders[exe_key] = entry["proxy"]  # OptiScaler loaded under this name: remember it
                await asyncio.to_thread(dk_fs.write_json, self.loaders_path, self.loaders)
            # OptiScaler never loaded: the game skipped that file name. Next name, like the widget's game watcher.
            if verdict == "none" and started:
                game = self._game(appid)
                nxt = game and sml_opti.pick_proxy(exe_dir, game["exe_name"], entry.get("tried", []) +
                                                   [entry["proxy"]])
                if nxt:
                    restored = await self._disable(appid, launch_options, keep_retry=True)
                    self.registry[key]["next_proxy"] = nxt
                    try:
                        manifest = await asyncio.to_thread(
                            sml_opti.install, exe_dir, game["exe_name"], sml_assets.package_dir(_data_dir()),
                            sml_assets.fsr4_paths(_data_dir()), self._settings_for_ini(), nxt, game["upscalers"])
                    except sml_opti.InstallError as e:
                        await asyncio.to_thread(self._save_registry)
                        return dk_rpc.ok(managed=True, verdict="none", detail=str(e), launch_options=restored)
                    new = sml_opti.with_override(restored, manifest["proxy"])
                    self.registry[key] = {"exe_dir": exe_dir, "proxy": manifest["proxy"],
                                          "tried": sorted(set(self.registry[key].get("tried", [])) |
                                                          {manifest["proxy"]}),
                                          "launch_original": entry.get("launch_original"), "launch_applied": new,
                                          "installed_at": time.time(), "verdict": "unplayed",
                                          "detail": f"Trying {manifest['proxy']}. Play once more."}
                    result.update(retry=manifest["proxy"], launch_options=new,
                                  detail=f"OptiScaler didn't load as {entry['proxy']}. Now set up as "
                                         f"{manifest['proxy']}: play once more.")
            await asyncio.to_thread(self._save_registry)
            return dk_rpc.ok(**result)

    # ---- check setup and the support report ----

    @rpc
    async def diagnose(self, appid: int) -> dict:
        return dk_rpc.ok(report=await asyncio.to_thread(self._diagnose, appid))

    def _proton(self, game):
        root = game["install_dir"]
        lib = root.split("/steamapps/")[0] if "/steamapps/" in root else _steam_root()
        try:
            with open(os.path.join(lib, "steamapps", "compatdata", str(game["appid"]), "config_info"),
                      encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return ""
        for line in lines:
            if "/compatibilitytools.d/" in line:
                return line.split("/compatibilitytools.d/")[1].split("/")[0]
            if "/common/Proton" in line:
                return line.split("/common/")[1].split("/")[0]
        return lines[0].strip() if lines else ""

    def _diagnose(self, appid):
        game = self._game(appid) or {}
        entry = self.registry.get(str(appid)) or {}
        exe_dir = entry.get("exe_dir") or game.get("exe_dir", "")
        manifest = sml_opti.load_manifest(exe_dir) if exe_dir else None
        missing = [r for r in (manifest or {}).get("created", []) if not os.path.exists(os.path.join(exe_dir, r))]
        log = sml_opti.read_log(exe_dir) if exe_dir else ""
        return {
            "name": game.get("name", f"App {appid}"), "installed": bool(entry.get("proxy")),
            "exe_dir": exe_dir, "exe_name": game.get("exe_name", ""), "proxy": entry.get("proxy", ""),
            "files_ok": bool(manifest) and not missing, "missing": missing[:5],
            "upscalers": game.get("upscalers", []), "anticheat": game.get("anticheat", ""),
            "proton": self._proton(game) if game else "",
            "verdict": entry.get("verdict", ""), "detail": entry.get("detail", ""),
            "log_lines": [l for l in log.splitlines() if any(k in l for k in (
                "FSR4", "Fsr4", "amdxcffx64", "amdvkffx64", "Lite", "upscaler", "Upscaler", "error", "Error"))][-12:],
        }

    @rpc
    async def save_report(self, appid: int) -> dict:
        return await asyncio.to_thread(self._save_report, appid)

    def _save_report(self, appid):
        d = self._diagnose(appid)
        exe_dir = d["exe_dir"]
        log = sml_opti.read_log(exe_dir, 256 * 1024) if exe_dir else ""
        try:
            with open(os.path.join(exe_dir, "OptiScaler.ini"), encoding="utf-8", errors="replace") as f:
                ini = [l for l in f.read().splitlines() if l and not l.startswith(";")]
        except OSError:
            ini = []
        text = "\n".join([
            f"FSR 4.1 Lite {VERSION} support report", f"OptiScaler: {sml_assets.OPTISCALER['build']}",
            f"Game: {d['name']} ({appid})", f"Exe: {d['exe_dir']}/{d['exe_name']}", f"Loader: {d['proxy']}",
            f"Proton: {d['proton']}", f"Upscalers found: {', '.join(d['upscalers']) or 'none'}",
            f"Files in place: {d['files_ok']} {d['missing']}", f"Last verdict: {d['verdict']} {d['detail']}",
            "", "== OptiScaler.ini (set values) ==", *ini, "", "== OptiScaler.log (end) ==",
            *(log.splitlines()[-400:] or ["(no log: OptiScaler hasn't run in this game yet)"]),
        ])
        try:
            downloads = os.path.join(_home(), "Downloads")
            os.makedirs(downloads, exist_ok=True)
            path = os.path.join(downloads, f"fsr4lite-report-{appid}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as e:
            return dk_rpc.fail(f"Couldn't save to Downloads ({dk_fs.shown(e)}).")
        return dk_rpc.ok(saved=path)

    # ---- the previous version (1.x) ----

    @rpc
    async def cleanup_legacy(self, appid: int, launch_options: str) -> dict:
        """Removes what FSR 4.1 Lite 1.x put in a game (its own amdxc64 and AMD files) and restores launch options."""
        import fsr4_install
        async with self.lock:
            manifest = fsr4_install.Manifest(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "manifest.json"))
            if appid not in manifest.entries:
                self.legacy = [a for a in self.legacy if a != appid]
                return dk_rpc.ok(await self._state(), launch_options=launch_options)
            result = await asyncio.to_thread(fsr4_install.disable, manifest, appid, launch_options)
            self.legacy = await asyncio.to_thread(self._legacy_entries)
            return dk_rpc.ok(await self._state(), launch_options=result["launch_options"])

    # ---- updates ----

    @rpc
    async def check_for_updates(self) -> dict:
        return await asyncio.to_thread(self.updates.check, True)

    @rpc
    async def perform_update(self, expected_version: str) -> dict:
        return await asyncio.to_thread(self.updates.download, expected_version)

    async def _unload(self):
        if not hasattr(self, "updates"):
            return
        self._cancel = True
        self.updates.close()
        if self._scan_task:
            self._scan_task.cancel()

    async def _uninstall(self):
        # Decky runs this on every plugin update too: games stay set up; "Uninstall from all games" is the cleanup.
        decky.logger.info(f"uninstall/update: leaving {len(getattr(self, 'registry', {}))} game(s) set up")
