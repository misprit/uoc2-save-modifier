"""S6：单位 —— 经验 / 战力 / 改名（写明文）。

**验收口径**（规范 §6.2、§5.2、§5.5、§5.4）：

* `xp` 超过 400 **必须被拦**；
* `type`（编制）**必须被拒**，并给出可读的理由；
* 改名**直接写明文**，改完游戏直接显示，**不产生任何 temp mod**；
* 战力上限按类型的 `max_st` **软提示**（不硬拦）；
* 非法字段名被拒。
"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save


class UnitEditingTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="unit_edit_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        self.skip_no_game = not self.catalog.has_unit_type("us_inf_42")

    def open(self):
        return open_save(str(self.save_path), self.paths)

    def plan(self, edits):
        with self.open() as save:
            return save.plan_edit(edits, catalog=self.catalog)

    def commit(self, edits):
        with self.open() as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            if not plan.ok:
                return plan, None
            return plan, save.commit(plan)


class TestUnitFields(UnitEditingTestBase):
    def test_set_xp(self):
        plan, res = self.commit([Edit.unit_field(1, "xp", 400)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            import yaml
            units = yaml.safe_load(zf.read("units.yml"))
        self.assertEqual(units[0]["xp"], 400)

    def test_xp_over_400_is_blocked(self):
        plan, res = self.commit([Edit.unit_field(1, "xp", 401)])
        self.assertFalse(plan.ok)
        self.assertIsNone(res)
        self.assertIn("400", plan.errors[0])

    def test_negative_xp_is_blocked(self):
        plan, _ = self.commit([Edit.unit_field(1, "xp", -1)])
        self.assertFalse(plan.ok)

    def test_set_strength(self):
        plan, res = self.commit([Edit.unit_field(2, "act_st", 7),
                                 Edit.unit_field(2, "sup_st", 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            import yaml
            units = yaml.safe_load(zf.read("units.yml"))
        self.assertEqual(units[1]["act_st"], 7)
        self.assertEqual(units[1]["sup_st"], 0)

    def test_strength_over_max_st_warns_but_allows(self):
        """上限是**软提示**，不硬拦 —— 禁用反而更糟（§6.2.1）。"""
        if self.skip_no_game:
            self.skipTest("本机没有游戏包")
        plan, res = self.commit([Edit.unit_field(1, "act_st", 99)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("max_st" in w for w in plan.warnings),
                        plan.warnings)
        self.assertTrue(res.ok)

    def test_unknown_unit_is_reported(self):
        plan, _ = self.commit([Edit.unit_field(999, "xp", 10)])
        self.assertFalse(plan.ok)
        self.assertIn("999", plan.errors[0])

    def test_disallowed_field_is_rejected(self):
        plan, _ = self.commit([Edit.unit_field(1, "losses", 999)])
        self.assertFalse(plan.ok)


class TestTypeIsReadOnly(UnitEditingTestBase):
    def test_type_change_is_rejected_with_reason(self):
        """`type` 是只读信息 —— 要改请改战力与特种兵（§5.4、§7.5）。"""
        plan, _ = self.commit([Edit.unit_field(1, "type", "ger_inf_39")])
        self.assertFalse(plan.ok)
        self.assertIn("只读", plan.errors[0])
        self.assertIn("act_st", plan.errors[0])

    def test_type_field_never_written(self):
        with self.open() as save:
            before = save.root_units()[0]["type"]
            plan = save.plan_edit([Edit.unit_field(1, "type", "ger_inf_39")],
                                  catalog=self.catalog)
        self.assertFalse(plan.ok)
        self.assertEqual(before, "us_inf_42")


class TestRenameInPlainText(UnitEditingTestBase):
    def test_rename_writes_plain_text(self):
        plan, res = self.commit([Edit.unit_field(1, "name_brief", "我的部队")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            import yaml
            units = yaml.safe_load(zf.read("units.yml"))
        self.assertEqual(units[0]["name_brief"], "我的部队")

    def test_rename_produces_no_temp_mod(self):
        """改名**不碰** `_packages/` —— 不产生任何 temp mod 目录（§5.5、§7.5）。"""
        before = sorted(p.name for p in
                        (Path.home() / "AppData" / "Local" / ".uoc2" / "_packages").glob("*"))
        self.commit([Edit.unit_field(1, "name_brief", "我的部队")])
        after = sorted(p.name for p in
                       (Path.home() / "AppData" / "Local" / ".uoc2" / "_packages").glob("*"))
        self.assertEqual(before, after)

    def test_localization_like_name_gets_a_hint(self):
        plan, _ = self.commit([Edit.unit_field(1, "name_brief", "id_xxx_brief")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("本地化" in w for w in plan.warnings), plan.warnings)

    def test_name_full_accepts_null(self):
        plan, res = self.commit([Edit.unit_field(1, "name_full", None)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)


class TestOnlyTargetEntryChanges(UnitEditingTestBase):
    def test_units_yml_is_the_only_changed_entry(self):
        plan, res = self.commit([Edit.unit_field(1, "xp", 123)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.changed, ["units.yml"])


if __name__ == "__main__":
    unittest.main()
