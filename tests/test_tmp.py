# SPDX-License-Identifier: BSD-3-Clause
"""tests/_tmp.py: the suite's temp folders go away, and the sweep removes only what this suite left."""
import os
import tempfile
import time
import unittest

import _harness  # noqa: F401
import _tmp
from _tmp import temp_dir  # noqa: E402


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Sweep(unittest.TestCase):
    def setUp(self):
        self.temp = temp_dir(self)
        old = time.time() - 3600
        self.made = []

        def folder(name, *files, age=old):
            path = os.path.join(self.temp, name)
            os.makedirs(path)
            for f in files:
                touch(os.path.join(path, f))
            os.utime(path, (age, age))
            self.made.append(name)
            return path
        self.folder = folder

    def test_only_this_suites_leftovers_go(self):
        self.folder("tmpsteam001", ".local/share/Steam/steamapps/common/PBZ/PBZ.exe")
        self.folder("tmpdata0001", "fsr4/amdxcffx64.dll", "optiscaler/latest.txt")
        self.folder("tmpsettings", "settings.json", "settings.json.last-good",
                    "settings.json.corrupt-20261109T003844Z-c53627")
        self.folder("tmpempty001")
        self.folder("fsr4lite-tests-abc12345", "anything")
        self.folder("decky-test-abc12345", "settings/x", "runtime/y")
        keep = [self.folder("tmpsomebody", "photo.jpg", "settings.json"),  # one name that isn't ours
                self.folder("tmpnew00001", "settings.json", age=time.time()),  # a run going on right now
                self.folder("notatmpname", "settings.json"),  # not a mkdtemp name
                self.folder("decky-test-otherthing", "settings/x", "mine.txt")]
        self.assertEqual(_tmp.sweep(self.temp), 6)
        self.assertEqual(sorted(os.listdir(self.temp)), sorted(os.path.basename(k) for k in keep))

    def test_this_run_keeps_its_temp_folders_in_one_place_that_is_removed_at_exit(self):
        self.assertTrue(os.path.basename(tempfile.gettempdir()).startswith(_tmp.RUN_PREFIX))
        self.assertEqual(os.path.dirname(tempfile.gettempdir()), _tmp.SYSTEM_TEMP)

    def test_a_test_folder_is_removed_when_its_test_ends(self):
        inner = unittest.TestCase("__init__")
        path = temp_dir(inner)
        touch(os.path.join(path, "big.bin"))
        inner.doCleanups()
        self.assertFalse(os.path.exists(path))


class SmallFsr4(unittest.TestCase):
    def test_amds_files_are_placeholders_of_64_bytes(self):
        import sml_assets
        with _tmp.small_fsr4():
            self.assertEqual({s["size"] for s in sml_assets.FSR4_FILES.values()}, {64})
        self.assertGreater(min(s["size"] for s in sml_assets.FSR4_FILES.values()), 70_000_000)


if __name__ == "__main__":
    unittest.main()
