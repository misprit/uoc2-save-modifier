"""S4：游戏包目录与类型表。

验收口径（规范 §5.3、§3.2b、§9.1.5）：

* `unit_types` 627 个、`specialists` 375 个、`cards` 39 个、`hq_types` 213 个、
  `generals` 304 个、战役包 15 个；
* **`max_st` 分布 = {3:4, 4:9, 5:83, 6:108, 7:423}**
  —— 不是"轴心 7 / 盟军 6"那种硬编码近似；
  ⚠️ **U60**：类型 yml 里**没写 max_st** 的 178 个类型，游戏按 schema 默认
  **7** 处理（`unit_types.pyc::_unit_type_schema`: `Required('max_st', default=7)`）⇒
  有效分布里 7 = 245（显式）+ 178（兜底）= 423；
* **`max_spec` 分布 = {1:233, 2:314, 3:25, 无:55}**；
* `fronts` 是**每个战役包各有一份**（west → france/italy）；
* **用户包优先**（mod 兼容）；
* **查不到的类型返回 None，不报错、不拦截**（表只做候选，绝不做白名单）。

游戏没装 / DLC 没买时，整组测试自动跳过。
"""

import collections
import unittest

from save_modifier_core import Catalog, CorePaths
from save_modifier_core import catalog as catalog_mod


class TestCatalogCounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = CorePaths.discover()
        cls.cat = Catalog(cls.paths)
        cls.skip = not cls.paths.packages()

    def setUp(self):
        if self.skip:
            self.skipTest("本机没找到游戏包目录，跳过")

    def test_type_counts(self):
        self.assertEqual(len(self.cat.unit_type_names()), 627)
        self.assertEqual(len(self.cat.spec_type_names()), 375)
        self.assertEqual(len(self.cat.card_type_names()), 39)
        self.assertEqual(len(self.cat.hq_type_names()), 213)
        self.assertEqual(len(self.cat.general_names()), 304)

    def test_campaign_count(self):
        self.assertEqual(len(self.cat.campaign_ids()), 15)

    def test_max_st_distribution(self):
        """规范 §5.3 的实测分布 —— 一字不差才算对。

        ⚠️ **U60**：178 个类型的 yml **没写** `max_st` ⇒ 游戏按 schema 默认
        **7** 处理（`unit_types.pyc::_unit_type_schema`:
        `Required('max_st', default=7) : All(int, Range(min=1, max=7))`）
        ⇒ 有效分布里 7 = 245（显式）+ 178（兜底）= 423。"""
        dist = collections.Counter()
        for name in self.cat.unit_type_names():
            ut = self.cat.unit_type(name)
            dist[ut.max_st if ut else "missing"] += 1
        self.assertEqual(dist, collections.Counter(
            {3: 4, 4: 9, 5: 83, 6: 108, 7: 423}))

    def test_max_spec_distribution(self):
        dist = collections.Counter()
        for name in self.cat.unit_type_names():
            ut = self.cat.unit_type(name)
            dist[ut.max_spec if ut else "missing"] += 1
        self.assertEqual(dist, collections.Counter(
            {1: 233, 2: 314, 3: 25, None: 55}))

    def test_spec_cap_formula(self):
        """特种兵上限 = `min(3, max_spec or 3)`。"""
        for name in self.cat.unit_type_names():
            ut = self.cat.unit_type(name)
            expected = min(3, ut.max_spec if ut.max_spec is not None else 3)
            self.assertEqual(ut.spec_cap, expected, name)
            self.assertEqual(self.cat.spec_cap(name), expected, name)

    def test_types_without_max_st_field_use_the_game_default(self):
        """**U60**：类型 yml 缺 `max_st` ⇒ 上限 = 7（游戏 schema 的默认值），
        **不是 None** —— 否则单位显示「上限 —」、血量条没有上限格。

        实测影响面：`Stalingrad.usg` 的 354 个单位里 **266 个（75%）**
        用的是这类类型（U54 当初只统计了 Blitzkrieg，所以漏了）。"""
        for name in ("ger_jag_dlc4", "sov_tank_dlc4", "rom_inf_dlc4",
                     "ger_inf_42", "ita_inf_42", "ger_pz_42"):
            self.assertEqual(self.cat.max_st(name), 7, name)
        # **查不到的类型**仍然是 None（None 只表示「没这个类型」）
        self.assertIsNone(self.cat.max_st("definitely_not_a_type"))

    def test_known_types(self):
        self.assertEqual(self.cat.max_st("us_inf_42"), 6)
        self.assertEqual(self.cat.max_st("ger_inf_39"), 7)
        self.assertEqual(self.cat.spec_cap("ger_inf_39"), 2)

    def test_equipment_exposed(self):
        """`equipment` / `equipment_q` 是类型定义里的字段，必须能读到。

        字节码实证（`hq_ctrl.pyc::_fp_helper`）：阶梯图标名 =
        `'steps/step{}'.format('_' + equipment + '_' + equipment_q if equipment else '')`
        ⇒ GUI 要靠这两个字段选图。
        """
        ut = self.cat.unit_type("us_arm_42")
        self.assertIsNotNone(ut)
        self.assertEqual(ut.equipment, "armor")
        self.assertEqual(ut.equipment_q, 2)

        plain = self.cat.unit_type("us_inf_42")
        self.assertIsNotNone(plain)
        self.assertIsNone(plain.equipment)
        self.assertEqual(plain.equipment_q, 0)

    def test_equipment_distribution(self):
        """base 包 627 个单位类型的 `(equipment, equipment_q)` 组合实测分布。"""
        dist = collections.Counter()
        for name in self.cat.unit_type_names():
            ut = self.cat.unit_type(name)
            dist[(ut.equipment, ut.equipment_q) if ut else ("missing", "missing")] += 1
        self.assertEqual(dist, collections.Counter(
            {(None, 0): 398, ("armor", 2): 135, ("armor", 1): 94}))

    def test_step_icon_rule(self):
        """阶梯图标名：先判 `equipment` 真假，再拼 `equipment_q`。

        * 无装备 → `step`
        * armor + 1 → `step_armor_1`
        * armor + 2 → `step_armor_2`
        """
        self.assertEqual(self.cat.step_icon("us_inf_42"), "step")
        self.assertEqual(self.cat.step_icon("us_arm_42"), "step_armor_2")
        self.assertEqual(self.cat.step_icon("ger_pz_dlc7"), "step_armor_2")

        # 未知类型回落到 step，不抛异常
        self.assertEqual(self.cat.step_icon("definitely_not_a_type"), "step")
        self.assertEqual(self.cat.unit_type("definitely_not_a_type"), None)

    def test_fronts_are_per_campaign(self):
        """fronts 每个战役包各有一份 —— west 有两条，stalingrad 也有自己的两条。"""
        self.assertEqual(self.cat.fronts("west"), ["france", "italy"])
        self.assertEqual(self.cat.fronts("stalingrad"), ["caucasus", "south"])
        self.assertNotEqual(self.cat.fronts("west"), self.cat.fronts("stalingrad"))

    def test_user_packages_come_first(self):
        """mod 优先于原版 —— 只扫游戏包会漏掉 mod 的类型（规范 §9.1.5）。"""
        pkgs = self.paths.packages()
        user = self.paths.user_packages_dir
        if user.is_dir():
            self.assertTrue(str(pkgs[0]).lower().startswith(str(user).lower()))


