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

from ._fixtures import make_save


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
        """单位 1 已有 idx=0 的特种 ⇒ 新增应占 idx=1。"""
        plan, res = self.commit([Edit.unit_spec_add(1, "ger_arty_40")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            units = yaml.safe_load(zf.read("units.yml"))
        specs = units[0]["specs"]
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[1]["idx"], 1)
        self.assertEqual(specs[1]["type"], "ger_arty_40")
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


if __name__ == "__main__":
    unittest.main()
