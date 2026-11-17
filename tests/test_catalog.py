"""S4：游戏包目录与类型表。

验收口径（规范 §5.3、§3.2b、§9.1.5）：

* `unit_types` 627 个、`specialists` 375 个、`cards` 39 个、`hq_types` 213 个、
  `generals` 304 个、战役包 15 个；
* **`max_st` 分布 = {3:4, 4:9, 5:83, 6:108, 7:245, 无:178}**
  —— 不是"轴心 7 / 盟军 6"那种硬编码近似；
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
        """规范 §5.3 的实测分布 —— 一字不差才算对。"""
        dist = collections.Counter()
        for name in self.cat.unit_type_names():
            ut = self.cat.unit_type(name)
            dist[ut.max_st if ut else "missing"] += 1
        self.assertEqual(dist, collections.Counter(
            {3: 4, 4: 9, 5: 83, 6: 108, 7: 245, None: 178}))

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

    def test_known_types(self):
        self.assertEqual(self.cat.max_st("us_inf_42"), 6)
        self.assertEqual(self.cat.max_st("ger_inf_39"), 7)
        self.assertEqual(self.cat.spec_cap("ger_inf_39"), 2)

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


class TestLegacyUnitsUseCatalog(unittest.TestCase):
    """旧 REPL 工具的 `units.py` 也要用真实的 max_st —— 不再有硬编码上限。"""

    def test_hardcoded_cap_is_gone(self):
        import save_modifier.units as U
        self.assertFalse(hasattr(U, "AXIS_STEP_CAP"),
                         "硬编码的战力上限应该已经被类型目录取代")

    def _make_session(self, unit_yaml: str):
        import tempfile
        import zipfile
        from pathlib import Path
        import yaml as _yaml
        from save_modifier.config import Config
        from save_modifier.savefile import SaveFile, SaveSession

        tmp = Path(tempfile.mkdtemp(prefix="legacy_units_"))
        self.addCleanup(__import__("shutil").rmtree, tmp, ignore_errors=True)
        cfg_path = tmp / "config.yml"
        cfg_path.write_text(_yaml.safe_dump({
            "uoc2_appdata": "%LOCALAPPDATA%/.uoc2",
            "state_dir": str(tmp),
            "uoc2_orig_packages_path": "",
            "setup_done": True,
        }, allow_unicode=True), encoding="utf-8")
        cfg = Config.load(cfg_path)

        save_path = tmp / "s.usg"
        with zipfile.ZipFile(save_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zi = zipfile.ZipInfo("units.yml", date_time=(2026, 1, 1, 0, 0, 0))
            zf.writestr(zi, unit_yaml.encode("utf-8"))
        return SaveSession(cfg, SaveFile(save_path, "campaign"))

    def test_set_strength_uses_real_max_st(self):
        import io
        from contextlib import redirect_stdout
        from save_modifier.units import UnitList

        cat = Catalog()
        if not cat.has_unit_type("us_inf_42"):
            self.skipTest("本机没有游戏包，跳过")
        sess = self._make_session(
            "- {id: 1, type: us_inf_42, xp: 10, act_st: 1, sup_st: 0}\n")
        ul = UnitList(sess, catalog=cat)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ul.set_strength(1, active=99)
        out = buf.getvalue()
        self.assertIn("6", out)               # us_inf_42 的 max_st = 6
        self.assertNotIn("7", out.split("超过")[0].split("合计")[-1][:10])

    def test_spec_cap_uses_real_max_spec(self):
        """ger_inf_39 的 max_spec = 2 ⇒ 挂第三个特种应当被拒。"""
        import io
        from contextlib import redirect_stdout
        from save_modifier.units import UnitList

        cat = Catalog()
        if not cat.has_unit_type("ger_inf_39"):
            self.skipTest("本机没有游戏包，跳过")
        sess = self._make_session(
            "- {id: 1, type: ger_inf_39, xp: 10, act_st: 1, sup_st: 0, specs: []}\n")
        ul = UnitList(sess, catalog=cat)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ul.add_spec(1, "s1")
            ul.add_spec(1, "s2")
            ul.add_spec(1, "s3")     # 应当被拒
        self.assertIn("特种已满（2）", buf.getvalue())


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
