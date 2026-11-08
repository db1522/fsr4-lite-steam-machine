# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Steam Machine Life
"""What FSR 4.1 Lite downloads. Nothing from AMD or OptiScaler ships inside the plugin.
- OptiScaler: the newest nightly from optiscaler/OptiScaler-nightly, like the Windows widget's OptiScalerSource (a
  .7z, unpacked with the bundled 7-Zip, bin/7zz). Looked for at most every 6 hours (update_optiscaler). Each download
  is checked against the SHA-256 GitHub publishes for it, and a build whose OptiScaler.ini lacks the settings that
  force the Lite model is never used. OPTISCALER is the fallback when GitHub's API can't be reached at the first
  download.
- AMD's FSR 4.1.2 files for DirectX 12 and Vulkan, from the FSR 4.1 Lite widget's file mirror (AMD-signed,
  unmodified), pinned by size and SHA-256.
- REFramework: the newest nightly from praydog/REFramework-nightly, only once a Capcom RE Engine game that needs it is
  set up (fetch_reframework), looked for once a day after that."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime

import dk_net

HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
REDIRECTS = HOSTS - {"github.com"}
API_HOSTS = frozenset({"api.github.com"})
API_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "FSR4Lite-SteamMachine"}
OPTI_API = "https://api.github.com/repos/optiscaler/OptiScaler-nightly/releases?per_page=10"
OPTI_DOWNLOADS = "https://github.com/optiscaler/OptiScaler-nightly/releases/download/"
REF_API = "https://api.github.com/repos/praydog/REFramework-nightly/releases/latest"
REF_DOWNLOADS = "https://github.com/praydog/REFramework-nightly/releases/download/"
OPTI_CHECK_EVERY = 6 * 3600  # the widget's CheckInterval: a new nightly reaches players the same day
REF_CHECK_EVERY = 24 * 3600  # the widget's REFrameworkSource.CheckEvery
MAX_ARCHIVE = 256 << 20
LITE_KEYS = ("Fsr4GpuSupport", "Fsr4Model")  # without them OptiScaler can't be told to run the Lite model

# The fallback for the first download when GitHub's API can't be reached (rate limit, outage): a known-good nightly.
OPTISCALER = {
    "name": "OptiScaler_v10.0.0-pre1_20261024",
    "url": "https://github.com/optiscaler/OptiScaler-nightly/releases/download/nightly-20261024/"
           "OptiScaler_v10.0.0-pre1_20261024.7z",
    "size": 57125569,
    "sha256": "74f20189e0ec76288c86d69057b3feb4750f4680118a9852fb743b343274ac1d",
    "folder": "optiscaler-20261024",  # where plugins before 2.2.17 kept it
}
FSR4_FILES = {
    "amdxcffx64.dll": {"url": "https://github.com/db1522/fsr4-files/releases/download/v4.1.2/amdxcffx64.dll",
                       "size": 85684104,
                       "sha256": "c33a287f3048bf02311cae430b6a977500b94ca7b315cd7bff751e6b03e483e3"},
    "amdvkffx64.dll": {"url": "https://github.com/db1522/fsr4-files/releases/download/v4.1.2/amdvkffx64.dll",
                       "size": 72497568,
                       "sha256": "80e761f7c8c0ec8ead7b321df01911baaf917defae51388d29eaecb1d6bc58bd"},
}
TOTAL = OPTISCALER["size"] + sum(f["size"] for f in FSR4_FILES.values())
# REFramework (praydog, MIT) for the RE Engine games OptiScaler needs it in. Only its dinput8.dll is used, as its
# release notes say for non-VR use. This one is the fallback when GitHub's API can't be reached at the first download.
REFRAMEWORK = {
    "tag": "nightly-01433-d4611aef1d63effd3a736bdf9404ea702428017d",
    "url": "https://github.com/praydog/REFramework-nightly/releases/download/"
           "nightly-01433-d4611aef1d63effd3a736bdf9404ea702428017d/REFramework.zip",
    "size": 13267029,
    "sha256": "b3ff4f497be6f108ef494c2c02156b61b8d04f3171378ecc0dc28c218ee296b3",
}


# ---- small helpers ----

def label(build):
    """"OptiScaler v10.0.0-pre1 (Nov 7, 2026)" for a build like "OptiScaler_v10.0.0-pre1_20261107" (the widget's
    OptiPackage.Label): nightlies share a version number, so the date tells them apart."""
    if not build:
        return ""
    name = build[len("OptiScaler_"):] if build.lower().startswith("optiscaler_") else build
    head, _, tail = name.rpartition("_")
    try:
        day = datetime.strptime(tail, "%Y%m%d")
        return f"OptiScaler {head} ({day.strftime('%b')} {day.day}, {day.year})"
    except ValueError:
        return f"OptiScaler {name}"


def ref_label(tag):
    """"REFramework nightly 01433" for a release tag like "nightly-01433-d4611ae..."."""
    m = re.match(r"nightly-(\d+)", tag or "")
    return f"REFramework nightly {m.group(1)}" if m else (f"REFramework {tag}" if tag else "")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _checked_at(path):
    try:
        return float(_read(path) or 0)
    except ValueError:
        return 0.0


def _api(url, cancelled=None):
    try:
        return json.loads(dk_net.get(url, 4 << 20, hosts=API_HOSTS, headers=API_HEADERS, deadline=60,
                                     cancel=cancelled))
    except ValueError as e:
        raise RuntimeError("GitHub sent an answer that isn't JSON") from e


def _digest(asset):
    """The SHA-256 GitHub publishes for a release file ("sha256:<hex>"), or None."""
    d = str(asset.get("digest") or "")
    return d[7:].lower() if d.lower().startswith("sha256:") and re.fullmatch(r"[0-9a-fA-F]{64}", d[7:]) else None


# ---- OptiScaler ----

def _opti_root(data):
    return os.path.join(data, "optiscaler")


def _migrate(data):
    """Before 2.2.17 the one pinned build sat in data/optiscaler-20261024: it becomes the current build."""
    old = os.path.join(data, OPTISCALER["folder"])
    if os.path.isfile(os.path.join(old, "OptiScaler.dll")) and not _read(os.path.join(_opti_root(data), "latest.txt")):
        target = os.path.join(_opti_root(data), OPTISCALER["name"])
        os.makedirs(_opti_root(data), exist_ok=True)
        if not os.path.isdir(target):
            os.replace(old, target)
        _write(os.path.join(_opti_root(data), "latest.txt"), OPTISCALER["name"])


def current(data):
    """The OptiScaler build ready to install ("OptiScaler_v10.0.0-pre1_20261107"), or "" before the first download."""
    try:
        _migrate(data)
    except OSError:
        pass
    build = _read(os.path.join(_opti_root(data), "latest.txt")) or OPTISCALER["name"]
    if "/" not in build and os.path.isfile(os.path.join(_opti_root(data), build, "OptiScaler.dll")):
        return build
    return ""


def package_dir(data):
    return os.path.join(_opti_root(data), current(data) or OPTISCALER["name"])


def fsr4_paths(data):
    return [os.path.join(data, "fsr4", name) for name in FSR4_FILES]


def ready(data):
    """True when OptiScaler is unpacked and both AMD files are there at their exact sizes."""
    if not current(data):
        return False
    for path, name in zip(fsr4_paths(data), FSR4_FILES):
        try:
            if os.path.getsize(path) != FSR4_FILES[name]["size"]:
                return False
        except OSError:
            return False
    return True


def newest_nightly(releases):
    """The newest usable OptiScaler build in a list of nightly releases (the widget's GetLatestAssetAsync): a .7z named
    OptiScaler*, not a debug build, fully uploaded, from a release that isn't a draft. {name, url, size, sha256}."""
    best = None
    for release in releases if isinstance(releases, list) else []:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        for a in release.get("assets") or []:
            if not isinstance(a, dict):
                continue
            name, url, size = str(a.get("name", "")), str(a.get("browser_download_url", "")), a.get("size")
            low = name.lower()
            if not (low.startswith("optiscaler") and low.endswith(".7z")) or "debug" in low or "/" in name:
                continue
            if a.get("state", "uploaded") != "uploaded" or not url.startswith(OPTI_DOWNLOADS):
                continue
            if not isinstance(size, int) or not 0 < size <= MAX_ARCHIVE:
                continue
            created = str(a.get("created_at", ""))
            if best is None or created > best["created"]:
                best = {"name": name[:-3], "url": url, "size": size, "sha256": _digest(a), "created": created}
    return best


def has_lite_settings(package):
    """The unpacked build's OptiScaler.ini still has the settings that force FSR 4's Lite model."""
    try:
        with open(os.path.join(package, "OptiScaler.ini"), encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    return all(re.search(rf"^\s*{k}\s*=", text, re.I | re.M) for k in LITE_KEYS)


def _unpack_optiscaler(data, sevenzip, spec, progress=None, cancelled=None, base=0):
    """Downloads one OptiScaler build, checks it and makes it the current one. Older builds are removed: set-up games
    keep their own copies."""
    sevenzip = runnable(sevenzip, data)
    root = _opti_root(data)
    os.makedirs(root, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        archive = os.path.join(tmp, "optiscaler.7z")
        step = (lambda n: progress(base + n, base + spec["size"])) if progress else None
        dk_net.download(spec["url"], archive, spec["size"], spec.get("sha256"), hosts=HOSTS, redirects=REDIRECTS,
                        deadline=1800, cancel=cancelled, progress=step)
        if os.path.getsize(archive) != spec["size"]:
            raise RuntimeError("OptiScaler's download is incomplete")
        out = os.path.join(tmp, "x")
        try:
            r = subprocess.run([sevenzip, "x", "-y", "-bd", f"-o{out}", archive], capture_output=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"Couldn't unpack OptiScaler ({e})") from e
        if r.returncode != 0 or not os.path.isfile(os.path.join(out, "OptiScaler.dll")):
            raise RuntimeError("Couldn't unpack OptiScaler: " + r.stderr.decode("utf-8", "replace")[-200:].strip())
        if not has_lite_settings(out):
            raise RuntimeError(f"{label(spec['name'])} has no setting for FSR 4's Lite model, so it isn't used")
        target = os.path.join(root, spec["name"])
        shutil.rmtree(target, ignore_errors=True)
        os.replace(out, target)
    _write(os.path.join(root, "latest.txt"), spec["name"])
    for name in os.listdir(root):
        if name != spec["name"] and os.path.isdir(os.path.join(root, name)):
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)
    shutil.rmtree(os.path.join(data, OPTISCALER["folder"]), ignore_errors=True)
    return spec["name"]


def update_optiscaler(data, sevenzip, force=False, cancelled=None, now=None):
    """Looks for a newer OptiScaler nightly (at most every 6 hours unless force) and makes it the current build.
    Returns (build, changed). Raises dk_net.NetError, OSError or RuntimeError; the current build stays in use."""
    now = time.time() if now is None else now
    have = current(data)
    marker = os.path.join(_opti_root(data), "last-check.txt")
    checked = _checked_at(marker)
    if have and not force and checked and 0 <= now - checked < OPTI_CHECK_EVERY:
        return have, False
    spec = newest_nightly(_api(OPTI_API, cancelled))
    _write(marker, str(now))
    if spec is None:
        raise RuntimeError("No OptiScaler build in the recent nightly releases")
    if spec["name"] == have:
        return have, False
    return _unpack_optiscaler(data, sevenzip, spec, cancelled=cancelled), True


# ---- REFramework ----

def _ref_root(data):
    return os.path.join(data, "reframework")


def reframework_path(data):
    return os.path.join(_ref_root(data), "dinput8.dll")


def reframework_build(data):
    """The REFramework nightly ready to install (its release tag), or ""."""
    tag = _read(os.path.join(_ref_root(data), "latest.txt"))
    return tag if tag and os.path.isfile(reframework_path(data)) else ""


def _ref_release(cancelled=None):
    rel = _api(REF_API, cancelled)
    tag = str(rel.get("tag_name", "")) if isinstance(rel, dict) else ""
    for a in (rel.get("assets") or []) if tag else []:
        url, size = str(a.get("browser_download_url", "")), a.get("size")
        if a.get("name") == "REFramework.zip" and url.startswith(REF_DOWNLOADS) and isinstance(size, int) \
                and 0 < size <= MAX_ARCHIVE:
            return {"tag": tag, "url": url, "size": size, "sha256": _digest(a)}
    raise RuntimeError("No REFramework.zip in REFramework's latest nightly")


def _unpack_reframework(data, spec, cancelled=None):
    folder = _ref_root(data)
    os.makedirs(folder, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        archive = os.path.join(tmp, "REFramework.zip")
        dk_net.download(spec["url"], archive, spec["size"], spec.get("sha256"), hosts=HOSTS,
                        redirects=REDIRECTS, deadline=600, cancel=cancelled)
        try:
            with zipfile.ZipFile(archive) as z:
                found = sorted((i for i in z.infolist() if i.filename.replace("\\", "/").split("/")[-1].lower() ==
                                "dinput8.dll" and not i.is_dir()), key=lambda i: i.filename.count("/"))
                if not found or found[0].flag_bits & 1 or found[0].file_size > 64 << 20:
                    raise RuntimeError("REFramework's download has no usable dinput8.dll")
                out = os.path.join(tmp, "dinput8.dll")
                with z.open(found[0]) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"Couldn't unpack REFramework ({e})") from e
        os.replace(out, reframework_path(data))
    _write(os.path.join(folder, "latest.txt"), spec["tag"])
    for name in os.listdir(data):  # pinned builds from before 2.2.17
        if name.startswith("reframework-"):
            shutil.rmtree(os.path.join(data, name), ignore_errors=True)
    return spec["tag"]


def update_reframework(data, force=False, cancelled=None, now=None):
    """REFramework's newest nightly, looked for at most once a day once one is here. Returns (tag, changed)."""
    now = time.time() if now is None else now
    have = reframework_build(data)
    marker = os.path.join(_ref_root(data), "last-check.txt")
    checked = _checked_at(marker)
    if have and not force and checked and 0 <= now - checked < REF_CHECK_EVERY:
        return have, False
    spec = _ref_release(cancelled)
    _write(marker, str(now))
    if spec["tag"] == have:
        return have, False
    return _unpack_reframework(data, spec, cancelled), True


def fetch_reframework(data, cancelled=None):
    """REFramework's dinput8.dll, downloaded the first time a game needs it (the newest nightly, else the pinned
    fallback); its path. Raises dk_net.NetError, OSError or RuntimeError with a message fit for the panel."""
    if reframework_build(data):
        return reframework_path(data)
    os.makedirs(data, exist_ok=True)
    try:
        update_reframework(data, force=True, cancelled=cancelled)
    except (dk_net.NetError, RuntimeError):
        if cancelled and cancelled():
            raise
        _unpack_reframework(data, REFRAMEWORK, cancelled)
    return reframework_path(data)


# ---- first download ----

def runnable(sevenzip, data):
    """The bundled 7-Zip, executable: plugin ZIPs don't keep the execute bit and Decky's plugin folder may not be
    ours to change, so a copy in the plugin's data folder is made executable when the original isn't."""
    if os.access(sevenzip, os.X_OK):
        return sevenzip
    try:
        os.chmod(sevenzip, 0o755)
        if os.access(sevenzip, os.X_OK):
            return sevenzip
    except OSError:
        pass
    copy = os.path.join(data, "7zz")
    shutil.copyfile(sevenzip, copy)
    os.chmod(copy, 0o755)
    return copy


def fetch(data, sevenzip, progress=None, cancelled=None):
    """Downloads and checks everything not there yet: AMD's files, then OptiScaler's newest nightly (the fallback
    build when GitHub's API can't be reached). progress(done, total) along the way. Raises dk_net.NetError, OSError
    or RuntimeError (unpacking) with a message fit for the panel."""
    os.makedirs(os.path.join(data, "fsr4"), exist_ok=True)
    done = 0

    def step(base):
        return (lambda n: progress(base + n, TOTAL)) if progress else None

    for path, name in zip(fsr4_paths(data), FSR4_FILES):
        spec = FSR4_FILES[name]
        if not (os.path.isfile(path) and os.path.getsize(path) == spec["size"]):
            dk_net.download(spec["url"], path, spec["size"], spec["sha256"], hosts=HOSTS, redirects=REDIRECTS,
                            deadline=1800, cancel=cancelled, progress=step(done))
        done += spec["size"]
    if not current(data):
        try:
            spec = newest_nightly(_api(OPTI_API, cancelled))
            if spec is None:
                raise RuntimeError("No OptiScaler build in the recent nightly releases")
        except (dk_net.NetError, RuntimeError):
            if cancelled and cancelled():
                raise
            spec = OPTISCALER
        try:
            _unpack_optiscaler(data, sevenzip, spec, progress, cancelled, base=done)
        except RuntimeError:
            if spec is OPTISCALER or (cancelled and cancelled()):
                raise
            _unpack_optiscaler(data, sevenzip, OPTISCALER, progress, cancelled, base=done)
        _write(os.path.join(_opti_root(data), "last-check.txt"), str(time.time()))
    if progress:
        progress(TOTAL, TOTAL)
