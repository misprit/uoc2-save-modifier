# -*- coding: utf-8 -*-
"""U84：特种兵的「被压制」状态（存档字段 = `active`）。

**机制实证**（游戏字节码，U84 取证）：
* 存档里特种兵条目只有 **4 个字段**：`type` / `active` / `captured` / `idx`
  —— `uoc2.state.entities.unit.SpecialistState.__init__(gamelike, type, active, captured, idx)`；
* **没有独立的 suppressed 字段** —— `active=False` **就是**被压制：
  - 渲染：`uoc2.common.scalables._render_status` 按 `active` 选
    `specialist/<类型>/status_act` 或 `status_sup`；
  - 产生：`UnitState.apply_losses_att_pindown`（火力压制）置 `spec.active=False`；
  - 恢复：`UnitState.apply_recovery_specs(k)` 按单位的恢复步数逐步恢复
    （唯一调用点是战役↔场景对账 `adjust_units_between_situations`）。

**为什么有这些测试**：用户要「能改特种兵的压制状态」，
同时要求「**别把已有属性改坏了**」⇒ 必须守住三件事：
① 只改 `active` 这一个键（同条目的 type / captured / idx 原样）；
② 别的 spec 条目原样；
③ 挂 / 卸特种兵时 4 个字段齐全（`captured` 不能丢）。
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

import yaml

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")


class SpecSuppressionTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="spec_sup_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def open(self):
        return open_save(str(self.save_path), self.paths)

    def commit(self, edits):
        with self.open() as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            if not plan.ok:
                return plan, None
            return plan, save.commit(plan)

    def units(self):
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read("units.yml"))


class TestSpecSuppression(SpecSuppressionTestBase):
    """核心库：改 `active` 一个键。"""

    def test_suppress_writes_active_false(self):
        plan, res = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        specs = self.units()[0]["specs"]
        self.assertEqual(len(specs), 1)
        self.assertFalse(specs[0]["active"])

    def test_restore_writes_active_true(self):
        """先压制、再恢复 —— 两步都要真的写进盘里。"""
        plan, res = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(self.units()[0]["specs"][0]["active"])
        plan, res = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, True)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(self.units()[0]["specs"][0]["active"])

    def test_only_the_active_key_changes(self):
        """⚠️ **不能把别的属性改坏** —— type / captured / idx 必须原样。"""
        before = self.units()[0]["specs"][0]
        plan, res = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        after = self.units()[0]["specs"][0]
        self.assertEqual(after["type"], before["type"])
        self.assertEqual(after["captured"], before["captured"])
        self.assertEqual(after["idx"], before["idx"])
        self.assertEqual(set(after.keys()), set(before.keys()),
                         "特种兵条目的字段集合不能变（游戏只认这 4 个）")

    def test_other_entries_are_untouched(self):
        """别的单位 / 别的条目一个字节都不许动。"""
        before = self.units()
        plan, res = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        after = self.units()
        self.assertEqual(after[1], before[1], "别的单位被改动了")
        self.assertEqual(after[0]["specs"][1:], before[0]["specs"][1:])

    def test_unknown_spec_is_reported(self):
        plan, _ = self.commit([Edit.unit_spec_active(1, "not_a_real_spec", 0, False)])
        self.assertFalse(plan.ok)
        self.assertIn("not_a_real_spec", plan.errors[0])

    def test_unknown_unit_is_reported(self):
        plan, _ = self.commit([Edit.unit_spec_active(999, "ger_arty_40", 0, False)])
        self.assertFalse(plan.ok)
        self.assertIn("999", plan.errors[0])

    def test_non_boolean_value_is_rejected(self):
        plan, _ = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, "yes")])
        self.assertFalse(plan.ok)
        self.assertIn("布尔", plan.errors[0])

    def test_warnings_explain_the_game_behaviour(self):
        """压制要提示：游戏会按恢复步数把它恢复（免得玩家以为永久）。"""
        plan, _ = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("恢复" in w for w in plan.warnings), plan.warnings)

    def test_same_value_is_a_no_op(self):
        """本来就活�� ⇒ **没事可做**（不是错误，也不该产生多余的备份）。"""
        plan, res = self.commit([Edit.unit_spec_active(1, "ger_arty_40", 0, True)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(plan.changes, [], "没有变化就不该产生任何写入")
        self.assertTrue(res.nothing_to_do, res.errors)


class TestSpecFieldsNotBroken(SpecSuppressionTestBase):
    """挂 / 卸特种兵时**不能把压制相关字段写坏**。"""

    def setUp(self):
        super().setUp()
        if not self.catalog.has_spec_type("us_arty_42"):
            self.skipTest("本机没有游戏包")

    def test_added_spec_has_all_four_fields(self):
        """新增的特种兵：`active` / `captured` / `idx` / `type` 一个都不能少。"""
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        spec = self.units()[0]["specs"][1]
        self.assertEqual(set(spec.keys()), {"active", "captured", "idx", "type"},
                         "特种兵条目必须正好是这 4 个字段")
        self.assertTrue(spec["active"], "新挂的特种兵应该是活跃的")
        self.assertFalse(spec["captured"])

    def test_removing_one_keeps_the_others(self):
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42")])
        self.assertTrue(plan.ok, plan.errors)
        plan2, res2 = self.commit([Edit.unit_spec_remove(1, "us_arty_42", 1)])
        self.assertTrue(plan2.ok, plan2.errors)
        self.assertTrue(res2.ok, res2.errors)
        specs = self.units()[0]["specs"]
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["type"], "ger_arty_40")
        self.assertTrue(specs[0]["active"])


class TestSpecSuppressionUi(unittest.TestCase):
    """界面：已挂特种兵有「压制 / 恢复」按钮，被压制时图标变灰。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def test_slot_card_has_a_suppress_button(self):
        self.assertIn("toggleSpecSuppressed", self.html)
        self.assertIn("supbtn", self.html)

    def test_suppressed_slot_is_greyed_out(self):
        self.assertIn(".slot.sup", self.html)
        self.assertIn("grayscale", self.html)

    def test_suppressed_slot_shows_the_state(self):
        self.assertIn("supstate", self.html)
        self.assertIn("被压制", self.html)

    def test_pending_state_is_previewed(self):
        """待应用里改过压制状态 ⇒ 界面要立刻反映（不能等写盘）。"""
        self.assertIn('pendingVal("unit_spec_active"', self.html)

    def test_only_real_slots_get_the_button(self):
        """还没写盘的新增件（临时负数 idx）不给按钮 —— 写盘后槽位才定。"""
        body = self.html[self.html.index("function specSlotHTML"):
                         self.html.index("function toggleSpecSuppressed")]
        self.assertIn("s.idx>=0", body)

    def test_english_words_exist(self):
        ui = self.table["ui"]
        for zh in ("被压制", "设为被压制", "恢复活跃"):
            self.assertIn(zh, ui, "词表里缺 %r" % zh)
        self.assertEqual(ui["被压制"], "Suppressed")


if __name__ == "__main__":
    unittest.main()
