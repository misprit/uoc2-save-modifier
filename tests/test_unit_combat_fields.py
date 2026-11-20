# -*- coding: utf-8 -*-
"""U85：单位详情的「工事等级 / 移动力 / 行动力」三张卡。

**机制取证**（游戏字节码，U85）：

* `entr` 工事等级 —— 0/1/2（游戏的 `unit_max_entr_level = 2`）；
  `can_make_entrenchment` 还要求单位在补给范围内、有行动力等；
* `mp` 移动力 —— **剩余**移动点（状态量：游戏的 `apply_mp_ap` 按类型的
  `_type.move` 重算，有补给就给满）；
* `ap` 行动力 —— 四个常量：`ap_none=0`（没有）/ `ap_conv=1`（只能转额外移动）
  / `ap_lock=2`（只能攻击）/ `ap_full=3`（可攻击 + 可转额外移动），
  `ap_max_value=3`。

**为什么有这些测试**：这三个字段以前只能改 `entr` / `ap`（核心库允许、
界面没入口），`mp` 连核心库都不许改；U85 要补上界面 + 放开 `mp`，
并守住范围（0..2 / 0..3 / ≥0）与中文名（玩家不该对着 `entr` 猜）。
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


class CombatFieldsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u85_"))
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

    def unit(self, unit_id=1):
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        for u in units:
            if u.get("id") == unit_id:
                return u
        return None


class TestEntrenchment(CombatFieldsTestBase):
    """工事等级 `entr`（0..2）。"""

    def test_set_entr(self):
        plan, res = self.commit([Edit.unit_field(1, "entr", 2)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.unit()["entr"], 2)

    def test_entr_over_max_is_blocked(self):
        """游戏的 `unit_max_entr_level = 2`。"""
        plan, _ = self.commit([Edit.unit_field(1, "entr", 3)])
        self.assertFalse(plan.ok)
        self.assertIn("entr", plan.errors[0])

    def test_entr_negative_is_blocked(self):
        plan, _ = self.commit([Edit.unit_field(1, "entr", -1)])
        self.assertFalse(plan.ok)

    def test_summary_uses_the_chinese_name(self):
        """变更说明里要写「工事等级」，别让玩家对着 `entr` 猜。"""
        plan, _ = self.commit([Edit.unit_field(1, "entr", 2)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertIn("工事等级", plan.notes[0])


class TestActionPoints(CombatFieldsTestBase):
    """行动力 `ap`（0..3，四档）。"""

    def test_set_ap(self):
        plan, res = self.commit([Edit.unit_field(1, "ap", 3)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.unit()["ap"], 3)

    def test_ap_over_max_is_blocked(self):
        """游戏的 `ap_max_value = 3`。"""
        plan, _ = self.commit([Edit.unit_field(1, "ap", 4)])
        self.assertFalse(plan.ok)
        self.assertIn("ap", plan.errors[0])

    def test_summary_uses_the_chinese_name(self):
        plan, _ = self.commit([Edit.unit_field(1, "ap", 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertIn("行动力", plan.notes[0])


class TestMovementPoints(CombatFieldsTestBase):
    """移动力 `mp`（U85 之前核心库**不许改**）。"""

    def test_mp_is_editable_now(self):
        plan, res = self.commit([Edit.unit_field(1, "mp", 5)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.unit()["mp"], 5)

    def test_negative_mp_is_blocked(self):
        plan, _ = self.commit([Edit.unit_field(1, "mp", -1)])
        self.assertFalse(plan.ok)
        self.assertIn("mp", plan.errors[0])

    def test_other_fields_are_untouched(self):
        """改移动力不许顺手改到别的字段。"""
        before = self.unit()
        plan, res = self.commit([Edit.unit_field(1, "mp", 5)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        after = self.unit()
        for k in ("act_st", "sup_st", "entr", "ap", "xp", "type"):
            self.assertEqual(after.get(k), before.get(k), k)


class TestViewExposesMovementPoints(CombatFieldsTestBase):
    """视图层要带 `mp`（U85 之前没有 ⇒ 界面读不到）。"""

    def test_unit_view_has_mp(self):
        with self.open() as save:
            u = save.view().units[0]
        self.assertIn("mp", u.__dict__ or {f: getattr(u, f, None)
                                          for f in u.__dataclass_fields__})


class TestCombatFieldsUi(unittest.TestCase):
    """界面：三张卡 + 词表。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def test_three_cards_exist(self):
        for fn in ("unitCombatFieldsHTML", "bindUnitCombatFields",
                   "setUnitEntr", "setUnitAp", "refreshUnitCombatFields"):
            self.assertIn("function " + fn, self.html, fn)

    def test_cards_are_in_the_detail_template(self):
        """三张卡插在**血量那行之后、特种兵之前**（dhead 的 .stats 里）。"""
        i = self.html.index('return L2(`<div class="dhead">')
        j = self.html.index("</div>`, avaImg(u.type", i)
        tpl = self.html[i:j]
        self.assertIn("{18}", tpl, "dhead 模板里要有三张卡的占位")
        # 占位在经验卡之后、.stats 结束之前
        self.assertLess(tpl.index("范围 0 – 400"), tpl.index("{18}"))

    def test_entrenchment_has_three_buttons(self):
        for lv in ("0", "1", "2"):
            self.assertIn("setUnitEntr(${u.id},%s)" % lv, self.html)

    def test_action_points_has_four_options(self):
        for v in ("0", "1", "2", "3"):
            self.assertIn('<option value="%s"' % v, self.html)

    def test_cards_wrap_by_width(self):
        """按栏宽自动换行（`auto-fit` + 最小列宽）。"""
        self.assertIn("grid-template-columns:repeat(auto-fit,minmax(190px,1fr))",
                      self.html)

    def test_english_words_exist(self):
        ui = self.table["ui"]
        for zh in ("工事等级", "移动力", "行动力", "没有行动力（不能攻击）",
                   "受限：只能攻击", "不受限：可攻击 + 可转额外移动"):
            self.assertIn(zh, ui, "词表里缺 %r" % zh)
        self.assertEqual(ui["不受限：可攻击 + 可转额外移动"],
                         "unlimited: can attack and convert to extra movement")

    def test_summaries_are_translated(self):
        errs = self.table["errors"]
        for zh in ("单位 {unit_id} 的工事等级（entr）：{old} → {value}",
                   "单位 {unit_id} 的行动力（ap）：{old} → {value}",
                   "单位 {unit_id} 的移动力（mp）：{old} → {value}"):
            self.assertIn(zh, errs, "词表里缺 %r" % zh)


if __name__ == "__main__":
    unittest.main()
