# -*- coding: utf-8 -*-
"""U106：**总部页**的清单不再跳到最上方（整体修）。

用户原话（2026-11-21）：
> 总部页面的总部列表还有选择总部后清单跳到最上方的问题，请整体修了，
> 记得不单单要修选择的时候不跳动，还有修改详情后也别跳

**根因**：总部页的「选总部」「切标签」「改详情」全都走 `show("hqs")` 整页重绘
⇒ `.hqlist`（独立滚动容器）被**重建** ⇒ scrollTop 归零 ⇒ 清单跳回顶部。
（`captureScroll` 只记了 `.rows` / `.detail`，**没记 `.hqlist`** —— U103 的漏网之鱼。）

**两道防线**：
1. **局部刷新** `refreshHqLocal()` —— 只重画【详情】+【清单里的这一行】，
   清单**不重建** ⇒ 滚动位置天然不动；
2. **滚动保位** —— `captureScroll` / `restoreScroll` 把 `.hqlist` 也记上
   （必须整页重绘的路径靠它兜底）；详情区的位置**只在「还是同一个总部的
   同一个标签页」时**才保（换了总部/换标签 ⇒ 内容变了 ⇒ 从顶部开始）。

**这些测试守着**：
① 选总部 / 切标签 / 改详情**都不许**再走整页重绘；
② 滚动保位必须把 `.hqlist` 算进去；
③ 局部刷新必须把「整页重绘上的副作用」一起搬过来（清单里那一行也要更新）。
"""

import io
import os
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


class HqScrollTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    @staticmethod
    def _body(html, start, end):
        i = html.index(start)
        j = html.index(end, i + len(start))
        return html[i:j]

    # ---------------------------------------------------------- 防线一：局部刷新

    def test_pick_hq_does_not_redraw_the_page(self):
        """选总部 ⇒ 局部刷新（清单不重建 ⇒ 滚动位置天然不动）。"""
        body = self._body(self.html, "function pickHq(id)", "function pickHqTab")
        self.assertNotIn('show("hqs")', body,
                         "选总部不能走整页重绘（会把清单重建 ⇒ 跳回顶部）")
        self.assertIn("refreshHqLocal(", body)

    def test_pick_hq_tab_does_not_redraw_the_page(self):
        body = self._body(self.html, "function pickHqTab(t)", "function refreshHqLocal")
        self.assertNotIn('show("hqs")', body)
        self.assertIn("refreshHqLocal(", body)

    def test_detail_edits_use_local_refresh(self):
        """⚠️ **改详情后也不许跳** —— 每个改详情的动作都要走局部刷新。"""
        pairs = [
            ("function commitRenameHq", "function hqTrucks"),
            ("function hqTrucks", "function hqBranchLevel"),
            ("function hqBranchLevel", "function hqSuppress"),
            ("function hqSuppress", "function hqSpecialize"),
            ("function hqSpecialize", "function hqPoolAdd"),
            ("function hqPoolAdd", "function hqPoolRemove"),
            ("function hqPoolRemove", "卡牌页（U36）"),
        ]
        for start, end in pairs:
            body = self._body(self.html, start, end)
            self.assertNotIn('show("hqs")', body,
                             "%s 还在整页重绘 ⇒ 改完详情会跳" % start)
            self.assertIn("refreshHqLocal(", body,
                          "%s 没用局部刷新" % start)

    def test_local_refresh_keeps_detail_scroll_when_asked(self):
        """改详情时详情区**自己的**滚动位置也要保住。"""
        body = self._body(self.html, "function refreshHqLocal", "function hqSkillHTML")
        self.assertIn("keepScroll", body)
        self.assertIn("scrollTop", body)

    def test_local_refresh_updates_the_list_row(self):
        """⚠️ 局部刷新必须把「整页重绘上的副作用」一起搬过来 ——
        清单里那一行的 CP 等显示的是**待应用**的值 ⇒ 也得跟着更新
        （U103 漏搬 ⇒ U104 候选池才出 bug）。"""
        body = self._body(self.html, "function refreshHqLocal", "function hqSkillHTML")
        self.assertIn("hqRowHTML", body)
        self.assertIn("outerHTML", body)

    def test_hq_row_carries_its_id(self):
        """清单行要有 `data-hqid` —— 局部刷新要按 id 找到那一行。"""
        body = self._body(self.html, "function hqRowHTML", "function pickHq(id)")
        self.assertIn("data-hqid", body)

    # ---------------------------------------------------------- 防线二：滚动保位

    def test_capture_scroll_includes_the_hq_list(self):
        """⚠️ 原来只记了 `.rows` / `.detail` ⇒ 总部清单整页重绘后跳回顶部。"""
        body = self._body(self.html, "function captureScroll(w)",
                          "function restoreScroll(w, st)")
        self.assertIn("hqlist", body)

    def test_restore_scroll_restores_the_hq_list(self):
        body = self._body(self.html, "function restoreScroll(w, st)",
                          "let LASTPAGE")
        self.assertIn("hqlist", body)

    def test_detail_scroll_only_kept_for_the_same_context(self):
        """换了总部 / 换了标签页 ⇒ 详情内容变了 ⇒ 旧位置没意义 ⇒ 从顶部开始。"""
        self.assertIn("function scrollCtx()", self.html)
        body = self._body(self.html, "function restoreScroll(w, st)", "let LASTPAGE")
        self.assertIn("scrollCtx()", body)


if __name__ == "__main__":
    unittest.main()
