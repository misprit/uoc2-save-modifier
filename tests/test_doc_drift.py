# -*- coding: utf-8 -*-
"""U137：护栏 —— **文档不许漂移**（外部评价：文档债是「改不完」的根源之一）。

《开发规范与Prompt.md》自称「唯一事实源」，但它是**手写**的 ⇒ 必然漂移
（外部审阅：28 种编辑里有 10 种在规范里**查无记载**）。

本轮已经把内容补齐（§0.3 按 `EDIT_KINDS` 列全 28 种）⇒ 再加一条**护栏**：
代码里新增 / 删除一种编辑，文档**没跟上 ⇒ 测试变红**。

这是「文档由代码生成」的最省事版本：**不生成 Markdown，而是自动比对**
（生成器要处理分组、说明文字，反而更容易写错）。
"""

import io
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core.edits import EDIT_KINDS  # noqa: E402

DOCS = os.path.join(REPO, "docs")
PROMPT = os.path.join(DOCS, "开发规范与Prompt.md")
CORE_DOC = os.path.join(DOCS, "核心库调用说明.md")
EDITS_PY = os.path.join(REPO_SRC, "save_modifier_core", "edits.py")

#: §0.3 那张表里**不是 kind**、但是正文里正当的词
#: （键名 / 子商店名 / 三个作战标记列表名）。
NOT_KINDS = {
    "card_store",          # main.yml 的 card_store（货架）
    "store",               # 子商店名
    "elite_store",         # 子商店名
    "theater_assets",      # 战斗 main.yml 的键名
    "no_retreat_units",    # 作战标记的三个 id 列表
    "rearguard_units",
    "elastic_defense_units",
}


def _read(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _section(text, start, end_prefix="\n### "):
    i = text.index(start)
    j = text.index(end_prefix, i + len(start))
    return text[i:j]


class DocDriftTest(unittest.TestCase):
    """文档 ↔ 代码 的**自动比对**。"""

    @classmethod
    def setUpClass(cls):
        cls.prompt = _read(PROMPT)
        cls.core_doc = _read(CORE_DOC)
        cls.edits_src = _read(EDITS_PY)

    # -------------------------------------------------- §0.3 的编辑总表
    def _table_kinds(self):
        sec = _section(self.prompt, "### 0.3")
        tbl = sec[sec.index("| 组 | 写入目标 |"):]
        return set(re.findall(r"`([a-z][a-z0-9_]*)`", tbl))

    def test_every_edit_kind_is_in_the_prompt_table(self):
        """⭐ 新增一种编辑 ⇒ 必须同步写进《开发规范与Prompt.md》§0.3。"""
        documented = self._table_kinds()
        missing = sorted(set(EDIT_KINDS) - documented)
        self.assertEqual([], missing,
                         "这些编辑没写进《开发规范与Prompt.md》§0.3：%r" % missing)

    def test_the_prompt_table_lists_no_phantom_kinds(self):
        """文档不许写**代码里没有**的编辑（否则照文档写代码就会写出空功能）。"""
        phantom = sorted(self._table_kinds() - set(EDIT_KINDS) - NOT_KINDS)
        self.assertEqual([], phantom,
                         "《开发规范与Prompt.md》§0.3 里这些 kind 代码里没有：%r" % phantom)

    def test_the_documented_count_matches(self):
        """文档里写的「28 种」必须等于 `EDIT_KINDS` 的条数。"""
        m = re.search(r"### 0\.3 本次范围（(\d+) 种编辑）", self.prompt)
        self.assertIsNotNone(m, "§0.3 的标题里没有写「N 种编辑」")
        self.assertEqual(len(EDIT_KINDS), int(m.group(1)),
                         "§0.3 标题里的种数与 `EDIT_KINDS` 对不上")

    # -------------------------------------------------- 核心库调用说明 §4
    def _code_factories(self):
        """`Edit` 的**工厂**方法（dunder 与 `describe` 不算）。"""
        names = set(re.findall(r"^    def ([a-z_]+)\(", self.edits_src, flags=re.M))
        return {n for n in names if not n.startswith("_")} - {"describe"}

    def test_the_core_doc_lists_every_edit_factory(self):
        """《核心库调用说明.md》§4 要列出**每一个** `Edit.xxx()` 工厂。"""
        sec = _section(self.core_doc, "## 4. `Edit`", "\n### ")
        doc_factories = set(re.findall(r"^Edit\.([a-z_]+)", sec, flags=re.M))
        missing = sorted(self._code_factories() - doc_factories)
        self.assertEqual([], missing,
                         "《核心库调用说明.md》§4 没写这些工厂：%r" % missing)

    def test_the_core_doc_lists_no_phantom_factories(self):
        sec = _section(self.core_doc, "## 4. `Edit`", "\n### ")
        doc_factories = set(re.findall(r"^Edit\.([a-z_]+)", sec, flags=re.M))
        phantom = sorted(doc_factories - self._code_factories())
        self.assertEqual([], phantom,
                         "《核心库调用说明.md》§4 写了代码里没有的工厂：%r" % phantom)

    def test_the_core_doc_heading_count_matches(self):
        m = re.search(r"## 4\. `Edit` —— (\d+) 种编辑", self.core_doc)
        self.assertIsNotNone(m, "§4 的标题里没有写「N 种编辑」")
        self.assertEqual(len(EDIT_KINDS), int(m.group(1)),
                         "§4 标题里的种数与 `EDIT_KINDS` 对不上")


if __name__ == "__main__":
    unittest.main()
