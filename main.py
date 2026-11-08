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
import dk_net  # noqa: E402
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
# FPS line with the upscaler and render -> output resolution; auto_update: each new OptiScaler nightly copied into
# every set-up game that isn't running (the widget's AutoUpdateGames, on by default).
DEFAULT_SETTINGS = {"session_toast": True, "watermark": False, "overlay": False, "overlay_size": "large",
                    "overlay_pos": "topleft", "auto_update": True}
NOT_INI = ("session_toast", "auto_update")  # settings that don't go into OptiScaler.ini
UPDATE_LOOK_EVERY = 300  # how often set-up games are compared with the current build (GitHub is asked far less)
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


def _with_overrides(options, manifest):
    """Steam launch options with OptiScaler's loader name and, when REFramework was added, dinput8: Proton only loads
    a game folder's dinput8.dll with an override, like OptiScaler's."""
    options = sml_opti.with_override(options, manifest["proxy"])
    return sml_opti.with_override(options, "dinput8.dll") if manifest.get("reframework") else options


def scan_library(steam_root, exes=None):
    """Every Steam game and non-Steam shortcut with a game exe. Games without upscaler files stay in the scan, like
    in the widget (many build FSR 2 or 3 in, which OptiScaler can search for); the panel offers them only while they
    run, not in the library list. exes: str(appid) -> the exe the game was seen running (relative to its folder),
    used instead of the folder guess."""
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
                seen = (exes or {}).get(appid[0])
                exe = os.path.join(root, *seen.split("/")) if seen else None
                exe = exe if exe and os.path.isfile(exe) else None
                games.append((int(appid[0]), title[0] if title else installdir[0], root, exe, False))
    for appid, name, exe in fsr4_games.shortcuts(steam_root):
        root = os.path.dirname(exe)
        if os.path.isdir(root):
            games.append((appid, name, root, exe, True))
    out = []
    for appid, name, root, exe, nonsteam in games:
        info = sml_opti.analyze(root, exe)
        if not info:
            continue
        out.append({"appid": appid, "name": name, "install_dir": root, "nonsteam": nonsteam, **info})
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
            # str(appid) -> the exe the game was seen running, relative to its folder (the widget installs next to
            # the running game's exe; folder layouts like Phantom Blade Zero's platform/steam/PBZ.exe fool a guess)
            self.exes_path = os.path.join(settings_dir, "exes.json")
            # the OptiScaler build the last "games updated" notification named (one notification per build)
            self.notice_path = os.path.join(settings_dir, "optiscaler.json")
            self.opti_note = ""  # the last check's outcome for the panel
            self.exes, self._watchers = {}, {}
            self.launchers = {}  # str(appid) -> exes OptiScaler showed never draw, never picked again
            self.seen = {}  # appid -> the game's processes the last watch saw, for the support report
            self.programs = {}  # appid -> every Windows program running at the last watch, for the support report
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
            exes = await asyncio.to_thread(_read, self.exes_path, {})

            def _rel_ok(v):
                return isinstance(v, str) and v.lower().endswith(".exe") and not os.path.isabs(v) \
                    and ".." not in v.split("/")
            launchers = exes.pop("launchers", {}) if isinstance(exes.get("launchers"), dict) else {}
            self.launchers = {k: [v for v in vs if _rel_ok(v)] for k, vs in launchers.items() if isinstance(vs, list)}
            self.exes = {k: v for k, v in exes.items() if _rel_ok(v) and v not in self.launchers.get(k, [])}
            try:
                os.chmod(SEVENZIP, 0o755)
            except OSError:
                pass
            self.assets_ok = await asyncio.to_thread(sml_assets.ready, _data_dir())
            await asyncio.to_thread(self._refresh_settings)
            self.legacy = await asyncio.to_thread(self._legacy_entries)
            self._scan_task = asyncio.create_task(self.scan_games())
            self._updater = asyncio.create_task(self._update_loop())
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
        view["tip"] = sml_opti.tips(g["exe_name"], g["upscalers"], g["name"])
        view["compat"] = sml_opti.compat_text(g["name"], g["exe_name"])
        view["verdict"], view["detail"] = ("", "")
        if entry:
            view["verdict"], view["detail"] = entry.get("verdict", "unplayed"), entry.get("detail", "")
            view["proxy"] = entry.get("proxy", "")
        return view

    async def _state(self):
        build = await asyncio.to_thread(sml_assets.current, _data_dir())
        return {
            "version": VERSION, "home": _home(), "assets_ready": self.assets_ok,
            "download": dict(self.download), "settings": dict(self.settings), "scanned": self.scanned,
            "games": [self._view(g) for g in self.games], "legacy": list(self.legacy),
            "optiscaler": sml_assets.label(build or sml_assets.OPTISCALER["name"]), "opti_note": self.opti_note,
        }

    # ---- OptiScaler and REFramework nightlies (the widget's OptiScalerSource + StartAutoUpdate) ----

    def _builds(self):
        """The builds an install copies, recorded in the game's manifest so update_opti knows what it has."""
        return {"build": sml_assets.current(_data_dir()), "ref_build": sml_assets.reframework_build(_data_dir())}

    async def _update_loop(self):
        """Every few minutes: a newer nightly (GitHub is asked at most every 6 hours, REFramework once a day), then
        every set-up game that isn't running brought up to it. A game that was running gets it once it's closed."""
        await asyncio.sleep(20)
        while True:
            try:
                await self._check_builds(force=False)
            except Exception as e:  # noqa: BLE001 - the loop must survive anything
                decky.logger.warning(f"nightly check: {e!r}")
            await asyncio.sleep(UPDATE_LOOK_EVERY)

    async def _check_builds(self, force):
        """Looks for newer nightlies, then updates games when automatic updates are on. A line for the panel."""
        if not self.assets_ok:
            return ""
        data = _data_dir()
        notice = await asyncio.to_thread(_read, self.notice_path, {})
        if not notice.get("notified"):  # first run with nightlies: the build already here is no news
            await asyncio.to_thread(dk_fs.write_json, self.notice_path,
                                    {"notified": await asyncio.to_thread(sml_assets.current, data)})
        try:
            build, changed = await asyncio.to_thread(sml_assets.update_optiscaler, data, SEVENZIP, force)
            if changed:
                decky.logger.info(f"new OptiScaler build: {build}")
            self.opti_note = ""
        except Exception as e:  # noqa: BLE001 - shown in the panel, the current build stays in use
            self.opti_note = f"Couldn't check for a newer OptiScaler ({e}). Using the one you have."
            decky.logger.warning(f"OptiScaler check: {e!r}")
        if any(e.get("reframework") for e in self.registry.values()) or sml_assets.reframework_build(data):
            try:
                await asyncio.to_thread(sml_assets.update_reframework, data, force)
            except Exception as e:  # noqa: BLE001
                decky.logger.warning(f"REFramework check: {e!r}")
        if not self.settings["auto_update"]:
            return self.opti_note
        updated, running = await self._update_games()
        build = await asyncio.to_thread(sml_assets.current, data)
        notice = await asyncio.to_thread(_read, self.notice_path, {})
        if updated and notice.get("notified") != build:
            await asyncio.to_thread(dk_fs.write_json, self.notice_path, {"notified": build})
            games = "1 game now uses" if updated == 1 else f"{updated} games now use"
            await decky.emit("games_updated", "FSR 4.1 Lite: games updated",
                             f"{games} {sml_assets.label(build)}. Their settings are unchanged.")
        if self.opti_note:
            return self.opti_note
        parts = []
        if updated:
            parts.append("Updated 1 game." if updated == 1 else f"Updated {updated} games.")
        if running:
            parts.append("1 running game updates once it's closed." if running == 1
                         else f"{running} running games update once they're closed.")
        return " ".join(parts)

    async def _update_games(self):
        """Every set-up game that isn't running brought to the current OptiScaler and REFramework builds, keeping its
        settings. Returns (games updated, games skipped because they run)."""
        data = _data_dir()
        build, package = sml_assets.current(data), sml_assets.package_dir(data)
        ref, ref_dll = sml_assets.reframework_build(data), sml_assets.reframework_path(data)
        if not build:
            return 0, 0
        updated = running = 0
        async with self.lock:
            for key, entry in list(self.registry.items()):
                if not entry.get("proxy"):
                    continue
                manifest = await asyncio.to_thread(sml_opti.load_manifest, entry["exe_dir"])
                if not manifest:
                    continue
                stale = manifest.get("opti_build") != build or bool(
                    manifest.get("reframework") and ref and manifest.get("ref_build") != ref)
                if not stale:
                    continue
                appid = int(key) if key.isdigit() else None
                game = self._game(appid) if appid is not None else None
                busy = appid in self.sessions
                if not busy and game:
                    busy = bool(await asyncio.to_thread(sml_opti.running_processes, game["install_dir"]))
                if busy:
                    running += 1
                    continue
                try:
                    did = await asyncio.to_thread(sml_opti.update_opti, entry["exe_dir"], package, build)
                    did = await asyncio.to_thread(sml_opti.update_reframework, entry["exe_dir"], ref_dll, ref) or did
                    if did and manifest.get("opti_build"):
                        updated += 1  # a game set up before nightly updates only gets its build noted
                except OSError as e:
                    decky.logger.warning(f"update failed in {entry['exe_dir']} ({dk_fs.shown(e)})")
        return updated, running

    @rpc
    async def check_optiscaler(self) -> dict:
        """Check now: GitHub asked right away for a newer nightly, then every game that isn't running updated."""
        note = await self._check_builds(force=True)
        build = sml_assets.label(await asyncio.to_thread(sml_assets.current, _data_dir()))
        return dk_rpc.ok(await self._state(), message=note or f"Up to date: {build}.")

    @rpc
    async def get_state(self) -> dict:
        return dk_rpc.ok(await self._state())

    @rpc
    async def scan_games(self) -> dict:
        self.games = await asyncio.to_thread(scan_library, _steam_root(), dict(self.exes))
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

    async def _use_exe(self, appid, path):
        """The game runs path: remember it and point the game at it (scans and the next setup use it)."""
        game = self._game(appid)
        if not game or game["nonsteam"] or os.path.join(game["exe_dir"], game["exe_name"]) == path:
            return
        rel = os.path.relpath(path, game["install_dir"]).replace(os.sep, "/")
        if rel in self.launchers.get(str(appid), []):
            return  # seen running, but OptiScaler showed it never draws: a launcher
        info = await asyncio.to_thread(sml_opti.analyze, game["install_dir"], path)
        if not info:
            return
        game.update(info)
        self.exes[str(appid)] = rel
        await asyncio.to_thread(dk_fs.write_json, self.exes_path, {**self.exes, "launchers": self.launchers})
        decky.logger.info(f"{appid} runs {rel}")

    async def _not_the_game(self, appid, helper):
        """helper ran a whole session with OptiScaler and never drew: a launcher. Never picked again; the game is an
        exe of the same name in Binaries/Win64, else the folder guess (sml_opti.game_besides)."""
        game = self._game(appid)
        rel = os.path.relpath(helper, game["install_dir"]).replace(os.sep, "/")
        marked = self.launchers.setdefault(str(appid), [])
        if rel not in marked:
            marked.append(rel)
        if self.exes.get(str(appid)) == rel:
            del self.exes[str(appid)]
        await asyncio.to_thread(dk_fs.write_json, self.exes_path, {**self.exes, "launchers": self.launchers})
        decky.logger.info(f"{appid}: {rel} is a launcher (OptiScaler saw it never draw)")
        alt = await asyncio.to_thread(sml_opti.game_besides, game["install_dir"], helper)
        if alt:
            await self._use_exe(appid, alt)

    async def _watch_exe(self, appid, started):
        """For the first two minutes of a session: the exe the game really runs, from the process list (graphics
        loaded and game-sized memory, see sml_opti.running_exe). Watched the whole time, so a launcher that starts the
        game is passed over for the game itself."""
        best = 0
        try:
            for _ in range(24):
                await asyncio.sleep(5)
                game = self._game(appid)
                if self.sessions.get(appid) != started or not game or game["nonsteam"]:
                    return
                seen = await asyncio.to_thread(sml_opti.running_processes, game["install_dir"])
                if seen:
                    self.seen[appid] = seen  # for the support report
                self.programs[appid] = await asyncio.to_thread(sml_opti.windows_programs)
                path, mb = sml_opti.pick_game(seen)
                if path and mb >= sml_opti.GAME_MEMORY_MB and mb > best:
                    best = mb
                    await self._use_exe(appid, path)
        finally:
            self._watchers.pop(appid, None)

    def _refresh_settings(self):
        """Every set-up game's OptiScaler.ini brought up to this version's settings (OptiDllPath, 2.2.9)."""
        for entry in list(self.registry.values()):
            if entry.get("proxy"):
                try:
                    sml_opti.apply_settings(entry["exe_dir"], self._settings_for_ini(entry.get("height")))
                except OSError as e:
                    decky.logger.warning(f"settings not refreshed in {entry['exe_dir']} ({dk_fs.shown(e)})")

    async def _move_to_real_exe(self, appid, entry, launch_options, started=None):
        """A game set up next to an exe it doesn't run (seen running, named in OptiScaler's log, or shown by the log
        to be a launcher that never draws): the setup moves next to the exe it does run. The result for
        session_ended, or None when nothing moved."""
        game = self._game(appid)
        if not game or game["nonsteam"]:
            return None
        log = await asyncio.to_thread(sml_opti.read_log, entry["exe_dir"])
        if "ffxProvider_FSR4Lite_Int8" in log:
            return None  # Lite runs from where it is: never move a working setup
        # a whole session (a minute or more) with OptiScaler loaded and no device, swapchain or upscaler: a launcher
        if (started and time.time() - started >= 60 and log and not sml_opti.renders(log)
                and sml_opti.log_time(entry["exe_dir"]) >= started - 2
                and os.path.normpath(game["exe_dir"]) == os.path.normpath(entry["exe_dir"])):
            await self._not_the_game(appid, os.path.join(game["exe_dir"], game["exe_name"]))
        logged = sml_opti.logged_exe(log)
        if logged and logged.lower() != game["exe_name"].lower():
            path = await asyncio.to_thread(sml_opti.find_exe, game["install_dir"], logged)
            if path:
                await self._use_exe(appid, path)
        if os.path.normpath(game["exe_dir"]) == os.path.normpath(entry["exe_dir"]):
            return None
        key, proxy = str(appid), entry["proxy"]
        restored = await self._disable(appid, launch_options, keep_retry=True)
        ref = sml_assets.reframework_path(_data_dir())
        try:
            manifest = await asyncio.to_thread(
                sml_opti.install, game["exe_dir"], game["exe_name"], sml_assets.package_dir(_data_dir()),
                sml_assets.fsr4_paths(_data_dir()), self._settings_for_ini(), proxy, game["upscalers"], None,
                ref if entry.get("reframework") and os.path.isfile(ref) else None, **self._builds())
        except sml_opti.InstallError as e:
            await asyncio.to_thread(self._save_registry)
            return {"managed": True, "verdict": "none", "detail": str(e), "launch_options": restored}
        new = _with_overrides(restored, manifest)
        detail = f"Moved next to {game['exe_name']}, the exe the game really runs. Play once more."
        self.registry[key] = {"exe_dir": game["exe_dir"], "proxy": manifest["proxy"], "tried": [manifest["proxy"]],
                              "launch_original": entry.get("launch_original"), "launch_applied": new,
                              "reframework": bool(manifest.get("reframework")), "installed_at": time.time(),
                              "verdict": "unplayed", "detail": detail}
        await asyncio.to_thread(self._save_registry)
        decky.logger.info(f"moved {appid} from {entry['exe_dir']} to {game['exe_dir']}")
        return {"managed": True, "verdict": "unplayed", "retry": manifest["proxy"], "launch_options": new,
                "detail": detail}

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
            if appid in self.sessions and not game["nonsteam"]:
                # The game is running: like the widget, set it up next to the exe that is the game right now (graphics
                # loaded, game-sized memory), not the folder guess. Only something small running yet (a launcher, a
                # game still starting): wait, as the widget only installs into the game on screen. Nothing seen at
                # all: the folder guess, as before.
                seen = await asyncio.to_thread(sml_opti.running_processes, game["install_dir"])
                if seen:
                    self.seen[appid] = seen
                self.programs[appid] = await asyncio.to_thread(sml_opti.windows_programs)
                path, mb = sml_opti.pick_game(seen)
                starting = time.time() - self.sessions[appid] < 90
                if path and (mb >= sml_opti.GAME_MEMORY_MB or not starting):
                    await self._use_exe(appid, path)  # after 90 s a small game's own process counts too
                    game = self._game(appid)
                elif path and starting:
                    # only something small draws yet (a launcher, a loading screen): the one case worth waiting for.
                    # Nothing seen drawing at all (graphics can't be read): the folder guess, never a refusal.
                    return dk_rpc.fail("The game is still starting. Wait until you're in its menu, then press "
                                       "Install again.", await self._state())
            reframework = None
            if sml_opti.needs_reframework(game["name"], game["exe_name"]):
                try:
                    reframework = await asyncio.to_thread(sml_assets.fetch_reframework, _data_dir())
                except (dk_net.NetError, OSError, RuntimeError) as e:
                    return dk_rpc.fail(f"Couldn't download REFramework, which this game needs ({e}). Try again.",
                                       await self._state())
            try:
                manifest = await asyncio.to_thread(
                    sml_opti.install, game["exe_dir"], game["exe_name"], sml_assets.package_dir(_data_dir()),
                    sml_assets.fsr4_paths(_data_dir()), self._settings_for_ini(), entry.get("next_proxy"),
                    game["upscalers"], self.loaders.get(game["exe_name"].lower()), reframework, **self._builds())
            except sml_opti.InstallError as e:
                return dk_rpc.fail(str(e), await self._state())
            original = entry.get("launch_original", launch_options)
            new = _with_overrides(launch_options, manifest)
            self.registry[key] = {"exe_dir": game["exe_dir"], "proxy": manifest["proxy"],
                                  "tried": sorted(set(entry.get("tried", [])) | {manifest["proxy"]}),
                                  "launch_original": original, "launch_applied": new,
                                  "reframework": bool(manifest.get("reframework")),
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
        if entry.get("reframework"):
            launch_options = sml_opti.without_override(launch_options, "dinput8.dll")
        restored = sml_opti.without_override(launch_options, entry["proxy"], entry.get("launch_original"))
        if keep_retry:
            self.registry[key] = {"tried": entry.get("tried", []), "launch_original": entry.get("launch_original"),
                                  "exe_dir": entry["exe_dir"], "reframework": entry.get("reframework", False)}
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
            if key not in NOT_INI:
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
        if appid not in self._watchers:
            self._watchers[appid] = asyncio.create_task(self._watch_exe(appid, self.sessions[appid]))
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
        """While the game runs: whether this session's OptiScaler.log already shows the Lite model, with what it runs
        (summary: input, render and output resolution, mode), checked until it does, however late in the session.
        hint: once the game has run 90 seconds without Lite, why (pick an upscaler, the FSR 4 file, ...)."""
        entry = self.registry.get(str(appid))
        started = self.sessions.get(appid)
        if not entry or not entry.get("proxy") or not started or entry.get("installed_at", 0) > started:
            return dk_rpc.ok(lite=False, done=True)
        waited = time.time() - started
        if sml_opti.log_time(entry["exe_dir"]) < started - 2:
            return dk_rpc.ok(lite=False, done=False, hint="OptiScaler hasn't loaded yet. When you quit, the plugin "
                             "tries the next loader name." if waited > 90 else "")
        log = await asyncio.to_thread(sml_opti.read_log, entry["exe_dir"])
        if "ffxProvider_FSR4Lite_Int8" in log:
            return dk_rpc.ok(lite=True, done=False, summary=sml_opti.summary(log), minutes=int(waited // 60))
        verdict, detail = sml_opti.verdict(log)
        return dk_rpc.ok(lite=False, done=False, hint=detail if waited > 90 and verdict != "fsr4" else "")

    @rpc
    async def session_ended(self, appid: int, launch_options: str = "") -> dict:
        key = str(appid)
        async with self.lock:
            entry = self.registry.get(key)
            started = self.sessions.pop(appid, None)
            if not entry or not entry.get("proxy"):
                return dk_rpc.ok(managed=False)
            moved = await self._move_to_real_exe(appid, entry, launch_options, started)
            if moved:
                return dk_rpc.ok(**moved)
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
            # OptiScaler loaded but looked for AMD's FSR 4 file in another folder (its DllPath, the folder Steam starts
            # some games in): the files go there too, and the next session can run Lite
            if detail == sml_opti.NO_FSR4_FILE and game:
                target = sml_opti.local_dir(game["install_dir"], sml_opti.logged_dll_dir(log))
                if target and os.path.normpath(target) != os.path.normpath(exe_dir) and await asyncio.to_thread(
                        sml_opti.add_fsr4_copy, exe_dir, target, sml_assets.fsr4_paths(_data_dir())):
                    where = os.path.relpath(target, game["install_dir"]).replace(os.sep, "/")
                    detail = f"OptiScaler looks for AMD's FSR 4 file in {where}, so it's there now too. Play once more."
                    entry["verdict"], entry["detail"] = "unplayed", detail
                    result.update(verdict="unplayed", detail=detail, retry=entry["proxy"],
                                  launch_options=launch_options)
                    decky.logger.info(f"{appid}: FSR 4 files added to {target}")
            # OptiScaler never loaded: the game skipped that file name. Next name, like the widget's game watcher.
            if verdict == "none" and started:
                ref = sml_assets.reframework_path(_data_dir()) if entry.get("reframework") else None
                nxt = game and sml_opti.pick_proxy(exe_dir, game["exe_name"], entry.get("tried", []) +
                                                   [entry["proxy"]])
                if nxt:
                    restored = await self._disable(appid, launch_options, keep_retry=True)
                    self.registry[key]["next_proxy"] = nxt
                    try:
                        manifest = await asyncio.to_thread(
                            sml_opti.install, exe_dir, game["exe_name"], sml_assets.package_dir(_data_dir()),
                            sml_assets.fsr4_paths(_data_dir()), self._settings_for_ini(), nxt, game["upscalers"],
                            None, ref if ref and os.path.isfile(ref) else None, **self._builds())
                    except sml_opti.InstallError as e:
                        await asyncio.to_thread(self._save_registry)
                        return dk_rpc.ok(managed=True, verdict="none", detail=str(e), launch_options=restored)
                    new = _with_overrides(restored, manifest)
                    self.registry[key] = {"exe_dir": exe_dir, "proxy": manifest["proxy"],
                                          "tried": sorted(set(self.registry[key].get("tried", [])) |
                                                          {manifest["proxy"]}),
                                          "reframework": bool(manifest.get("reframework")),
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
            "opti_build": sml_assets.label((manifest or {}).get("opti_build", "")),
            "opti_current": sml_assets.label(sml_assets.current(_data_dir())),
            "log_lines": [l for l in log.splitlines() if any(k in l for k in (
                "FSR4", "Fsr4", "amdxcffx64", "amdvkffx64", "Lite", "upscaler", "Upscaler", "error", "Error"))][-12:],
        }

    def _report_finding(self, appid):
        """How the plugin picked the exe: the remembered one, launchers it ruled out, the folder guess, and the game's
        processes the last watch saw (memory, graphics loaded)."""
        game = self._game(appid) or {}
        root = game.get("install_dir", "")
        rel = (lambda p: os.path.relpath(p, root).replace(os.sep, "/")) if root else (lambda p: p)
        guess = sml_opti.analyze(root) if root and os.path.isdir(root) else None
        seen = self.seen.get(appid, [])
        entry = self.registry.get(str(appid)) or {}
        return ["== How the plugin found the game ==",
                f"Game folder: {root}",
                f"Seen running and remembered: {self.exes.get(str(appid), '(none)')}",
                f"Ruled out as launchers: {', '.join(self.launchers.get(str(appid), [])) or '(none)'}",
                f"Folder guess: {rel(os.path.join(guess['exe_dir'], guess['exe_name'])) if guess else '(none)'}",
                f"Launch options set: {entry.get('launch_applied', '')}",
                "Processes from the game folder at the last check (first two minutes of a session):",
                *([f"  {rel(p['path'])}: {p['mb']} MB, graphics {'loaded' if p['graphics'] else 'not loaded'}"
                   for p in seen] or ["  (none seen since the plugin loaded)"]),
                "", "== Windows programs running ==",
                "At the last check in the game's first two minutes:",
                *self._programs_lines(self.programs.get(appid)),
                "Now, as this report was saved:",
                *self._programs_lines(sml_opti.windows_programs()),
                "", "== Every .exe in the game folder ==",
                *([f"  {p} ({mb:.1f} MB)" for p, mb in sml_opti.game_exes(root)] if root and os.path.isdir(root)
                  else ["  (game folder not found)"])]

    @staticmethod
    def _programs_lines(programs):
        if programs is None:
            return ["  (no check yet since the plugin loaded)"]
        return [f"  {p['exe']}  [{p['mb']} MB, graphics {'loaded' if p['graphics'] else 'not loaded'}, "
                f"started in {p['cwd']}]" for p in programs] or ["  (none)"]

    def _report_other_logs(self, appid, exe_dir):
        """Every other OptiScaler.log in the game folder (a launcher's, an older setup's), newest first."""
        game = self._game(appid) or {}
        root = game.get("install_dir", "")
        logs = sml_opti.all_logs(root) if root and os.path.isdir(root) else []
        logs = [p for p in logs if os.path.normpath(os.path.dirname(p)) != os.path.normpath(exe_dir or "")]
        out = ["== Other OptiScaler logs in the game folder =="]
        if not logs:
            return out + ["(none)"]
        for path in logs:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
            out += ["", f"-- {os.path.relpath(path, root).replace(os.sep, '/')} ({when}) --",
                    *sml_opti.read_log(os.path.dirname(path), 64 * 1024).splitlines()[-150:]]
        return out

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
            f"FSR 4.1 Lite {VERSION} support report",
            f"OptiScaler: {d['opti_current']} (this game: {d['opti_build'] or 'set up before nightly updates'})",
            f"Game: {d['name']} ({appid})", f"Exe: {d['exe_dir']}/{d['exe_name']}", f"Loader: {d['proxy']}",
            f"Proton: {d['proton']}", f"Upscalers found: {', '.join(d['upscalers']) or 'none'}",
            f"Files in place: {d['files_ok']} {d['missing']}", f"Last verdict: {d['verdict']} {d['detail']}",
            "", "== OptiScaler.ini (set values) ==", *ini, "", "== OptiScaler.log (end) ==",
            *(log.splitlines()[-400:] or ["(no log: OptiScaler hasn't run in this game yet)"]),
            "", *self._report_finding(appid), "", *self._report_other_logs(appid, exe_dir),
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
        for task in (self._scan_task, getattr(self, "_updater", None)):
            if task:
                task.cancel()

    async def _uninstall(self):
        # Decky runs this on every plugin update too: games stay set up; "Uninstall from all games" is the cleanup.
        decky.logger.info(f"uninstall/update: leaving {len(getattr(self, 'registry', {}))} game(s) set up")
