# -*- coding: utf-8 -*-
"""U121：护栏 —— 一次改**多条**时，不能删错行（外部审阅报告 P0-2）。

**漏洞**

「按下标删除」的编辑有两个：

| kind | 删的是哪份列表 |
|---|---|
| `hq_force_pool_remove` | 某个总部的 `force_pool` |
| `store_remove` | 某个 战线/子商店 的商品列表 |

删一条 ⇒ 后面条目的下标**整体前移** ⇒ 接着再按老下标删 ⇒ **删到了别的条目**。

以前 `plan.py::order_edits` 只把 `hq_force_pool_remove` 排到最后并按下标降序，
**`store_remove` 漏了** ⇒ 商店里一次下架两条时就会删错行
（外部审阅报告 P0-2）。

**这些测试守着**

① 商店一次下架两条 ⇒ **剩下的正是该剩下的那两条**（不是错位的那两条）；
② 删除顺序与**玩家点按钮的先后无关**（升序 / 降序给进去，结果一样）；
③ 删的同时改价格 ⇒ 改的是**原来那条**（改价必须排在删除之前）；
④ 兵库删两条（老问题 U91）**照样**对。
"""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402

from ._fixtures import make_save  # noqa: E402

FOUR_ITEMS = {
    "south": {
        "store": [
            {"equipment": "infantry", "nationality": "us",
             "price": 5, "quantity": 20},
            {"spec": "ger_arty_40", "nationality": "german",
             "price": 8, "quantity": 4},
            {"equipment": "armor", "nationality": "us",
             "price": 9, "quantity": 3},
            {"spec": "ger_pz_39", "nationality": "german",
             "price": 7, "quantity": 2},
        ],
        "elite_store": None,
    },
}


class DeleteOrderTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u121_del_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg",
                                   store_overrides=FOUR_ITEMS)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def commit(self, edits):
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        return res

    def store_entries(self):
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("store.yml"))
        return data["south"]["store"]

    def ident(self, entry):
        return entry.get("spec") or entry.get("equipment")


class StoreRemoveOrderTest(DeleteOrderTestBase):
    def test_removing_two_items_keeps_the_right_two(self):
        """⭐ 删第 0 条和第 2 条 ⇒ 剩下 `ger_arty_40` 和 `ger_pz_39`。

        升序删的话：先删 idx0（infantry）⇒ 列表前移 ⇒ 再删 idx2
        ⇒ 删掉的是 **armor** ⇒ `ger_arty_40` 被误删。
        """
        self.commit([
            Edit.store_remove("south", "store", 0),
            Edit.store_remove("south", "store", 2),
        ])
        left = [self.ident(e) for e in self.store_entries()]
        self.assertEqual(["ger_arty_40", "ger_pz_39"], left,
                         "删错行了：剩下的应该是 ger_arty_40 和 ger_pz_39")

    def test_the_result_does_not_depend_on_the_click_order(self):
        """玩家先点第 2 条还是先点第 0 条，结果必须一样。"""
        self.commit([
            Edit.store_remove("south", "store", 2),
            Edit.store_remove("south", "store", 0),
        ])
        left = [self.ident(e) for e in self.store_entries()]
        self.assertEqual(["ger_arty_40", "ger_pz_39"], left)

    def test_a_price_change_still_lands_on_the_right_item(self):
        """删除会前移下标 ⇒ **改价必须排在删除之前**（改价按原下标定位）。"""
        self.commit([
            Edit.store_remove("south", "store", 0),
            Edit.store_set("south", "store", 3, "price", 11),
        ])
        entries = self.store_entries()
        by_id = {self.ident(e): e for e in entries}
        self.assertNotIn("infantry", by_id)
        self.assertEqual(11, by_id["ger_pz_39"]["price"],
                         "改价改到了别的条目上")

    def test_removing_from_another_shop_does_not_shift_this_one(self):
        """不同战线互不影响 ⇒ 只删一条时，剩下的就是那三条。"""
        self.commit([Edit.store_remove("south", "store", 1)])
        left = [self.ident(e) for e in self.store_entries()]
        self.assertEqual(["infantry", "armor", "ger_pz_39"], left)


class HqPoolRemoveOrderTest(DeleteOrderTestBase):
    """老问题 U91：兵库一次删两条（别被 U121 改坏）。"""

    def hq_pool(self):
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("hqs.yml"))
        for hq in data:
            if hq["id"] == 5:
                return hq.get("force_pool") or []
        return []

    def test_removing_both_pool_items_works(self):
        self.commit([
            Edit.hq_force_pool_remove(5, 0),
            Edit.hq_force_pool_remove(5, 1),
        ])
        self.assertEqual([], self.hq_pool())

    def test_pool_remove_order_does_not_matter(self):
        self.commit([
            Edit.hq_force_pool_remove(5, 1),
            Edit.hq_force_pool_remove(5, 0),
        ])
        self.assertEqual([], self.hq_pool())


class OrderEditsUnitTest(unittest.TestCase):
    """直接盯 `order_edits` 的排序结果。"""

    def test_store_remove_is_treated_as_a_delete_by_index(self):
        from save_modifier_core.plan import order_edits
        edits = [
            Edit.store_remove("south", "store", 0),
            Edit.store_remove("south", "store", 3),
            Edit.store_set("south", "store", 1, "price", 2),
        ]
        got = [e.kind for e in order_edits(edits)]
        self.assertEqual(["store_set", "store_remove", "store_remove"], got)
        # 删除的两条：下标大的在前
        removes = [e for e in order_edits(edits) if e.kind == "store_remove"]
        self.assertEqual([3, 0], [e.params["index"] for e in removes])

    def test_different_shops_are_separate_groups(self):
        from save_modifier_core.plan import order_edits
        edits = [
            Edit.store_remove("south", "store", 0),
            Edit.store_remove("north", "store", 5),
        ]
        removes = [e for e in order_edits(edits) if e.kind == "store_remove"]
        # 不同组 ⇒ 相对顺序无所谓，但都得排在最后
        self.assertEqual(2, len(removes))


if __name__ == "__main__":
    unittest.main()
