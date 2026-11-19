"""S7：特种兵（specs）+ 总部兵库（force_pool）。

**验收口径**（规范 §6.2b、§5.3、§4.2）：

* 特种兵 `type` **必须在游戏包的 375 个 specialists 里**，否则被拦；
* 能挂几个特种 = 该单位类型的 `min(3, max_spec or 3)` —— 不是写死的 3；
* 槽位 `idx` 填空闲位（0..2）；
* 总部兵库 `force_pool[].quantity` **可改**（L1，游戏任何重组路径都不重算它）；
* 兵库条目里 `spec` 与 `equipment` **二选一**。
"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import dump, make_save


class SpecPoolTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="spec_pool_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def open(self):
        return open_save(str(self.save_path), self.paths)

    def plan(self, edits, catalog=True):
        with self.open() as save:
            return save.plan_edit(edits,
                                  catalog=self.catalog if catalog else None)

    def commit(self, edits, catalog=True):
        with self.open() as save:
            p = save.plan_edit(edits,
                               catalog=self.catalog if catalog else None)
            if not p.ok:
                return p, None
            return p, save.commit(p)


class TestAddSpec(SpecPoolTestBase):
    def setUp(self):
        super().setUp()
        if not self.catalog.has_spec_type("ger_arty_40"):
            self.skipTest("本机没有游戏包")

    def test_add_spec_uses_free_slot(self):
        """单位 1 已有 idx=0 的特种 ⇒ 新增应占 idx=1。

        ⚠ **U49**：新增的特种必须是**合法挂载**（阵营相同 + 国籍相同或父国籍匹配）
        ⇒ 这里用美籍的 `us_arty_42`（单位 1 是 `us_inf_42`）。
        单位 1 已有的 `ger_arty_40` 是**历史遗留的非法挂载** ——
        核心库**只读保留**（不主动改）、仍可卸载 ⇒ 见 `TestMountLegality`。
        """
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        specs = units[0]["specs"]
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[1]["idx"], 1)
        self.assertEqual(specs[1]["type"], "us_arty_42")
        self.assertTrue(specs[1]["active"])
        self.assertFalse(specs[1]["captured"])

    def test_unknown_spec_type_is_blocked(self):
        plan, _ = self.commit([Edit.unit_spec_add(1, "not_a_real_specialist")])
        self.assertFalse(plan.ok)
        self.assertIn("不存在", plan.errors[0])

    def test_spec_cap_uses_type_max_spec(self):
        """ger_inf_39 的 max_spec=2 ⇒ 挂满 2 个后第三个被拒。"""
        if not self.catalog.has_unit_type("ger_inf_39"):
            self.skipTest("本机没有游戏包")
        self.assertEqual(self.catalog.spec_cap("ger_inf_39"), 2)
        plan, res = self.commit([Edit.unit_spec_add(2, "ger_arty_40")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        plan2, res2 = self.commit([Edit.unit_spec_add(2, "ger_arty_40")])
        self.assertTrue(plan2.ok, plan2.errors)      # 第 2 个还在上限内
        self.assertTrue(res2.ok, res2.errors)
        plan3, _ = self.commit([Edit.unit_spec_add(2, "ger_arty_40")])
        self.assertFalse(plan3.ok, "第 3 个超过类型的 max_spec，应当被拒")
        self.assertIn("最多挂 2 个", plan3.errors[0])

    def test_no_catalog_gives_clear_error(self):
        """没有游戏包时不能瞎猜类型 —— 报错要说清楚。"""
        plan, _ = self.commit([Edit.unit_spec_add(1, "ger_arty_40")],
                              catalog=False)
        self.assertFalse(plan.ok)
        self.assertIn("游戏包", plan.errors[0])

    def test_add_spec_to_unknown_unit(self):
        plan, _ = self.commit([Edit.unit_spec_add(999, "ger_arty_40")])
        self.assertFalse(plan.ok)


class TestMountLegality(SpecPoolTestBase):
    """U49：**挂载合法性** —— 阵营相同 + 国籍相同或**单位国籍的 parent_nationality** 匹配。

    游戏自己的判定（`uoc2/state/entities/unit.pyc::_can_add_specialist_no_len`，
    `e162` 字节码 / 规范 §7.3.2）**单向**：
    **罗马尼亚人能用德军装备，德军用不了罗马尼亚装备**。

    ⇒ 核心库 `_unit_spec_add` 必须**硬拦**（前端曾经把方向写反了，
    德国单位能挂罗马尼亚装备）。
    """

    def setUp(self):
        super().setUp()
        for t in ("us_inf_42", "ger_inf_39", "rom_arm_41"):
            if not self.catalog.has_unit_type(t):
                self.skipTest("本机没有游戏包")
        for t in ("ger_arty_40", "us_arty_42", "rom_armx_41"):
            if not self.catalog.has_spec_type(t):
                self.skipTest("本机没有游戏包")

    def _save_with_romanian_unit(self):
        """造一个含**罗马尼亚单位**（id=3，`rom_arm_41`）的存档。

        罗马尼亚的 `parent_nationality` 是 `german` ⇒ 它**能**挂德军特种兵。
        """
        units = [
            {"id": 1, "type": "us_inf_42", "name_brief": "id_us_inf_42_brief",
             "name_full": None, "hq_id": 5, "xp": 10, "act_st": 4, "sup_st": 0,
             "losses": 0, "ap": 1, "mp": 3, "entr": 0, "supply": 3,
             "retreated": False, "hidden_defense": False,
             "specs": [], "supplied_by": 0, "uv": [12, 34]},
            {"id": 2, "type": "ger_inf_39", "name_brief": "我的警卫队",
             "name_full": None, "hq_id": 5, "xp": 50, "act_st": 6, "sup_st": 1,
             "losses": 2, "ap": 2, "mp": 2, "entr": 1, "supply": 2,
             "retreated": False, "hidden_defense": False,
             "specs": [], "supplied_by": 1, "uv": [13, 35]},
            {"id": 3, "type": "rom_arm_41", "name_brief": "id_rom_arm_41_brief",
             "name_full": None, "hq_id": 5, "xp": 0, "act_st": 4, "sup_st": 0,
             "losses": 0, "ap": 1, "mp": 3, "entr": 0, "supply": 3,
             "retreated": False, "hidden_defense": False,
             "specs": [], "supplied_by": 0, "uv": [14, 36]},
        ]
        make_save(self.save_path, extra_entries={"units.yml": dump(units)})

    def test_cross_faction_mount_is_blocked(self):
        """德军装备挂到美国连队上 ⇒ 拒（阵营不同）。"""
        plan, _ = self.commit([Edit.unit_spec_add(1, "ger_arty_40")])
        self.assertFalse(plan.ok)
        self.assertIn("不能挂到", plan.errors[0])
        self.assertIn("阵营不同", plan.errors[0])

    def test_other_nationality_mount_is_blocked(self):
        """德国单位挂罗马尼亚装备 ⇒ 拒（德国没有父国籍，反向不成立）。"""
        plan, _ = self.commit([Edit.unit_spec_add(2, "rom_armx_41")])
        self.assertFalse(plan.ok)
        self.assertIn("不能挂到", plan.errors[0])
        self.assertIn("没有父国籍", plan.errors[0])

    def test_parent_nationality_mount_is_allowed(self):
        """**罗马尼亚单位可以挂德军装备**（罗马尼亚的父国籍是德国）。"""
        self._save_with_romanian_unit()
        plan, res = self.commit([Edit.unit_spec_add(3, "ger_arty_40")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        rom = next(u for u in units if u["id"] == 3)
        self.assertEqual([s["type"] for s in rom["specs"]], ["ger_arty_40"])

    def test_parent_nationality_is_one_way(self):
        """**反向不行** —— 德国单位挂不了罗马尼亚装备。"""
        self._save_with_romanian_unit()
        plan, _ = self.commit([Edit.unit_spec_add(2, "rom_armx_41")])
        self.assertFalse(plan.ok)

    def test_existing_illegal_mount_is_preserved_and_removable(self):
        """历史遗留的非法挂载：**只读保留**（不主动改），但**仍可卸载**。"""
        with zipfile.ZipFile(self.save_path) as zf:
            before = yaml.safe_load(zf.read("units.yml"))
        self.assertEqual(before[0]["specs"][0]["type"], "ger_arty_40")
        plan, res = self.commit([Edit.unit_spec_remove(1, "ger_arty_40")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            after = yaml.safe_load(zf.read("units.yml"))
        self.assertEqual(after[0]["specs"], [])


class TestRemoveSpec(SpecPoolTestBase):
    def test_remove_spec(self):
        plan, res = self.commit([Edit.unit_spec_remove(1, "ger_arty_40")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        self.assertEqual(units[0]["specs"], [])

    def test_remove_spec_by_idx(self):
        plan, res = self.commit([Edit.unit_spec_remove(1, "ger_arty_40", idx=0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)

    def test_remove_missing_spec_is_reported(self):
        plan, _ = self.commit([Edit.unit_spec_remove(1, "not_there")])
        self.assertFalse(plan.ok)
        self.assertIn("没有", plan.errors[0])


class TestForcePool(SpecPoolTestBase):
    def test_change_force_pool_quantity(self):
        """总部兵库是 L1 可写字段 —— 游戏任何重组路径都不重算它。"""
        plan, res = self.commit([Edit.hq_force_pool(5, 0, 500)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        self.assertEqual(hqs[0]["force_pool"][0]["quantity"], 500)
        # 其余字段原样保留
        self.assertEqual(hqs[0]["force_pool"][0]["equipment"], "infantry")
        self.assertEqual(hqs[0]["force_pool"][0]["nationality"], "us")
        self.assertEqual(hqs[0]["force_pool"][0]["delay"], 0)

    def test_change_spec_entry_quantity(self):
        plan, res = self.commit([Edit.hq_force_pool(5, 1, 7)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        self.assertEqual(hqs[0]["force_pool"][1]["quantity"], 7)
        self.assertEqual(hqs[0]["force_pool"][1]["spec"], "ger_arty_40")

    def test_negative_quantity_is_blocked(self):
        plan, _ = self.commit([Edit.hq_force_pool(5, 0, -1)])
        self.assertFalse(plan.ok)

    def test_bad_index_is_reported(self):
        plan, _ = self.commit([Edit.hq_force_pool(5, 99, 10)])
        self.assertFalse(plan.ok)

    def test_unknown_hq_is_reported(self):
        plan, _ = self.commit([Edit.hq_force_pool(999, 0, 10)])
        self.assertFalse(plan.ok)

    def test_only_hqs_yml_changes(self):
        plan, res = self.commit([Edit.hq_force_pool(5, 0, 500)])
        self.assertEqual(res.changed, ["hqs.yml"])


class TestForcePoolAddNationality(SpecPoolTestBase):
    """U22：兵库加一条时，**国籍跟着特种兵类型走**。

    取证：真实存档里 **商店 1043 条 + 兵库 1747 条 spec 条目，
    国籍 100% 等于该特种兵类型自身的 `nationality`，0 条例外**
    ⇒ 给了 `spec` 就自动填国籍；填错了要警告。
    """

    def setUp(self):
        super().setUp()
        if not self.catalog.has_spec_type("ger_arty_40"):
            self.skipTest("本机没有游戏包")
        self.spec_nat = self.catalog.spec_type("ger_arty_40").nationality

    def _pool(self):
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        return hqs[0]["force_pool"]

    def test_nationality_is_filled_from_spec_type(self):
        """不传 nationality ⇒ 自动填成该特种兵自己的国籍（原来填的是空串）。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            5, {"quantity": 2, "spec": "ger_arty_40", "delay": 1})])
        self.assertTrue(res.ok, res.errors)
        pool = self._pool()
        self.assertEqual(pool[-1]["spec"], "ger_arty_40")
        self.assertEqual(pool[-1]["nationality"], self.spec_nat)
        self.assertTrue(self.spec_nat, "游戏包里这个特种兵应当有国籍")

    def test_mismatched_nationality_warns(self):
        """显式填了别的国籍 ⇒ 警告（不硬拦，但要说清游戏自己的规矩）。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            5, {"quantity": 2, "spec": "ger_arty_40", "nationality": "us",
                "delay": 1})])
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("国籍" in w for w in plan.warnings), plan.warnings)
        self.assertEqual(self._pool()[-1]["nationality"], "us")

    def test_equipment_entry_keeps_its_nationality(self):
        """装备条目的国籍是独立组合（实测 20+ 种）⇒ 原样保留，不被覆盖。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            5, {"quantity": 5, "equipment": "armor", "nationality": "soviet"})])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self._pool()[-1]["nationality"], "soviet")

    def test_equipment_entry_without_nationality_warns(self):
        """装备条目没给国籍 ⇒ 仍是空串，但必须警告（游戏读不出来）。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            5, {"quantity": 5, "equipment": "armor"})])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self._pool()[-1]["nationality"], "")
        self.assertTrue(any("国籍" in w for w in plan.warnings), plan.warnings)


class TestForcePoolDuplicate(SpecPoolTestBase):
    """U23：总部兵库的**重复条目**规则（用户口径 2026-11-18）。

    * **每个总部的兵库独立** —— 判重范围 = 单个 hq 的 `force_pool`。
    * **同身份 + 同延迟**不许并存（「肯定不允许同时出现两个 0 延迟的同样特种兵」）；
      **延迟不同可以共存**（X 回合延迟 = 那个部队等几个回合才能部署，是合法机制）。
    """

    def setUp(self):
        super().setUp()
        if not self.catalog.has_spec_type("ger_arty_40"):
            self.skipTest("本机没有游戏包")

    def _pool(self, hq_id=5):
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        for hq in hqs:
            if hq.get("id") == hq_id:
                return hq["force_pool"]
        return None

    def test_duplicate_in_same_hq_is_rejected(self):
        """同一个总部里已经有同样一条（0 延迟）⇒ 不许再加。"""
        plan = self.plan([Edit.hq_force_pool_add(
            5, {"quantity": 2, "spec": "ger_arty_40"})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("已经有" in e for e in plan.errors), plan.errors)

    def test_same_spec_with_different_delay_is_allowed(self):
        """**延迟不同可以共存** —— 这是游戏自己的合法机制。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            5, {"quantity": 2, "spec": "ger_arty_40", "delay": 1})])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self._pool()[-1]["delay"], 1)

    def test_same_spec_in_another_hq_is_allowed(self):
        """**每个总部的兵库独立** —— 另一个总部可以随便加。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            6, {"quantity": 2, "spec": "ger_arty_40"})])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self._pool(6)[-1]["spec"], "ger_arty_40")

    def test_different_nationality_is_a_different_entry(self):
        """国籍**算进身份** —— 同样是德国特种兵，`german` 和 `us` 是两样东西。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            5, {"quantity": 2, "spec": "ger_arty_40", "nationality": "us"})])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self._pool()[-1]["nationality"], "us")

    def test_same_spec_different_delay_warns_about_staggering(self):
        """同身份、延迟不同 ⇒ 允许，但要提示「分批上线」的语义。"""
        plan, res = self.commit([Edit.hq_force_pool_add(
            5, {"quantity": 2, "spec": "ger_arty_40", "delay": 2})])
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("分批上线" in w for w in plan.warnings), plan.warnings)

    def test_duplicate_equipment_is_rejected_too(self):
        """装备条目同样按身份判重（身份 = 类别 + 国籍）。"""
        plan = self.plan([Edit.hq_force_pool_add(
            5, {"quantity": 2, "equipment": "infantry", "nationality": "us"})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("已经有" in e for e in plan.errors), plan.errors)


if __name__ == "__main__":
    unittest.main()


# =====================================================================
# U48：同一种特种兵可以挂多个（游戏规则没有「不能重复」这一条）
# =====================================================================


class TestSameSpecialistTwice(SpecPoolTestBase):
    """同一个单位挂**两个同样的**特种兵 —— 规则允许（§7.3.2）。"""

    def test_same_specialist_can_be_mounted_twice(self):
        """挂两个一样的 ⇒ 落盘是两个**独立槽位**。"""
        plan, res = self.commit([Edit.unit_spec_add(2, "ger_arty_40"),
                                 Edit.unit_spec_add(2, "ger_arty_40")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        specs = next(u for u in units if u["id"] == 2)["specs"]
        self.assertEqual(len(specs), 2)
        self.assertTrue(all(s["type"] == "ger_arty_40" for s in specs))
        self.assertEqual(sorted(s["idx"] for s in specs), [0, 1])

    def test_remove_one_of_two_same_specialists(self):
        """按 idx 卸 ⇒ 只卸那一个，另一个还在。"""
        plan, res = self.commit([Edit.unit_spec_add(2, "ger_arty_40"),
                                 Edit.unit_spec_add(2, "ger_arty_40")])
        self.assertTrue(res.ok, res.errors)
        plan2, res2 = self.commit([Edit.unit_spec_remove(2, "ger_arty_40", idx=1)])
        self.assertTrue(plan2.ok, plan2.errors)
        self.assertTrue(res2.ok, res2.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        specs = next(u for u in units if u["id"] == 2)["specs"]
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["idx"], 0)
