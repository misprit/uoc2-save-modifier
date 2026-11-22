# -*- coding: utf-8 -*-
"""U154：护栏 —— 战区资产的「场景自带 / 新增」与控件 base 要**按当前这一方**取。

**曾经的 bug**

* P2-1：候选卡是**两方共用**的一张表，但「场景自带 / 新增 / 场景本来就没有」
  的判断恒用**玩家方**的 `u.scenario`
  ⇒ 切到对手方时，把「玩家场景里有」显示成「对手场景里有」。
* P2-2：数值控件的 `base`（存档原值）恒取**玩家方**的列表
  ⇒ 对手方没动过的数字也会被标成「已改动」（dirty）。

**这些测试守着**

① 徽章与说明文字按当前这一方取（`theaterSideField(u,"scenario")`）；
② 控件 base 取**当前这一方**的资产列表（`theaterSideAssets()`）；
③ 添加弹窗按**弹窗记录的那一方**取（弹窗期间切页签也不串）；
④ 「另一方有这项」提示用**阵营名**（双 local 时「对手那一方」是错的）。
"""

import io
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")


class TheaterSideFieldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    def test_the_helper_exists_and_knows_both_sides(self):
        self.assertIn("function theaterSideField(u, key, side)", self.html)
        self.assertIn("u.opponent_scenario : u.scenario", self.html)
        self.assertIn("opp ? u.in_player : u.in_opponent", self.html)

    def test_the_badges_use_the_current_side(self):
        """① 徽章不再直接读 `u.scenario`。"""
        self.assertNotIn("else if(on && !u.scenario) badge", self.html)
        self.assertNotIn("else if(u.scenario) badge", self.html)
        self.assertIn('else if(on && !theaterSideField(u,"scenario")) badge', self.html)
        self.assertIn('else if(theaterSideField(u,"scenario")) badge', self.html)

    def test_the_missing_hint_uses_the_current_side(self):
        """① 没这一项时的说明也按当前这一方。"""
        self.assertNotIn("head, u.scenario\n", self.html)
        self.assertIn('head, theaterSideField(u,"scenario")\n', self.html)

    def test_the_control_base_comes_from_the_current_side(self):
        """② base（存档原值）取当前这一方的列表。"""
        self.assertNotIn(
            "const a = ((VIEW&&VIEW.theater_assets)||[]).find(x=>x.asset===asset) || {};",
            self.html)
        self.assertIn(
            "const a = theaterSideAssets().find(x=>x.asset===asset) || {};",
            self.html)

    def test_the_add_modal_uses_its_own_recorded_side(self):
        """③ 弹窗按**弹窗记录的那一方**取（切页签也不串）。"""
        self.assertIn(
            'theaterSideField(u,"scenario", M.side||theaterSide())', self.html)

    def test_the_other_side_hint_uses_the_faction_name(self):
        """④ 另一方用**阵营名**（双 local 时「对手那一方」是错的）。"""
        self.assertIn("function theaterOtherCn()", self.html)
        self.assertIn("L2(\"<div class=\\\"talt\\\">{0}有这项（他们能用）。</div>\"",
                      self.html)


if __name__ == "__main__":
    unittest.main()
