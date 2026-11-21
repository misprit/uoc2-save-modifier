# -*- coding: utf-8 -*-
"""U132：护栏 —— 备份**兜底**也不许回到存档目录（外部审阅报告 P2-13）。

**漏洞**

U109 把备份挪到了 `<修改器目录>/bak/`（游戏看不见），但**兜底**还是
「退回存档旁边」⇒ 那个目录建不出来时（修改器装在 Program Files 下），
备份又会落回**游戏会扫的目录** ⇒ 游戏把备份当存档列出来。

⇒ 兜底改成 `<游戏数据目录>/bak/`（游戏不扫那儿）；
两处都不行就**报错**（写盘因此停下 ⇒ 绝不出现「没备份就写存档」）。

**这些测试守着**

① `fallback_backup_dir()` = `<游戏数据目录>/bak`；
② `make_backup` **不再**用「存档旁边」那个老位置；
③ 兜底时存档目录里**一个备份都不留**（在 test_backup_location.py 里）。
"""

import io
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core.paths import (BACKUP_DIR_NAME,  # noqa: E402
                                      appdata_dir, fallback_backup_dir)


class FallbackBackupDirTest(unittest.TestCase):
    def test_it_is_the_appdata_bak_folder(self):
        self.assertEqual(appdata_dir() / BACKUP_DIR_NAME,
                         fallback_backup_dir())

    def test_it_is_not_next_to_the_save(self):
        """兜底目录**不是**存档目录（游戏会扫那儿）。"""
        self.assertNotIn("campaigns", str(fallback_backup_dir()).lower())
        self.assertNotIn("games", str(fallback_backup_dir()).lower())


class MakeBackupSourceTest(unittest.TestCase):
    """静态看 `make_backup` 的源码：不许再退回存档旁边。"""

    @classmethod
    def setUpClass(cls):
        p = os.path.join(REPO_SRC, "save_modifier_core", "writer.py")
        with io.open(p, encoding="utf-8") as f:
            cls.src = f.read()

    def test_make_backup_does_not_use_the_legacy_location(self):
        i = self.src.index("def make_backup(")
        j = self.src.index("def read_entries(", i)
        body = self.src[i:j]
        self.assertNotIn("legacy_backup_path_for", body,
                         "make_backup 又退回存档旁边了（游戏会把它当存档）")
        self.assertIn("fallback_backup_dir", body,
                      "兜底应该走 <游戏数据目录>/bak/")


if __name__ == "__main__":
    unittest.main()
