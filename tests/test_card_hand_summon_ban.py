"""U187：手牌（根 `cards.yml`）不许直接加**空降 / 登陆卡**。

**为什么**（U187 实测，2026-11-25 用户报）：召唤卡用的时候要召唤单位，而本战役
为它登记的那个单位 id（`document/main.yml.card_type_units`）**可能已经被召唤过**
（`used_card_types_with_unit`）—— 再写进手牌就是「同一个单位 id 被认领两次」
⇒ **游戏读到就会崩**（用户给「霸王行动」加 82 空降师 ⇒ 崩）。

⇒ 用户 2026-11-25 拍板：**手牌这一侧一刀切禁掉**，不判断「用没用过」（最保险）。
  · **存档里原本就有的不检测** —— 读路径一行不改，照常显示；
  · **卡牌商店（货架）那侧不受影响** —— 它走 `card_whitelist`，
    那里本来就把「已召唤过 / 已在手牌 / 预留单位阵亡」排除了。

⚠️ 以前的护栏只查了「本战役有没有为它登记可召唤的单位」——
**没查「那个单位是不是已经被召唤过」** ⇒ 一路漏到用户实机才炸（U187 实锤）。

**规范**：§6.3 卡牌与商店。
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "src" / "save_modifier_web" / "web"

#: 会召唤单位的卡牌类型 = 空降 / 登陆卡（游戏自己的 `has_unit` 标志）
SUMMON_CARD = "tactical_para_german"


class SummonCardBanTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u187_card_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        if not self.catalog.has_card_type(SUMMON_CARD):
            self.skipTest("本机没有游戏包（缺 %s）" % SUMMON_CARD)

    def open(self):
        return open_save(str(self.save_path), self.paths)

    def plan(self, edits):
        with self.open() as save:
            return save.plan_edit(edits, catalog=self.catalog)


class TestSummonCardIsBannedFromTheHand(SummonCardBanTestBase):
    """手牌侧一刀切禁掉空降/登陆卡。"""

    def test_summon_card_cannot_be_added(self):
        p = self.plan([Edit.card_add(SUMMON_CARD)])
        self.assertFalse(p.ok)
        self.assertTrue(any("空降/登陆卡" in e for e in p.errors), p.errors)

    def test_the_ban_wins_over_a_correct_unit_id(self):
        """`unit_id` 填对了也一样禁 —— 禁的是**卡种**，不是参数。

        夹具的 `document/main.yml.card_type_units` 登记了
        `tactical_para_german → 718` ⇒ 以前这条是能加进去的（U187 之前）。
        """
        p = self.plan([Edit.card_add(SUMMON_CARD, unit_id=718)])
        self.assertFalse(p.ok)
        self.assertTrue(any("空降/登陆卡" in e for e in p.errors), p.errors)

    def test_the_ban_wins_over_a_wrong_unit_id(self):
        p = self.plan([Edit.card_add(SUMMON_CARD, unit_id=1)])
        self.assertFalse(p.ok)
        self.assertTrue(any("空降/登陆卡" in e for e in p.errors), p.errors)

    def test_a_normal_card_is_still_allowed(self):
        """反例也要成立：不召唤单位的卡照常能加（别把功能一起砍了）。"""
        p = self.plan([Edit.card_add("air_attack_allies")])
        self.assertTrue(p.ok, p.errors)

    def test_a_summon_card_that_is_not_registered_is_banned_the_same_way(self):
        """本战役没登记单位的召唤卡也是同一条报错（口径统一）。"""
        if not self.catalog.has_card_type("tactical_naval_assault_us"):
            self.skipTest("本机没有这个卡牌类型")
        p = self.plan([Edit.card_add("tactical_naval_assault_us")])
        self.assertFalse(p.ok)
        self.assertTrue(any("空降/登陆卡" in e for e in p.errors), p.errors)


class TestExistingSummonCardInHandIsNotFlagged(SummonCardBanTestBase):
    """⚠️ **存档里原本就有的召唤卡，不检测**（用户 2026-11-25 的原话）。"""

    def setUp(self):
        super().setUp()
        # 造一个「手牌里本来就有一张召唤卡」的存档
        self.save_path = make_save(
            self.tmp / "has_para.usg",
            cards_override=[{"card_type": SUMMON_CARD, "is_free": False,
                             "position": 1, "unit_id": 718, "used": False}])

    def test_the_save_still_opens_and_shows_the_card(self):
        with self.open() as save:
            view = save.view(catalog=self.catalog)
            types = [c.card_type for c in view.hand]
            self.assertIn(SUMMON_CARD, types)

    def test_other_edits_still_work(self):
        """读路径不拦 ⇒ 别的编辑照常能规划（别把存档锁死）。"""
        p = self.plan([Edit.card_add("air_attack_allies")])
        self.assertTrue(p.ok, p.errors)


class TestShelfIsNotAffected(SummonCardBanTestBase):
    """⚠️ **卡牌商店（货架）那侧不受影响** —— 它走 `card_whitelist`。"""

    def setUp(self):
        super().setUp()
        # 货架要存在（`main.yml.card_store` 是列表）才谈得上「上架」
        self.save_path = make_save(
            self.tmp / "shelf.usg",
            main_overrides={"card_store": [
                {"card_type": "air_attack_allies", "is_free": False,
                 "position": 1, "unit_id": None, "used": False}]})

    def test_listing_a_summon_card_on_the_shelf_still_works(self):
        """空降/登陆卡**仍然可以上架** —— 那条路是游戏自己走的，白名单已经管住了。"""
        with self.open() as save:
            wl = self.catalog.card_whitelist(save)
        self.assertIn(SUMMON_CARD, wl.allowed,
                      "夹具里 %s 本来就该能上架（白名单没排除它）" % SUMMON_CARD)
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)])
        self.assertTrue(p.ok, p.errors)

    def test_a_summon_card_that_was_already_used_is_still_blocked_on_the_shelf(self):
        """白名单那道门**照旧在** —— 已被召唤过的卡上架不了。"""
        p = self.plan([Edit.card_store_add(2, "tactical_naval_assault_us")])
        self.assertFalse(p.ok)
        self.assertTrue(any("不能上架" in e for e in p.errors), p.errors)


class TestFrontendAndI18n(unittest.TestCase):
    """前端把召唤卡灰掉 + 两边文案都在词表里。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(WEB / "index.html", encoding="utf-8").read()
        cls.table = json.load(io.open(WEB / "i18n.json", encoding="utf-8"))

    def test_the_hand_picker_greys_out_summon_cards(self):
        """手牌选择器里 `has_unit` 的卡要标成 blocked（点不动）。"""
        body = self.html[self.html.index("function renderCardPickerModal("):
                        self.html.index("function renderCardPickerModal(") + 2000]
        self.assertIn('const isHand = M.mode==="hand";', body)
        self.assertIn("if(!blocked && isHand && info.has_unit)", body)
        self.assertIn('L("空降/登陆卡不能直接加到手牌")', body)

    def test_the_reason_is_in_the_ui_table(self):
        self.assertIn("空降/登陆卡不能直接加到手牌", self.table["ui"])

    def test_the_core_error_is_in_the_errors_table(self):
        keys = [k for k in self.table["errors"] if "空降/登陆卡" in k]
        self.assertTrue(keys, "核心库的硬拦文案没进 errors 词表")
        for k in keys:
            self.assertIn("{card_type}", k)


if __name__ == "__main__":
    unittest.main()
