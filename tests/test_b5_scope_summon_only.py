# -*- coding: utf-8 -*-
"""B-5 口径收窄（用户 2026-11-27 拍板）：**只有召唤卡**才不许重复上架。

* 「只有空降和登陆这种绑定单位的卡牌，添加多张才会导致 bug。
  普通的空袭卡天然就能有多张，还能买多张。不应该限制他们。」
* 「不允许手牌和商店同时出现空降和登陆卡牌。」

**这些测试守着**
① **普通卡**（不召唤单位）在货架上可以**重复**（买多张）⇒ 不再被拦；
② 换牌成货架上已有的**普通卡**类型 ⇒ 允许；
③ **召唤卡**：货架上已有 ⇒ 不能重复上架（同一个 `unit_id` 被认领两次）；
④ **召唤卡**：手牌里有 ⇒ 不能上架同一张（手牌与商店互斥）—— 这条
   由 `catalog.card_whitelist` 守着（`elif name in hand_types` 在 `has_unit` 分支里）。

⚠️ 货架必须**非空** —— 能力位据此判断「在会议界面」（`card_store` 为空 ⇒ 没有货架）。
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save

#: 会召唤单位的卡（`has_unit`）—— 社区报的伞兵卡
SUMMON_CARD = "tactical_para_german"
#: 夹具 `document/main.yml` 给它登记的可召唤单位 id
SUMMON_UNIT_ID = 718


class ShelfScopeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b5_scope_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        if not self.catalog.has_card_type(SUMMON_CARD):
            self.skipTest("本机没有游戏包（缺 %s）" % SUMMON_CARD)
        # 先造一份存档来取白名单（白名单不看货架）
        probe = make_save(self.tmp / "probe.usg")
        self.ordinary = self._pick_ordinary(probe)
        self.save_path = make_save(self.tmp / "s.usg", main_overrides={"card_store": [
            {"card_type": self.ordinary, "is_free": False, "position": 1,
             "unit_id": None, "used": False}]})

    def _pick_ordinary(self, path):
        """白名单里**不召唤单位**的一张卡（普通卡）。"""
        with open_save(str(path), self.paths) as save:
            wl = self.catalog.card_whitelist(save)
        for name in sorted(wl.allowed):
            if not (self.catalog.card_type(name) or {}).get("has_unit"):
                return name
        self.skipTest("本机白名单里没有普通卡")

    def plan(self, edits, path=None):
        with open_save(str(path or self.save_path), self.paths) as save:
            return save.plan_edit(edits, catalog=self.catalog)

    def whitelist(self, path=None):
        with open_save(str(path or self.save_path), self.paths) as save:
            return self.catalog.card_whitelist(save)


class TestOrdinaryCardsMayRepeat(ShelfScopeBase):
    """① ② 普通卡可以有多张。"""

    def test_ordinary_card_can_be_listed_twice(self):
        """货架上已有一张普通卡 ⇒ **还能再上一张**（以前一律被拦）。"""
        p = self.plan([Edit.card_store_add(2, self.ordinary)])
        self.assertTrue(p.ok, p.errors)

    def test_two_copies_in_one_batch(self):
        """同一批里上两张同类型普通卡 ⇒ 也允许。"""
        p = self.plan([Edit.card_store_add(2, self.ordinary),
                       Edit.card_store_add(3, self.ordinary)])
        self.assertTrue(p.ok, p.errors)

    def test_replacing_with_an_ordinary_type_already_on_the_shelf_is_allowed(self):
        """换牌成货架上已有的**普通卡**类型 ⇒ 允许（换牌本来就不是「多一张」）。"""
        other = [n for n in sorted(self.whitelist().allowed) if n != self.ordinary]
        if not other:
            self.skipTest("本机没有别的可上架卡")
        p = self.plan([Edit.card_store_add(2, other[0]),
                       Edit.card_store_set(2, card_type=self.ordinary)])
        self.assertTrue(p.ok, p.errors)


class TestSummonCardsStayRestricted(ShelfScopeBase):
    """③④ 召唤卡的限制**保持**。"""

    def setUp(self):
        super().setUp()
        # 货架上放一张**召唤卡**（另测「召唤卡不能重复上架」）
        self.save_path = make_save(self.tmp / "summon.usg", main_overrides={"card_store": [
            {"card_type": SUMMON_CARD, "is_free": False, "position": 1,
             "unit_id": SUMMON_UNIT_ID, "used": False}]})

    def test_summon_card_cannot_be_listed_twice(self):
        """同一张召唤卡不能上两次货架（同一个单位被认领两次 ⇒ 两个同款兵模）。"""
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)])
        self.assertFalse(p.ok, "同一张召唤卡上了两次货架，计划居然通过了")
        self.assertTrue(any("已经有同类型" in e for e in p.errors), p.errors)

    def test_summon_card_in_hand_cannot_be_listed_on_the_shelf(self):
        """⭐ 手牌里已有召唤卡 ⇒ **不能**再上架同一张（手牌与商店互斥）。

        ⚠️ 这条由白名单守着（`card_whitelist` 的 `elif name in hand_types`
        就在 `has_unit` 分支里）⇒ 别以后被放宽掉。
        """
        path = make_save(self.tmp / "hand.usg",
                         main_overrides={"card_store": [
                             {"card_type": self.ordinary, "is_free": False,
                              "position": 1, "unit_id": None, "used": False}]},
                         cards_override=[
                             {"card_type": SUMMON_CARD, "is_free": False,
                              "position": 1, "unit_id": SUMMON_UNIT_ID,
                              "used": False}])
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)], path=path)
        self.assertFalse(p.ok, "手牌与商店同时出现同一张召唤卡，计划居然通过了")
        self.assertTrue(any("手牌里已有同类型" in e for e in p.errors), p.errors)


if __name__ == "__main__":
    unittest.main()
