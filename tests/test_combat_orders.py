# -*- coding: utf-8 -*-
"""U89：作战标记（HQ 技能的三种「命令」）—— 读取 + 编辑。

**机制**（用户特制存档 + 游戏字节码实证）：
三个**单位 id 列表**在**当前战斗**的 `main.yml`：
`no_retreat_units`（不能撤退）/ `rearguard_units`（后卫部队）/
`elastic_defense_units`（反击）。
⚠️ 它们是**命令**，敌方下一回合结束前有效 ⇒ 游戏回合开始会清。
⚠️ 写的是**战斗层**（本仓库第二个 L3 例外，用户 2026-11-20 批准）。
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Edit, open_save, yamlio  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")

ORDERS = {"no_retreat_units": [1], "rearguard_units": [2], "elastic_defense_units": [1]}


class CombatOrdersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orders_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg", battle_overrides=dict(ORDERS))

    def open(self):
        return open_save(str(self.save_path))

    def battle_lists(self):
        with zipfile.ZipFile(self.save_path) as z:
            d = yamlio.load(z.read("games/avalanche/main.yml"))
        return {k: d.get(k) for k in ORDERS}

    # ---------------------------------------------------------- 读取
    def test_orders_are_read_from_the_battle_layer(self):
        with self.open() as save:
            v = save.view()
            byid = {u.id: u for u in v.units}
        self.assertIn("no_retreat", byid[1].orders)
        self.assertIn("rearguard", byid[2].orders)

    def test_conflicting_unit_exposes_only_the_effective_order(self):
        """U102：存档里单位 1 同时在「死守」和「反击」两个列表里
        （游戏自己造不出这种状态）⇒ **只暴露游戏会认的那一个**。

        依据：`Gamelike.get_defense_flag_string`（gamelike.pyc:1470-1476）
        按 no_retreat → rearguard → elastic_defense 的顺序**只返回一个**。
        """
        with self.open() as save:
            v = save.view()
            byid = {u.id: u for u in v.units}
        self.assertEqual(tuple(byid[1].orders), ("no_retreat",))
        self.assertTrue(byid[1].orders_conflict, "冲突要标出来")
        self.assertEqual(tuple(byid[2].orders), ("rearguard",))
        self.assertFalse(byid[2].orders_conflict)

    def test_orders_conflict_is_not_written_to_the_save(self):
        """冲突只是**读出来**的提示 ⇒ 读取本身不改存档。"""
        with zipfile.ZipFile(self.save_path) as z:
            before = {n: z.read(n) for n in z.namelist()}
        with self.open() as save:
            save.view()
        with zipfile.ZipFile(self.save_path) as z:
            after = {n: z.read(n) for n in z.namelist()}
        self.assertEqual(before, after)

    def test_unit_without_orders_has_empty_tuple(self):
        with self.open() as save:
            v = save.view()
            for u in v.units:
                if u.id not in (1, 2):
                    self.assertEqual(tuple(u.orders), ())

    # ---------------------------------------------------------- 编辑
    def test_edit_adds_an_order(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["no_retreat"])])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
            self.assertTrue(res.ok, res.errors)
        self.assertIn(1, self.battle_lists()["no_retreat_units"])
        self.assertNotIn(1, self.battle_lists()["elastic_defense_units"])
        self.assertNotIn(1, self.battle_lists()["rearguard_units"])

    def test_two_orders_at_once_are_rejected(self):
        """U102：一个单位**只能有一个**标记 ⇒ 一次给两个 ⇒ **硬拦**。

        （U89 的老测试断言这里能成功 —— 那正是用户发现的 bug。）
        """
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["no_retreat",
                                                      "elastic_defense"])])
        self.assertFalse(plan.ok)
        self.assertIn("只能有一个", plan.errors[0])

    def test_rejection_explains_why(self):
        """拦的时候要说清是**游戏**的规矩（玩家能看懂）。"""
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["rearguard",
                                                      "elastic_defense"])])
        self.assertFalse(plan.ok)
        err = plan.errors[0]
        self.assertIn("互斥", err)
        self.assertIn("_set_flags", err)          # 依据写出来

    def test_rejected_edit_does_not_touch_the_save(self):
        """被拦的编辑**一个字节都不许写**。"""
        with zipfile.ZipFile(self.save_path) as z:
            before = {n: z.read(n) for n in z.namelist()}
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["no_retreat",
                                                      "elastic_defense"])])
            self.assertFalse(plan.ok)
        with zipfile.ZipFile(self.save_path) as z:
            after = {n: z.read(n) for n in z.namelist()}
        self.assertEqual(before, after)

    def test_edit_removes_an_order(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, [])])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
            self.assertTrue(res.ok, res.errors)
        self.assertNotIn(1, self.battle_lists()["no_retreat_units"])

    def test_other_units_are_untouched(self):
        """改一个单位 ⇒ **别的单位**不受影响。

        语义 = 「把这个单位的标记集合设成 orders」⇒ 该单位自己的其它标记
        会被撤掉（前端三个开关算的是完整集合）。
        """
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["rearguard"])])
            self.assertTrue(plan.ok, plan.errors)
            save.commit(plan)
        self.assertEqual(self.battle_lists()["rearguard_units"], [2, 1])
        # id=2 仍在后卫部队里；id=1 的另外两个标记被撤掉
        self.assertIn(2, self.battle_lists()["rearguard_units"])
        self.assertEqual(self.battle_lists()["no_retreat_units"], [])
        self.assertEqual(self.battle_lists()["elastic_defense_units"], [])

    def test_unknown_order_is_rejected(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["fly_away"])])
        self.assertFalse(plan.ok)
        self.assertIn("fly_away", plan.errors[0])

    def test_orders_must_be_a_list(self):
        with self.open() as save:
            plan = save.plan_edit([Edit("unit_orders",
                                       {"unit_id": 1, "orders": "no_retreat"})])
        self.assertFalse(plan.ok)

    def test_edit_can_be_undone(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["elastic_defense"])])
            self.assertTrue(plan.ok, plan.errors)
            save.commit(plan)
            r = save.undo()
        self.assertTrue(getattr(r, "ok", False), getattr(r, "errors", None))
        self.assertEqual(self.battle_lists()["no_retreat_units"], [1])

    def test_only_the_battle_entry_is_written(self):
        """只写战斗层那一个条目 —— 其它条目一个字节都不动。"""
        with zipfile.ZipFile(self.save_path) as z:
            before = {n: z.read(n) for n in z.namelist()}
        with self.open() as save:
            plan = save.plan_edit([Edit.unit_orders(1, ["elastic_defense"])])
            self.assertTrue(plan.ok, plan.errors)
            save.commit(plan)
        with zipfile.ZipFile(self.save_path) as z:
            after = {n: z.read(n) for n in z.namelist()}
        self.assertEqual(sorted(before), sorted(after), "条目集合不能变")
        diff = [n for n in before if before[n] != after[n]]
        self.assertEqual(diff, ["games/avalanche/main.yml"], diff)


class CombatOrdersUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def test_ui_has_the_toggle(self):
        self.assertIn("function toggleUnitOrder", self.html)
        self.assertIn("orderbtn", self.html)
        self.assertIn("special_defense_", self.html)

    def test_words_exist(self):
        for zh in ("作战标记", "点击切换"):
            self.assertIn(zh, self.table["ui"], zh)

    def test_ui_replaces_instead_of_stacking(self):
        """U102：界面点新的标记 = **替换**旧的（不是叠加）。

        依据：游戏下达命令是「先从三个列表全清掉、再加进其中一个」
        （`UnitSetFlags._set_flags`）。
        """
        body = self.html[self.html.index("function toggleUnitOrder"):]
        body = body[:body.index("function setUnitEntr")]
        self.assertIn("cur.length===1 && cur[0]===key", body)
        self.assertNotIn("cur.concat(", body)
        self.assertNotIn("cur.filter(k=>k!==key)", body)

    def test_ui_shows_the_mutual_exclusion_hint(self):
        self.assertIn("三个标记互斥：选新的会撤掉旧的", self.html)
        self.assertIn("存档里这个单位同时有多个标记，游戏只认第一个", self.html)
        self.assertIn("u.orders_conflict", self.html)

    def test_new_words_are_in_the_word_table(self):
        for zh in ("三个标记互斥：选新的会撤掉旧的",
                   "存档里这个单位同时有多个标记，游戏只认第一个"):
            self.assertIn(zh, self.table["ui"], zh)
            self.assertTrue(self.table["ui"][zh], zh)


if __name__ == "__main__":
    unittest.main()
