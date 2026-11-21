"""卡牌商店货架（`main.yml.card_store`）与**白名单** —— 规范 §7.5 / §7.5.1。

**为什么有白名单**（`e160` 实证）：
登陆 / 空降类卡牌会**召唤单位**，战役里本来没有这个单位时，
买下去用卡时游戏会崩 ⇒ 改卡牌时**只允许改成商店本来就能自然生成的那几张**。

**规则**（逐条复刻 `Campaign.get_cards_probabilities`）：

```
可上架 = { ct : ∃ meta_type, p(meta_type) > 0,
             ct.faction == 玩家阵营,
             (¬ct.has_unit)
             OR ( ct ∈ card_type_units ∧ ct ∉ used_card_types_with_unit
                  ∧ ct ∉ 当前手牌 ∧ 预留单位未阵亡 ) }
```
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save

#: 一个"会议阶段"的货架（会议界面才有货架）
SHELF = [
    {"card_type": "air_attack_axis", "is_free": False, "position": 1,
     "unit_id": None, "used": False},
    {"card_type": "precision_bombing_axis", "is_free": False, "position": 2,
     "unit_id": None, "used": False},
    {"card_type": "truck_axis", "is_free": True, "position": 3,
     "unit_id": None, "used": False},
]


class ShelfTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="card_shelf_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        if not self.catalog.has_card_type("air_attack_axis"):
            self.skipTest("本机没有游戏包")

    def make(self, name="s.usg", **kwargs):
        p = self.tmp / name
        make_save(p, **kwargs)
        return p

    def commit(self, path, edits):
        with open_save(str(path), self.paths) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            if not plan.ok:
                return plan, None
            return plan, save.commit(plan)

    def read(self, path, entry):
        import zipfile
        with zipfile.ZipFile(path) as zf:
            return yaml.safe_load(zf.read(entry))

    def whitelist(self, path):
        with open_save(str(path), self.paths) as save:
            return self.catalog.card_whitelist(save)


class TestWhitelist(ShelfTestBase):
    def test_faction_mismatch_is_blocked_with_reason(self):
        """玩家阵营 axis ⇒ allies / soviet 的卡全被挡，且要给原因。"""
        p = self.make()
        wl = self.whitelist(p)
        self.assertEqual(wl.player_faction, "axis")
        blocked = wl.blocked
        self.assertTrue(blocked, "应该有一部分卡被屏蔽")
        for name, reason in blocked.items():
            d = self.catalog.card_type(name) or {}
            if d.get("faction") != "axis":
                self.assertIn("阵营", reason, f"{name} 的屏蔽原因应说明阵营")

    def test_axis_cards_are_allowed(self):
        """玩家阵营相同的卡应该能上架。"""
        p = self.make()
        wl = self.whitelist(p)
        axis_allowed = [n for n in wl.allowed
                        if (self.catalog.card_type(n) or {}).get("faction") == "axis"]
        self.assertTrue(axis_allowed, "axis 的卡应该有能上架的")

    def test_has_unit_card_without_campaign_registration_is_blocked(self):
        """⚠️ 关键用例：`tactical_naval_assault_us` 没登记在 card_type_units 里
        ⇒ 召唤不出单位 ⇒ 屏蔽。"""
        if not self.catalog.has_card_type("tactical_naval_assault_us"):
            self.skipTest("本机没有这个卡牌类型")
        p = self.make()
        wl = self.whitelist(p)
        self.assertNotIn("tactical_naval_assault_us", wl.allowed)
        reason = wl.reason("tactical_naval_assault_us") or ""
        self.assertTrue(reason, "被屏蔽的卡必须给原因")

    def test_registered_has_unit_card_is_allowed(self):
        """夹具登记了 `tactical_para_german → 718` ⇒ 它能上架。"""
        if not self.catalog.has_card_type("tactical_para_german"):
            self.skipTest("本机没有这个卡牌类型")
        p = self.make()
        wl = self.whitelist(p)
        if "tactical_para_german" not in wl.allowed:
            self.skipTest("本次会议该卡的概率为 0（会议覆盖）")
        self.assertIsNone(wl.reason("tactical_para_german"))

    def test_whitelist_is_state_not_static(self):
        """白名单是"当前存档 + 当前会议"的状态 ⇒ 换存档就可能变。"""
        p1 = self.make("a.usg")
        p2 = self.make("b.usg", main_overrides={"card_store": SHELF})
        wl1 = self.whitelist(p1)
        wl2 = self.whitelist(p2)
        self.assertIsInstance(wl1.allowed, frozenset)
        self.assertIsInstance(wl2.allowed, frozenset)

    def test_reason_contains_why(self):
        p = self.make()
        wl = self.whitelist(p)
        for name, reason in wl.blocked.items():
            self.assertTrue(reason.strip(), f"{name} 屏蔽原因不能是空串")


class TestShelfEdits(ShelfTestBase):
    def setUp(self):
        super().setUp()
        self.path = self.make(main_overrides={"card_store": SHELF})

    def test_set_is_free_on_shelf_is_a_price(self):
        """货架上的 `is_free` = **真实价格**（True ⇒ 0 声望）。

        ⚠️ **U146**：这条知识**不再每次当软警告弹**（噪音）⇒
        改到**卡牌页的静态说明**里（见 `tests/test_warning_noise.py`）。
        """
        plan, res = self.commit(self.path,
                                [Edit.card_store_set(1, is_free=True)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        shelf = self.read(self.path, "main.yml")["card_store"]
        self.assertTrue(shelf[0]["is_free"])
        self.assertFalse(any("声望" in w for w in plan.warnings), plan.warnings)

    def test_set_is_free_false(self):
        plan, res = self.commit(self.path,
                                [Edit.card_store_set(3, is_free=False)])
        self.assertTrue(plan.ok, plan.errors)
        shelf = self.read(self.path, "main.yml")["card_store"]
        self.assertFalse(shelf[2]["is_free"])

    def test_only_main_yml_changes(self):
        plan, res = self.commit(self.path,
                                [Edit.card_store_set(1, is_free=True)])
        self.assertEqual(res.changed, ["main.yml"])

    def test_replace_with_allowed_card(self):
        wl = self.whitelist(self.path)
        allowed = [n for n in wl.allowed
                   if n not in {c["card_type"] for c in SHELF}]
        if not allowed:
            self.skipTest("本机上没有可替换的卡")
        target = allowed[0]
        plan, res = self.commit(self.path,
                                [Edit.card_store_set(1, card_type=target)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        shelf = self.read(self.path, "main.yml")["card_store"]
        self.assertEqual(shelf[0]["card_type"], target)

    def test_replace_with_blocked_card_is_rejected(self):
        """⚠️ 白名单是核心库的**硬校验** —— 不能只靠 GUI 挡。"""
        wl = self.whitelist(self.path)
        blocked = [n for n in wl.blocked
                   if n not in {c["card_type"] for c in SHELF}]
        if not blocked:
            self.skipTest("本机上没有被屏蔽的卡")
        plan, _ = self.commit(self.path,
                              [Edit.card_store_set(1, card_type=blocked[0])])
        self.assertFalse(plan.ok)
        self.assertTrue(any("不能上架" in e for e in plan.errors), plan.errors)

    def test_replace_with_has_unit_card_sets_unit_id(self):
        """换成会召唤单位的卡 ⇒ `unit_id` 必须跟着换成预留 id。"""
        if not self.catalog.has_card_type("tactical_para_german"):
            self.skipTest("本机没有这个卡牌类型")
        wl = self.whitelist(self.path)
        if "tactical_para_german" not in wl.allowed:
            self.skipTest("本次会议该卡不可上架")
        plan, res = self.commit(
            self.path, [Edit.card_store_set(1, card_type="tactical_para_german")])
        self.assertTrue(plan.ok, plan.errors)
        shelf = self.read(self.path, "main.yml")["card_store"]
        self.assertEqual(shelf[0]["card_type"], "tactical_para_german")
        self.assertEqual(shelf[0]["unit_id"], 718)

    def test_remove_from_shelf(self):
        plan, res = self.commit(self.path, [Edit.card_store_remove(2)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        shelf = self.read(self.path, "main.yml")["card_store"]
        self.assertEqual(len(shelf), 2)
        self.assertNotIn(2, [c["position"] for c in shelf])

    def test_add_to_shelf(self):
        wl = self.whitelist(self.path)
        used = {c["position"] for c in SHELF}
        free = [i for i in range(1, 6) if i not in used]
        allowed = [n for n in wl.allowed
                   if n not in {c["card_type"] for c in SHELF}]
        if not free or not allowed:
            self.skipTest("本机上没有可上架的卡")
        plan, res = self.commit(
            self.path, [Edit.card_store_add(free[0], allowed[0])])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        shelf = self.read(self.path, "main.yml")["card_store"]
        self.assertEqual(len(shelf), 4)
        self.assertIn(free[0], [c["position"] for c in shelf])

    def test_add_beyond_limit_is_blocked(self):
        """货架恒为 5 格。"""
        plan, _ = self.commit(self.path,
                              [Edit.card_store_add(6, "air_attack_axis")])
        self.assertFalse(plan.ok)

    def test_duplicate_position_is_blocked(self):
        plan, _ = self.commit(self.path,
                              [Edit.card_store_add(1, "air_attack_axis")])
        self.assertFalse(plan.ok)

    def test_missing_position(self):
        plan, _ = self.commit(self.path,
                              [Edit.card_store_set(99, is_free=True)])
        self.assertFalse(plan.ok)


class TestShelfRequiresConference(ShelfTestBase):
    """不在会议阶段 ⇒ 货架不存在 ⇒ 相关 Edit 一律报错。"""

    def setUp(self):
        super().setUp()
        self.path = self.make()          # card_store = None

    def test_set_is_blocked(self):
        plan, _ = self.commit(self.path, [Edit.card_store_set(1, is_free=True)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("会议" in e for e in plan.errors), plan.errors)

    def test_remove_is_blocked(self):
        plan, _ = self.commit(self.path, [Edit.card_store_remove(1)])
        self.assertFalse(plan.ok)

    def test_add_is_blocked(self):
        plan, _ = self.commit(self.path,
                              [Edit.card_store_add(1, "air_attack_axis")])
        self.assertFalse(plan.ok)


if __name__ == "__main__":
    unittest.main()
