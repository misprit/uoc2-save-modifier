# -*- coding: utf-8 -*-
"""U82：单位页的三处交互修正 —— 回归护栏。

1. **选单位不再把列表弹回顶部** —— 原来 `pickUnit()` 走 `show("units")`
   （整页重绘）⇒ 列表的滚动位置被重置，每选一个单位都得重新滚回去
   （用户反馈：反人类）。
2. **「显示全部」→「显示所有特种兵」** —— 朋友反馈原文案看不懂。
3. **Alt+滚轮方向跟活跃一致** —— 原来两个分支是反的（向上滚反而让
   活跃减少），跟人的直觉相反。

这三条都是**前端**行为（`index.html` 里的 JS）⇒ Python 跑不了 JS
⇒ 这里守两样东西：
   * **源码里的关键语句**（方向一旦改反就红）；
   * 一份**等价的 Python 语义表** —— 把「方向一致」写死成可执行的规格，
     免得只靠注释说事。
"""

import io
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")
INDEX = os.path.join(WEB, "index.html")
I18N = os.path.join(WEB, "i18n.json")


def _read(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _strip_comments(src):
    """去掉注释 —— 注释里提到旧写法（比如 show("units")）不算代码。"""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    return src


def _block(src, start_marker, end_marker):
    """取 start_marker 到 end_marker（不含）之间的源码。"""
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    assert i < j, "标记顺序不对：%r / %r" % (start_marker, end_marker)
    return src[i:j]


# --------------------------------------------------------------- 规格（JS 等价）


def wheel_dir(delta_y):
    """前端 `const d = ev.deltaY>0 ? -1 : 1;` 的等价。

    滚轮**向上** ⇒ deltaY < 0 ⇒ d = +1。
    """
    return -1 if delta_y > 0 else 1


def plain_wheel(delta_y, act, sup, cap):
    """普通滚轮 = 调活跃（超过上限就消减压制补上）。"""
    d = wheel_dir(delta_y)
    if d > 0:
        a = act + 1
        if cap > 0:
            a = min(a, cap)
            over = a + sup - cap
            if over > 0:
                sup = max(0, sup - over)
        return a, sup
    a = max(0, act - 1)
    if a + sup < 1:
        a = max(0, 1 - sup)
    return a, sup


def alt_wheel(delta_y, act, sup):
    """Alt+滚轮 = 调压制（两者之和不变，方向跟活跃一致）。"""
    d = wheel_dir(delta_y)
    if d < 0:                       # 向下滚 ⇒ 活跃减、压制增
        if act < 1:
            return act, sup
        return act - 1, sup + 1
    else:                           # 向上滚 ⇒ 活跃增、压制减
        if sup < 1:
            return act, sup
        return act + 1, sup - 1


# ------------------------------------------------------------------ 测试


class PickUnitTest(unittest.TestCase):
    """U82-①：选单位**只重画详情**，不动列表。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read(INDEX)
        cls.code = _strip_comments(cls.html)

    def test_pick_unit_does_not_repaint_the_whole_page(self):
        body = _block(self.code, "function pickUnit(id){",
                      "function unitDetailHTML")
        self.assertNotIn('show("units")', body,
                         "pickUnit 不能整页重绘（会让列表滚动位置被重置）")
        self.assertIn('getElementById("udetail")', body,
                      "pickUnit 应该只重画 #udetail")
        self.assertIn("paintPending()", body,
                      "pickUnit 之后要刷新待应用改动数")

    def test_pick_unit_keeps_the_selected_row_highlighted(self):
        body = _block(self.code, "function pickUnit(id){",
                      "function unitDetailHTML")
        self.assertIn('classList.toggle("sel"', body,
                      "pickUnit 要把选中行标成 .sel（不然看不出选了谁）")


class SpecialForcesLabelTest(unittest.TestCase):
    """U82-②：「显示全部」→「显示所有特种兵」。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read(INDEX)
        cls.table = json.loads(_read(I18N))

    def test_label_wording(self):
        self.assertIn("显示所有特种兵", self.html)
        self.assertNotIn(">显示全部</label>", self.html,
                         "旧文案「显示全部」还在（朋友反馈看不懂）")

    def test_label_has_a_hover_hint(self):
        self.assertIn('title="把该单位所有可挂的特种兵都列出来', self.html,
                      "复选框要有 title 说明，否则还是看不懂")

    def test_english_translation_exists(self):
        ui = self.table["ui"]
        self.assertEqual(ui.get("显示所有特种兵"), "Show all special forces")
        self.assertNotIn("显示全部", ui, "旧词条没删干净")

    def test_tooltip_attribute_is_translated_as_a_whole(self):
        """`trNode` 是按属性**整段精确匹配**查表的 ⇒ 整段必须进词表。"""
        ui = self.table["ui"]
        tip = re.search(r'data-tip="(<b>血量条</b>[^"]+)"', self.html)
        self.assertIsNotNone(tip, "血量条的 data-tip 没找到")
        self.assertIn(tip.group(1), ui,
                      "血量条 tooltip 的整段没进 ui 词表（英文模式会留中文）")
        self.assertIn("same direction as the active force",
                      ui[tip.group(1)])


class AltWheelDirectionTest(unittest.TestCase):
    """U82-③：Alt+滚轮的方向要跟活跃兵力一致。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read(INDEX)
        cls.code = _strip_comments(cls.html)

    def _alt_block(self):
        # ⚠️ 定位用**原文**（标记里带注释），断言用**剥掉注释**的块
        return _strip_comments(_block(self.html, "if(ev.altKey){",
                                        "} else {\n        /* 普通滚轮"))

    def _plain_block(self):
        return _strip_comments(_block(self.html, "} else {\n        /* 普通滚轮",
                                        "if(a===a0 && s===s0) return;"))

    def test_delta_sign_convention_is_unchanged(self):
        self.assertIn("const d = ev.deltaY>0 ? -1 : 1;", self.html,
                      "滚轮方向的换算改了 ⇒ 护栏要先更新")

    def test_plain_wheel_grows_active_when_scrolling_up(self):
        block = self._plain_block()
        self.assertIn("if(d>0)", block)
        self.assertIn("a+=1;", block)
        self.assertIn("a-=1;", block)

    def test_alt_branch_is_not_mirrored(self):
        """U82 的核心：Alt 分支的两个方向**对调**过了。"""
        block = self._alt_block()
        # 向下滚（d<0）⇒ 压制增、活跃减
        self.assertIn("if(d<0)", block,
                      "Alt 分支的第一个条件必须还是 d<0（向下滚）")
        self.assertIn("s+=1; a-=1;", block)
        # 向上滚（d>0）⇒ 活跃增、压制减
        self.assertIn("s-=1; a+=1;", block)
        self.assertNotIn("if(d>0){ if(a<1) return; s+=1; a-=1; }", block,
                         "Alt 的方向又反回去了（U82 的原 bug）")

    def test_alt_and_active_move_in_the_same_direction(self):
        """规格：Alt+滚轮时活跃兵力的变化方向 == 普通滚轮。"""
        act, sup, cap = 5, 2, 7
        for delta_y in (-120, 120):
            pa, _ = plain_wheel(delta_y, act, sup, cap)
            aa, _ = alt_wheel(delta_y, act, sup)
            self.assertEqual(
                (aa > act), (pa > act),
                "向上/向下滚时 Alt 与普通滚轮的活跃变化方向不一致"
                "（deltaY=%d）" % delta_y)

    def test_alt_keeps_the_total_unchanged(self):
        for delta_y in (-120, 120):
            act, sup = 5, 2
            a, s = alt_wheel(delta_y, act, sup)
            self.assertEqual(a + s, act + sup,
                             "Alt+滚轮必须保持活跃+压制之和不变")

    def test_alt_respects_the_lower_bound(self):
        """活跃 + 压制 >= 1（游戏内 bug 的红线）。"""
        # 向下滚：活跃 1 → 0，压制 0 → 1（总和仍是 1，没越过红线）
        self.assertEqual(alt_wheel(120, 1, 0), (0, 1),
                         "活跃=1、压制=0 时向下滚应当是 (0, 1)")
        self.assertEqual(alt_wheel(-120, 3, 0), (3, 0),
                         "没有压制可搬运时应当静默不动")


if __name__ == "__main__":
    unittest.main()
