# -*- coding: utf-8 -*-
"""B-1：商店「删一条再添同一条」必须能应用（社区反馈的老问题）。

**根因**：`plan.order_edits()` 把按下标删除的编辑排最后 ⇒ `store_add` 先跑
⇒ 判重时旧条目还在 ⇒ 撞重复校验 ⇒ 整批 plan 失败。

**修法**：判重看「这一批改完之后」的列表 —— 本批待删的那几条不参与判重。

**这个测试怎么写的**（U188 的教训：不要复刻判定逻辑自证）：
用**真实存档副本**（`pick_save`）+ **真实核心库**跑一遍 ⇒ 验的是行为，不是复刻。
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


class TestStoreReplaceInsteadOfDuplicate(unittest.TestCase):
    """删一条 + 添同一条 = 替换（不是重复）。"""

    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog_mod.default()

    def _first_store_entry(self, save):
        """存档里第一个有商品的 (战线, 子商店) 与它的第一条。"""
        store = save.read_yaml("store.yml", {})
        if not isinstance(store, dict):
            return None, None, None
        for front, subs in store.items():
            if not isinstance(subs, dict):
                continue
            for sub in ("store", "elite_store"):
                lst = subs.get(sub)
                if isinstance(lst, list) and lst and isinstance(lst[0], dict):
                    return front, sub, lst[0]
        return None, None, None

    def test_remove_then_add_same_entry_succeeds(self):
        """删一条 → 再添同样的一条 ⇒ **能应用**，且存档里**只有一条**。"""
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        with open_save(str(info.path)) as save:
            front, sub, entry = self._first_store_entry(save)
            if front is None:
                self.skipTest("这个存档没有商店数据")
            ident = {"equipment": entry.get("equipment"), "spec": entry.get("spec"),
                     "nationality": entry.get("nationality"),
                     "price": entry.get("price"), "quantity": entry.get("quantity")}
            plan = save.plan_edit([
                Edit.store_add(front, sub, ident),
                Edit.store_remove(front, sub, 0),
            ], catalog=self.catalog)
            self.assertTrue(plan.ok, "删一条再添同一条应当能应用：%s" % plan.errors)

    def test_remove_then_add_same_entry_keeps_one_copy(self):
        """应用后存档里那个条目**只应有一条**（不是两条，也不是零条）。"""
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp(prefix="uoc2_b1_")
        try:
            dst = os.path.join(tmp, "t.usg")
            shutil.copy2(info.path, dst)
            with open_save(dst) as save:
                front, sub, entry = self._first_store_entry(save)
                if front is None:
                    self.skipTest("这个存档没有商店数据")
                before = sum(len(v.get(sub) or [])
                             for v in (save.read_yaml("store.yml", {}) or {}).values()
                             if isinstance(v, dict))
                ident = {"equipment": entry.get("equipment"), "spec": entry.get("spec"),
                         "nationality": entry.get("nationality"),
                         "price": entry.get("price"), "quantity": entry.get("quantity")}
                plan = save.plan_edit([
                    Edit.store_add(front, sub, ident),
                    Edit.store_remove(front, sub, 0),
                ], catalog=self.catalog)
                self.assertTrue(plan.ok, plan.errors)
                res = save.commit(plan)
                self.assertTrue(res.ok, res.errors)
            with zipfile.ZipFile(dst) as zf:
                import yaml
                store = yaml.safe_load(zf.read("store.yml"))
            after = sum(len(v.get(sub) or [])
                        for v in (store or {}).values() if isinstance(v, dict))
            self.assertEqual(before, after,
                             "删一条添一条 ⇒ 条目总数应不变（实得 %d → %d）" % (before, after))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_duplicate_without_remove_is_still_rejected(self):
        """⚠️ **不能**把判重规则放松 —— 真的重复（没删就加）仍必须被拦。"""
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        with open_save(str(info.path)) as save:
            front, sub, entry = self._first_store_entry(save)
            if front is None:
                self.skipTest("这个存档没有商店数据")
            ident = {"equipment": entry.get("equipment"), "spec": entry.get("spec"),
                     "nationality": entry.get("nationality"),
                     "price": entry.get("price"), "quantity": entry.get("quantity")}
            plan = save.plan_edit([Edit.store_add(front, sub, ident)],
                                   catalog=self.catalog)
            self.assertFalse(plan.ok, "没删就加同样的条目 ⇒ 必须被拦")
            self.assertTrue(any("已经有" in e for e in plan.errors), plan.errors)

    def test_removing_a_different_entry_does_not_exempt_the_duplicate(self):
        """删的是**别的**条目 ⇒ 待加的这个重复**仍必须被拦**（不能放宽过头）。"""
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        with open_save(str(info.path)) as save:
            front, sub, entry = self._first_store_entry(save)
            if front is None:
                self.skipTest("这个存档没有商店数据")
            lst = save.read_yaml("store.yml", {})[front][sub]
            if len(lst) < 2:
                self.skipTest("这个商店只有一条，没法测「删别的」")
            # 加**第 2 条**的复制品，同时删**第 1 条** ⇒ 第 2 条的重复必须仍被拦
            other = lst[1]
            ident = {"equipment": other.get("equipment"), "spec": other.get("spec"),
                     "nationality": other.get("nationality"),
                     "price": other.get("price"), "quantity": other.get("quantity")}
            plan = save.plan_edit([
                Edit.store_add(front, sub, ident),
                Edit.store_remove(front, sub, 0),
            ], catalog=self.catalog)
            self.assertFalse(plan.ok,
                             "删的是别的条目 ⇒ 待加的这个重复**仍必须被拦**")
            self.assertTrue(any("已经有" in e for e in plan.errors), plan.errors)


if __name__ == "__main__":
    unittest.main()
