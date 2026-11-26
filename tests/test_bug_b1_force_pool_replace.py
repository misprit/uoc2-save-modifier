# -*- coding: utf-8 -*-
"""给兵库补 B-1 的对应用例（「删一条再添同一条」= 替换）。

⚠️ 为什么单独一个文件：B-1 的商店侧用例在 test_bug_b1_store_replace.py，
   而兵库侧的**实现是另一处**（`_hq_force_pool_add`）⇒ 同一规则两处实现 ⇒
   断言必须**对称**覆盖（U188 的教训：只覆盖一处 ⇒ 另一处坏了没人管）。
"""
import io
import os
import sys
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from save_modifier_core import catalog as catalog_mod  # noqa: E402
from save_modifier_core import open_save  # noqa: E402
from save_modifier_core.edits import Edit  # noqa: E402

from ._helpers import pick_save  # noqa: E402


class TestForcePoolReplaceInsteadOfDuplicate(unittest.TestCase):
    """兵库：删一条 + 添同一条 = 替换（不是重复）。"""

    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog_mod.default()

    def _pool_with_entry(self, save):
        """找一个**兵库非空**的总部，返回 (hq_id, force_pool)。"""
        for hq in save.read_yaml("hqs.yml", []) or []:
            if not isinstance(hq, dict):
                continue
            pool = hq.get("force_pool")
            if isinstance(pool, list) and pool and isinstance(pool[0], dict):
                return hq.get("id"), pool
        return None, None

    def test_remove_then_add_same_entry_succeeds(self):
        """删一条 → 再添同样的一条 ⇒ **能应用**。"""
        if not self.catalog.has_spec_type("ger_arty_40"):
            self.skipTest("本机没有游戏包")
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        with open_save(str(info.path)) as save:
            hq_id, pool = self._pool_with_entry(save)
            if hq_id is None:
                self.skipTest("这个存档的兵库都是空的")
            old = pool[0]
            entry = {"quantity": old.get("quantity", 1),
                     "spec": old.get("spec"), "equipment": old.get("equipment"),
                     "nationality": old.get("nationality", ""),
                     "delay": old.get("delay", 0)}
            if not entry.get("spec") and not entry.get("equipment"):
                self.skipTest("第一条兵库条目不是可复制的形态")
            plan = save.plan_edit([
                Edit.hq_force_pool_add(hq_id, entry),
                Edit.hq_force_pool_remove(hq_id, 0),
            ], catalog=self.catalog)
            self.assertTrue(plan.ok,
                            "删一条再添同一条应当能应用：%s" % plan.errors)

    def test_duplicate_without_remove_is_still_rejected(self):
        """⚠️ 没删就加同样的 ⇒ **仍必须被拦**（不能把判重放松）。"""
        if not self.catalog.has_spec_type("ger_arty_40"):
            self.skipTest("本机没有游戏包")
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        with open_save(str(info.path)) as save:
            hq_id, pool = self._pool_with_entry(save)
            if hq_id is None:
                self.skipTest("这个存档的兵库都是空的")
            old = pool[0]
            entry = {"quantity": old.get("quantity", 1),
                     "spec": old.get("spec"), "equipment": old.get("equipment"),
                     "nationality": old.get("nationality", ""),
                     "delay": old.get("delay", 0)}
            if not entry.get("spec") and not entry.get("equipment"):
                self.skipTest("第一条兵库条目不是可复制的形态")
            plan = save.plan_edit([Edit.hq_force_pool_add(hq_id, entry)],
                                   catalog=self.catalog)
            self.assertFalse(plan.ok, "没删就加同样的条目 ⇒ 必须被拦")
            self.assertTrue(any("已经有" in e for e in plan.errors), plan.errors)


if __name__ == "__main__":
    unittest.main()
