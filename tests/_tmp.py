# SPDX-License-Identifier: BSD-3-Clause
"""Temp folders for FSR 4.1 Lite's backend tests, cleaned up without fail.

Import it in every plugin test module (after `_harness`). On import it:
- sweeps folders an earlier run left behind (an interrupted run, or one from before this module existed), matched by
  this suite's fixture layouts only (sweep);
- points Python's tempfile at one folder for this run, %TEMP%/fsr4lite-tests-<random>, removed when the run ends, so
  every mkdtemp() in the run, the shared DeckyKit tests' too, lands there and goes away with it.
temp_dir(case) is a folder removed right after the test, and small_fsr4() makes AMD's FSR 4 files 64 bytes for tests:
before 2026-11-09 each test wrote both at full size (158 MB) and nothing deleted them.
"""

import atexit
import os
import re
import shutil
import sys
import tempfile
import time
from unittest import mock

import sml_assets

RUN_PREFIX = "fsr4lite-tests-"
SYSTEM_TEMP = tempfile.gettempdir()
_MKDTEMP = re.compile(r"^tmp[a-z0-9_]{8}$")  # Python's own mkdtemp() names


# Every name this suite (and the shared DeckyKit tests) puts at the top of a temp folder, as found in %TEMP% on
# 2026-11-09 across 19,000 leftover folders.
FIXTURE_NAMES = {
    ".config", ".local", "100", "101", "Downloads", "EasyAntiCheat", "Engine", "Game", "Game.exe", "Games", "Old",
    "Online",
    "OptiPatcher.asi", "OptiScaler.dll", "OptiScaler.ini", "OptiScaler.log", "Overwatch.exe", "Ubisoft", "Witcher",
    "a", "a.exe", "amdvkffx64.dll", "amdxcffx64.dll", "b.exe", "backup", "big.bin", "c.exe", "compat.json",
    "dinput8.dll", "exes.json", "f.bin", "ffx.dll", "file.bin", "fsr4", "g.exe", "game", "game.exe", "games.json",
    "loaders.json", "manifest.json", "old-optiscaler", "op", "optipatcher", "optiscaler", "optiscaler-20261024",
    "optiscaler.json", "outside", "pkg", "proc", "readme.txt", "ref", "reframework", "release.json", "settings.json",
    "shim.dll", "steamapps", "sub", "userdata", "x",
}
_FIXTURE_NAME = re.compile(r"^(.+?)(\.last-good)*(\.corrupt-\d{8}T\d{6}Z-[0-9a-f]{6})?$|^reframework-\d+$")


def _is_fixture(path):
    """Whether a tmpXXXXXXXX folder is one this suite made: its big layouts (a fake Steam home, a fake download
    folder with AMD's files, a package and a game folder), or nothing at the top but this suite's names. An empty
    one counts too: nothing is lost removing it."""
    j = os.path.join
    try:
        top = set(os.listdir(path))
    except OSError:
        return False
    if (os.path.isdir(j(path, ".local", "share", "Steam")) or os.path.isfile(j(path, "fsr4", "amdxcffx64.dll"))
            or os.path.isfile(j(path, "fsr4", "amdvkffx64.dll")) or {"pkg", "game"} <= top):
        return True

    def known(name):
        m = _FIXTURE_NAME.match(name)
        return name in FIXTURE_NAMES or bool(m and (m.group(1) in FIXTURE_NAMES or name.startswith("reframework-")))
    return all(known(n) for n in top)


def _is_decky_base(path):
    """The shared harness's decky-test-* folder: only the stand-in folders it makes."""
    try:
        return set(os.listdir(path)) <= {"settings", "runtime", "logs", "home", "homebrew"}
    except OSError:
        return False


def sweep(temp=SYSTEM_TEMP, keep=(), min_age=1800):
    """Folders earlier runs left in temp, removed: earlier run folders, the shared harness's decky-test-* folders and
    tmpXXXXXXXX folders with this suite's fixture layout, untouched for min_age seconds. Returns how many."""
    now = time.time()
    removed = 0
    try:
        names = os.listdir(temp)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(temp, name)
        if path in keep or not os.path.isdir(path) or os.path.islink(path):
            continue
        try:
            if now - os.path.getmtime(path) < min_age:  # another run going on at the same time keeps its folders
                continue
        except OSError:
            continue
        if (name.startswith(RUN_PREFIX) or (name.startswith("decky-test-") and _is_decky_base(path))
                or (_MKDTEMP.match(name) and _is_fixture(path))):
            shutil.rmtree(path, ignore_errors=True)
            removed += not os.path.exists(path)
    return removed


def _start():
    decky = sys.modules.get("decky")
    base = os.path.dirname(getattr(decky, "DECKY_PLUGIN_SETTINGS_DIR", "") or "")
    sweep(keep={base})
    run = tempfile.mkdtemp(prefix=RUN_PREFIX, dir=SYSTEM_TEMP)
    tempfile.tempdir = run
    atexit.register(shutil.rmtree, run, True)
    if os.path.basename(base).startswith("decky-test-"):  # the shared harness made it before this module loaded
        atexit.register(shutil.rmtree, base, True)


if not getattr(tempfile, "_fsr4lite_run", False):
    tempfile._fsr4lite_run = True
    _start()


def temp_dir(case):
    """A new folder, removed when the test ends (pass or fail)."""
    path = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, path, True)
    return path


def small_fsr4(size=64):
    """mock.patch.dict that makes AMD's FSR 4 files `size` bytes for the plugin's size checks: the tests write
    placeholders, never AMD's real files, so they needn't be 158 MB."""
    return mock.patch.dict(sml_assets.FSR4_FILES, {n: {**s, "size": size} for n, s in sml_assets.FSR4_FILES.items()})
