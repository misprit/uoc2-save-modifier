# -*- coding: utf-8 -*-
"""U118：两个界面问题。

**① 商店新上架的商品在界面上看不见**（要写盘后才出现）

根因：`projectedStore()` 把待应用的「上架」推进投影时**没带 front / sub**
⇒ 这一行匹配不上当前选中的 (战线, 子商店) ⇒ 永远画不出来。
（总部兵库没这个问题 ⇒ 它的投影带了归属信息。）

**② 点「应用更改」看不到改了什么东西的列表**（有软警告时）

以前：只要有软警告 ⇒ 直接弹「警告框」⇒ 同意「仍然应用」⇒ **立刻写盘**
⇒ 玩家从没看到改动明细。

现在（用户要的顺序）：
① 先弹**改动明细列表**；
② 点「应用更改」⇒ **逐条**弹软警告，逐个同意；
③ 全部同意 ⇒ 才写盘。

⚠️ **U147（2026-11-21 用户反馈：「软警告太多了，而且需要一个个确认」）**
上面 ②③ 那套**逐条弹、逐个同意**已经**取消** ⇒ 软警告改成
**在同一个页面里一页列全**（相同的合并成一条 + 「×N」），一次确认就够。
"""

import io
import os
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


class StorePendingUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    @staticmethod
    def _body(html, start, end):
        i = html.index(start)
        j = html.index(end, i + len(start))
        return html[i:j]

    # ------------------------------------------------------------------ ①

    def test_the_projection_carries_front_and_sub(self):
        """待上架的商品必须带上 (战线, 子商店) ⇒ 才能匹配上当前选中的那一栏。"""
        body = self._body(self.html, "function projectedStore(", "function pageStore(")
        self.assertIn("front:p.params.front", body)
        self.assertIn("sub:p.params.sub", body)

    def test_the_new_item_uses_a_negative_index(self):
        """下标用负数 ⇒ 不会和存档里的真实下标（≥ 0）撞
        （否则价格 / 库存的待应用 key 会串到别的条目上）。"""
        body = self._body(self.html, "function projectedStore(", "function pageStore(")
        self.assertIn("index:-(added+1)", body)

    def test_removing_a_pending_item_drops_the_add(self):
        """撤掉一个**还没写盘**的商品 ⇒ 撤掉那条「上架」，
        而不是去删存档里的第 index 条（会删错行）。"""
        body = self._body(self.html, "function storeRemove(", "/* ===")
        self.assertIn("r._new", body)
        self.assertIn('dropPendingByKey("store_add", r._key)', body)

    # ------------------------------------------------------------------ ②

    def test_apply_always_shows_the_change_list_first(self):
        """有软警告时**也要先给列表**（警告在同一页里列全）。"""
        body = self._body(self.html, "async function doApply()",
                           "async function showWarningsOnly(")
        self.assertIn('openConfirm("ok"', body)
        self.assertIn("warnings:", body)

    def test_warnings_are_listed_on_one_page(self):
        """⚠️ **U147**：软警告**一页列全** —— 不再"一条一条弹、逐个同意"。"""
        self.assertNotIn('openConfirm("warn"', self.html,
                         "逐条弹软警告的框子已经取消（U147）")
        self.assertNotIn("APPLY_WARNINGS", self.html,
                         "警告队列已经取消（U147）")

    def test_the_confirm_page_shows_all_warnings(self):
        """确认页里**直接列出**全部软警告（合并同类项 + 「×N」）。"""
        body = self._body(self.html, "function openConfirm(", "/* ===")
        self.assertIn("warnBoxHTML(info.warnings||[])", body)
        self.assertIn('onclick="reallyApply()"', body,
                      "确认一次就写盘，不再逐条同意")


if __name__ == "__main__":
    unittest.main()
