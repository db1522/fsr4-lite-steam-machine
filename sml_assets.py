# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Steam Machine Life
"""The three files FSR 4.1 Lite needs, downloaded once and checked byte for byte:
- OptiScaler, one tested nightly build from its own GitHub (a .7z: unpacked with the bundled 7-Zip, bin/7zz)
- AMD's FSR 4.1.2 files for DirectX 12 and Vulkan, from the FSR 4.1 Lite widget's file mirror (AMD-signed,
  unmodified). Nothing from AMD or OptiScaler ships inside the plugin.
Plus REFramework, downloaded only when a Capcom RE Engine game that needs it is set up (fetch_reframework)."""
import os
import shutil
import subprocess
import tempfile
import zipfile

import dk_net

HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
REDIRECTS = HOSTS - {"github.com"}

OPTISCALER = {
    "build": "OptiScaler v10.0.0-pre1 (2026-10-24)",
    "url": "https://github.com/optiscaler/OptiScaler-nightly/releases/download/nightly-20261024/"
           "OptiScaler_v10.0.0-pre1_20261024.7z",
    "size": 57125569,
    "sha256": "74f20189e0ec76288c86d69057b3feb4750f4680118a9852fb743b343274ac1d",
    "folder": "optiscaler-20261024",
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
# REFramework (praydog, MIT) for the RE Engine games OptiScaler needs it in (the widget's REFrameworkSource): one
# pinned nightly, at least two weeks old. Only its dinput8.dll is used, as its release notes say for non-VR use.
REFRAMEWORK = {
    "build": "REFramework nightly 01433 (2026-10-21)",
    "url": "https://github.com/praydog/REFramework-nightly/releases/download/"
           "nightly-01433-d4611aef1d63effd3a736bdf9404ea702428017d/REFramework.zip",
    "size": 13267029,
    "sha256": "b3ff4f497be6f108ef494c2c02156b61b8d04f3171378ecc0dc28c218ee296b3",
    "folder": "reframework-01433",
}


def package_dir(data):
    return os.path.join(data, OPTISCALER["folder"])


def fsr4_paths(data):
    return [os.path.join(data, "fsr4", name) for name in FSR4_FILES]


def ready(data):
    """True when OptiScaler is unpacked and both AMD files are there at their exact sizes."""
    if not os.path.isfile(os.path.join(package_dir(data), "OptiScaler.dll")):
        return False
    for path, name in zip(fsr4_paths(data), FSR4_FILES):
        try:
            if os.path.getsize(path) != FSR4_FILES[name]["size"]:
                return False
        except OSError:
            return False
    return True


def reframework_path(data):
    return os.path.join(data, REFRAMEWORK["folder"], "dinput8.dll")


def fetch_reframework(data, cancelled=None):
    """REFramework's dinput8.dll, downloaded and checked the first time a game needs it; its path. Raises
    dk_net.NetError, OSError or RuntimeError with a message fit for the panel."""
    path = reframework_path(data)
    if os.path.isfile(path):
        return path
    os.makedirs(data, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data) as tmp:
        archive = os.path.join(tmp, "REFramework.zip")
        dk_net.download(REFRAMEWORK["url"], archive, REFRAMEWORK["size"], REFRAMEWORK["sha256"], hosts=HOSTS,
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
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.replace(out, path)
    for name in os.listdir(data):  # older builds are no longer needed
        if name.startswith("reframework-") and name != REFRAMEWORK["folder"]:
            shutil.rmtree(os.path.join(data, name), ignore_errors=True)
    return path


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
    """Downloads and checks everything not there yet. progress(done, total) along the way. Raises dk_net.NetError,
    OSError or RuntimeError (unpacking) with a message fit for the panel."""
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
    target = package_dir(data)
    if not os.path.isfile(os.path.join(target, "OptiScaler.dll")):
        sevenzip = runnable(sevenzip, data)
        with tempfile.TemporaryDirectory(dir=data) as tmp:
            archive = os.path.join(tmp, "optiscaler.7z")
            dk_net.download(OPTISCALER["url"], archive, OPTISCALER["size"], OPTISCALER["sha256"], hosts=HOSTS,
                            redirects=REDIRECTS, deadline=1800, cancel=cancelled, progress=step(done))
            out = os.path.join(tmp, "x")
            try:
                r = subprocess.run([sevenzip, "x", "-y", "-bd", f"-o{out}", archive], capture_output=True, timeout=600)
            except (OSError, subprocess.TimeoutExpired) as e:
                raise RuntimeError(f"Couldn't unpack OptiScaler ({e})") from e
            if r.returncode != 0 or not os.path.isfile(os.path.join(out, "OptiScaler.dll")):
                raise RuntimeError("Couldn't unpack OptiScaler: " + r.stderr.decode("utf-8", "replace")[-200:].strip())
            shutil.rmtree(target, ignore_errors=True)
            os.replace(out, target)
        # older builds are no longer needed
        for name in os.listdir(data):
            if name.startswith("optiscaler-") and name != OPTISCALER["folder"]:
                shutil.rmtree(os.path.join(data, name), ignore_errors=True)
    if progress:
        progress(TOTAL, TOTAL)
