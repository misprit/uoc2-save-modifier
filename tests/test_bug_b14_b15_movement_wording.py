# -*- coding: utf-8 -*-
"""B-14 + B-15：移动力上限 + 行动力/移动力文案。

**B-14**：移动力输入框必须有**上限**（= 该单位类型的基础移动力）
  ⇒ 否则能写出游戏读不出的值。

**B-15**：行动力四档的文案必须说人话（社区：「『只能转成额外移动』的说法有点令人费解」）。
  ⚠️ 用户已确认：**只优化文案** —— 存档里没有「扩展移动」这个独立字段，
  「额外移动」是**行动力转换**（游戏常量 `ap_conv`），
  ⇒ 社区设想的「基础 + 扩展」双值展示在数据上不成立，**不能照做**。
"""
import io
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")


def _read(name):
    with io.open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


class TestMovementCapAndWording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")
        with io.open(os.path.join(WEB, "i18n.json"), encoding="utf-8") as f:
            cls.i18n = json.load(f)

    # ---------- B-14：移动力输入框有上限 ----------
    def test_movement_input_has_a_cap(self):
        """移动力的 `bindNumIn` 必须给 max（= 类型的基础移动力）。"""
        i = self.html.index('bindNumIn(mpEl, {')
        chunk = self.html[i:i + 400]
        self.assertIn("max:", chunk,
                      "移动力输入框没有上限 ⇒ 能写出游戏读不出的值（B-14）")

    def test_movement_cap_comes_from_the_unit_type(self):
        """上限的来源必须是**类型的基础移动力**（`unit_types/<类型>.yml` 的 `move`）。"""
        i = self.html.index('bindNumIn(mpEl, {')
        chunk = self.html[i:i + 400]
        self.assertRegex(chunk, r"max:.*mpMax",
                         "移动力上限应取自 mpMax（类型基础移动力）")
        # mpMax 本身要从 CATALOG.unit_types 取
        j = self.html.index("const mpMax")
        self.assertIn("CATALOG", self.html[j:j + 200],
                      "mpMax 应从 CATALOG（游戏类型目录）取")

    def test_movement_cap_is_not_a_hardcoded_number(self):
        """⚠️ 上限**不能**写死一个数 —— 各单位类型的基础移动力不同。"""
        i = self.html.index('bindNumIn(mpEl, {')
        chunk = self.html[i:i + 400]
        m = re.search(r"max:\s*([^,\n]+)", chunk)
        self.assertIsNotNone(m, "没找到 max")
        self.assertNotRegex(m.group(1).strip(), r"^\d+$",
                            "移动力上限写死成数字了（各类型不同）")

    # ---------- B-15：文案说人话 ----------
    def test_action_point_options_are_plain(self):
        """四档行动力的文案不许再用「只能转成额外移动」这种费解说法。"""
        for bad in ("只能转成额外移动", "不受限：可攻击 + 可转额外移动"):
            self.assertNotIn(bad, self.html,
                             "行动力文案还在用费解的说法：%r" % bad)
        for good in ("可转为移动力", "不受限（可攻击 + 可转移动力）"):
            self.assertIn(good, self.html, "缺新文案：%r" % good)

    def test_wording_is_translated(self):
        """新文案必须在 i18n 词表里（英文界面渲染的是词表那份）。"""
        for cn in ("可转为移动力", "无行动力（不能攻击）", "受限（只能攻击）",
                   "不受限（可攻击 + 可转移动力）",
                   "0 无 · 1 可转移动力 · 2 只能攻击 · 3 不受限"):
            self.assertIn(cn, self.i18n["ui"], "词表里缺：%r" % cn)
            en = self.i18n["ui"][cn]
            self.assertTrue(en and not re.search(r"[一-鿿]", en),
                            "译文没翻或还有中文：%r ⇒ %r" % (cn, en))

    def test_old_wording_is_gone_from_the_glossary(self):
        """旧文案要从词表里清掉（不然就是孤儿词条）。"""
        for cn in ("只能转成额外移动", "没有行动力（不能攻击）", "受限：只能攻击",
                   "不受限：可攻击 + 可转额外移动"):
            self.assertNotIn(cn, self.i18n["ui"], "旧文案还在词表里：%r" % cn)


if __name__ == "__main__":
    unittest.main()
