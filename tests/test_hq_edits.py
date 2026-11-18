"""总部页的新增编辑：字段 / 分支等级 / 兵库增删 —— 规范 §7.4 / §8.1。

实测依据（`e156`）：总部一条 26 个字段，`branch_levels` 是
`{engineering/force_pool/intel/logistics/operations: {level, suppressed}}`，
`force_pool` 的条目 = `{delay, nationality, quantity, spec?|equipment?}`。
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from save_modifier_core import CorePaths, Edit, open_save

from ._fixtures import make_save


class HqTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hq_edits_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()

    def commit(self, edits):
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(edits, catalog=None)
            if not plan.ok:
                return plan, None
            return plan, save.commit(plan)

    def read(self, entry="hqs.yml"):
        import zipfile
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read(entry))

    def hq(self):
        return self.read()[0]


class TestHqField(HqTestBase):
    def test_set_xp(self):
        plan, res = self.commit([Edit.hq_field(5, "xp", 42)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.hq()["xp"], 42)

    def test_set_cp(self):
        plan, res = self.commit([Edit.hq_field(5, "cp", 9)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(self.hq()["cp"], 9)

    def test_cp_above_max_is_warned(self):
        plan, _ = self.commit([Edit.hq_field(5, "cp", 99)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("上限" in w for w in plan.warnings), plan.warnings)

    def test_disallowed_field_is_blocked(self):
        plan, _ = self.commit([Edit.hq_field(5, "branch_levels", {})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("不允许改总部字段" in e for e in plan.errors),
                        plan.errors)

    def test_negative_value_is_blocked(self):
        plan, _ = self.commit([Edit.hq_field(5, "xp", -1)])
        self.assertFalse(plan.ok)

    def test_missing_hq_is_blocked(self):
        plan, _ = self.commit([Edit.hq_field(999, "xp", 1)])
        self.assertFalse(plan.ok)

    def test_only_hqs_yml_changes(self):
        plan, res = self.commit([Edit.hq_field(5, "xp", 42)])
        self.assertEqual(res.changed, ["hqs.yml"])


class TestHqBranchLevel(HqTestBase):
    def test_set_level(self):
        plan, res = self.commit([Edit.hq_branch_level(5, "engineering", 3)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.hq()["branch_levels"]["engineering"]["level"], 3)

    def test_other_branches_untouched(self):
        plan, res = self.commit([Edit.hq_branch_level(5, "engineering", 3)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.hq()["branch_levels"]["force_pool"]["level"], 1)

    def test_set_suppressed(self):
        plan, res = self.commit(
            [Edit.hq_branch_level(5, "intel", 2, suppressed=True)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(self.hq()["branch_levels"]["intel"]["suppressed"])

    def test_unknown_branch_is_blocked(self):
        plan, _ = self.commit([Edit.hq_branch_level(5, "nuclear", 1)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("未知的分支" in e for e in plan.errors), plan.errors)

    def test_negative_level_is_blocked(self):
        plan, _ = self.commit([Edit.hq_branch_level(5, "intel", -1)])
        self.assertFalse(plan.ok)

    def test_downgrade_warns(self):
        """降级要二次确认 ⇒ 至少要有提醒。"""
        plan, _ = self.commit([Edit.hq_branch_level(5, "force_pool", 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("降级" in w for w in plan.warnings), plan.warnings)


class TestHqForcePoolAddRemove(HqTestBase):
    def test_add_entry(self):
        plan, res = self.commit([Edit.hq_force_pool_add(5, {
            "delay": 0, "nationality": "german", "quantity": 6,
            "equipment": "infantry"})])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        pool = self.hq()["force_pool"]
        self.assertEqual(len(pool), 3)
        self.assertEqual(pool[2]["quantity"], 6)
        self.assertEqual(pool[2]["nationality"], "german")

    def test_add_at_index(self):
        plan, res = self.commit([Edit.hq_force_pool_add(5, {
            "delay": 0, "nationality": "german", "quantity": 1,
            "equipment": "armor"}, index=0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(self.hq()["force_pool"][0]["equipment"], "armor")

    def test_spec_and_equipment_exclusive(self):
        plan, _ = self.commit([Edit.hq_force_pool_add(5, {
            "delay": 0, "nationality": "german", "quantity": 1,
            "spec": "ger_arty_40", "equipment": "armor"})])
        self.assertFalse(plan.ok)

    def test_neither_spec_nor_equipment_is_blocked(self):
        plan, _ = self.commit([Edit.hq_force_pool_add(5, {
            "delay": 0, "nationality": "german", "quantity": 1})])
        self.assertFalse(plan.ok)

    def test_negative_quantity_is_blocked(self):
        plan, _ = self.commit([Edit.hq_force_pool_add(5, {
            "delay": 0, "nationality": "german", "quantity": -1,
            "equipment": "infantry"})])
        self.assertFalse(plan.ok)

    def test_remove_entry(self):
        plan, res = self.commit([Edit.hq_force_pool_remove(5, 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        pool = self.hq()["force_pool"]
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["spec"], "ger_arty_40")

    def test_remove_bad_index(self):
        plan, _ = self.commit([Edit.hq_force_pool_remove(5, 99)])
        self.assertFalse(plan.ok)


if __name__ == "__main__":
    unittest.main()
