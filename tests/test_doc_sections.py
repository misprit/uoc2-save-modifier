# -*- coding: utf-8 -*-
"""文档一级标题**不许断号** —— 挡住「插入脚本把锚点吃掉」这个老坑。

**为什么有这条测试**：U90/U91 写文档时用 `s.replace(anchor, new)`，
把**锚点本身**替换掉了 ⇒ 章节标题消失；U92 补回来了。
U98 又踩了同一个坑（GUI 规范的「## 11. 实施路线」、
开发上下文的「## 6. 已踩过的坑（别再踩）」被吃掉），U99 补回 + 加这条护栏。

**规矩**：往文档里插内容时，必须用 **`s.replace(anchor, new + anchor)`**
（保留锚点），不要用 `s.replace(anchor, new)`。
"""

import io
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")

#: 一级标题是「## N. 标题」形式的文档（数字必须连续）
NUMBERED = ("GUI设计规范.md", "开发上下文.md", "核心库调用说明.md")


def headings(text):
    """返回 [(编号, 标题全文)]，只取 `## N. …` 这种带编号的。"""
    out = []
    for m in re.finditer(r"^## (\d+)\. (.+)$", text, re.M):
        out.append((int(m.group(1)), m.group(0)))
    return out


class TestDocSectionsNoGap(unittest.TestCase):
    """一级标题不许断号。"""

    def _read(self, name):
        return io.open(os.path.join(DOCS, name), encoding="utf-8", newline="").read()

    def test_numbered_headings_are_consecutive(self):
        for name in NUMBERED:
            hs = headings(self._read(name))
            self.assertTrue(hs, "%s 没有编号标题？" % name)
            nums = [n for n, _ in hs]
            expected = list(range(nums[0], nums[0] + len(nums)))
            self.assertEqual(nums, expected,
                             "%s 的一级标题断号了：%s" % (name, nums))

    def test_gui_spec_has_section_11(self):
        """GUI 规范必须有「## 11. 实施路线」（U98 误删过一次）。"""
        s = self._read("GUI设计规范.md")
        self.assertIn("## 11. 实施路线", s)

    def test_dev_context_has_section_6(self):
        """开发上下文必须有「## 6. 已踩过的坑（别再踩）」（U98 误删过一次）。"""
        s = self._read("开发上下文.md")
        self.assertIn("## 6. 已踩过的坑（别再踩）", s)

    def test_every_section_has_a_body(self):
        """每个编号标题后面都要有正文（不许出现「空章节」）。"""
        for name in NUMBERED:
            s = self._read(name)
            for m in re.finditer(r"^## (\d+)\. (.+)$", s, re.M):
                tail = s[m.end():m.end() + 40].lstrip("\n")
                self.assertTrue(tail.strip(),
                                "%s 的「%s」后面是空的" % (name, m.group(0)))


if __name__ == "__main__":
    unittest.main()
