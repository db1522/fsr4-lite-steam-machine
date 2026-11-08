# SPDX-License-Identifier: BSD-3-Clause
"""OptiScaler from its newest nightly, like the Windows widget's OptiScalerSource: which build is picked, when GitHub
is asked, what a download has to pass before it's used, and the pinned fallback."""
import os
import tempfile
import unittest
from unittest import mock

import _harness  # noqa: F401
import dk_net
import sml_assets as A

DL = "https://github.com/optiscaler/OptiScaler-nightly/releases/download/"


def asset(name, created, size=100, digest="sha256:" + "b" * 64, **kw):
    return {"name": name, "created_at": created, "size": size, "digest": digest, "state": "uploaded",
            "browser_download_url": DL + "nightly-x/" + name, **kw}


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Pick(unittest.TestCase):
    def test_the_newest_finished_non_debug_build_is_picked(self):
        releases = [
            {"assets": [asset("OptiScaler_v10.0.0-pre2_20261108.7z", "2026-11-08T02:00:00Z", state="starter")]},
            {"assets": [asset("OptiScaler_v10.0.0-pre2_20261107_debug.7z", "2026-11-07T03:00:00Z"),
                        asset("OptiScaler_v10.0.0-pre2_20261107.7z", "2026-11-07T02:00:00Z")]},
            {"draft": True, "assets": [asset("OptiScaler_v10.0.0-pre2_20261109.7z", "2026-11-09T02:00:00Z")]},
            {"assets": [asset("OptiScaler_v10.0.0-pre1_20261106.7z", "2026-11-06T02:00:00Z")]},
        ]
        best = A.newest_nightly(releases)
        self.assertEqual(best["name"], "OptiScaler_v10.0.0-pre2_20261107")
        self.assertEqual(best["sha256"], "b" * 64)

    def test_files_from_anywhere_else_or_too_big_are_ignored(self):
        bad = [{"assets": [
            {**asset("OptiScaler_a.7z", "2026-11-07"), "browser_download_url": "https://example.com/OptiScaler_a.7z"},
            asset("OptiScaler_b.7z", "2026-11-07", size=A.MAX_ARCHIVE + 1),
            asset("readme.txt", "2026-11-07")]}]
        self.assertIsNone(A.newest_nightly(bad))
        self.assertIsNone(A.newest_nightly({"message": "API rate limit exceeded"}))

    def test_labels_name_the_build_date(self):
        self.assertEqual(A.label("OptiScaler_v10.0.0-pre1_20261107"), "OptiScaler v10.0.0-pre1 (Nov 7, 2026)")
        self.assertEqual(A.label(""), "")


class Update(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp()

    def fake_unpack(self, ini=b"[FSR]\nFsr4GpuSupport=auto\nFsr4Model=auto\n"):
        def unpack(data, sevenzip, spec, *a, **kw):
            # the real one downloads and unpacks; this checks what it would refuse the same way
            out = os.path.join(tempfile.mkdtemp(), "x")
            touch(os.path.join(out, "OptiScaler.dll"))
            touch(os.path.join(out, "OptiScaler.ini"), ini)
            if not A.has_lite_settings(out):
                raise RuntimeError("no Lite setting")
            touch(os.path.join(A._opti_root(data), spec["name"], "OptiScaler.dll"))
            A._write(os.path.join(A._opti_root(data), "latest.txt"), spec["name"])
            return spec["name"]
        return unpack

    def test_github_is_asked_at_most_every_6_hours(self):
        touch(os.path.join(self.data, "optiscaler", "OptiScaler_v10.0.0-pre1_20261024", "OptiScaler.dll"))
        releases = [{"assets": [asset("OptiScaler_v10.0.0-pre2_20261107.7z", "2026-11-07")]}]
        with mock.patch("sml_assets._api", return_value=releases) as api, \
                mock.patch("sml_assets._unpack_optiscaler", self.fake_unpack()):
            self.assertEqual(A.update_optiscaler(self.data, "7zz", now=1000),
                             ("OptiScaler_v10.0.0-pre2_20261107", True))
            self.assertEqual(A.update_optiscaler(self.data, "7zz", now=1000 + 5 * 3600)[1], False)
            self.assertEqual(api.call_count, 1)
            A.update_optiscaler(self.data, "7zz", now=1000 + 7 * 3600)
            A.update_optiscaler(self.data, "7zz", force=True, now=1000 + 7 * 3600)
            self.assertEqual(api.call_count, 3)
        self.assertEqual(A.current(self.data), "OptiScaler_v10.0.0-pre2_20261107")

    def test_a_build_without_the_lite_settings_is_never_used(self):
        touch(os.path.join(self.data, "optiscaler", "OptiScaler_v10.0.0-pre1_20261024", "OptiScaler.dll"))
        releases = [{"assets": [asset("OptiScaler_v11_20261201.7z", "2026-12-01")]}]
        with mock.patch("sml_assets._api", return_value=releases), \
                mock.patch("sml_assets._unpack_optiscaler", self.fake_unpack(ini=b"[FSR]\nFsr4Model=auto\n")):
            with self.assertRaises(RuntimeError):
                A.update_optiscaler(self.data, "7zz", now=1000)
        self.assertEqual(A.current(self.data), "OptiScaler_v10.0.0-pre1_20261024")

    def test_the_pinned_build_from_before_moves_over(self):
        touch(os.path.join(self.data, "optiscaler-20261024", "OptiScaler.dll"), b"pinned")
        self.assertEqual(A.current(self.data), A.OPTISCALER["name"])
        self.assertTrue(A.ready(self.data) is False)  # the AMD files aren't here in this test
        self.assertFalse(os.path.exists(os.path.join(self.data, "optiscaler-20261024")))
        with open(os.path.join(A.package_dir(self.data), "OptiScaler.dll"), "rb") as f:
            self.assertEqual(f.read(), b"pinned")

    def test_the_first_download_falls_back_to_the_pinned_build_without_githubs_api(self):
        for name, spec in A.FSR4_FILES.items():
            path = os.path.join(self.data, "fsr4", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.truncate(spec["size"])
        got = []
        with mock.patch("sml_assets._api", side_effect=dk_net.NetError("rate limited")), \
                mock.patch("sml_assets._unpack_optiscaler", lambda d, z, spec, *a, **k: got.append(spec)):
            A.fetch(self.data, "7zz")
        self.assertEqual(got[0]["url"], A.OPTISCALER["url"])
        self.assertEqual(got[0]["sha256"], A.OPTISCALER["sha256"])

    def test_the_real_ini_check(self):
        out = tempfile.mkdtemp()
        touch(os.path.join(out, "OptiScaler.ini"), b"[FSR]\r\n; comment\r\nFsr4GpuSupport=auto\r\nFsr4Model=auto\r\n")
        self.assertTrue(A.has_lite_settings(out))
        touch(os.path.join(out, "OptiScaler.ini"), b"[FSR]\r\nFsr4GpuSupport=auto\r\n")
        self.assertFalse(A.has_lite_settings(out))


if __name__ == "__main__":
    unittest.main()
