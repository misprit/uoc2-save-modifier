"""S8：卡牌（cards.yml）与商店（store.yml）。

**验收口径**（规范 §6.3、§4.6、§4.6.1、§10 第 9/12/15/34/37/48 条）：

* `price: 0` = **免费商品**，不是下架；
* `quantity: 0` = **非法值**，必须被拦 —— 游戏没有「售罄」标记，
  买完是**把条目删掉**，所以「下架」的正确做法是**删条目**；
* 商店的顶层键**只能用存档已有的战线键**（存档的键是游戏包 `fronts/` 的子集
  = 当前已激活战线），**不要凭空新建**；
* `nationality` 是**国籍 id**，不是阵营；
* 卡牌类型必须在游戏包的 39 个里；带单位的卡（`has_unit: true`）
  必须填 `unit_id`，且该 id 要在战役名册里。
"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save


class CardStoreTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="card_store_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def open(self):
        return open_save(str(self.save_path), self.paths)

    def commit(self, edits):
        with self.open() as save:
            p = save.plan_edit(edits, catalog=self.catalog)
            if not p.ok:
                return p, None
            return p, save.commit(p)

    def read(self, entry):
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read(entry))


class TestStorePriceAndQuantity(CardStoreTestBase):
    def test_set_price(self):
        plan, res = self.commit([Edit.store_set("south", 0, "price", 3)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        store = self.read("store.yml")
        self.assertEqual(store["south"][0]["price"], 3)
        self.assertEqual(store["south"][0]["quantity"], 20)   # 其余不动

    def test_price_zero_means_free_not_sold_out(self):
        plan, res = self.commit([Edit.store_set("south", 0, "price", 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        store = self.read("store.yml")
        self.assertEqual(store["south"][0]["price"], 0)
        self.assertTrue(any("免费" in w for w in plan.warnings), plan.warnings)

    def test_quantity_zero_is_blocked(self):
        """`quantity: 0` 是游戏从不产生的非法状态。"""
        plan, _ = self.commit([Edit.store_set("south", 0, "quantity", 0)])
        self.assertFalse(plan.ok)
        self.assertIn("删除该条目", plan.errors[0])

    def test_negative_quantity_blocked(self):
        plan, _ = self.commit([Edit.store_set("south", 0, "quantity", -5)])
        self.assertFalse(plan.ok)

    def test_set_quantity_upwards(self):
        plan, res = self.commit([Edit.store_set("south", 0, "quantity", 99)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.read("store.yml")["south"][0]["quantity"], 99)

    def test_cannot_create_new_front(self):
        """存档的键是游戏包 fronts/ 的子集 —— 不要凭空新建战线键。"""
        plan, _ = self.commit([Edit.store_set("north", 0, "price", 1)])
        self.assertFalse(plan.ok)
        self.assertIn("战线", plan.errors[0])

    def test_nationality_faction_hint(self):
        plan, _ = self.commit([Edit.store_set("south", 0, "price", 1)])
        self.assertTrue(plan.ok, plan.errors)

    def test_only_store_yml_changes(self):
        plan, res = self.commit([Edit.store_set("south", 0, "price", 3)])
        self.assertEqual(res.changed, ["store.yml"])


class TestStoreRemove(CardStoreTestBase):
    def test_remove_entry_is_the_way_to_delist(self):
        """下架商品 = 删条目。"""
        plan, res = self.commit([Edit.store_remove("south", 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        store = self.read("store.yml")
        self.assertEqual(len(store["south"]), 1)
        self.assertEqual(store["south"][0]["spec"], "ger_arty_40")

    def test_remove_bad_index(self):
        plan, _ = self.commit([Edit.store_remove("south", 99)])
        self.assertFalse(plan.ok)


class TestCards(CardStoreTestBase):
    def setUp(self):
        super().setUp()
        if not self.catalog.has_card_type("air_attack_allies"):
            self.skipTest("本机没有游戏包")

    def test_add_card(self):
        plan, res = self.commit([Edit.card_add("air_attack_allies")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        cards = self.read("cards.yml")
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[1]["card_type"], "air_attack_allies")
        self.assertEqual(cards[1]["position"], 2)     # 现有最大 +1
        self.assertFalse(cards[1]["used"])

    def test_add_card_with_explicit_position(self):
        plan, res = self.commit([Edit.card_add("air_attack_allies", position=7)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        cards = self.read("cards.yml")
        self.assertEqual(cards[1]["position"], 7)

    def test_duplicate_position_is_blocked(self):
        plan, _ = self.commit([Edit.card_add("air_attack_allies", position=1)])
        self.assertFalse(plan.ok)

    def test_unknown_card_type_is_blocked(self):
        plan, _ = self.commit([Edit.card_add("not_a_real_card")])
        self.assertFalse(plan.ok)
        self.assertIn("不存在", plan.errors[0])

    def test_card_with_unit_requires_unit_id(self):
        """带单位的卡必须指定 unit_id。"""
        if not self.catalog.has_card_type("tactical_naval_assault_us"):
            self.skipTest("本机没有这个卡牌类型")
        plan, _ = self.commit([Edit.card_add("tactical_naval_assault_us")])
        self.assertFalse(plan.ok)
        self.assertIn("unit_id", plan.errors[0])

    def test_card_with_unit_accepts_roster_unit(self):
        if not self.catalog.has_card_type("tactical_naval_assault_us"):
            self.skipTest("本机没有这个卡牌类型")
        plan, res = self.commit(
            [Edit.card_add("tactical_naval_assault_us", unit_id=1)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        cards = self.read("cards.yml")
        self.assertEqual(cards[1]["unit_id"], 1)

    def test_card_with_unknown_unit_is_blocked(self):
        if not self.catalog.has_card_type("tactical_naval_assault_us"):
            self.skipTest("本机没有这个卡牌类型")
        plan, _ = self.commit(
            [Edit.card_add("tactical_naval_assault_us", unit_id=9999)])
        self.assertFalse(plan.ok)

    def test_remove_card(self):
        plan, res = self.commit([Edit.card_remove(1)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(len(self.read("cards.yml")), 0)

    def test_remove_missing_card(self):
        plan, _ = self.commit([Edit.card_remove(99)])
        self.assertFalse(plan.ok)

    def test_only_cards_yml_changes(self):
        plan, res = self.commit([Edit.card_add("air_attack_allies")])
        self.assertEqual(res.changed, ["cards.yml"])


class TestRestoreHand(CardStoreTestBase):
    def test_restore_hand_from_checkpoint(self):
        """恢复上次会议的牌局：读 L2 的 card_store → 写 L1（§6.3）。"""
        plan, res = self.commit([Edit.hand_restore()])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        main = self.read("main.yml")
        self.assertEqual(len(main["card_store"]), 2)
        self.assertEqual(main["card_store"][0]["card_type"], "air_attack_allies")
        # 检查点本身**不能被改**（只读）—— 恢复只写根 main.yml
        self.assertEqual(len(self.read("last_conference/main.yml")["card_store"]), 2)

    def test_restore_hand_requires_checkpoint(self):
        """没有 `last_conference/` 就不能恢复 —— 能力位要挡住。"""
        import zipfile as zf
        # 造一个没有检查点的存档
        p = make_save(self.tmp / "nocp.usg")
        with zf.ZipFile(p) as z:
            names = [n for n in z.namelist() if not n.startswith("last_")]
            data = {n: z.read(n) for n in names}
        with zf.ZipFile(p, "w") as z:
            for n, d in data.items():
                zi = zf.ZipInfo(n, date_time=(2026, 1, 2, 3, 4, 6))
                z.writestr(zi, d)
        with open_save(str(p), self.paths) as save:
            plan = save.plan_edit([Edit.hand_restore()], catalog=self.catalog)
        self.assertFalse(plan.ok)
        self.assertIn("检查点", plan.errors[0])


if __name__ == "__main__":
    unittest.main()
