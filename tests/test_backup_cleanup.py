import os
import shutil
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
        self.enterContext(patch.object(mod.core_paths, "modifier_home", return_value=self.primary.parent))
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

    def test_only_primary_can_be_recycled_even_if_override_names_fallback(self):
        primary, fallback = self.add(), self.add(folder=self.fallback)
        row, = self.service.preview(self.save)
        self.assertEqual("primary", row["source"])
        self.service.recycle_one(self.save, row["id"])
        self.backend.assert_called_once_with(primary)
        with patch.dict(os.environ, UOC2_BAK_DIR=str(self.fallback)):
            self.assertEqual([], self.service.preview(self.save))
        self.assertEqual(b"backup", fallback.read_bytes())

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
        new_root = mod.core_paths.import_roots()[0]
        new_root.mkdir(parents=True)
        imported = self.add("east.usg", new_root)
        backup = self.add("east_BACKUP.usg")
        token = self.service.preview(imported)[0]["id"]
        self.service.recycle_one(imported, token)
        self.backend.assert_called_once_with(backup)
        self.backend.reset_mock()
        for old_root in mod.core_paths.import_roots()[1:]:
            with self.subTest(root=old_root):
                old_root.mkdir(parents=True, exist_ok=True)
                legacy = self.add(imported.name, old_root)
                with self.assertRaisesRegex(mod.BackupCleanupError, "同名"):
                    self.service.recycle_one(imported, token)
                with self.assertRaisesRegex(mod.BackupCleanupError, "同名"):
                    self.service.preview(legacy)
                self.backend.assert_not_called()
                legacy.rename(old_root / "other.usg")

    def test_recycle_result_judges_by_behaviour_not_hresult(self):
        """实测（2026-11-27）：Windows 回收**成功**时也可能返回正值状态码
        `0x00270008`（COPYENGINE_S_USER_IGNORED）⇒ 判据必须是
        **「文件已离开原处」**，不是「HRESULT == 0」。

        旧判据把成功报成失败 ⇒ 玩家看到「回收失败」，备份其实已在回收站里。
        """
        gone = Path(tempfile.gettempdir()) / "uoc2-definitely-not-here.txt"
        self.assertFalse(gone.exists())
        for hr in (0, 0x00270008):
            with self.subTest(hr=hr):
                mod._check_recycle_result(hr, object(), gone)      # 不抛 = 成功
        for hr, target in ((0, None), (0x00270008, None), (-1, object())):
            with self.subTest(hr=hr, target=target), self.assertRaises(mod.BackupCleanupError):
                mod._check_recycle_result(hr, target, gone)
        # 文件**还在原处** ⇒ 失败（哪怕 hr == 0）
        here = self.add()
        with self.assertRaises(mod.BackupCleanupError):
            mod._check_recycle_result(0, object(), here)

    def test_backend_failure_keeps_file_and_stops_batch(self):
        p = self.add()
        self.add("west_BACKUP_2.usg")
        self.backend.side_effect = OSError("refused")
        ids = [i["id"] for i in self.service.preview(self.save)]
        with self.assertRaisesRegex(OSError, "refused"):
            self.service.recycle_many(self.save, ids)
        self.backend.assert_called_once()
        self.assertEqual(b"backup", p.read_bytes())


@unittest.skipUnless(os.name == "nt", "真实回收站路径只测 Windows")
class TestRealRecycleBin(unittest.TestCase):
    """**真实**调 `ITransferSource::RecycleItem`（前面的测试都用模拟后端）。

    ⚠️ 副作用：测试文件会进**用户的回收站**（不自动清理 —— 清空回收站会删掉
    用户自己的东西）。文件名固定带 `uoc2-recycle-selftest`，好认。
    """

    def test_real_recycle_takes_file_out_of_original_path(self):
        d = Path(tempfile.mkdtemp(prefix="uoc2_recycle_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = d / "uoc2-recycle-selftest.txt"
        p.write_text("x", encoding="utf-8")
        self.assertTrue(p.exists())
        mod._recycle_windows(p)
        self.assertFalse(p.exists(), "回收后原路径不该再有这个文件")

    def test_real_recycle_raises_when_file_stays(self):
        """文件留在原处 ⇒ 必须报失败（这是行为判据的核心）。"""
        d = Path(tempfile.mkdtemp(prefix="uoc2_recycle_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = d / "uoc2-recycle-selftest-stay.txt"
        p.write_text("x", encoding="utf-8")
        with self.assertRaises(mod.BackupCleanupError):
            mod._check_recycle_result(0, object(), p)
