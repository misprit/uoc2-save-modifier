# -*- coding: utf-8 -*-
"""U108：战区资产「调数量」界面不刷新（朋友反馈）。

反馈（2026-11-21）：
> 战区资产调数量好像没反应，删除和添加资产倒是正常生效，不过对同一个项目进行
> 多次操作之后界面不会更新……要改成界面始终呈现当前修改要求提出后的状态，
> 这个问题其实和从前卡牌区那个免费不免费改了不显示大概率是一种问题。

**根因（Edge + CDP 实测抓到的）**

① `theaterFieldCn` 是**对象**（`{to_use:L(...), …}`），`theaterSet` 却当**函数**调
   ⇒ 每次都抛 `TypeError: theaterFieldCn is not a function`
   ⇒ 数量的改动**根本没进「待应用」**、页面也不重绘；
   删除 / 添加走别的路径 ⇒ 它们正常生效（与反馈完全对上）。
② 三个字段**共用一条**待应用，`queueEdit` 的「值 == 存档原值 ⇒ 撤掉整条」
   ⇒ 把**一个**字段改回原值 ⇒ 另外两个字段的改动**一起消失**。
③ 整页重绘把**正在输入的框**换掉 ⇒ 玩家打「12」只会进「1」。

**这些测试守着**

① 字段名 helper 必须是**函数**；
② **一般化护栏**：`index.html` 里不许出现「`const` 对象被当函数调用」
   —— 那会让那个操作**静默失效**（抛异常没人看见）；
③ 改一个字段不许连累另外两个字段；
④ 重绘后要把焦点与光标放回输入框；
⑤ 界面显示的三个数必须**来自待应用**（而不是存档原值）。
"""

import io
import os
import re
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


class TheaterUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    @staticmethod
    def _body(html, start, end):
        i = html.index(start)
        j = html.index(end, i + len(start))
        return html[i:j]

    # -------------------------------------------------------------- 根因 ①

    def test_field_name_helper_is_a_function(self):
        """⚠️ 以前是**对象**却被当函数调 ⇒ 每次操作都抛异常 ⇒ 改动没进待应用。"""
        self.assertIn("function theaterFieldCn(field)", self.html)
        self.assertNotIn("const theaterFieldCn = {", self.html)

    def test_no_const_object_is_called_as_a_function(self):
        """**一般化护栏**（U108 的教训）：`const X = {…}` 是对象，
        拿它当函数调 ⇒ 运行时 `TypeError` ⇒ 那个操作**静默失效**
        （界面上看着「没反应」，改动其实压根没进待应用）。

        ⚠️ 这类错**不会**让测试变红 —— 只能静态扫出来。
        """
        html = self.html
        objs = set(re.findall(r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*\{", html))
        funcs = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", html))
        calls = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", html))
        bad = (objs & calls) - funcs
        self.assertEqual(set(), bad,
                         "这些是 const 对象，却被当函数调用了（运行时会抛 TypeError）：%r"
                         % sorted(bad))

    # -------------------------------------------------------------- 根因 ②

    def test_changing_one_field_keeps_the_others(self):
        """三个字段共用一条待应用 ⇒ 撤整条必须**按字段**判断。"""
        body = self._body(self.html, "function theaterSet(", "function theaterFieldCn(")
        self.assertIn("allSame", body)
        for f in ("to_use", "uses_total", "uses_turn"):
            self.assertIn(f, body)
        self.assertNotIn("queueEdit(", body,
                         "queueEdit 的「值 == 原值 ⇒ 撤整条」会连累另外两个字段")

    # -------------------------------------------------------------- 根因 ③

    def test_redraw_keeps_the_focus_and_the_caret(self):
        """整页重绘会把正在输入的框换掉 ⇒ 焦点与光标要放回去。"""
        body = self._body(self.html, "function theaterSet(", "function theaterFieldCn(")
        self.assertIn("activeElement", body)
        self.assertIn("focus()", body)
        self.assertIn("setSelectionRange", body)

    # ------------------------------------------------ 「界面始终呈现当前状态」

    def test_display_comes_from_the_pending_edit(self):
        """三个数必须取**待应用**里的值（否则改了不显示 —— U-cards-free-ui 同类）。"""
        body = self._body(self.html, "function theaterCur(", "function theaterSet(")
        self.assertIn('kind==="theater_asset"', body)
        self.assertIn("p.params.to_use", body)
        self.assertIn("p.params.uses_total", body)
        self.assertIn("p.params.uses_turn", body)

    def test_add_and_remove_still_work(self):
        """删除 / 添加是**另外**两条路径（本来就没坏）—— 别改坏它们。"""
        self.assertIn('setPending("theater_asset_remove"', self.html)
        self.assertIn('setPending("theater_asset_add"', self.html)


if __name__ == "__main__":
    unittest.main()
