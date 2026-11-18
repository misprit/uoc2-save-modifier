"""总部页的新增编辑：字段 / 分支等级 / 技能专精 / 兵库增删 —— 规范 §7.4 / §8.1。

实测依据（`e156`）：总部一条 26 个字段，`branch_levels` 是
`{engineering/force_pool/intel/logistics/operations: {level, suppressed}}`，
`force_pool` 的条目 = `{delay, nationality, quantity, spec?|equipment?}`。

实测依据（`e165`，U12）：总部还有一棵**技能树** `branches`
`{分支: [{action, cost, level, sp_avail, sp_used}]}` ——
`level` 是**级别 tier**（游戏里矩阵的列），`sp_used` 是**已专精次数 = 技能等级**，
`sp_avail` 是还能再专精几次（≤2）；专精 = 该技能发动时 **CP 消耗 −1**
⇒ 存档里的 `cost` 存的是**已扣减**的值（原始 CP = `cost + sp_used`）。
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


class TestHqBranchSp(HqTestBase):
    """技能专精（`branches[].sp_used`）—— 规范 §7.4 / §8.1。

    实测依据（`e165`）：
    * 一条技能 = `{action, cost, level, sp_avail, sp_used}`；
    * `level` 是**级别 tier**（矩阵的列），不是分支等级；
    * `sp_used` = **已专精次数 = 技能等级**，`sp_avail` = 还能再专精几次（≤ 2）；
    * 专精效果 = 该技能发动时 **CP 消耗 −1** ⇒ 存档里 `cost` 存的是**已扣减**的值，
      原始 CP = `cost + sp_used` ⇒ 改 `sp_used` 必须同步改 `cost`。
    """

    def node(self, branch, action):
        for it in self.hq()["branches"][branch]:
            if it["action"] == action:
                return it
        raise AssertionError("fixture 里没有 %s/%s" % (branch, action))

    # ---------- 正常写入 ----------
    def test_specialize_once(self):
        plan, res = self.commit(
            [Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 1)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        n = self.node("engineering", "bridge_destroy")
        self.assertEqual(n["sp_used"], 1)

    def test_cost_is_synced_down(self):
        """专精 1 次 ⇒ CP 消耗 2 → 1。"""
        self.commit([Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 1)])
        self.assertEqual(self.node("engineering", "bridge_destroy")["cost"], 1)

    def test_cost_is_synced_up_when_undoing(self):
        """bridge_destroy 原始 CP = cost(2) + sp_used(0) = 2 ⇒ 取消专精回到 2。"""
        self.commit([Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 1)])
        self.commit([Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 0)])
        n = self.node("engineering", "bridge_destroy")
        self.assertEqual(n["sp_used"], 0)
        self.assertEqual(n["cost"], 2)

    def test_specialize_to_max(self):
        """bridge_create：sp_avail=2 ⇒ 可以专精到 2，CP 3 → 1。"""
        plan, res = self.commit(
            [Edit.hq_branch_sp(5, "engineering", "bridge_create", 2)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        n = self.node("engineering", "bridge_create")
        self.assertEqual(n["sp_used"], 2)
        self.assertEqual(n["cost"], 1)

    def test_existing_specialization_keeps_cost_consistent(self):
        """bridge_repair 存档里已经专精 1 次（cost 2 = 原始 3 − 1）。

        再专精到 2 ⇒ cost 1；退到 0 ⇒ cost 3（原始值）。
        """
        self.assertEqual(self.node("engineering", "bridge_repair")["cost"], 2)
        self.commit([Edit.hq_branch_sp(5, "engineering", "bridge_repair", 2)])
        self.assertEqual(self.node("engineering", "bridge_repair")["cost"], 1)
        self.commit([Edit.hq_branch_sp(5, "engineering", "bridge_repair", 0)])
        n = self.node("engineering", "bridge_repair")
        self.assertEqual(n["cost"], 3)
        self.assertEqual(n["sp_used"], 0)

    def test_summary_mentions_skill(self):
        plan, _ = self.commit(
            [Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 1)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("bridge_destroy" in s for s in plan.notes), plan.notes)

    def test_only_hqs_yml_changes(self):
        plan, res = self.commit(
            [Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 1)])
        self.assertEqual(res.changed, ["hqs.yml"])

    def test_other_skills_untouched(self):
        self.commit([Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 1)])
        self.assertEqual(self.node("engineering", "bridge_repair")["sp_used"], 1)
        self.assertEqual(self.node("operations", "pindown")["sp_used"], 0)

    # ---------- 边界 ----------
    def test_over_limit_is_blocked(self):
        plan, _ = self.commit(
            [Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 2)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("最多能专精" in e for e in plan.errors), plan.errors)

    def test_negative_is_blocked(self):
        plan, _ = self.commit(
            [Edit.hq_branch_sp(5, "engineering", "bridge_destroy", -1)])
        self.assertFalse(plan.ok)

    def test_unknown_branch_is_blocked(self):
        plan, _ = self.commit(
            [Edit.hq_branch_sp(5, "nuclear", "bridge_destroy", 1)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("未知的分支" in e for e in plan.errors), plan.errors)

    def test_unknown_action_is_blocked(self):
        plan, _ = self.commit(
            [Edit.hq_branch_sp(5, "engineering", "nuke", 1)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("没有技能" in e for e in plan.errors), plan.errors)

    def test_missing_hq_is_blocked(self):
        plan, _ = self.commit(
            [Edit.hq_branch_sp(999, "engineering", "bridge_destroy", 1)])
        self.assertFalse(plan.ok)

    def test_force_pool_action_has_no_sp_points(self):
        """兵库分支的动作 sp_avail=null ⇒ 不能专精（游戏里也不画小点）。"""
        plan, _ = self.commit([Edit.hq_branch_sp(5, "force_pool", "reorg", 1)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("没有技能点" in e for e in plan.errors), plan.errors)

    def test_motor_pool_has_no_sp_points(self):
        plan, _ = self.commit([Edit.hq_branch_sp(5, "logistics", "motor_pool", 1)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("没有技能点" in e for e in plan.errors), plan.errors)

    def test_intel_branch_has_no_skills(self):
        """情报分支在存档里恒为空列表（e165）⇒ 只能报错，不能凭空造技能。"""
        plan, _ = self.commit(
            [Edit.hq_branch_sp(5, "intel", "recon_in_force", 1)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("没有技能" in e for e in plan.errors), plan.errors)

    def test_hq_without_branches_is_blocked(self):
        """老存档可能没有 branches ⇒ 明确报错，不静默新建。"""
        from ._fixtures import dump
        tmp = Path(tempfile.mkdtemp(prefix="hq_nobranch_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = make_save(tmp / "s.usg", extra_entries={
            "hqs.yml": dump([{"id": 5, "name_brief": "id_hq_5_brief"}])})
        with open_save(str(p), self.paths) as save:
            plan = save.plan_edit(
                [Edit.hq_branch_sp(5, "engineering", "bridge_destroy", 1)],
                catalog=None)
        self.assertFalse(plan.ok)
        self.assertTrue(any("branches" in e for e in plan.errors), plan.errors)


class TestHqViewBranches(unittest.TestCase):
    """`HqView.branches` / `HqView.branch_tiers`（GUI 画矩阵直接用）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="hq_view_"))
        cls.path = make_save(cls.tmp / "s.usg")
        cls.paths = CorePaths.discover()
        with open_save(str(cls.path), cls.paths) as save:
            cls.hq = save.view().hqs[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_branches_exposed(self):
        self.assertIsInstance(self.hq.branches, dict)
        self.assertIn("engineering", self.hq.branches)
        self.assertEqual(self.hq.branches["intel"], [])

    def test_branch_tiers_grouped_by_tier(self):
        tiers = self.hq.branch_tiers
        self.assertEqual(sorted(tiers["engineering"]), [1, 2, 3])
        acts = {it["action"] for it in tiers["engineering"][1]}
        self.assertEqual(acts, {"bridge_repair", "river_crossing", "entrenchment"})

    def test_branch_tiers_empty_for_intel(self):
        self.assertEqual(self.hq.branch_tiers.get("intel", {}), {})

    def test_tier_is_not_branch_level(self):
        """`level`(tier) 与 `branch_levels[分支]['level']` 不是一回事。"""
        self.assertEqual(self.hq.branch_levels["engineering"]["level"], 1)
        self.assertEqual(
            sorted(self.hq.branch_tiers["engineering"]), [1, 2, 3])

    def test_branch_tiers_missing_when_no_branches(self):
        self.assertEqual(self.hq.branch_tiers.get("nosuch", {}), {})


if __name__ == "__main__":
    unittest.main()
