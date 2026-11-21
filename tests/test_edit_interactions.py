# -*- coding: utf-8 -*-
"""U138：护栏 —— **交互类**用例（外部评价：测试要「测交互」而不是「测函数」）。

这批 bug 集中在**接缝**上（前端↔后端 / plan↔commit / 进程↔进程 / 工具↔文件系统），
单函数测试**测不出来**。本文件补三类**交互**用例：

1. **同批编辑的组合** —— 上架 + 下架同批（U118 的负下标 + U121 的删除排序）；
2. **plan → commit 之间档被改过** —— commit 是**拿同一批 edits 在当前状态上重新规划**
   （⚠️ 已知边界：外部审阅 P1-1）⇒ 这里把这条**语义钉住**；
3. **入口输入** —— 路径穿越 / `save_id` 越界 / 并发写盘（分别在别的文件里）。

**为什么第 2 条要专门钉**：将来谁把 commit 改成「用 plan 的结果」，行为就变了
（玩家看到的 diff 与写下去的不一致）⇒ 有这条测试才会**当场变红**。
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
from save_modifier_core.writer import write_overlay  # noqa: E402

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


class InteractionTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u138_inter_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg",
                                   store_overrides=FOUR_ITEMS)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        self._old_bak = os.environ.get("UOC2_BAK_DIR")
        os.environ["UOC2_BAK_DIR"] = str(self.tmp / "bak")
        self.addCleanup(self._restore_bak)

    def _restore_bak(self):
        if self._old_bak is None:
            os.environ.pop("UOC2_BAK_DIR", None)
        else:
            os.environ["UOC2_BAK_DIR"] = self._old_bak

    def plan(self, edits):
        with open_save(str(self.save_path), self.paths) as save:
            return save.plan_edit(edits, catalog=self.catalog)

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


class SameBatchCombinationsTest(InteractionTestBase):
    """同批编辑的**组合**。"""

    def test_add_and_remove_in_the_same_batch(self):
        """⭐ 同批里既有上架又有下架 ⇒ 上架落在**末尾**、下架删的是**原来那条**。

        （上架是 append ⇒ 不影响老下标；删除必须排在最后、按老下标定位。）
        """
        self.commit([
            Edit.store_add("south", "store", {"equipment": "armor",
                                              "nationality": "german",
                                              "price": 11, "quantity": 2}),
            Edit.store_remove("south", "store", 1),
        ])
        ids = [self.ident(e) for e in self.store_entries()]
        self.assertEqual(["infantry", "armor", "ger_pz_39", "armor"], ids,
                         "上架要落在末尾、下架要删掉原来第 2 条（ger_arty_40）")

    def test_remove_and_add_in_the_other_order(self):
        """顺序反过来（先删后加）⇒ 结果一样。"""
        self.commit([
            Edit.store_remove("south", "store", 1),
            Edit.store_add("south", "store", {"equipment": "armor",
                                              "nationality": "german",
                                              "price": 11, "quantity": 2}),
        ])
        ids = [self.ident(e) for e in self.store_entries()]
        self.assertEqual(["infantry", "armor", "ger_pz_39", "armor"], ids)

    def test_two_removes_and_one_add(self):
        """两条删除 + 一条上架 ⇒ 删掉的是**原来那两条**。"""
        self.commit([
            Edit.store_add("south", "store", {"equipment": "armor",
                                              "nationality": "german",
                                              "price": 11, "quantity": 2}),
            Edit.store_remove("south", "store", 0),
            Edit.store_remove("south", "store", 2),
        ])
        ids = [self.ident(e) for e in self.store_entries()]
        self.assertEqual(["ger_arty_40", "ger_pz_39", "armor"], ids,
                         "该剩下 ger_arty_40、ger_pz_39 与新上架的 armor")


class PlanThenCommitTest(InteractionTestBase):
    """plan → commit 之间档被改过（⚠️ 已知边界 P1-1）。"""

    def _patch_main(self, old, new):
        """**绕过撤销栈**改 main.yml（模拟游戏自己存了档）。"""
        with zipfile.ZipFile(self.save_path) as zf:
            raw = zf.read("main.yml").decode("utf-8")
        self.assertIn(old, raw)
        res = write_overlay(self.save_path,
                            {"main.yml": raw.replace(old, new).encode("utf-8")})
        self.assertTrue(res.ok, res.errors)

    def test_commit_uses_the_current_state_not_the_planned_one(self):
        """⚠️ commit **不缓存 plan 的结果** ⇒ 它拿同一批 edits **在当前状态上重新规划**。

        ⇒ 玩家在确认框停留期间游戏改了档 ⇒ 实际写入按**新状态**算
        （「以最新状态为准」的语义）。
        这条测试把语义**钉住**：将来若改成「用 plan 的结果」，这里会当场变红。
        """
        edits = [Edit.progress("prestige", 500)]
        plan = self.plan(edits)
        self.assertTrue(plan.ok, plan.errors)
        self.assertIn("main.yml", plan.changed_entries)

        # 游戏自己存了档：prestige 320 → 7、score 2980 → 1111（其它内容不动）
        self._patch_main("prestige: 320", "prestige: 7")
        self._patch_main("score: 2980", "score: 1111")

        self.commit(edits)
        with zipfile.ZipFile(self.save_path) as zf:
            main = yaml.safe_load(zf.read("main.yml"))
        self.assertEqual(500, main["prestige"], "改动应该写下去")
        # ⭐ 关键：**游戏改的那个字段必须留着** ⇒ 说明写盘用的是**当前状态**，
        # 而不是 plan 时的那份快照（否则会把 score 改回 2980）。
        self.assertEqual(1111, main["score"],
                         "commit 用的是**当前**状态（不是 plan 时的快照）")
        self.assertEqual("west", main["campaign_id"], "其它字段没被动过")

    def test_the_plan_itself_never_touches_the_disk(self):
        """plan **不碰磁盘**（U55 的老规矩，别在重构时弄丢）。"""
        before = self.save_path.read_bytes()
        self.plan([Edit.progress("prestige", 500)])
        self.assertEqual(before, self.save_path.read_bytes(),
                         "plan 阶段不该动存档")


if __name__ == "__main__":
    unittest.main()
