"""GUI 骨架的冒烟测试（G1）。

**测什么**
----------

1. 7 个页面都能建起来（不抛异常），且 Rail 顺序 = 规范 §2 的页面表；
2. **概览页不能有通用占位框** —— 它是唯一有真内容的页，叠了占位框
   就会在页首显示「这一页将在后续阶段实现」，与下方的真实体检结果
   自相矛盾（2026-11-18 实测踩到，已修）；
3. 概览页必须真的显示「能力位体检 / 战役进度 / 注意事项」三个面板；
4. 其余 6 页**必须**保留占位框 —— 别把「这一页还没做」的信息弄丢了；
5. 能力位判定只认能力位、不认阶段（`capability_ok`）。

⚠️ **需要能开窗**。起不来（无桌面会话 / 缺 tcl/tk）就整个跳过 ——
不要让核心库的回归测试因为 GUI 环境而挂掉。
"""

from __future__ import annotations

import unittest


def _all_text(widget) -> list[str]:
    """递归收集控件树里所有文字（用来断言页面内容）。"""
    out: list[str] = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except Exception:
            text = ""
        if text:
            out.append(str(text))
        out.extend(_all_text(child))
    return out


class GuiSmokeTest(unittest.TestCase):
    """Tk 界面的骨架断言。"""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from save_modifier_gui.app import Application
            cls.app = Application()
            cls.app.withdraw()          # 测试时别闪一个窗
        except Exception as exc:        # pragma: no cover —— 无桌面环境
            raise unittest.SkipTest(f"Tk 起不来，跳过 GUI 冒烟测试：{exc}")

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.app.destroy()
        except Exception:               # pragma: no cover
            pass

    def _page(self, cls):
        return cls(self.app, self.app)

    # ---- 页面注册表 ----

    def test_seven_pages_registered(self):
        from save_modifier_gui.pages import PAGES
        self.assertEqual(len(PAGES), 7)

    def test_page_order_matches_spec(self):
        """Rail 顺序 = 《GUI设计规范.md》§2 的页面表。"""
        from save_modifier_gui.pages import PAGES
        self.assertEqual(
            [p.key for p in PAGES],
            ["overview", "units", "specialists", "hq", "cards", "store", "theater"])

    def test_all_pages_build(self):
        from save_modifier_gui.pages import PAGES
        for cls in PAGES:
            with self.subTest(page=cls.__name__):
                page = self._page(cls)
                self.assertTrue(page.key, "页面必须有 key（Rail 靠它切页）")
                self.assertTrue(page.title, "页面必须有标题")
                self.assertTrue(page.icon, "页面必须有图标")

    # ---- 概览页（唯一有真内容的页）----

    def test_overview_has_no_generic_placeholder(self):
        """概览页**不许**叠通用占位框。"""
        from save_modifier_gui.pages.overview import OverviewPage
        page = self._page(OverviewPage)
        self.assertIsNone(page._placeholder_box)

    def test_overview_shows_real_panels(self):
        from save_modifier_gui.pages.overview import OverviewPage
        page = self._page(OverviewPage)
        texts = " ".join(_all_text(page))
        for want in ("能力位体检", "战役进度", "注意事项"):
            self.assertIn(want, texts)

    # ---- 其余 6 页：占位框要留着 ----

    def test_stub_pages_keep_placeholder(self):
        from save_modifier_gui.pages.stubs import (CardsPage, HqPage,
                                                   SpecialistsPage, StorePage,
                                                   TheaterPage, UnitsPage)
        for cls in (UnitsPage, SpecialistsPage, HqPage, CardsPage,
                    StorePage, TheaterPage):
            with self.subTest(page=cls.__name__):
                page = self._page(cls)
                self.assertIsNotNone(page._placeholder_box,
                                     f"{cls.__name__} 丢了占位框")

    # ---- 能力位判定 ----

    def test_capability_ok_only_reads_capability_bits(self):
        """能力位只认能力位，不认阶段 —— 禁用页连点都点不动。"""
        from save_modifier_gui.app import capability_ok

        class _Caps:
            can_edit_units = False
            can_edit_hqs = True
            can_edit_hand = False
            can_edit_shelf = False
            can_edit_store = True
            can_edit_theater_assets = False

        caps = _Caps()
        self.assertFalse(capability_ok(caps, "units"))
        self.assertTrue(capability_ok(caps, "hqs"))
        self.assertFalse(capability_ok(caps, "cards"))      # 手牌货架都不行
        self.assertTrue(capability_ok(caps, "store"))
        self.assertFalse(capability_ok(caps, "theater_assets"))
        self.assertTrue(capability_ok(caps, "unknown"))     # 未知项不拦


if __name__ == "__main__":
    unittest.main()