class TestCatalogUnknownTypes(unittest.TestCase):
    """查不到的类型**不能报错、不能拦截** —— 表只做候选，绝不做白名单。"""

    def setUp(self):
        self.cat = Catalog()

    def test_unknown_unit_type_returns_none(self):
        self.assertIsNone(self.cat.unit_type("definitely_not_a_type"))
        self.assertIsNone(self.cat.max_st("definitely_not_a_type"))
        self.assertEqual(self.cat.spec_cap("definitely_not_a_type"), 3)

    def test_empty_type_name(self):
        self.assertIsNone(self.cat.unit_type(""))
        self.assertIsNone(self.cat.unit_type(None))

    def test_has_helpers(self):
        self.assertFalse(self.cat.has_unit_type("definitely_not_a_type"))
        self.assertFalse(self.cat.has_spec_type("definitely_not_a_spec"))


class TestModuleLevelApi(unittest.TestCase):
    """规范 §0.2 的 `catalog.units()` / `catalog.card_types()` … 形态。"""

    def test_module_functions_exist(self):
        for name in ("units", "hq_types", "card_types", "spec_types",
                     "fronts", "store_defaults", "default"):
            self.assertTrue(hasattr(catalog_mod, name), name)

    def test_default_is_singleton(self):
        self.assertIs(catalog_mod.default(), catalog_mod.default())

    def test_unknown_campaign_fronts_is_empty(self):
        self.assertEqual(catalog_mod.fronts("no_such_campaign"), [])


class TestViewWithCatalog(unittest.TestCase):

    def test_view_fills_limits(self):
        from save_modifier_core import list_saves, open_save
        paths = CorePaths.discover()
        saves = list_saves(paths)
        if not saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        cat = Catalog(paths)
        with open_save(saves[0].save_id, paths) as save:
            v = save.view(catalog=cat)
        typed = [u for u in v.units if u.type]
        if not typed:
            self.skipTest("该存档的单位没有 type 字段")
        for u in typed:
            if cat.has_unit_type(u.type):
                self.assertEqual(u.max_st, cat.max_st(u.type), u.type)
                self.assertEqual(u.max_spec, cat.spec_cap(u.type), u.type)

    def test_view_without_catalog_leaves_limits_empty(self):
        from save_modifier_core import list_saves, open_save
        paths = CorePaths.discover()
        saves = list_saves(paths)
        if not saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        with open_save(saves[0].save_id, paths) as save:
            v = save.view()
        for u in v.units:
            self.assertIsNone(u.max_st)
            self.assertIsNone(u.max_spec)


if __name__ == "__main__":
    unittest.main()
