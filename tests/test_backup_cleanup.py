import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from save_modifier_web import backup_cleanup as mod


class BackupCleanupTest(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch, prefix="r1_test_")))
        self.base = self.tmp / "data"
        self.primary = self.tmp / "modifier" / "bak"
        self.fallback = self.base / "bak"
        self.save = self.base / "save" / "campaigns" / "west.usg"
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b"save")
        self.primary.mkdir(parents=True)
        self.fallback.mkdir(parents=True)
        self.enterContext(patch.dict(os.environ, UOC2_APPDATA=str(self.base), UOC2_BAK_DIR=str(self.primary)))
        self.backend = Mock()
        self.service = mod.BackupCleanup(backend=self.backend)

    def add(self, name="west_BACKUP.usg", folder=None):
        path = (folder or self.primary) / name
        path.write_bytes(b"backup")
        return path

    def test_writer_names_and_roots(self):
        for n in ("west_BACKUP.usg", "west_BACKUP_2.usg", "west_BACKUP_10.usg", "west_BACKUP_1.usg",
                  "west_BACKUP_02.usg", "west_backup_3.usg", "other_BACKUP.usg"):
            self.add(n)
        self.add(folder=self.save.parent)
        (self.primary / "west_BACKUP_4.usg").mkdir()
        self.assertEqual({i["name"] for i in self.service.preview(self.save)},
                         {"west_BACKUP.usg", "west_BACKUP_2.usg", "west_BACKUP_10.usg"})
        with patch.dict(os.environ, UOC2_BAK_DIR=str(self.save.parent)):
            self.assertEqual([], self.service.preview(self.save))

    def test_two_roots_same_name_single_and_batch(self):
        first, second = self.add(), self.add(folder=self.fallback)
        a, b = self.service.preview(self.save)
        self.assertNotEqual(a["id"], b["id"])
        self.service.recycle_one(self.save, a["id"])
        self.service.recycle_many(self.save, [b["id"]])
        self.assertEqual([first, second], [call.args[0] for call in self.backend.call_args_list])
        for path in (first, second):
            self.assertEqual(b"backup", path.read_bytes())

    def test_stale_forged_expired_or_path_rejected(self):
        p = self.add()
        with patch.object(mod.time, "monotonic", return_value=100):
            token = self.service.preview(self.save)[0]["id"]
        with patch.object(mod.time, "monotonic", return_value=400), self.assertRaises(ValueError):
            self.service.recycle_one(self.save, token)
        st = p.stat()
        p.write_bytes(b"change")
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
        for value in (str(p), "../" + p.name, "9999999999." + "a" * 64, token):
            with patch.object(mod.time, "monotonic", return_value=101), self.assertRaises(ValueError):
                self.service.recycle_one(self.save, value)
        self.backend.assert_not_called()

    def test_reparse_ancestor_rejected_before_traversal(self):
        self.add()
        real = Path.lstat
        def fake_lstat(p):
            if p == self.primary.parent:
                return Mock(st_mode=0o40755, st_file_attributes=0x400)
            return real(p)
        with patch.object(Path, "lstat", fake_lstat):
            self.assertEqual([], self.service.preview(self.save))

    def test_same_save_basename_blocks_even_after_preview(self):
        self.add()
        token = self.service.preview(self.save)[0]["id"]
        imports = self.base / "modifier_imports"
        imports.mkdir()
        self.add(self.save.name, imports)
        with self.assertRaisesRegex(ValueError, "同名"):
            self.service.recycle_one(self.save, token)
        self.backend.assert_not_called()

    def test_new_import_and_name_collision_with_legacy_import(self):
        new_root = self.base / "modifier" / "modifier_imports"
        old_root = self.base / "modifier_imports"
        new_root.mkdir(parents=True)
        imported = self.add("east.usg", new_root)
        backup = self.add("east_BACKUP.usg")
        token = self.service.preview(imported)[0]["id"]
        self.service.recycle_one(imported, token)
        self.backend.assert_called_once_with(backup)
        self.backend.reset_mock()
        old_root.mkdir()
        legacy = self.add(imported.name, old_root)
        with self.assertRaisesRegex(mod.BackupCleanupError, "同名"):
            self.service.recycle_one(imported, token)
        with self.assertRaisesRegex(mod.BackupCleanupError, "同名"):
            self.service.preview(legacy)
        self.backend.assert_not_called()

    def test_recycle_result_requires_s_ok_and_destination(self):
        dest = object()
        mod._check_recycle_result(0, dest)
        for hr, target in ((0, None), (0x0027000B, dest), (0x00270005, dest), (-1, dest)):
            with self.subTest(hr=hr, target=target), self.assertRaises(mod.BackupCleanupError):
                mod._check_recycle_result(hr, target)

    def test_backend_failure_keeps_file_and_stops_batch(self):
        p = self.add()
        self.add("west_BACKUP_2.usg")
        self.backend.side_effect = OSError("refused")
        ids = [i["id"] for i in self.service.preview(self.save)]
        with self.assertRaisesRegex(OSError, "refused"):
            self.service.recycle_many(self.save, ids)
        self.backend.assert_called_once()
        self.assertEqual(b"backup", p.read_bytes())
