# -*- coding: utf-8 -*-
"""U74：英文支持 —— 词表与**显示层**报错翻译。

**为什么有这些测试**：英文支持是「界面层的事」，核心库一个字都不改 ⇒
中文报错是在**服务端**被翻成英文的（`server.tr_error`）。这里守着三件事：

1. **词表不能漏** —— 核心库新加一条中文报错，就得同时加一条英文译文
   （`test_core_templates_all_translated`）；
2. **前端也不能漏** —— `index.html` 里 `L()`/`L2()` 的中文得在 `ui` 词表里；
3. **翻译只在显示层** —— 中文界面时 `tr_error` 原样返回；
   英文界面时整条 / 模板 / 片段三种形态都要翻对。
"""

import ast
import io
import json
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_web import server  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")
CORE = os.path.join(REPO_SRC, "save_modifier_core")

CJK = re.compile(r"[\u4e00-\u9fff]")


# ---------------------------------------------------------------- 抽模板的工具


def _norm_ph(inner):
    name = inner.split("!")[0].split(":")[0]
    name = re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_")
    return name or "arg"


def _const_str(node):
    """常量 / f-string / `%` 拼接 / `+` 拼接 ⇒ 带 `{name}` 占位符的模板。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(v.value)
            else:
                parts.append("{%s}" % _norm_ph(ast.unparse(v.value)))
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_str(node.left)
        right = _const_str(node.right)
        if right is None and isinstance(node.right, ast.Call):
            right = "{joined}"
        if left is None or right is None:
            return None
        return left + right
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left = _const_str(node.left)
        if left is None:
            return None
        idx = [0]

        def sub(m):
            nm = "arg%d" % idx[0]
            idx[0] += 1
            return "{%s}" % nm
        return re.sub(r"%[-+ #0-9.]*[a-zA-Z]", sub, left)
    return None


def core_templates():
    """核心库里**用户看得见**的中文模板（报错 / 警告 / 摘要）。"""
    found = set()

    class V(ast.NodeVisitor):
        def visit_Raise(self, node):
            exc = node.exc
            if isinstance(exc, ast.Call):
                for a in list(exc.args) + [k.value for k in exc.keywords]:
                    s = _const_str(a)
                    if s:
                        found.add(s)
            self.generic_visit(node)

        def visit_Assign(self, node):
            names = []
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
                elif isinstance(t, ast.Attribute):
                    names.append(t.attr)
            for n in names:
                if n in ("msg", "message", "error", "reason", "detail", "why",
                         "text", "summary"):
                    s = _const_str(node.value)
                    if s:
                        found.add(s)
            self.generic_visit(node)

        def visit_AugAssign(self, node):
            t = node.target
            name = t.id if isinstance(t, ast.Name) else getattr(t, "attr", "")
            if name in ("summary", "msg", "message"):
                s = _const_str(node.value)
                if s:
                    found.add(s)
            self.generic_visit(node)

        def visit_Call(self, node):
            f = node.func
            name = getattr(f, "attr", None) or getattr(f, "id", None)
            if name in ("append", "add", "extend"):
                for a in node.args:
                    s = _const_str(a)
                    if s:
                        found.add(s)
            self.generic_visit(node)

        def visit_Dict(self, node):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value in (
                        "error", "errors", "warnings", "notes", "detail"):
                    s = _const_str(v)
                    if s:
                        found.add(s)
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            if node.name == "summary":
                for r in ast.walk(node):
                    if isinstance(r, ast.Return):
                        s = _const_str(r.value)
                        if s:
                            found.add(s)
            self.generic_visit(node)

    for fn in sorted(os.listdir(CORE)):
        if not fn.endswith(".py"):
            continue
        tree = ast.parse(io.open(os.path.join(CORE, fn), encoding="utf-8").read())
        V().visit(tree)
    return {t for t in found if CJK.search(t)}


def ui_literals():
    """`index.html` 里 `L("…")` / `L2("…")` / `L2(\`…\`)` 的中文字面量。

    模板串（反引号）里常有换行 + 缩进 ⇒ 键里也带换行。
    """
    html = io.open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    nc = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    nc = re.sub(r"(?m)^\s*//.*$", "", nc)

    def unescape(s):
        return (s.replace('\\"', '"').replace("\\'", "'")
                .replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\"))

    out = set()
    for raw in re.findall(r'\bL2?\(\s*"((?:[^"\\]|\\.)*)"', nc):
        s = unescape(raw)
        if CJK.search(s):
            out.add(s)
    for raw in re.findall(r"\bL2?\(\s*`([^`]*)`", nc):
        if CJK.search(raw):
            out.add(raw)
    # ⚠️ **单引号**也算（U77 补的 16 条就是漏在这儿）
    for raw in re.findall(r"\bL2?\(\s*'((?:[^'\\]|\\.)*)'", nc):
        s = raw.replace("\\'", "'")
        if CJK.search(s):
            out.add(s)
    # ⚠️ **U150**：以前**只**收反引号与单引号 ⇒ **双引号**的 `L("…")`（前端里最常见的那种）
    # 一直没被检查过 ⇒ 双引号里的漏译测试抓不到。现在三种引号全收。
    for raw in re.findall(r'\bL2?\(\s*"((?:[^"\\]|\\.)*)"', nc):
        s = raw.replace('\\"', '"')
        if CJK.search(s):
            out.add(s)
    return out


# ---------------------------------------------------------------- 测试


class I18nTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = json.load(io.open(os.path.join(WEB, "i18n.json"),
                                     encoding="utf-8"))

    def test_table_has_three_sections(self):
        for k in ("ui", "errors", "values"):
            self.assertIn(k, self.table)
            self.assertIsInstance(self.table[k], dict)
        self.assertGreater(len(self.table["ui"]), 100)
        self.assertGreater(len(self.table["errors"]), 100)

    def test_ui_table_covers_every_l_call(self):
        missing = sorted(s for s in ui_literals() if s not in self.table["ui"])
        self.assertEqual([], missing,
                         "index.html 里的中文没进 ui 词表：%r" % (missing[:5],))

    def test_core_templates_all_translated(self):
        missing = sorted(t for t in core_templates()
                         if t not in self.table["errors"])
        self.assertEqual([], missing,
                         "核心库的中文报错/摘要没进 errors 词表：%r" % (missing[:5],))

    def test_error_translations_keep_placeholders(self):
        ph = re.compile(r"\{([^{}]*)\}")
        for zh, en in self.table["errors"].items():
            self.assertEqual(ph.findall(zh), ph.findall(en),
                             "占位符对不上：%r -> %r" % (zh, en))

    def test_ui_translations_keep_placeholders(self):
        ph = re.compile(r"\{([^{}]*)\}")
        for zh, en in self.table["ui"].items():
            self.assertEqual(ph.findall(zh), ph.findall(en),
                             "占位符对不上：%r -> %r" % (zh, en))


class TrErrorTest(unittest.TestCase):
    """`server.tr_error` —— 显示层翻译。"""

    def setUp(self):
        self._orig = server.ui_language
        server.ui_language = lambda: "en"
        server._UI_LANG_CACHE = None

    def tearDown(self):
        server.ui_language = self._orig
        server._UI_LANG_CACHE = None

    def test_exact_match(self):
        self.assertEqual("there is nothing to write",
                         server.tr_error("没有要写入的内容"))

    def test_template_match(self):
        self.assertEqual(
            "unit U1: xp=900 is out of range (must be 0..399)",
            server.tr_error("单位 U1 的 xp=900 越界（必须 0..399）"))

    def test_fragment_match(self):
        # 核心库把几条错误用 `；` 拼成一串 ⇒ 整条匹配不上，得靠片段替换
        out = server.tr_error("❌ 单位 U1 的 xp=900 越界（必须 0..399）；"
                              "总部 hq1 的 cp：3 → 5")
        self.assertIn("unit U1: xp=900 is out of range", out)
        self.assertIn("HQ hq1: cp: 3 → 5", out)
        self.assertNotIn("越界", out)
        self.assertNotIn("总部", out)

    def test_value_translation(self):
        # 难度名是核心库写死的中文 ⇒ 按占位符名字精确替换
        self.assertEqual(
            'the hand is full (the cap for difficulty "Normal" is 5 cards) — '
            "delete one before adding",
            server.tr_error("手牌已满（本难度「普通」的上限是 5 张）—— 先删一张再添加"))

    def test_no_chinese_left(self):
        for s in ("单位 U1 的 xp=900 越界（必须 0..399）",
                  "总部 hq1 的 cp：3 → 5",
                  "存档里没有 id 为 hq1 的总部",
                  "目录不存在：D:\\nope",
                  # ⚠️ 战区资产的**字段名**是拼进**值**里的
                  #    （U161 把 `{arg1}` 挪到了 `{arg2}`）⇒ values 段得按新的
                  #    占位符名给映射，否则英文摘要里夹中文。
                  "战区资产 air_attack（盟军）：当前可用 1 → 3"):
            out = server.tr_error(s)
            self.assertFalse(CJK.search(out), "还有中文：%r -> %r" % (s, out))

    def test_non_chinese_untouched(self):
        for s in ("", None, "Unit U1", "main.yml", 42):
            self.assertEqual(s, server.tr_error(s))

    def test_chinese_ui_not_translated(self):
        server.ui_language = lambda: "chi"
        self.assertEqual("没有要写入的内容", server.tr_error("没有要写入的内容"))


class TrPayloadTest(unittest.TestCase):
    def setUp(self):
        self._orig = server.ui_language
        server.ui_language = lambda: "en"
        server._UI_LANG_CACHE = None

    def tearDown(self):
        server.ui_language = self._orig
        server._UI_LANG_CACHE = None

    def test_only_user_facing_keys_are_translated(self):
        payload = {
            "ok": False,
            "errors": ["单位 U1 的 xp=900 越界（必须 0..399）"],
            "warnings": ["没有要写入的内容"],
            "save_name": "我的存档.usg",          # 存档名**不翻**（是数据）
            "changes": [{"entry": "units.yml",
                         "notes": ["单位 U1 的 xp：9 → 400"]}],
        }
        out = server._tr_payload(payload)
        self.assertIn("is out of range", out["errors"][0])
        self.assertEqual("there is nothing to write", out["warnings"][0])
        self.assertEqual("我的存档.usg", out["save_name"])   # 数据不动
        self.assertIn("unit U1: xp: 9 → 400", out["changes"][0]["notes"][0])

    def test_chinese_ui_leaves_payload_alone(self):
        server.ui_language = lambda: "chi"
        payload = {"errors": ["没有要写入的内容"]}
        self.assertEqual(payload, server._tr_payload(payload))


class PerfGuardTest(unittest.TestCase):
    """U81：英文界面的**响应时间**护栏。"""

    def test_view_in_english_is_not_slow(self):
        """英文界面下打开一个存档要够快（曾经 23 秒 ⇒ 像「打不开」）。"""
        import time

        from ._helpers import find_saves
        saves = find_saves(limit_per_dir=1)
        if not saves:
            self.skipTest("本机没有存档 ⇒ 没法测打开存档的耗时")
        sid = str(saves[0])
        orig = server.ui_language
        server.ui_language = lambda: "en"
        try:
            t0 = time.time()
            server.api_view(sid)
            dt = time.time() - t0
        finally:
            server.ui_language = orig
        # 曾经的 bug 是 23 秒；留足余量也只要 8 秒
        self.assertLess(dt, 8.0,
                        "英文界面打开存档用了 %.1f 秒（U81 的性能回归？）" % dt)

    def test_ui_language_is_cheap(self):
        """`ui_language()` 在热路径上 ⇒ 不能每次都去扫游戏目录。"""
        import time

        t0 = time.time()
        for _ in range(200):
            server.ui_language()
        dt = time.time() - t0
        self.assertLess(dt, 3.0,
                        "ui_language() 调 200 次用了 %.1f 秒（热路径太贵）" % dt)


class LangButtonPlaceTest(unittest.TestCase):
    """U81：语言按钮只能在**启动页**（改语言会整页刷新 ⇒ 会弄丢已打开的存档）。"""

    def test_lang_button_only_in_splash(self):
        html = io.open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
        self.assertEqual(html.count('id="btnLang"'), 1,
                         "语言按钮应该只有一个")
        pos = html.index('id="btnLang"')
        app = html.index('<div id="app">')
        self.assertLess(pos, app, "语言按钮必须在启动页（主界面里不该有）")

    def test_header_has_no_lang_button(self):
        html = io.open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
        head = html[html.index('<div class="hdr">'):html.index('<div class="hdr">') + 2000]
        self.assertNotIn('id="btnLang"', head, "页头里不该再有语言按钮")


if __name__ == "__main__":
    unittest.main()
