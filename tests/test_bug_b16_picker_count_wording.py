# -*- coding: utf-8 -*-
"""B-16：「可用数目」的文案必须说清口径。

**社区原话**：「新增特种兵选显示全部时右侧给出的可用数目应该是指当前战役已经出场的特种数目？
这个说法有点费解。」

**根因**：两个模态框的写法**不一致** ——
商店模态写的是 `{5} 种`（**光秃秃一个数，没说是什么**），
兵库模态写的是 `玩家可用 {1} 种`（说明了口径）。
⇒ 社区看到的是商店那个 ⇒ 不知道那个数是什么。

**验收**：两个模态**都要**说明两个数字的口径：
* 「玩家可用 N 种」= 玩家挂得上的数量
* 「显示全部（游戏定义过的 M 种）」= 游戏定义过的**全部**特种兵
  （**不是**社区猜的「当前战役已经出场的」⇒ 那个是 `campaign_pool`）
"""
import io
import json
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")


def _read(name):
    with io.open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


class TestPickCountsHaveClearWording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")
        with io.open(os.path.join(WEB, "i18n.json"), encoding="utf-8") as f:
            cls.i18n = json.load(f)

    def _picker_templates(self):
        """所有带「显示全部」勾选框的模板（商店 / 兵库 / 卡牌）。"""
        return [k for k in self.i18n["ui"] if "spick_all" in k]

    def test_both_pickers_state_the_available_count(self):
        """两个模态都要写「玩家可用 N 种」。"""
        tpls = self._picker_templates()
        self.assertGreaterEqual(len(tpls), 2, "找不到两个选择器模板")
        for k in tpls:
            self.assertIn("玩家可用", k,
                          "选择器模板里没有说明「可用」的含义：%r" % k[:90])

    def test_both_pickers_state_what_show_all_means(self):
        """「显示全部」的那个数必须说明是**游戏定义过的全部**。

        ⚠️ 社区猜的是「当前战役已经出场的特种数目」⇒ 那其实是 `campaign_pool`
        （另一个口径）⇒ 文案不写清楚就会误导。
        """
        for k in self._picker_templates():
            self.assertIn("游戏定义过的", k,
                          "「显示全部」没说明口径（是游戏定义过的全部，不是战役在场的）：%r"
                          % k[:90])

    def test_no_bare_count_without_a_label(self):
        """不许再出现**光秃秃**的 `{N} 种`（没说明是什么的数）。"""
        for k in self._picker_templates():
            self.assertNotIn('<span class="spc">{', k,
                             "选择器里还有没标注的裸数字：%r" % k[:90])

    def test_html_and_glossary_agree(self):
        """index.html 与 i18n 词表里的文案要一致（英文界面渲染的是词表那份）。"""
        for k in self._picker_templates():
            self.assertIn("玩家可用 {", k)
            self.assertIn("游戏定义过的 {", k)
        # index.html 里也要有对应的说法
        self.assertIn("玩家可用 {", self.html)
        self.assertIn("游戏定义过的 {", self.html)


if __name__ == "__main__":
    unittest.main()
