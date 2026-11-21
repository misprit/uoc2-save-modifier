# -*- coding: utf-8 -*-
"""U144：战区资产的「总次数 ÷ 每回合次数」提示（软警告）。

**机制**（字节码 `state/game/game.py:1823` 回合开始 / `:1841` 消耗）：

    回合开始：to_use = uses_turn（uses_total 为 None = 无限）
               to_use = min(uses_turn, uses_total)（有限时）
    用掉一次：to_use -= 1；uses_total -= 1

⇒ `uses_total` 是**整场战斗的总预算**（游戏自己的中文文案：
「阵营N**总共**可使用次数」），`uses_turn` 是**每回合恢复**的额度。

**用户的问题**：敌方空袭"只有前三回合能用"是不是靠"总次数"实现的？
⇒ **是**：总预算 = N × 每回合额度 ⇒ 正好"前 N 个回合"。
   设计者对空袭**全部**这么写 —— 游戏包里空袭的 46 个有限值 **100% 整除**、
   存档里 203 个也 **100% 整除**（其它资产 88%–99%）。

**这条检测怎么落地**：**软警告**，不拦。
因为游戏 schema 允许不整除（`uses_total ∈ {None} ∪ 非负整数`），
不整除的**后果**只是「最后一个可用回合用不满」（浪费 `总次数 % 每回合次数` 次额度）：

    可用回合数 = ceil(总次数 / 每回合次数)

**这些测试守着**

① 公式本身（Python 侧照抄 `index.html` 的 `theaterBudgetInfo`）；
② 「无限」「0」「整除」三种情况**都不提示**；
③ 不整除时给出的回合数 / 最后一回合余量对不对；
④ `index.html` 里那三个 helper 还在、公式的关键表达式没被改掉
   （**防漂移**：前端公式改了、这边没改 ⇒ 这里红）。
"""

import io
import os
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


def theater_budget_info(uses_total, uses_turn):
    """**照抄** `index.html` 的 `theaterBudgetInfo()`（改坏了两边都会红）。

    返回 `None` = 不提示；否则 `{total, turn, rem, rounds, last}`。
    """
    if uses_total is None:
        return None
    try:
        tot = int(uses_total)
        turn = int(uses_turn)
    except (TypeError, ValueError):
        return None
    if turn < 1 or tot <= 0:
        return None
    rem = tot % turn
    if rem == 0:
        return None
    return {"total": tot, "turn": turn, "rem": rem,
            "rounds": tot // turn + 1, "last": rem}


class TheaterBudgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    # -------------------------------------------------------------- 不提示

    def test_unlimited_never_warns(self):
        """`uses_total = None` = **无限** ⇒ 没有"整除"这回事。"""
        self.assertIsNone(theater_budget_info(None, 1))
        self.assertIsNone(theater_budget_info(None, 3))

    def test_zero_never_warns(self):
        """`uses_total = 0` = 这项资产整个场景都用不了（存档里的常态），
        不是"除不尽"的问题 ⇒ 不提示。"""
        self.assertIsNone(theater_budget_info(0, 1))
        self.assertIsNone(theater_budget_info(0, 4))

    def test_divisible_never_warns(self):
        """整除 = 每个回合都用得满 ⇒ 没有可提醒的。"""
        for tot, turn in ((6, 2), (3, 1), (10, 2), (4, 4), (1, 1), (9, 3)):
            self.assertIsNone(theater_budget_info(tot, turn),
                              "%s / %s 应当不提示" % (tot, turn))

    # -------------------------------------------------------------- 要提示

    def test_reports_rounds_and_last_turn(self):
        """不整除 ⇒ 给出「一共能用几个回合」和「最后一个回合能用几次」。"""
        cases = {
            (3, 2): (2, 1),      # 回合1 用 2 次，回合2 只剩 1 次
            (6, 4): (2, 2),      # 回合1 用 4 次，回合2 只剩 2 次
            (1, 4): (1, 1),      # 只有一个回合，且用不满
            (7, 2): (4, 1),      # 3 个整回合 + 最后 1 次
            (5, 3): (2, 2),
        }
        for (tot, turn), (rounds, last) in cases.items():
            b = theater_budget_info(tot, turn)
            self.assertIsNotNone(b, "%s / %s 应当提示" % (tot, turn))
            self.assertEqual(rounds, b["rounds"])
            self.assertEqual(last, b["last"])
            self.assertEqual(tot % turn, b["rem"])
            # 可用回合数 = ceil(总次数 / 每回合次数)
            self.assertEqual(b["rounds"], -(-tot // turn))

    def test_total_used_up_never_goes_negative(self):
        """回合数不能因为「总次数 < 每回合次数」而算错。"""
        b = theater_budget_info(1, 4)
        self.assertEqual(1, b["rounds"])
        self.assertEqual(1, b["last"])

    # ------------------------------------------------------- 前端防漂移

    def test_frontend_has_the_helpers(self):
        for fn in ("function theaterBudgetInfo(",
                   "function theaterBudgetTipHTML(",
                   "function theaterModalBudgetTipHTML(",
                   "function theaterModalBudgetTipRefresh("):
            self.assertIn(fn, self.html)

    def test_frontend_formula_is_unchanged(self):
        """**防漂移**：前端公式的关键表达式还在（改了公式就得同步改这里）。"""
        self.assertIn("const rem = tot % turn;", self.html)
        self.assertIn("rounds:Math.floor(tot / turn) + 1", self.html)
        self.assertIn("if(rem === 0) return null;", self.html)

    def test_card_and_modal_show_the_hint(self):
        """卡片和添加弹窗**都要**提示（一个看存量、一个在填数时提示）。"""
        self.assertIn("theaterBudgetTipHTML(cur.uses_total, cur.uses_turn)",
                      self.html)
        self.assertIn("theaterModalBudgetTipHTML()", self.html)
        self.assertIn("mp_budget_tip", self.html)

    def test_the_hint_is_a_soft_warning(self):
        """⚠️ **不许**把它变成拦截（游戏 schema 允许不整除）——
        前端只显示提示，核心库也没有"整除"校验。"""
        self.assertIn('<div class="twarn">', self.html)
        core = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "src", "save_modifier_core")
        for fn in ("handlers.py", "edits.py"):
            txt = io.open(os.path.join(core, fn), encoding="utf-8").read()
            self.assertNotIn("整除", txt,
                             "%s 里出现了『整除』—— 这条是软警告，不该进写盘路径"
                             % fn)


if __name__ == "__main__":
    unittest.main()
