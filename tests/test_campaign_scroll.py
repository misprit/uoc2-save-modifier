# -*- coding: utf-8 -*-
"""U99：战役页的长块 —— 限高 + 框内上下滚动。

**用户原话**：
「最后一页战役，因为信息很多，所以表往下拉得特别多。是不是某些长度特别超长的选项卡
可以规定一个大小，让它在自己的选项卡里进行上下滚动。让这个战役页整体显示的数据量
在大小上符合一般逻辑。」

**实测（west 存档，隔离副本）**：改之前整页 ≈ 2500px（3.5 屏）——
名册 45 行占了 1450px、会议商店 20 张卡 330px、路线图 28 个场景 213px。
改之后：每个长块**自己限高 + 自己滚**，整页 ≈ 1450px（2 屏左右）。

**守则（本文件盯着）**：
① 三个长块都有上限，且**上限是有限值**（不许写回 `max-height:none`）；
② 表格在框里滚 ⇒ 表头吸顶；
③ 真的溢出的块，标题栏上出现「↕」提示（没溢出的块**不许**出现）；
④ **词表一个字都不许动** —— `L2()` 的模板字面量就是词表 key，
   改模板 ⇒ 英文界面掉回中文（U99 因此只改实参、不改模板）。
"""

import io
import json
import os
import re
import unittest

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")


class CampaignScrollTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def slice(self, start_marker, end_marker):
        i = self.html.index(start_marker)
        j = self.html.index(end_marker, i)
        return self.html[i:j]


class TestScrollBoxCss(CampaignScrollTestBase):
    """① 限高 + 滚动 + 吸顶表头。"""

    def test_scrollbox_has_overflow_auto(self):
        self.assertIn(".scrollbox{overflow:auto}", self.html)

    def test_three_blocks_are_capped(self):
        """三个长块各有上限。"""
        for cls in ("routebox", "rosterbox", "storebox"):
            self.assertRegex(self.html, r"\.scrollbox\.%s\{max-height:\d+px\}" % cls)

    def test_caps_are_finite_and_small(self):
        """上限必须是**有限值**，而且不许大到没意义（≤ 420px）。"""
        caps = re.findall(r"\.scrollbox\.\w+\{max-height:(\d+)px\}", self.html)
        self.assertEqual(len(caps), 3, "三个块都要有上限")
        for c in caps:
            self.assertGreater(int(c), 0)
            self.assertLessEqual(int(c), 420)

    def test_scrollbar_is_styled(self):
        """Windows/Edge 上默认滚动条太细 ⇒ 定制一下。"""
        self.assertIn(".scrollbox::-webkit-scrollbar{", self.html)
        self.assertIn(".scrollbox::-webkit-scrollbar-thumb{", self.html)

    def test_table_header_is_sticky(self):
        """框内滚动时表头吸顶（列名一直在）。"""
        self.assertIn(".scrollbox table.rlist thead th{position:sticky;top:0",
                      self.html)

    def test_scroll_hint_badge_exists(self):
        """③ 溢出提示：`.storegrp.has-scroll .storetitle::after`。"""
        self.assertIn(".storegrp.has-scroll .storetitle::after{content:\"↕\"",
                      self.html)


class TestCampaignBlocksAreWrapped(CampaignScrollTestBase):
    """三个长块真的被包起来了。"""

    def test_route_is_wrapped(self):
        body = self.slice("function routeBox", "function markScrollable")
        self.assertIn('<div class="scrollbox routebox">', body)
        self.assertIn("routeHTML()", body)

    def test_store_is_wrapped(self):
        body = self.slice("function storeBox", "function routeBox")
        self.assertIn('<div class="scrollbox storebox">', body)
        self.assertIn("conferenceStoreHTML()", body)

    def test_roster_table_is_wrapped(self):
        body = self.slice("function rosterHTML", "/* ---------- 这场会议的商店")
        self.assertIn('<div class="scrollbox rosterbox"><table class="rlist">',
                      body)
        self.assertIn("'</table></div>'", body)

    def test_page_uses_the_wrappers(self):
        body = self.slice("function pageCampaign", "/* ---------- U99：战役页的三个长块")
        self.assertIn("routeBox()", body)
        self.assertIn("storeBox()", body)
        self.assertIn("markScrollable(w)", body)

    def test_mark_scrollable_only_flags_overflowing_boxes(self):
        """只给真的装不下的块加提示（`scrollHeight > clientHeight`）。"""
        body = self.slice("function markScrollable", "/* ---------- 场景名册")
        self.assertIn("scrollHeight > b.clientHeight", body)
        self.assertIn('classList.add("has-scroll")', body)


class TestWordTableUntouched(CampaignScrollTestBase):
    """④ 词表一个字都不许动（U99 只改实参、不改模板）。"""

    def test_no_scrollbox_in_word_table(self):
        """词表里出现 `scrollbox` ⇒ 说明有人改了 L2 的模板字面量 ⇒ 英文界面会掉回中文。"""
        for section, words in self.table.items():
            if not isinstance(words, dict):
                continue
            for k, v in words.items():
                self.assertNotIn("scrollbox", k,
                                 "词表 %s 段的 key 里出现了 scrollbox —— 模板被改了" % section)
                self.assertNotIn("scrollbox", v,
                                 "词表 %s 段的译文里出现了 scrollbox —— 模板被改了" % section)

    def test_campaign_template_key_still_exists(self):
        """战役页的大模板仍然是原来那个 key（英文译文还挂得上）。"""
        ui = self.table["ui"]
        keys = [k for k in ui if k.startswith('<div class="panel"><h3>战役位置</h3>')]
        self.assertEqual(len(keys), 1, "战役页模板的 key 变了或不见了")
        self.assertIn("</div></div>", keys[0])
        # 三个实参位置还在（U99 是包**实参**，不是改模板）
        for ph in ("{2}", "{8}", "{11}"):
            self.assertIn(ph, keys[0])

    def test_roster_template_key_still_exists(self):
        """名册模板的 key 也没变。"""
        ui = self.table["ui"]
        keys = [k for k in ui
                if k.startswith('<div class="note" style="margin:0 0 10px">')
                and "地图 {0}" in k]
        self.assertEqual(len(keys), 1, "名册模板的 key 变了或不见了")
        self.assertIn("{7}", keys[0])

    def test_english_templates_still_translated(self):
        """英文译文还在（没被改成中文原文）。"""
        ui = self.table["ui"]
        for k, v in ui.items():
            if k.startswith('<div class="panel"><h3>战役位置</h3>'):
                self.assertIn("Campaign position", v)
            if k.startswith('<div class="note" style="margin:0 0 10px">') and "地图 {0}" in k:
                self.assertIn("Map {0}", v)


if __name__ == "__main__":
    unittest.main()
