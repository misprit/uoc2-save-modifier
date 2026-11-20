# -*- coding: utf-8 -*-
"""U96：单位「兵力上限」的语义与**误报**修复。

**游戏口径**（字节码实证）：

* `max_st` 是**该单位类型**的普通部队上限（627 个类型的取值是
  `[3, 4, 5, 6, 7]`，类型 yml 没写时按 schema 默认 **7**）——
  **每个类型各按各的**，不是常数；
* 这个上限约束的是**普通部队**（`act_st` 活跃 + `sup_st` 被压制），
  **特种兵不占名额**（特种兵另占「总战力」= 普通部队 + 特种兵数；
  而总战力超上限**游戏允许** —— 真实存档 1430 个单位里有 166 个如此
  ⇒ 「7 兵 + 2 特种兵」是合法的）；
* 游戏读档时也只查这两项（`UnitState.check_data_consistency`），
  超了由 `UnitState._repair_data` **截回上限**。

**误报的根因与修法**：

前端滚轮调兵力时会**同时**改 `act_st` 与 `sup_st`（夹到上限时从压制里扣），
而核心库是**依次执行**这两条编辑的 ⇒ 先执行 `act_st` 那条时 `sup_st`
还是旧值 ⇒ 「活跃 + 压制」算出来超过上限 ⇒ **误报警告**
（用户 2026-11-20 报告：「上限 6 的兵，界面最多只能调到 6，
可保存时还是弹警告」）。

修法：① 核心库写入时**自动配平**（先扣压制、再截活跃；与前端夹取、
游戏读档修复一致）；② 前端把两条编辑的顺序摆正（压制在前）。
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

#: fixtures 的单位 1 = `us_inf_42` ⇒ `max_st = 6`（不是 7！）；
#: 单位 2 = `ger_inf_39` ⇒ `max_st = 7`。
UNIT_LIMITED = 1      # us_inf_42 → 6
UNIT_ROOMY = 2        # ger_inf_39 → 7


class UnitStLimitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u96_st_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.catalog = Catalog(CorePaths.discover())
        if not self.catalog.has_unit_type("us_inf_42"):
            self.skipTest("本机没有游戏包")
        self.save_path = self.tmp / "s.usg"
        make_save(self.save_path)

    # ---------- 工具 ----------
    def plan(self, edits):
        with open_save(str(self.save_path)) as save:
            return save.plan_edit(edits, catalog=self.catalog)

    def commit(self, edits):
        with open_save(str(self.save_path)) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            return save.commit(plan)

    def unit(self, uid=UNIT_LIMITED):
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        return next(u for u in units if u.get("id") == uid)

    def over_warnings(self, plan):
        """只挑「超过上限」类的警告（配平说明不算）。"""
        return [w for w in plan.warnings if "超过该类型的上限" in w]

    # ---------- 上限是**按类型**的，不是常数 ----------
    def test_limit_comes_from_the_unit_type(self):
        self.assertEqual(self.catalog.max_st("us_inf_42"), 6)
        self.assertEqual(self.catalog.max_st("ger_inf_39"), 7)
        self.assertNotEqual(self.catalog.max_st("us_inf_42"),
                            self.catalog.max_st("ger_inf_39"))

    # ---------- 误报回归 ----------
    def test_no_false_warning_when_front_ends_with_suppressed_first(self):
        """前端滚轮的顺序（压制在前、活跃在后）⇒ 不该再报「超过上限」。"""
        plan = self.plan([Edit.unit_field(UNIT_LIMITED, "sup_st", 2),
                          Edit.unit_field(UNIT_LIMITED, "act_st", 6)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(self.over_warnings(plan), [],
                         "不该再报「超过上限」：%s" % self.over_warnings(plan))

    def test_no_false_warning_with_the_old_order_either(self):
        """就算顺序反了（活跃在前），核心库也会**配平** ⇒ 同样不该报。"""
        plan = self.plan([Edit.unit_field(UNIT_LIMITED, "act_st", 6),
                          Edit.unit_field(UNIT_LIMITED, "sup_st", 2)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(self.over_warnings(plan), [],
                         "不该再报「超过上限」：%s" % self.over_warnings(plan))

    # ---------- 配平 ----------
    def test_writing_act_balances_the_suppressed_part(self):
        """直接改活跃（没同步改压制）⇒ 核心库从压制里扣，保持合计 ≤ 上限。"""
        self.commit([Edit.unit_field(UNIT_LIMITED, "sup_st", 2)])
        res = self.commit([Edit.unit_field(UNIT_LIMITED, "act_st", 6)])
        self.assertTrue(res.ok, res.errors)
        u = self.unit()
        self.assertEqual(u["act_st"], 6)
        self.assertEqual(u["sup_st"], 0)
        self.assertLessEqual(u["act_st"] + u["sup_st"],
                             self.catalog.max_st("us_inf_42"))

    def test_writing_beyond_the_limit_caps_the_active_part(self):
        """活跃直接写超上限 ⇒ 截到上限（并说明）。"""
        res = self.commit([Edit.unit_field(UNIT_LIMITED, "act_st", 9)])
        self.assertTrue(res.ok, res.errors)
        u = self.unit()
        self.assertEqual(u["act_st"], 6)
        self.assertTrue(any("截断" in w for w in res.warnings),
                        res.warnings)

    def test_balance_warning_explains_what_happened(self):
        plan = self.plan([Edit.unit_field(UNIT_LIMITED, "sup_st", 2),
                          Edit.unit_field(UNIT_LIMITED, "act_st", 6)])
        self.assertTrue(plan.ok, plan.errors)
        # 配平后不该再有「超过上限」，但要有一条**说明**（压制被调了）
        self.assertTrue(any("被压制兵力" in w for w in plan.warnings),
                        plan.warnings)

    # ---------- 特种兵不占名额 ----------
    def _allied_spec(self):
        """找一个能挂到 `us_inf_42`（allies / us）上的特种兵。"""
        for name in self.catalog.spec_type_names():
            st = self.catalog.spec_type(name)
            if st and st.faction == "allies" and st.nationality == "us":
                return name
        self.skipTest("游戏包里没有 us/allies 的特种兵")

    def test_special_forces_do_not_consume_the_limit(self):
        """挂两个特种兵 + 活跃满 6 ⇒ 合法，不该报「超过上限」。"""
        spec = self._allied_spec()
        plan = self.plan([Edit.unit_spec_add(UNIT_LIMITED, spec),
                          Edit.unit_spec_add(UNIT_LIMITED, spec),
                          Edit.unit_field(UNIT_LIMITED, "act_st", 6)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(self.over_warnings(plan), [],
                         "特种兵不该算进上限：%s" % self.over_warnings(plan))


if __name__ == "__main__":
    unittest.main()
