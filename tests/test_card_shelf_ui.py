# -*- coding: utf-8 -*-
"""U114：卡牌商店货架 —— 「上架新牌」与「换牌」是**两件事**，不能杂糅。

用户反馈（2026-11-21，朋友）：
> 卡牌商店也有问题，要上架新的牌，但只有一个换牌功能。按道理来说应该是可以选择
> 换牌，或者是下架旧牌之后再上架新的。但是现在这两个功能被杂糅到一起了，
> 槽位有牌的时候不能换牌只能下架

**核心库的语义本来就分得很清**：
* `card_store_add`（上架）—— 槽位**必须空**（否则「槽位 N 已经被占了」）；
* `card_store_set`（换牌 / 改免费）—— 槽位**必须有卡**（否则「货架上没有槽位
  号为 N 的卡」）；
⇒ 而前端**一律**走「换牌」⇒ **上架新牌根本做不到**；
⇒ 而有卡的格子**没有「换牌」入口** ⇒ 只能先下架。

**这些测试守着**
① 选择器带 `act`（上架 / 换牌），没传就**按槽位有没有牌自动判断**；
② 空槽位 ⇒ 上架；有卡的格子 ⇒ 换牌（点卡面）；
③ 没有货架的存档**别显示 5 个空槽位**（点了上架也会被核心库拒）。
"""

import io
import os
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


class CardShelfUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    @staticmethod
    def _body(html, start, end):
        i = html.index(start)
        j = html.index(end, i + len(start))
        return html[i:j]

    def test_the_picker_carries_the_action(self):
        """选择器必须知道自己是「上架」还是「换牌」。"""
        body = self._body(self.html, "function openCardPickerModal(",
                          "function renderCardPickerModal(")
        self.assertIn("act:", body, "MODAL 里必须带上 act")
        self.assertIn("shelf.some(x=>x.position===position) ? \"set\" : \"add\"", body,
                      "没传 act 时要按槽位有没有牌自动判断")

    def test_the_empty_slot_lists_a_new_card(self):
        """空槽位 ⇒ 上架（不是换牌！）。"""
        self.assertIn("openCardPicker('shelf',{0},'add')", self.html)

    def test_a_filled_slot_can_be_swapped(self):
        """有卡的格子 ⇒ 点卡面换牌（按钮行放不下第三个按钮 ⇒ 用卡面）。"""
        body = self._body(self.html, "function cardTileHTML(", "function openCardPicker(")
        self.assertIn("openCardPicker('shelf',${c.position},'set')", body,
                      "货架上有牌时必须能换牌")

    def test_confirm_branches_on_the_action(self):
        body = self._body(self.html, "function cardPickConfirm(", "/* ---------- ③ 上架新商品 ---------- */")
        self.assertIn('else if(M.act==="add") cardStoreAdd(M.position, M.sel);', body)
        self.assertIn("else cardStoreSet(M.position, M.sel);", body)

    def test_the_picker_title_says_which_one_it_is(self):
        body = self._body(self.html, "function renderCardPickerModal(",
                          "function cardPick(")
        self.assertIn('L("上架一张新卡")', body)
        self.assertIn('L("换牌")', body)

    def test_no_shelf_means_no_fake_slots(self):
        """没有货架的存档**别显示 5 个空槽位**（点了上架也会被核心库拒）。"""
        body = self._body(self.html, "function pageCards(", "function restoreHand(")
        self.assertIn("shelfFeat", body)
        self.assertIn("shelfOK", body)
        self.assertIn('L("这个存档现在没有卡牌商店货架")', body)


if __name__ == "__main__":
    unittest.main()
