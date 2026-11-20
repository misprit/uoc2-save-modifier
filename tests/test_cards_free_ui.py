# -*- coding: utf-8 -*-
"""U90：卡牌页的「免费 / 收费」——**改完立刻看得见**，而且状态**单独一行**。

**用户原话**：
「卡牌界面，切换卡牌免费与否的功能，点击后不会立即让页面变化，应用后卡牌目前
的免费收费状态才变。这和修改器整体的修改效果立即可视矛盾，会让人迷惑我到底
有没有勾上。调整现在ui，让呈现方式更清晰，例如，可以把免费或收费单独做一个状态
显示在卡牌名称下方，而不是现在这样作为卡牌名称的后缀（顺带一提，如果卡牌名字
很长，根本看不到免费状态的后缀）」

**根因**：`projectedCards()` 只把 `card_add` / `card_remove` /
`card_store_add` / `card_store_remove` 四种挂起改动投影到界面上，
**漏了 `card_set` / `card_store_set`** ⇒ 重画时读到的还是存档原值，
所以「点了没反应，要等应用」。这和修改器「改动立即可视」的规矩冲突。

**呈现方案**：状态从**卡名后缀**改成**卡名下方独立一行**（`.hcard .freeline`）——
卡名被截断时状态照样看得见；按钮文案随状态变（免费⇒「改收费」，收费⇒「改免费」）。

**为什么有这些测试**：守住三条 ——
① 挂起的「免费 / 收费」改动**必须**投影到界面（点一下就变，不许等写盘）；
② 卡名与状态**分两行**（不许再退回卡名后缀）；
③ 英文界面下状态词也跟着变。
"""

import io
import json
import os
import unittest

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")


class CardsFreeUiTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def slice(self, start_marker, end_marker):
        """截出两个标记之间的函数体（避免全文件匹配太松）。"""
        i = self.html.index(start_marker)
        j = self.html.index(end_marker, i)
        return self.html[i:j]


class TestPendingFreeIsProjected(CardsFreeUiTestBase):
    """① 挂起的「免费 / 收费」必须**立刻**投影到界面。"""

    def setUp(self):
        self.body = self.slice("function projectedCards", "function cardTileHTML")

    def test_card_set_is_projected(self):
        """手牌改免费 / 收费（`card_set`）—— 以前漏了，点了界面不变。"""
        self.assertIn('p.kind==="card_set"', self.body)
        self.assertIn("p.params.value", self.body)

    def test_card_store_set_is_projected(self):
        """货架改免费 / 收费（`card_store_set`）—— 同样以前漏了。"""
        self.assertIn('p.kind==="card_store_set"', self.body)
        self.assertIn("p.params.is_free", self.body)

    def test_card_set_only_applies_to_the_is_free_field(self):
        """`card_set` 只能改 `is_free`（核心库 `CARD_FIELD_ALLOWED`），别的字段不许投影。"""
        self.assertIn('p.params.field==="is_free"', self.body)

    def test_store_card_type_change_is_projected_too(self):
        """同一 kind 的另一半字段——**换牌**，也要马上看到（别一半投影一半不投影）。"""
        self.assertIn("p.params.card_type", self.body)

    def test_projection_does_not_touch_the_other_list(self):
        """手牌改动不许串到货架去，反之亦然。"""
        self.assertIn('p.kind==="card_set" && kind==="hand"', self.body)
        self.assertIn('p.kind==="card_store_set" && kind==="shelf"', self.body)


class TestFreeStateOnItsOwnLine(CardsFreeUiTestBase):
    """② 状态单独一行，卡名不再带后缀。"""

    def setUp(self):
        self.tile = self.slice("function cardTileHTML", "function closeCardPicker")

    def test_freeline_row_exists(self):
        self.assertIn("freeline", self.tile)

    def test_card_name_has_no_free_suffix_anymore(self):
        """❌ 旧的「卡名 · 免费」后缀不许再回来。"""
        self.assertNotIn("· 免费", self.tile)
        self.assertNotIn("· 收费", self.tile)

    def test_status_words_are_translated(self):
        """状态词走词表（英文界面自动 Free / Paid）。"""
        self.assertIn('L("免费")', self.tile)
        self.assertIn('L("收费")', self.tile)

    def test_buttons_follow_the_current_state(self):
        """按钮文案随状态变：免费⇒「改收费」，收费⇒「改免费」。"""
        self.assertIn('free?L("改收费"):L("改免费")', self.tile)

    def test_freeline_has_its_own_css(self):
        """.hcard .freeline —— 免费 / 收费两套颜色。"""
        self.assertIn(".hcard .freeline", self.html)
        self.assertIn(".hcard .freeline.free", self.html)
        self.assertIn(".hcard .freeline.paid", self.html)

    def test_freeline_is_not_truncated(self):
        """状态行**不许**被 ellipsis 截掉（卡名长的时候也要看得见）。"""
        css = self.slice(".hcard .freeline{", "/* U47")
        self.assertIn("text-overflow:clip", css)
        self.assertNotIn("text-overflow:ellipsis", css)


class TestFreeEnglishWords(CardsFreeUiTestBase):
    """③ 英文界面。"""

    def test_words_exist(self):
        ui = self.table["ui"]
        self.assertIn("免费", ui)
        self.assertIn("收费", ui)

    def test_english_translations(self):
        ui = self.table["ui"]
        self.assertEqual(ui["免费"], "Free")
        self.assertEqual(ui["收费"], "Paid")


if __name__ == "__main__":
    unittest.main()
