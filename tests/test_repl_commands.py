# -*- coding: utf-8 -*-
"""U116：自测入口（REPL）的命令**不许一敲就 TypeError**。

**为什么补这个测试**：矛盾审阅发现
`store set` / `store del` 在 REPL 里**少传了 `sub`**（商店是两层结构：
`store` / `elite_store`）⇒ 一敲就 `TypeError: Edit.store_set() missing
1 required positional argument` ⇒ 而《命令参考》里还把它们列成可用命令。
⇒ REPL 里**一条测试都没有** ⇒ 这种错能一直躺着。

**这些测试守着**
① `store set` / `store del` 能真的生成编辑（子商店默认 `store`，可选 `elite_store`）；
② `asset` 省略参数时**合法**（每回合默认 1 —— 游戏要求 ≥ 1）；
③ `supspec`（压制）在 `help` 里能查到（命令本来就有，之前 help 里漏了）。
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

from save_modifier_core import open_save  # noqa: E402
from save_modifier.repl import HELP_TEXT, Repl  # noqa: E402

from ._fixtures import make_save  # noqa: E402


class TestReplCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u116_repl_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.repl = Repl()
        self.repl._save = open_save(str(self.save_path), self.repl.paths)
        self.addCleanup(self.repl.close)

    def test_store_set_builds_an_edit(self):
        """⚠️ 以前少传 `sub` ⇒ TypeError。"""
        self.repl.cmd_store_set(["south", "0", "price", "5"])
        self.assertTrue(self.repl._last_edits, "没有生成编辑")
        self.assertEqual("store_set", self.repl._last_edits[0].kind)

    def test_store_set_accepts_the_elite_store(self):
        self.repl.cmd_store_set(["south", "0", "price", "5", "elite_store"])
        self.assertTrue(self.repl._last_edits)

    def test_store_del_builds_an_edit(self):
        self.repl.cmd_store_del(["south", "0"])
        self.assertTrue(self.repl._last_edits)
        self.assertEqual("store_remove", self.repl._last_edits[0].kind)

    def test_asset_with_omitted_arguments_is_valid(self):
        """省略「总次数 / 每回合」时也必须**合法**
        （每回合 ≥ 1 是游戏的硬范围；以前默认 0 ⇒ 必然被核心库拒）。"""
        self.repl.cmd_asset(["air", "3"])
        self.assertTrue(self.repl._last_edits)
        plan = self.repl._last_plan
        self.assertTrue(plan.ok, plan.errors)

    def test_supspec_is_listed_in_help(self):
        self.assertIn("supspec", HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
