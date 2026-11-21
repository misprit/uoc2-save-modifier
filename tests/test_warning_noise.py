# -*- coding: utf-8 -*-
"""U146：软警告**降噪** —— 噪音级的那些不许再回来；知识必须留在**界面说明**里。

**用户反馈**
> 现在的软警告太多了，而且需要一个个确认，后续把所有软警告放到一页里。
> 有些不是特别严重的软警告就不要报了，看的人们头皮发麻。

**甄别标准**（判据要硬）：

| 留 | 删 |
|---|---|
| 改了会**白改**（被游戏截断 / 重算 / 覆盖） | 纯**说明性**（"以后会怎样"、"这没有玩法影响"） |
| 可能**读不出来**（国籍填阵营、手牌超上限） | 玩家自己**刚做的选择**的复述（"is_free=True = 价格 0"） |
| 数据会**不自洽**（每回合恢复 > 本场景剩余） | **好消息**（"解除压制"、"专精让 CP 消耗降低"） |
| 缺了信息就**没法校验**（没有游戏包目录） | 每次都出现的**通用规则**（"货架只管这一场会议"） |

⚠️ **删警告 ≠ 丢知识**：凡是玩家可能误解游戏规则的知识点，
都要搬进**界面的静态说明**（长期能看见的地方）。

**这些测试守着**

① 那批噪音警告**不许回来**（按 AST 提取**真正的警告文本**再比对 ——
   注释里提到某个短语不算数）；
② 对应的知识**在界面说明里**（正向断言）；
③ **重要的警告不许被误删**（CP 截断 / 白改 / 不自洽 / 读不出来）；
④ 警告来源总数有上限（防"再加一批"的回潮）。
"""

import ast
import io
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(REPO, "src", "save_modifier_core")
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")

#: U146 删掉的"噪音级"警告（片段即可，用来反向断言）
NOISE = [
    "都在上限内，但**买新卡**时游戏会按新上限判断",
    "难度还决定**以后**开的新会议",
    "被压制的特种兵不提供效果",
    "只对**当前这场战斗**生效",
    "卡车数决定总部的补给作用范围",
    "解除压制 —— 生效等级回到",
    "专精会让",
    "**延迟不同可以共存**",
    "手牌上的 is_free **没有玩法影响**",
    "货架上的 is_free=True",
    "is_free=True = **价格 0**",
    "货架只管**这一场会议**",
    "price=0 表示**免费商品**",
    "战区资产**无法通过游戏内的『重置会议』撤销**",
]

#: 被删的那些知识点 —— 现在**必须**在界面说明里看得见
KNOWLEDGE = [
    ("难度还决定<b>以后</b>开的新会议", "难度页说明"),
    ("被压制时不提供效果", "特种兵槽位按钮的悬停说明"),
    ("恢复步数逐步恢复", "特种兵槽位按钮的悬停说明"),
    ("补给作用范围", "总部的卡车说明"),
    ("敌方下一回合结束前有效", "作战标记说明"),
    ("货架只管<b>这一场会议</b>", "卡牌页说明"),
    ("价格 0 = 免费商品", "商店页说明"),
    ("无法通过游戏内的『重置会议』撤销", "战区资产页说明"),
    ("延迟不同可以共存", "兵库弹窗说明"),
]

#: 重要的警告 —— **不许**被降噪误删
KEEP = [
    "超过该总部的上限",              # 会被游戏截断
    "游戏读档时按上限截断",           # 会被游戏截断
    "回合开始时游戏会把当前可用次数重置为",  # 不自洽
    "看起来是本地化 id",              # 会读错
    "看着像阵营",                    # 会读不出来
    "挂不到自己的单位上",             # 买了白买
]


def warning_texts(path):
    """抽出该文件里**所有真的 `warnings.append(...)` 的文本**（按 AST）。

    ⚠️ 不能直接扫全文 —— 注释里提到某个短语不算"报了这条警告"。
    f-string 只取其中的**字面量**部分（变量部分用 `{}` 占位）。
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out = []

    class V(ast.NodeVisitor):
        def visit_Call(self, node):
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr == "append"
                    and isinstance(f.value, ast.Attribute)
                    and f.value.attr == "warnings" and node.args):
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    out.append(a.value)
                elif isinstance(a, ast.JoinedStr):
                    parts = []
                    for v in a.values:
                        if isinstance(v, ast.Constant):
                            parts.append(str(v.value))
                        else:
                            parts.append("{…}")
                    out.append("".join(parts))
                elif isinstance(a, ast.BinOp) and isinstance(a.op, ast.Add):
                    try:
                        out.append(ast.unparse(a))
                    except Exception:
                        pass
            self.generic_visit(node)

    V().visit(tree)
    return out


class WarningNoiseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = warning_texts(os.path.join(CORE, "handlers.py"))
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    # ---------------------------------------------------------- ① 不许回来

    def test_noise_warnings_are_gone(self):
        left = [t for t in NOISE
                if any(t in w for w in self.texts)]
        self.assertEqual([], left,
                         "这些是噪音级警告，不该再每次弹：%r" % left)

    # ---------------------------------------------------------- ② 知识还在

    def test_the_knowledge_is_still_visible_in_the_ui(self):
        missing = [t for t, _ in KNOWLEDGE if t not in self.html]
        self.assertEqual([], missing,
                         "删掉软警告后，知识必须搬进界面说明：%r" % missing)

    # ---------------------------------------------------------- ③ 重要的还在

    def test_important_warnings_are_still_reported(self):
        missing = [t for t in KEEP
                   if not any(t in w for w in self.texts)]
        self.assertEqual([], missing,
                         "这些警告是『改了会白改 / 读不出来』⇒ 不许降噪：%r"
                         % missing)

    # ---------------------------------------------------------- ④ 防回潮

    def test_warning_sources_stay_under_the_cap(self):
        """警告来源总数有上限 —— 防止"再加一批说明性警告"。"""
        n = len(self.texts)
        self.assertLessEqual(n, 34,
                             "软警告来源有 %d 处（上限 34）—— 又开始刷屏了" % n)
        self.assertGreaterEqual(n, 25, "警告来源只剩 %d 处，是不是删过头了？" % n)


if __name__ == "__main__":
    unittest.main()
