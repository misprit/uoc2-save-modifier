"""S8：手牌（cards.yml）、卡牌商店货架（main.yml.card_store）与商店（store.yml）。

**验收口径**（规范 §6.3、§4.6、§4.6.1、§7.5、§7.6、§10 第 9/12/15/34/37/48 条）：

* `price: 0` = **免费商品**，不是下架；
* `quantity: 0` = **非法值**，必须被拦 —— 游戏没有「售罄」标记，
  买完是**把条目删掉**，所以「下架」的正确做法是**删条目**；
* 商店的顶层键**只能用存档已有的战线键**（存档的键是游戏包 `fronts/` 的子集
  = 当前已激活战线），**不要凭空新建**；
* `nationality` 是**国籍 id**，不是阵营；
* `store.yml` 是**两层**的：`{战线: {store: [...], elite_store: [...]}}`
  ⇒ 改商品必须带 `sub`（普通 / 精英）；
* 手牌 = 根 `cards.yml`；货架 = 根 `main.yml.card_store` —— **别搞反**；
* 卡牌类型必须在游戏包的 39 个里；带单位的卡（`has_unit: true`）
  的 `unit_id` 必须等于本战役为它登记的**预留 id**，
  不是"名册里任意一个单位"（§8.1）。
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
        plan, res = self.commit([Edit.store_set("south", "store", 0, "price", 3)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        store = self.read("store.yml")
        self.assertEqual(store["south"]["store"][0]["price"], 3)
        self.assertEqual(store["south"]["store"][0]["quantity"], 20)   # 其余不动

    def test_price_zero_means_free_not_sold_out(self):
        plan, res = self.commit([Edit.store_set("south", "store", 0, "price", 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        store = self.read("store.yml")
        self.assertEqual(store["south"]["store"][0]["price"], 0)
        self.assertTrue(any("免费" in w for w in plan.warnings), plan.warnings)

    def test_quantity_zero_is_blocked(self):
        """`quantity: 0` 是游戏从不产生的非法状态。"""
        plan, _ = self.commit([Edit.store_set("south", "store", 0, "quantity", 0)])
        self.assertFalse(plan.ok)
        self.assertIn("删除该条目", plan.errors[0])

    def test_negative_quantity_blocked(self):
        plan, _ = self.commit([Edit.store_set("south", "store", 0, "quantity", -5)])
        self.assertFalse(plan.ok)

    def test_set_quantity_upwards(self):
        plan, res = self.commit([Edit.store_set("south", "store", 0, "quantity", 99)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.read("store.yml")["south"]["store"][0]["quantity"], 99)

    def test_cannot_create_new_front(self):
        """存档的键是游戏包 fronts/ 的子集 —— 不要凭空新建战线键。"""
        plan, _ = self.commit([Edit.store_set("north", "store", 0, "price", 1)])
        self.assertFalse(plan.ok)
        self.assertIn("战线", plan.errors[0])

    def test_unknown_sub_store_is_blocked(self):
        """`store.yml` 是两层结构 —— 子商店只能是 store / elite_store。"""
        plan, _ = self.commit([Edit.store_set("south", "vip", 0, "price", 1)])
        self.assertFalse(plan.ok)
        self.assertIn("子商店", plan.errors[0])

    def test_elite_store_null_is_reported_not_crashed(self):
        """精英商店没启用时（`elite_store: null`）要报错，不是崩。"""
        plan, _ = self.commit([Edit.store_set("south", "elite_store", 0, "price", 1)])
        self.assertFalse(plan.ok)
        self.assertIn("精英商店", plan.errors[0])

    def test_nationality_faction_hint(self):
        plan, _ = self.commit([Edit.store_set("south", "store", 0, "price", 1)])
        self.assertTrue(plan.ok, plan.errors)

    def test_only_store_yml_changes(self):
        plan, res = self.commit([Edit.store_set("south", "store", 0, "price", 3)])
        self.assertEqual(res.changed, ["store.yml"])


class TestStoreRemove(CardStoreTestBase):
    def test_remove_entry_is_the_way_to_delist(self):
        """下架商品 = 删条目。"""
        plan, res = self.commit([Edit.store_remove("south", "store", 0)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        store = self.read("store.yml")
        self.assertEqual(len(store["south"]["store"]), 1)
        self.assertEqual(store["south"]["store"][0]["spec"], "ger_arty_40")

    def test_remove_bad_index(self):
        plan, _ = self.commit([Edit.store_remove("south", "store", 99)])
        self.assertFalse(plan.ok)


class TestStoreAdd(CardStoreTestBase):
    """上架新商品（`e154`：价格/数量在存档里，改了就是改了）。"""

    def test_add_entry(self):
        plan, res = self.commit([Edit.store_add("south", "store", {
            "equipment": "armor", "nationality": "german",
            "price": 30, "quantity": 5})])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        entries = self.read("store.yml")["south"]["store"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[2]["equipment"], "armor")
        self.assertEqual(entries[2]["price"], 30)

    def test_spec_and_equipment_are_exclusive(self):
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "spec": "ger_arty_40", "equipment": "armor",
            "nationality": "german", "price": 30, "quantity": 5})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("二选一" in e for e in plan.errors), plan.errors)

    def test_one_of_spec_or_equipment_required(self):
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "nationality": "german", "price": 30, "quantity": 5})])
        self.assertFalse(plan.ok)

    def test_quantity_must_be_positive(self):
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "equipment": "armor", "nationality": "german",
            "price": 30, "quantity": 0})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("正整数" in e for e in plan.errors), plan.errors)

    def test_price_must_be_non_negative(self):
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "equipment": "armor", "nationality": "german",
            "price": -1, "quantity": 3})])
        self.assertFalse(plan.ok)

    def test_unknown_spec_is_blocked(self):
        """游戏里没有的特种兵不能凭空新增（schema 是枚举校验）。"""
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "spec": "not_a_real_spec", "nationality": "german",
            "price": 30, "quantity": 5})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("游戏里没有" in e for e in plan.errors), plan.errors)

    def test_elite_store_not_enabled_cannot_add(self):
        plan, _ = self.commit([Edit.store_add("south", "elite_store", {
            "equipment": "armor", "nationality": "german",
            "price": 30, "quantity": 5})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("精英商店" in e for e in plan.errors), plan.errors)


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
        """显式指定槽位（夹具难度 hard ⇒ 手牌上限 3）。"""
        plan, res = self.commit([Edit.card_add("air_attack_allies", position=3)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        cards = self.read("cards.yml")
        self.assertEqual(cards[1]["position"], 3)

    def test_position_over_limit_is_blocked(self):
        """⚠️ U25：超限的槽位**游戏读不到**（按 position 索引读手牌）⇒ 白写 ⇒ 拦。

        原来的用例用 position=7，**建立在一个错的前提上**（以为槽位可以超限）。
        """
        plan, _ = self.commit([Edit.card_add("air_attack_allies", position=7)])
        self.assertFalse(plan.ok)
        self.assertIn("上限", plan.errors[0])

    def test_position_zero_is_blocked(self):
        plan, _ = self.commit([Edit.card_add("air_attack_allies", position=0)])
        self.assertFalse(plan.ok)

    def test_duplicate_position_is_blocked(self):
        plan, _ = self.commit([Edit.card_add("air_attack_allies", position=1)])
        self.assertFalse(plan.ok)

    def test_unknown_card_type_is_blocked(self):
        plan, _ = self.commit([Edit.card_add("not_a_real_card")])
        self.assertFalse(plan.ok)
        self.assertIn("不存在", plan.errors[0])

    def test_card_with_unit_takes_reserved_unit_id(self):
        """⚠️ `unit_id` 的真实语义 = 本战役为这张卡登记的**预留 id**。

        夹具里 `document/main.yml.card_type_units` 登记了
        `tactical_para_german → 718` ⇒ 不传 unit_id 也能加（自动补上）。
        """
        if not self.catalog.has_card_type("tactical_para_german"):
            self.skipTest("本机没有这个卡牌类型")
        plan, res = self.commit([Edit.card_add("tactical_para_german")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        cards = self.read("cards.yml")
        self.assertEqual(cards[1]["unit_id"], 718)

    def test_card_with_unit_rejects_wrong_unit_id(self):
        """填错 ⇒ 召唤出**错误的单位** —— 必须拦。"""
        if not self.catalog.has_card_type("tactical_para_german"):
            self.skipTest("本机没有这个卡牌类型")
        plan, _ = self.commit([Edit.card_add("tactical_para_german", unit_id=1)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("预留的单位是 718" in e for e in plan.errors), plan.errors)

    def test_card_with_unit_not_registered_in_campaign_is_blocked(self):
        """本战役没为它登记单位 ⇒ 硬写进去用卡时游戏会崩。"""
        if not self.catalog.has_card_type("tactical_naval_assault_us"):
            self.skipTest("本机没有这个卡牌类型")
        plan, _ = self.commit([Edit.card_add("tactical_naval_assault_us")])
        self.assertFalse(plan.ok)
        self.assertTrue(any("登记" in e for e in plan.errors), plan.errors)

    def test_card_without_unit_rejects_unit_id(self):
        plan, _ = self.commit([Edit.card_add("air_attack_allies", unit_id=1)])
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


class TestCardSet(CardStoreTestBase):
    """改手牌某个字段（`is_free`）—— §7.5.2。"""

    def test_set_is_free(self):
        plan, res = self.commit([Edit.card_set(1, "is_free", False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        cards = self.read("cards.yml")
        self.assertFalse(cards[0]["is_free"])
        self.assertEqual(cards[0]["card_type"], "air_attack_allies")  # 其余不动

    def test_only_is_free_is_allowed(self):
        plan, _ = self.commit([Edit.card_set(1, "card_type", "x")])
        self.assertFalse(plan.ok)
        self.assertTrue(any("不允许改手牌字段" in e for e in plan.errors), plan.errors)

    def test_value_must_be_bool(self):
        plan, _ = self.commit([Edit.card_set(1, "is_free", "yes")])
        self.assertFalse(plan.ok)

    def test_missing_position(self):
        plan, _ = self.commit([Edit.card_set(99, "is_free", False)])
        self.assertFalse(plan.ok)

    def test_only_cards_yml_changes(self):
        plan, res = self.commit([Edit.card_set(1, "is_free", False)])
        self.assertEqual(res.changed, ["cards.yml"])


class TestRestoreHand(CardStoreTestBase):
    def test_restore_hand_from_checkpoint(self):
        """恢复上次会议的牌局：读 L2 的 card_store → 写 L1（§6.3）。

        ⚠️ 恢复的是**货架**（`main.yml.card_store`）——
        实测 L2 的 `cards.yml` 与根一致，而 `card_store` 是上次会议的货架快照。
        """
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


class TestStoreDuplicate(CardStoreTestBase):
    """U23：商店的**重复条目**规则（用户口径 2026-11-18）。

    * 同一个 **(战线, 子商店)** 里**不能出现重复条目** —— 价格/库存不同**也算重复**；
    * **多个前线的商店库存彼此独立** —— 判重**不能跨战线**。
    """

    def test_duplicate_entry_in_same_store_is_rejected(self):
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "equipment": "infantry", "nationality": "us",
            "price": 5, "quantity": 20})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("已经有" in e for e in plan.errors), plan.errors)

    def test_duplicate_with_different_price_is_also_rejected(self):
        """价格 / 库存不同**也**是重复条目。"""
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "equipment": "infantry", "nationality": "us",
            "price": 99, "quantity": 1})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("已经有" in e for e in plan.errors), plan.errors)

    def test_same_item_in_another_front_is_allowed(self):
        """**多个前线的商店库存彼此独立** —— 不能混着判重。

        north 战线里**没有** `infantry/us`（south 有）⇒ 在 north 上架它应当通过。
        """
        p = make_save(self.tmp / "north.usg", store_overrides={
            "north": {
                "store": [
                    {"equipment": "armor", "nationality": "german",
                     "price": 12, "quantity": 3},
                ],
                "elite_store": None,
            },
        })
        with open_save(str(p), self.paths) as save:
            plan = save.plan_edit([Edit.store_add("north", "store", {
                "equipment": "infantry", "nationality": "us",
                "price": 5, "quantity": 20})], catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
            self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(p) as zf:
            entries = yaml.safe_load(zf.read("store.yml"))["north"]["store"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1]["equipment"], "infantry")


if __name__ == "__main__":
    unittest.main()
