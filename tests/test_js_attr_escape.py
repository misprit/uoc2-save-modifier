# -*- coding: utf-8 -*-
"""U125：护栏 —— 前端**属性插值必须转义**（外部审阅报告 P1-8）。

**漏洞**

值直接拼进 HTML 属性 / JS 字符串：

* `src="${surf(p)}"` —— 路径里有个 `"` 就能**提前闭合属性**；
* `onclick="storeRemove('${front}','${sub}',${index})"` —— 战线名里有个 `'`
  就能**提前闭合 JS 字符串**，后面的内容被当代码执行。

**这些测试守着**

① `onclick` / `onchange` 里 `'${…}'` 的插值 ⇒ 必须走 `jsq()`
   （或 `encodeURIComponent` —— 那是另一条已验证安全的写法）；
② `src="${surf(…)}"` ⇒ 必须写成 `src="${esc(surf(…))}"`；
③ `jsq` 本身要**先按 JS 规则转义、再按 HTML 规则转义**（顺序不能反）；
④ `surf()` 必须**逐段 URL 编码**。
"""

import io
import os
import re
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


def _code(html):
    nc = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", nc)


class AttrEscapeGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with io.open(os.path.join(WEB, "index.html"),
                     encoding="utf-8", newline="") as f:
            cls.html = f.read()
        cls.code = _code(cls.html)

    # -------------------------------------------------- ① onclick 的字符串参数
    def test_onclick_string_arguments_use_jsq(self):
        """值进 **JS 单引号字符串** ⇒ 必须 `jsq()`。"""
        bad = []
        for m in re.finditer(r'on(?:click|change|input)\s*=\s*"([^"]*)"',
                             self.code):
            attr = m.group(1)
            for mm in re.finditer(r"'\$\{(.*?)\}'", attr):
                expr = mm.group(1)
                if expr.startswith("jsq("):
                    continue
                if "encodeURIComponent" in expr:
                    continue          # 那条自己处理了 `'`
                bad.append(expr)
        self.assertEqual([], bad,
                         "这些 onclick 的字符串参数没转义（要用 jsq()）：%r" % bad[:6])

    # -------------------------------------------------- ② 图片 URL
    def test_surface_urls_are_escaped_in_attributes(self):
        """`src="${surf(…)}"` ⇒ 必须 `src="${esc(surf(…))}"`。"""
        bad = re.findall(r'src="\$\{surf\(', self.code)
        self.assertEqual([], bad, "贴图 URL 没做属性转义（要 esc(surf(...))）")

    def test_no_raw_surface_path_in_attributes(self):
        """别再直接拼 `/surfaces/${…}`（路径没编码）。"""
        bad = re.findall(r'src="/surfaces/\$\{', self.code)
        self.assertEqual([], bad, "贴图路径直接拼进 src 了（要 surf()）")

    # -------------------------------------------------- ③ jsq 的转义顺序
    def test_jsq_escapes_js_first_then_html(self):
        """**JS 转义在内、HTML 转义在外** —— HTML 实体是在 JS 解析**之前**还原的，
        所以必须是「先 JS 转义 → 再 HTML 转义」，源码上就是 `esc(<JS 转义>)`。"""
        m = re.search(r"function jsq\(s\)\{(.*?)\n\}", self.code, flags=re.S)
        self.assertIsNotNone(m, "没有 jsq() 这个函数")
        body = m.group(1)
        self.assertIn("return esc(", body, "jsq 最后必须过一遍 esc()")
        self.assertIn("replace(/\\\\/g", body, "jsq 要转义反斜杠")
        self.assertIn(".replace(/'/g", body, "jsq 要转义单引号")
        self.assertLess(body.index("return esc("), body.index(".replace(/'/g"),
                       "esc() 必须包在 JS 转义**外面**（先 JS 转义，再 HTML 转义）")

    # -------------------------------------------------- ④ surf 逐段编码
    def test_surf_encodes_each_segment(self):
        m = re.search(r"function surf\(p\)\{(.*?)\n\}", self.code, flags=re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("encodeURIComponent", body, "surf 必须做 URL 编码")
        self.assertIn('split("/")', body, "surf 要逐段编码（保留 / 分隔）")


if __name__ == "__main__":
    unittest.main()
