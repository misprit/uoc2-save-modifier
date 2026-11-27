# -*- coding: utf-8 -*-
"""v1.4.3 护栏（补）：鸣谢那一行 —— **人名不翻译**。

**要求（用户 2026-11-27）**：「IQ180 的学生会会计」是**群友的名字** ⇒ 不翻译。

**这些测试守着**：
① 鸣谢那行仍存在，且**分三段**（可译 / 人名 / 可译）；
② 人名**不在 i18n 词表里** ⇒ 英文界面原样显示；
③ 人名进了审计的 `NO_TRANS` 白名单（明确标成「故意不翻」）；
④ **node 真跑 `trNode`** ⇒ 英文界面下：人名保留、其余已翻译
   （不靠推理，直接验行为）。
"""
import io
import json
import os
import re
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(REPO, "src", "save_modifier_web", "web", "index.html")
I18N = os.path.join(REPO, "src", "save_modifier_web", "web", "i18n.json")
AUDIT = os.path.join(REPO, "tools", "i18n_audit.py")

NAME = "IQ180 的学生会会计"


def read(path):
    return io.open(path, encoding="utf-8", newline="").read()


class TestThanksNameNotTranslated(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.html = read(HTML)
        cls.tbl = json.loads(read(I18N))["ui"]

    def test_thanks_line_is_split_into_three_parts(self):
        """① 鸣谢那行分三段：可译 / **人名** / 可译。"""
        m = re.search(r'<div class="thanks">(.*?)</div>', self.html, re.S)
        self.assertIsNotNone(m, "找不到鸣谢那一行")
        inner = m.group(1)
        self.assertIn("<span>特别鸣谢</span>", inner)
        self.assertIn('<span class="nm">%s</span>' % NAME, inner)
        self.assertIn("<span>的详细测试</span>", inner)

    def test_name_is_not_in_the_i18n_table(self):
        """② 人名**不在词表里** ⇒ 翻译器不会碰它。"""
        self.assertNotIn(NAME, self.tbl,
                         "人名进了词表 ⇒ 会被翻译（名字必须原样）")

    def test_translatable_parts_are_in_the_i18n_table(self):
        """可译的两段**必须在词表里** ⇒ 英文界面才能翻。"""
        self.assertIn("特别鸣谢", self.tbl)
        self.assertIn("的详细测试", self.tbl)

    def test_name_is_in_the_no_translate_whitelist(self):
        """③ 人名进了审计的 `NO_TRANS`（明确标成「故意不翻」）。"""
        audit = read(AUDIT)
        self.assertIn("NO_TRANS", audit)
        m = re.search(r"NO_TRANS\s*=\s*\((.*?)\)", audit, re.S)
        self.assertIsNotNone(m, "找不到 NO_TRANS")
        self.assertIn(NAME, m.group(1),
                      "人名没进 NO_TRANS ⇒ 审计会把它当漏译")

    @unittest.skipUnless(subprocess.run(["where", "node"], capture_output=True,
                                         shell=True).returncode == 0, "没有 node")
    def test_english_ui_keeps_the_name_and_translates_the_rest(self):
        """④ **node 真跑 `trNode`** ⇒ 英文界面：人名原样、其余已翻。

        ⚠️ 不靠推理 —— 直接把 `index.html` 里那段静态 HTML 喂给**真函数**。
        """
        line = re.search(r'<div class="thanks">.*?</div>', self.html, re.S).group(0)
        trnode = re.search(r"function trNode\(node\)\{.*?\n\}", self.html, re.S)
        self.assertIsNotNone(trnode, "找不到 trNode")
        prog = (
            "const I18N = __I18N__;\nconst LANG = 'en';\n__TRNODE__\n"
            "function run(html){\n"
            "  const out=[];\n"
            "  for(const p of html.split(/(<[^>]+>)/)){\n"
            "    if(p.startsWith('<')||!p.trim()){ out.push(p); continue; }\n"
            "    const node={nodeType:3,nodeValue:p,getAttribute:null};\n"
            "    trNode(node); out.push(node.nodeValue);\n"
            "  }\n  return out.join('');\n"
            "}\n"
            "console.log(JSON.stringify(run(__HTML__)));\n")
        prog = (prog.replace("__I18N__", json.dumps(self.tbl, ensure_ascii=False))
                    .replace("__TRNODE__", trnode.group(0))
                    .replace("__HTML__", json.dumps(line, ensure_ascii=False)))
        r = subprocess.run(["node", "-"], input=prog, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        self.assertEqual(0, r.returncode, r.stderr[-1500:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIn(NAME, out, "英文界面下人名不见了")
        self.assertNotIn("特别鸣谢", out, "「特别鸣谢」没翻译")
        self.assertNotIn("的详细测试", out, "「的详细测试」没翻译")
        self.assertIn("Special thanks to", out)


if __name__ == "__main__":
    unittest.main()
