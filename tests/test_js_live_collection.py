# -*- coding: utf-8 -*-
"""U110：给「工事等级点不动」补护栏（追加到 U110 的测试文件里）。

**两个根因（都是「静默」失败 ⇒ 界面看着正常、就是不动）**

1. `/* U87：解除敌方控制区的锁定。` 注释**没闭合** ⇒ `function setUnitEntr`
   整个被当成注释 ⇒ 按钮的 onclick 报
   `ReferenceError: setUnitEntr is not defined`；
2. `refreshUnitCombatFields` 用 `forEach.call(tmp.children, …)` 遍历**活的**
   HTMLCollection —— 循环体里 `old.replaceWith(child)` 把元素**移出**集合
   ⇒ 下标错位（要换的卡被跳过）⇒ 最后 `child` 是 `undefined` ⇒ 抛 TypeError
   ⇒ 异常静默、卡片不刷新。
   ⇒ 修法：`Array.from(tmp.children)`（先拷成静态数组）。
"""
import io
import os
import re
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


class TestLiveCollectionGuard(unittest.TestCase):
    """**活集合**遍历的通用护栏。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    def test_no_for_each_over_a_live_children_collection(self):
        """⚠️ `forEach.call(el.children, …)` 是**活**集合：
        循环体里一旦把元素移出（`replaceWith` / `appendChild`），
        下标就错位，最后多半抛 `TypeError`（静默失败）。
        ⇒ 一律先用 `Array.from(...)` 拷成静态数组。"""
        bad = re.findall(r"forEach\.call\([A-Za-z_$][\w$]*\.children", self.html)
        self.assertEqual([], bad,
                         "这些地方遍历的是**活**的 children 集合 ⇒ 先 Array.from")

    def test_the_combat_cards_refresh_uses_a_static_array(self):
        i = self.html.index("function refreshUnitCombatFields(")
        j = self.html.index("function unitDetailHTML(", i)
        body = self.html[i:j]
        self.assertIn("Array.from(tmp.children)", body)
        self.assertNotIn("forEach.call(tmp.children", body)

    def test_the_level_helper_is_not_swallowed_by_a_comment(self):
        """注释少写一个 `*/` ⇒ 整个函数被注释掉 ⇒ onclick 报 ReferenceError。"""
        self.assertIn("function setUnitEntr(unitId, lv)", self.html)
        # 注释里不能出现「未闭合」：函数定义前后的注释必须成对
        i = self.html.index("/* 解除敌方控制区的锁定。")
        line = self.html[i:self.html.index("\n", i)]
        self.assertTrue(line.rstrip().endswith("*/"),
                        "U87 那条注释必须闭合（少一个 */ ⇒ 整个函数被注释掉）")


if __name__ == "__main__":
    unittest.main()
