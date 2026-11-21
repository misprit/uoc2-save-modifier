# -*- coding: utf-8 -*-
"""U103：单位页**局部刷新** —— 加/卸特种兵不再把列表弹回顶部。

**用户反馈**（朋友）：
「单位修改界面虽然点选单位是不会跳到最上方了，但是添加新特种会跳到最上方，
有点诡异。改一下，保证单位修改后的贴图刷新不导致单位列表跳跃吧」

**根因**：U82 把「选单位」改成了局部刷新（只重画详情）；但**加/卸特种兵**
走的还是 `show("units")` —— **整页重绘**。而单位页有**两个独立的滚动容器**
（`.rows` 单位列表 / `.detail` 详情），`w.innerHTML = ...` 一换，
两个容器都被重建 ⇒ **scrollTop 归零 ⇒ 列表跳回顶部**；
而且几百个头像 `<img>` 全部重建 ⇒ 闪一下。

**两道防线**（本文件盯着）
1. **局部刷新**：加/卸特种兵、切换候选池、候选表到位 ⇒ 只重画
   【详情】+【这一行的特种兵徽章】，列表与头像原位不动；
2. **滚动保位**：`show(p)` 整页重绘时记住并放回 `.rows` / `.detail` / `#work`
   的 scrollTop（**只对同一页生效**）。

**实测**（Edge + CDP，宽窗口 1600×1000）：
* 标记实验：加特种兵后列表 DOM **没被重建**，scrollTop 700 → 700；
* 对照实验（把保位关掉 = 旧行为）：整页重绘 ⇒ 700 → **0**（复现用户反馈）；
* 护栏实验（保位开着）：整页重绘 ⇒ 700 → 700。
"""

import io
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")


def _body(html, start, end=None):
    """截出从 `start` 开始的那一段（默认截到**下一个** `function ` 之前）。"""
    i = html.index(start)
    if end:
        j = html.index(end, i)
    else:
        k = html.find("\nfunction ", i + len(start))
        j = k if k > 0 else len(html)
    return html[i:j]


def _code(html):
    """去掉注释 —— 注释里会提到 `show("units")` 这类**历史**写法，
    断言「不许调用」时不能被注释里的字眼误伤。"""
    import re
    s = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    s = re.sub(r"(?m)^\s*//.*$", "", s)
    return s


class UnitScrollTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    # ---------------------------------------------------- ① 局部刷新
    def test_refresh_unit_local_exists(self):
        self.assertIn("function refreshUnitLocal(unitId)", self.html)

    def test_local_refresh_only_touches_detail_and_row_badges(self):
        """只重画【详情】+【这一行的徽章】—— 不许碰整个列表。"""
        body = _body(self.html, "function refreshUnitLocal(unitId)")
        self.assertIn('document.getElementById("udetail")', body)
        self.assertIn('unitDetailHTML(u)', body)
        self.assertIn(".ubadges", body)
        self.assertIn("unitBadgesHTML(u)", body)
        # 不许整体重绘
        self.assertNotIn('show("units")', _code(body))
        self.assertNotIn("innerHTML = pageUnits", _code(body))

    def test_spec_operations_use_local_refresh(self):
        """加 / 卸 / 候选池切换 / 候选表到位 —— 一律走局部刷新。"""
        cases = [
            ("function addSpec(unitId, specType)", "refreshUnitLocal(unitId)"),
            ("function removeSpec(unitId, specType, idx)", "refreshUnitLocal(unitId)"),
            ("function toggleFullPool()", "refreshUnitLocal(SEL.units)"),
        ]
        for start, expect in cases:
            body = _body(self.html, start)
            self.assertIn(expect, body, start)
            self.assertNotIn('show("units")', _code(body), start)

    def test_pickers_load_does_not_repaint_whole_page(self):
        """候选表到位（异步）也不许整页重绘。

        U104：这段改成 `ensureUnitPool(cur)`（同一个入口，pickUnit 也走它），
        到位后仍然只重画详情。
        ⚠️ `pageUnits` 里**搜索框 / 筛选器**那几处 `show("units")` 是合法的
        （列表内容真的变了 ⇒ 必须重绘），所以这里只盯**候选池那两个入口**。
        """
        page = _body(self.html, "function pageUnits(w)")
        self.assertIn("ensureUnitPool(cur)", page)
        self.assertIn("prefetchUnitPools(", page)
        for fn in ("function ensureUnitPool(u)", "function prefetchUnitPools(types)"):
            self.assertNotIn('show("units")', _code(_body(self.html, fn)), fn)

    def test_rename_does_not_repaint_whole_page(self):
        body = _body(self.html, "function commitRename(id)")
        self.assertIn("refreshUnitLocal(id)", body)
        self.assertNotIn('show("units")', _code(body))

    # ---------------------------------------------------- ② 滚动保位
    def test_show_is_a_wrapper_with_scroll_preservation(self):
        """`show(p)` = 包一层：渲染 + 记住/放回滚动位置。"""
        body = _body(self.html, "let LASTPAGE = \"\";", "function renderPage(p){")
        self.assertIn("function show(p)", body)
        self.assertIn("renderPage(p)", body)
        self.assertIn("captureScroll(w)", body)
        self.assertIn("restoreScroll(w, st)", body)
        self.assertIn("LASTPAGE", body)

    def test_scroll_restore_covers_all_three_containers(self):
        body = _body(self.html, "function restoreScroll(w, st)")
        self.assertIn("w.scrollTop", body)
        self.assertIn('".rows"', body)
        self.assertIn('".detail"', body)

    def test_restore_waits_for_layout(self):
        """恢复必须等**布局完成**（刚换完 innerHTML 时赋值会落空）。"""
        body = _body(self.html, "let LASTPAGE = \"\";", "function renderPage(p){")
        self.assertIn("requestAnimationFrame", body)

    def test_scroll_is_only_kept_on_the_same_page(self):
        """换页仍然从顶部开始（不能把上一页的滚动位置带过去）。"""
        body = _body(self.html, "let LASTPAGE = \"\";", "function renderPage(p){")
        self.assertIn("p===LASTPAGE", body)

    # ---------------------------------------------------- ③ 别退化
    def test_pick_unit_still_only_repaints_detail(self):
        """U82 的老规矩不许退化：选单位仍然只重画详情。"""
        body = _body(self.html, "function pickUnit(id)")
        self.assertIn('document.getElementById("udetail")', body)
        self.assertNotIn('show("units")', _code(body))

    def test_badges_html_is_shared(self):
        """列表行与局部刷新**共用**一份徽章 HTML（别写两遍）。"""
        self.assertIn("function unitBadgesHTML(u)", self.html)
        row = _body(self.html, "function unitRowHTML(u)", "/* U103：列表行里的特种兵徽章")
        self.assertIn("unitBadgesHTML(u)", row)

    def test_spec_slots_are_clickable_after_local_refresh(self):
        """局部刷新后，槽位与候选池的点击还得在（inline onclick ⇒ 重画后仍在）。"""
        self.assertIn('onclick="removeSpec(', self.html)
        self.assertIn("('addSpec('+u.id", self.html)


class UnitScrollWordsTest(unittest.TestCase):
    """这次没加新文案（复用已有词），但要确认词表没被弄坏。"""

    def test_i18n_still_parses(self):
        t = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                               encoding="utf-8", newline="").read())
        self.assertIn("ui", t)
        self.assertIn("errors", t)
        self.assertGreater(len(t["ui"]), 100)


if __name__ == "__main__":
    unittest.main()
