# -*- coding: utf-8 -*-
"""v1.4.3 护栏：**程序解压在存档目录里面**时，备份管理必须能用。

**症状（玩家实测 v1.4.2）**：程序解压到
`%LOCALAPPDATA%\\.uoc2\\save\\uoc2-save-modifier` ⇒
`bak/` 正好在**存档目录里面** ⇒
概览页能显示备份，**「管理备份」里一条都没有**。

**根因**：`backup_cleanup._enumerate()` 里那道闸
「`bak/` 落在存档/导入目录里就整个跳过」⇒ 把**程序专属**的
`<修改器目录>/bak/` 也一起否了。

**这些测试守着**：
① 程序专属的 `bak/`（`<修改器目录>/bak/`）**即使物理上在存档目录里面**
   ⇒ 也要能列出备份；
② 概览页与「管理备份」**两处口径一致**（概览能看到的，管理里也能看到）；
③ **安全边界不破**：环境变量把 `bak` 指到**存档目录本身**时
   ⇒ 仍然一个都不列（那些 `_BACKUP.usg` 可能是玩家/游戏造的）；
④ 旧 fallback bak（`<游戏数据目录>/bak/`）仍然**只读不列**。
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from save_modifier_web import backup_cleanup as mod


class TestBackupDirInsideSaveRoot(unittest.TestCase):
    """程序解压在存档目录里面的情形（玩家实测的用法）。"""

    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tmp = Path(self.enterContext(
            tempfile.TemporaryDirectory(dir=scratch, prefix="bak_gate_")))
        # 游戏数据目录
        self.base = self.tmp / ".uoc2"
        # ⚠️ **程序就装在存档目录里面**（玩家的实际用法）
        self.modifier = self.base / "save" / "uoc2-save-modifier"
        self.bak = self.modifier / "bak"
        self.bak.mkdir(parents=True)
        self.save = self.base / "save" / "campaigns" / "west.usg"
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b"save")
        # 程序自己的备份
        self.backup = self.bak / "west_BACKUP.usg"
        self.backup.write_bytes(b"backup")
        self.enterContext(patch.dict(
            os.environ, UOC2_APPDATA=str(self.base)))
        # ⚠️ **不设 UOC2_BAK_DIR** ⇒ 走默认布局 `<修改器目录>/bak/`
        os.environ.pop("UOC2_BAK_DIR", None)
        self.enterContext(patch.object(
            mod.core_paths, "modifier_home", return_value=self.modifier))
        self.backend = unittest.mock.Mock()
        self.service = mod.BackupCleanup(backend=self.backend)

    def test_backups_are_listed_when_modifier_sits_inside_save_root(self):
        """① 程序专属的 bak 在存档目录里面 ⇒ **必须能列出来**。"""
        rows = self.service.preview(self.save)
        self.assertEqual(1, len(rows),
                         "程序装在存档目录里时，管理备份一条都没列出来")
        self.assertEqual("west_BACKUP.usg", rows[0]["name"])

    def test_recycle_works_in_that_layout(self):
        """能列出来也要能删（回收）。"""
        row, = self.service.preview(self.save)
        self.service.recycle_one(self.save, row["id"])
        self.backend.assert_called_once_with(self.backup)

    def test_overview_and_management_agree(self):
        """② **两处口径一致**：概览页看得到的，管理里也得看得到。

        概览页的备份列表（`server.py` 的 `api_undo_stack`）扫
        `backup_dir()` / `fallback_backup_dir()` / 存档旁边；
        管理备份只扫 `backup_dir()` ⇒ 口径本来就窄 ⇒
        这里对比两边的**交集**：管理里有的，概览里必须有。
        """
        from save_modifier_web import server
        rows = self.service.preview(self.save)
        self.assertTrue(rows)
        names = {r["name"] for r in rows}
        with patch.object(server, "_save_id_checked", return_value=str(self.save)):
            with patch.object(server, "api_undo_stack", wraps=server.api_undo_stack):
                stack = server.api_undo_stack(str(self.save))
        overview = {b["name"] for b in stack.get("backups", [])}
        self.assertTrue(names.issubset(overview),
                        "管理备份列出的 %s 概览页却没有" % (names - overview))


class TestBackupDirSafetyBoundary(unittest.TestCase):
    """⚠️ **安全边界不许破**。"""

    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tmp = Path(self.enterContext(
            tempfile.TemporaryDirectory(dir=scratch, prefix="bak_safe_")))
        self.base = self.tmp / ".uoc2"
        self.modifier = self.base / "save" / "uoc2-save-modifier"
        self.modifier.mkdir(parents=True)
        self.save = self.base / "save" / "campaigns" / "west.usg"
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b"save")
        self.enterContext(patch.dict(
            os.environ, UOC2_APPDATA=str(self.base)))
        self.enterContext(patch.object(
            mod.core_paths, "modifier_home", return_value=self.modifier))
        self.backend = unittest.mock.Mock()
        self.service = mod.BackupCleanup(backend=self.backend)

    def test_env_var_pointing_at_save_dir_still_lists_nothing(self):
        """③ 环境变量把 bak 指到**存档目录本身** ⇒ 仍然一个都不列。

        那些 `_BACKUP.usg` 可能是玩家/游戏造的 ⇒ 有歧义 ⇒ 不动。
        """
        beside = self.save.parent / "west_BACKUP.usg"
        beside.write_bytes(b"player-made")
        with patch.dict(os.environ, UOC2_BAK_DIR=str(self.save.parent)):
            self.assertEqual([], self.service.preview(self.save))

    def test_old_fallback_bak_is_not_listed(self):
        """④ 旧 fallback bak（`<游戏数据目录>/bak/`）仍然只读不列。"""
        fallback = self.base / "bak"
        fallback.mkdir(parents=True)
        (fallback / "west_BACKUP.usg").write_bytes(b"legacy")
        with patch.dict(os.environ, UOC2_BAK_DIR=str(fallback)):
            self.assertEqual([], self.service.preview(self.save))
        self.assertTrue((fallback / "west_BACKUP.usg").exists(),
                        "旧 fallback bak 里的文件不该被动")


if __name__ == "__main__":
    unittest.main()
