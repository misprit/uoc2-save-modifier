# -*- coding: utf-8 -*-
"""U109：**备份存档**改放 `<修改器所在目录>/bak/`（不再放存档旁边）。

用户要求（2026-11-21）：
> 每次进行改动都添加一个备份这一点可以优化一下，至少放在一个新文件夹里面，
> 或者让这些备份不会被游戏识别和读取。我能想到的方法是以后的所有备份存档都放在
> 修改器exe文件同一个目录下的bak文件下。这样好找，也不会出一大堆备份烦到使用者

**为什么必须改**

1. **游戏会把备份当存档**：游戏只扫存档目录里的 `*.usg` ⇒
   `<存档名>_BACKUP.usg` 就在**游戏自己的存档列表里**（修改器过滤掉了，
   **游戏可不管**）⇒ 玩家可能手抖加载了备份。
2. **存档目录越来越乱**：改一次多一个文件。

**这些测试守着**

① 备份落在 `bak/` 里，**存档目录一个备份都不留**（游戏看不到）；
② 序号照旧递增（`_BACKUP` / `_BACKUP_2` …，**绝不覆盖**）；
③ `bak/` 就在**修改器所在目录**下（玩家在 exe 旁边就找得到）；
④ `bak/` 建不出来 / 不可写 ⇒ **拒绝写盘**，且不回退到外部或存档旁边；
⑤ 撤销栈**不受影响**（它记的是内容本身，与备份文件无关）。
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.paths import BACKUP_DIR_NAME, backup_dir, modifier_home  # noqa: E402
from save_modifier_core.writer import backup_path_for  # noqa: E402

from ._fixtures import make_save  # noqa: E402


class BackupLocationTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u109_bak_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        # 本测试的备份目录 = 自己的临时目录（不写进仓库）
        self._bak_old = os.environ.get("UOC2_BAK_DIR")
        self.bak = self.tmp / "bak"
        os.environ["UOC2_BAK_DIR"] = str(self.bak)
        self.addCleanup(self._restore_bak)

    def _restore_bak(self):
        if self._bak_old is None:
            os.environ.pop("UOC2_BAK_DIR", None)
        else:
            os.environ["UOC2_BAK_DIR"] = self._bak_old

    def commit(self, edits):
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        return res

    def usgs_in_save_dir(self):
        return sorted(p.name for p in self.tmp.glob("*.usg")
                      if p.name != self.save_path.name)


class TestBackupLocation(BackupLocationTestBase):
    def test_backup_lands_in_the_bak_dir(self):
        res = self.commit([Edit.progress("prestige", 5)])
        self.assertIsNotNone(res.backup)
        self.assertEqual(res.backup.parent, self.bak,
                         "备份必须落在 bak 目录里")
        self.assertTrue(res.backup.is_file())

    def test_the_save_folder_keeps_no_backup(self):
        """⭐ **游戏只扫存档目录里的 `*.usg`** ⇒ 那里一个备份都不能留。"""
        self.commit([Edit.progress("prestige", 5)])
        self.commit([Edit.progress("prestige", 6)])
        self.assertEqual([], self.usgs_in_save_dir(),
                         "存档目录里不该再有备份 .usg（游戏会把它当存档）")

    def test_numbering_increments_and_never_overwrites(self):
        first = self.commit([Edit.progress("prestige", 5)]).backup
        second = self.commit([Edit.progress("prestige", 6)]).backup
        self.assertEqual("s_BACKUP.usg", first.name)
        self.assertEqual("s_BACKUP_2.usg", second.name)
        self.assertTrue(first.is_file(), "第一份备份不能被覆盖")

    def test_bak_dir_is_under_the_modifier_home(self):
        """`bak/` 就在**修改器所在目录**下（exe 旁边 ⇒ 玩家找得到）。"""
        old = os.environ.pop("UOC2_BAK_DIR", None)
        try:
            self.assertEqual(modifier_home() / BACKUP_DIR_NAME, backup_dir())
            self.assertEqual("bak", BACKUP_DIR_NAME)
        finally:
            if old is not None:
                os.environ["UOC2_BAK_DIR"] = old

    def test_backup_path_preview_matches_the_real_path(self):
        """确认框里预告的文件名 = 真正写出来的那个。"""
        want = backup_path_for(self.save_path)
        self.assertEqual(self.bak, want.parent)
        self.assertEqual("s_BACKUP.usg", want.name)

    def test_backup_failure_rejects_write_without_external_fallback(self):
        """bak 不可用时拒绝写回，且不在外部或存档旁边生成备份。"""
        blocker = self.tmp / "not_a_dir"
        blocker.write_text("x", encoding="utf-8")
        os.environ["UOC2_BAK_DIR"] = str(blocker)
        before = self.save_path.read_bytes()
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit([Edit.progress("prestige", 5)], catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertFalse(res.ok)
        self.assertTrue(any("备份失败" in error for error in res.errors), res.errors)
        self.assertEqual(before, self.save_path.read_bytes())
        self.assertEqual([], self.usgs_in_save_dir())

    def test_backup_failure_does_not_leave_save_sidecar(self):
        blocker = self.tmp / "not_a_dir"
        blocker.write_text("x", encoding="utf-8")
        os.environ["UOC2_BAK_DIR"] = str(blocker)
        before = self.save_path.read_bytes()
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit([Edit.progress("prestige", 5)], catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            result = save.commit(plan)
        self.assertFalse(result.ok)
        self.assertEqual(before, self.save_path.read_bytes())
        self.assertEqual([], self.usgs_in_save_dir())


class TestUndoStillWorks(BackupLocationTestBase):
    def test_undo_after_moving_the_backups(self):
        """撤销栈记的是**内容本身** ⇒ 备份挪走了也不影响撤销。"""
        self.commit([Edit.progress("prestige", 999)])
        with open_save(str(self.save_path), self.paths) as save:
            res = save.undo()
        self.assertTrue(res.ok, res.errors)
        import yaml
        import zipfile
        with zipfile.ZipFile(self.save_path) as zf:
            main = yaml.safe_load(zf.read("main.yml"))
        self.assertEqual(320, main["prestige"], "撤销后应回到原来的声望")

    def test_the_undo_stack_file_stays_next_to_the_save(self):
        """撤销栈（`<存档名>.undo.json`）**留在存档旁边** ——
        一个存档一个文件，游戏只扫 `*.usg` ⇒ 不会被当成存档。"""
        self.commit([Edit.progress("prestige", 999)])
        from save_modifier_core.undo import stack_path_for
        stack = stack_path_for(self.save_path)
        self.assertTrue(stack.is_file())


if __name__ == "__main__":
    unittest.main()
