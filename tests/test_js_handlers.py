# -*- coding: utf-8 -*-
"""U110：单位详情的「工事等级」点不动 + **一般化护栏**（onclick 指向的函数必须存在）。

**根因**：`/* U87：解除敌方控制区的锁定。` 这条注释**没写闭合的 `*/`** ⇒
它把后面的 `function setUnitEntr(unitId, lv){…}` **整个当成了注释** ⇒
按钮的 `onclick="setUnitEntr(...)"` 一按就报
`ReferenceError: setUnitEntr is not defined` ⇒ **界面看着正常、点不动**。

**为什么要有「一般化护栏」**：JS 里的异常是**静默**的（事件处理函数抛异常，
界面没有任何提示）⇒ 自动化测试**测不出来**，只能静态扫。
⇒ `index.html` 里每一个 `onclick` / `onchange` / `oninput` 指向的函数
**必须真的存在** —— 漏一个 `*/` 就会把整个函数注释掉，这类错一次只能靠
「浏览器里点一下」发现。
"""

import io
import os
import re
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


class JsHandlerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        # 去掉注释与行注释（注释里的话不算代码）
        nc = re.sub(r"/\*.*?\*/", "", cls.html, flags=re.S)
        nc = re.sub(r"(?m)^\s*//.*$", "", nc)
        cls.code = nc

    def _handlers(self):
        return set(re.findall(
            r'on(?:click|change|input|load)\s*=\s*"([A-Za-z_$][\w$]*)\s*\(', self.code))

    def _defined(self):
        out = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", self.code))
        out |= set(re.findall(
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function", self.code))
        out |= set(re.findall(
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\([^)]*\)\s*=>", self.code))
        return out

    def test_every_inline_handler_exists(self):
        """⭐ **一般化护栏**（U110）——
        onclick 指向的函数必须存在；少一个 `*/` 就会把函数注释掉，
        按钮点下去报 `ReferenceError` ⇒ **界面看着正常、点不动**。"""
        missing = sorted(self._handlers() - self._defined())
        self.assertEqual([], missing,
                         "这些 onclick 指向的函数**不存在**（多半是被注释掉了）：%r" % missing)

    def test_the_scan_actually_catches_something(self):
        """护栏本身要**有效** —— 故意删掉一个函数名，必须被抓出来。"""
        broken = self.code.replace("function setUnitEntr(", "function _gone(", 1)
        missing = set(re.findall(
            r'on(?:click|change|input|load)\s*=\s*"([A-Za-z_$][\w$]*)\s*\(', broken))
        defined = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", broken))
        self.assertIn("setUnitEntr", missing - defined,
                      "护栏没抓到被注释掉的 handler ⇒ 护栏本身坏了")

    def test_the_handler_count_is_reasonable(self):
        """扫出来的 handler 不能少得离谱（正则写坏了要能发现）。"""
        self.assertGreater(len(self._handlers()), 30)


class TestEntrLevelUi(unittest.TestCase):
    """「工事等级（单位驻垒等级）」那一档。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    def test_the_helper_exists(self):
        self.assertIn("function setUnitEntr(unitId, lv)", self.html)

    def test_the_three_level_buttons_are_rendered(self):
        for lv in (0, 1, 2):
            self.assertIn("onclick=\"setUnitEntr(${u.id},%d)\"" % lv, self.html)

    def test_the_queue_uses_the_original_value_as_base(self):
        """`queueEdit` 的 `base` 必须是**存档原值** ⇒
        「改回原值」会撤掉那条待应用，而不是留一条改了等于没改的。"""
        i = self.html.index("function setUnitEntr(")
        j = self.html.index("function setUnitAp(", i)
        body = self.html[i:j]
        self.assertIn("const base = (u.entr==null)?0:u.entr;", body)
        self.assertIn("base, lv,", body)

    def test_the_ap_helper_has_the_same_fix(self):
        i = self.html.index("function setUnitAp(")
        j = self.html.index("function refreshUnitCombatFields(", i)
        body = self.html[i:j]
        self.assertIn("const base = (u.ap==null)?0:u.ap;", body)

    def test_the_core_accepts_the_entr_field(self):
        """核心库那边 `entr` 是能写的（U85）—— 界面别把门堵死。"""
        from save_modifier_core import Edit
        e = Edit.unit_field(1, "entr", 2)
        self.assertEqual("unit_field", e.kind)
        self.assertEqual(2, e.params["value"])


if __name__ == "__main__":
    unittest.main()
