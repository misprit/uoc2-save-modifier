# -*- coding: utf-8 -*-
"""U147：软警告**一页列全**（不再"一条一条弹、逐个同意"）。

**用户反馈**
> 现在的软警告太多了，而且需要一个个确认，后续把所有软警告放到一页里。

**改法**

| 改前 | 改后 |
|---|---|
| 点「应用更改」⇒ **逐条**弹软警告，逐个点「同意，继续」 | 确认页里**直接列出全部**软警告 ⇒ 一次确认 |
| 同一句话出现 N 次就弹 N 次 | 相同的**合并成一条** + 「×N」徽标 |
| 软警告只在应用时看得到 | 顶栏加「看提醒」⇒ 随时能看这一批改动的全部提醒（不写盘） |

**这些测试守着**

① 「逐条弹」那套（`openConfirm("warn"` / `APPLY_WARNINGS` / `applyStep`）**不许回来**；
② 确认页里**必须**列出全部软警告，且**一次确认**就写盘；
③ 相同的警告**必须合并** + 「×N」；
④ 汇总区**必须可滚动**（页���不会撑爆）；
⑤ 文案里的 `**粗体**` **先转义再加粗**（不许引入注入点）；
⑥ 「看提醒」**只读**（不写盘）。
"""

import io
import os
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


class WarningSummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    @staticmethod
    def _body(html, start, end):
        i = html.index(start)
        j = html.index(end, i + len(start))
        return html[i:j]

    # ------------------------------------------------- ① 逐条弹那套不许回来

    def test_no_more_one_by_one_warning_dialogs(self):
        self.assertNotIn('openConfirm("warn"', self.html)
        self.assertNotIn("APPLY_WARNINGS", self.html)
        self.assertNotIn("function applyStep(", self.html)

    # ------------------------------------------------------------ ② 一页列全

    def test_the_confirm_page_lists_all_warnings(self):
        body = self._body(self.html, "function openConfirm(", "/* ===")
        self.assertIn("warnBoxHTML(info.warnings||[])", body)

    def test_one_confirmation_writes_the_save(self):
        """确认一次就写盘 —— 不再逐条同意。"""
        body = self._body(self.html, "function openConfirm(", "/* ===")
        self.assertIn('onclick="reallyApply()"', body)

    def test_the_summary_helper_exists(self):
        self.assertIn("function warnBoxHTML(", self.html)

    # ------------------------------------------------------------ ③ 合并 + ×N

    def test_identical_warnings_are_merged_with_a_counter(self):
        body = self._body(self.html, "function warnBoxHTML(", "function planFiles(")
        self.assertIn("new Map()", body)
        self.assertIn("cnt.get(k)||0)+1", body)
        self.assertIn("×{0}", body)

    # ------------------------------------------------------------ ④ 可滚动

    def test_the_summary_area_scrolls(self):
        """条目很多时页面不能被撑爆 ⇒ 汇总区自己滚动。"""
        self.assertIn(".warnbox .wl{", self.html)
        self.assertIn("max-height:", self.html)
        self.assertIn("overflow:auto", self.html)

    # ------------------------------------------------------------ ⑤ 安全

    def test_bold_markup_is_escaped_first(self):
        """⚠️ 文案里的 `**粗体**` **先转义再加粗** ⇒ 不会变成注入点。"""
        body = self._body(self.html, "function mdBold(", "function warnBoxHTML(")
        self.assertIn("esc(", body)
        self.assertLess(body.index("esc("), body.index(".replace("),
                        "必须先转义、再替换粗体标记")

    # ------------------------------------------------------------ ⑥ 只读入口

    def test_the_header_has_a_reminders_button(self):
        self.assertIn('id="btnWarn"', self.html)
        self.assertIn("showWarningsOnly()", self.html)

    def test_looking_at_reminders_does_not_write(self):
        """「看提醒」只列出来，**不写盘**（只调 /api/plan）。"""
        body = self._body(self.html, "async function showWarningsOnly(",
                           "/* 确认框里点「应用更改」")
        self.assertIn("/api/plan", body)
        self.assertNotIn("/api/commit", body)

    def test_the_reminders_button_follows_the_pending_count(self):
        body = self._body(self.html, "function paintPending(",
                           "/* U55：在确认弹窗里移除某一条")
        self.assertIn("btnWarn", body)


if __name__ == "__main__":
    unittest.main()
