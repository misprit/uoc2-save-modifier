# -*- coding: utf-8 -*-
r"""i18n 全面审计（U150）—— **翻译有没有效**，一键可复跑。

**查什么**

| # | 检查 | 判据 |
|---|---|---|
| ① | `L()` / `L2()` 里的中文**有没有漏译** | 三种引号（反引号 / 单引号 / **双引号**）全收 ⇒ 必须在 `ui` 段 |
| ② | **静态 HTML** 里的中文有没有漏译 | 文本节点 + `title`/`placeholder`/`data-tip`/`alt`，按**整段精确匹配**翻 ⇒ 必须在 `ui` 段 |
| ③ | 核心库 / 服务端的中文消息有没有漏译 | 必须在 `errors` 段 |
| ④ | 占位符对不对得上 | `{0}` / `{argN}` 的**顺序与个数**，中英必须一致 |
| ⑤ | 空译文 / 没翻 / 英文里还有中文 | 列出来让人看（有些是**故意**的，如量词、署名） |
| ⑥ | **孤儿词条** | 代码里已经不再产生的文案还留在词表里 ⇒ 提示清理 |

**为什么要有它**

* 以前 `tests/test_i18n.py` 的字面量正则**只认反引号与单引号**
  ⇒ **双引号**（前端最常见的那种）里的漏译一直抓不到（U150 补上）；
* 词表里留着一堆**已经不用的**旧文案（U146/U147 删掉的软警告）
  ⇒ 以后有人照着它改会白改（U150 清掉 + 这里能查出来）。

**用法**

```bat
python tools\i18n_audit.py            :: 审计（退出码 0 = 没问题）
python tools\i18n_audit.py --lang en  :: 顺便列出英文译文里仍有中文的条目
```

⚠️ **只读**：不改任何文件（发现问题自己改词表 / 源码）。
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import sys
from html.parser import HTMLParser

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")
CORE = os.path.join(REPO, "src", "save_modifier_core")
SERVER = os.path.join(REPO, "src", "save_modifier_web", "server.py")

CJK = re.compile(r"[一-鿿]")
PH = re.compile(r"\{([^{}]*)\}")
ATTRS = ("title", "placeholder", "data-tip", "alt")
#: 作者署名**故意不翻**（U98）
NO_TRANS = ("烟柳边城",)
#: **故意**空译文的条目：量词（英文里没有"个/条"）与语言名（"中文"）。
KNOWN_EMPTY = {"个", "条", "个", " 条", "中文", "中文"}


def _strip_code(html: str) -> str:
    """去掉注释（免得注释里的中文被当成字面量）。"""
    nc = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", nc)


def js_literals(nc: str) -> set:
    """`L()` / `L2()` 的字面量（**三种引号**全收）。"""
    out = set()
    for pat in (r"\bL2?\(\s*`((?:[^`\\]|\\.)*)`",
                r"\bL2?\(\s*'((?:[^'\\]|\\.)*)'",
                r"\bL2?\(\s*\"((?:[^\"\\]|\\.)*)\""):
        for raw in re.findall(pat, nc):
            s = raw.replace("\\`", "`").replace("\\'", "'").replace('\\"', '"')
            if CJK.search(s):
                out.add(s)
    return out


def all_js_strings(nc: str) -> set:
    """JS 里**所有**字符串字面量（模板也算）—— 用来判断 ui 词条是不是孤儿。"""
    out = set()
    for pat in (r"`((?:[^`\\]|\\.)*)`",
                r"\"((?:[^\"\\]|\\.)*)\"",
                r"'((?:[^'\\]|\\.)*)'"):
        for raw in re.findall(pat, nc):
            s = raw.replace("\\`", "`").replace("\\'", "'").replace('\\"', '"')
            if CJK.search(s):
                out.add(s)
    return out


def static_html_chunks(html: str):
    """静态 HTML 里的中文：文本节点 + 4 个属性（`trNode` 按**整段**匹配的就是它们）。"""
    texts, attrs = [], []

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.skip = 0

        def handle_starttag(self, tag, attrs_):
            if tag in ("script", "style"):
                self.skip += 1
                return
            for k, v in attrs_:
                if k in ATTRS and v:
                    attrs.append(v)

        def handle_endtag(self, tag):
            if tag in ("script", "style") and self.skip:
                self.skip -= 1

        def handle_data(self, data_):
            if self.skip:
                return
            t = data_.strip()
            if t:
                texts.append(t)

    p = P()
    p.feed(html)
    return texts, attrs


def _const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            else:
                nm = re.sub(r"[^0-9A-Za-z_]+", "_", ast.unparse(v.value)).strip("_")
                parts.append("{%s}" % (nm or "arg"))
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        l, r = _const(node.left), _const(node.right)
        if l is None or r is None:
            return None
        return l + r
    return None


def core_messages():
    """核心库 + 服务端里**用户看得见**的中文消息模板。"""
    out = set()
    files = [SERVER] + [os.path.join(CORE, f) for f in sorted(os.listdir(CORE))
                        if f.endswith(".py")]

    class V(ast.NodeVisitor):
        def visit_Raise(self, node):
            exc = node.exc
            if isinstance(exc, ast.Call):
                for a in list(exc.args) + [k.value for k in exc.keywords]:
                    s = _const(a)
                    if s:
                        out.add(s)
            self.generic_visit(node)

        def visit_Call(self, node):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ("append", "add"):
                for a in node.args:
                    s = _const(a)
                    if s:
                        out.add(s)
            self.generic_visit(node)

        def visit_Assign(self, node):
            for t in node.targets:
                nm = getattr(t, "id", "") or getattr(t, "attr", "")
                if nm in ("msg", "message", "error", "reason", "detail",
                          "warning", "warnings", "errors", "notes", "note",
                          "summary", "text", "why"):
                    s = _const(node.value)
                    if s:
                        out.add(s)
            self.generic_visit(node)

    for path in files:
        try:
            V().visit(ast.parse(io.open(path, encoding="utf-8").read()))
        except (OSError, SyntaxError):
            continue
    return out


def main() -> int:
    html = io.open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                               encoding="utf-8", newline="").read())
    ui = table.get("ui") or {}
    errs = table.get("errors") or {}
    vals = table.get("values") or {}

    nc = _strip_code(html)
    lits = js_literals(nc)
    every = all_js_strings(nc)
    texts, attrs = static_html_chunks(html)
    core = core_messages()

    problems = []
    hints = []

    # ① L()/L2() 的中文漏译
    miss = sorted(s for s in lits if s not in ui)
    if miss:
        problems.append(("① L()/L2() 的中文没进 ui 词表", miss))

    # ② 静态 HTML 的中文漏译
    miss2 = sorted({t for t in texts
                     if CJK.search(t) and t not in ui
                     and not any(x in t for x in NO_TRANS)})
    miss2b = sorted({v for v in attrs
                      if CJK.search(v) and v not in ui
                      and not any(x in v for x in NO_TRANS)})
    if miss2:
        problems.append(("② 静态 HTML 文本节点的中文没进 ui 词表", miss2))
    if miss2b:
        problems.append(("② 静态 HTML 属性的中文没进 ui 词表", miss2b))

    # ③ 核心库 / 服务端的消息漏译
    # ⚠️ **U150**：errors 段的键走的是**模板匹配** ⇒ 占位符的**名字不必与源码一致**
    # （源码 `f"{e.entry}：…"` ⇒ 词表里可以写 `{entry}：…`）⇒
    # 比较时**去掉占位符**、只看"骨架"是否相同。
    def _skel(t):
        return re.sub(r"\{[^}]*\}", "{}", t)

    err_skel = {_skel(k) for k in errs} | {_skel(k) for k in vals}
    miss3 = sorted(t for t in core
                   if CJK.search(t) and t not in errs
                   and _skel(t) not in err_skel)
    if miss3:
        problems.append(("③ 核心库/服务端的中文消息没进 errors 词表", miss3))

    # ④ 占位符对不上
    ph = []
    for section, tbl in (("ui", ui), ("errors", errs)):
        for zh, en in tbl.items():
            if not isinstance(en, str):
                continue
            if PH.findall(zh) != PH.findall(en):
                ph.append("[%s] %r ⇒ %r" % (section, zh[:70], en[:70]))
    if ph:
        problems.append(("④ 占位符对不上", ph))

    # ⑤ 空译文 / 没翻 / 英文里还有中文
    #    ⚠️ **量词**（" 个" / " 条"）在英文里**就该是空的**、**语言名**（"中文"）也不翻
    #    ⇒ 这两类是**故意**的，不算问题（只当提示）。
    odd, known_ok = [], []
    for section, tbl in (("ui", ui), ("errors", errs)):
        for zh, en in tbl.items():
            if not isinstance(en, str):
                continue
            if not en.strip():
                (known_ok if zh.strip() in KNOWN_EMPTY else odd).append(
                    "[%s] 空译文: %r" % (section, zh[:60]))
            elif en.strip() == zh.strip() and CJK.search(zh):
                (known_ok if zh.strip() in KNOWN_EMPTY else odd).append(
                    "[%s] 没翻: %r" % (section, zh[:60]))
            elif CJK.search(en) and not any(x in en for x in NO_TRANS):
                odd.append("[%s] 英文里还有中文: %r ⇒ %r"
                           % (section, zh[:40], en[:60]))
    if odd:
        problems.append(("⑤ 空译文 / 没翻 / 英文里还有中文", odd))
    if known_ok:
        hints.append(("⑤ 故意不翻 / 空译文的条目（提示）", known_ok))

    # ⑥ 孤儿词条（代码里已经不再产生）
    used_ui = lits | every | set(texts) | set(attrs)
    orphan_ui = sorted(k for k in ui if k not in used_ui)
    orphan_err = sorted(k for k in errs
                        if k not in core and k not in vals
                        and k not in every)
    if orphan_ui:
        # ⚠️ **只提示、不算问题**：ui 段里有一批**片段**（"取消"、"单位"、"。"）——
        # 它们是给 `trNode()` 用的（动态 HTML 的文本节点**整段**匹配），
        # 在源码里从来不是完整字面量 ⇒ "孤儿"判定对它们**不成立**。
        hints.append(("⑥ ui 段的孤儿候选（片段类的是 `trNode` 用的，不算问题）",
                      orphan_ui))
    # ⚠️ 同样按**骨架**比（占位符名可以不同）
    core_skel = {_skel(t) for t in core} | {_skel(t) for t in vals}
    orphan_err = sorted(k for k in errs
                        if _skel(k) not in core_skel)
    if orphan_err:
        # ⚠️ **只提示、不算问题**：词表条目与源码消息有多形态
        # （`%` 格式 / f-string / `+=` / 拼接）⇒ 自动判定"这条消息还在不在"不可靠。
        hints.append(("⑥ errors 段的孤儿候选（核心库已不再产生 ⇒ 可以清）",
                      orphan_err))

    print("i18n 审计：ui %d 条 / errors %d 条 / values %d 条"
          % (len(ui), len(errs), len(vals)))
    print("  L()/L2() 字面量 %d · 静态 HTML 文本 %d 段 / 属性 %d 个 · 核心库消息 %d 条"
          % (len(lits), len(texts), len(attrs), len(core)))
    if not problems:
        print("\n✅ 没问题。")
        for name, items in hints:
            print("--- 提示 · %s：%d 条" % (name, len(items)))
        return 0
    for name, items in problems:
        print("\n=== %s：%d 条" % (name, len(items)))
        for it in items[:20]:
            print("   %s" % (str(it)[:160],))
        if len(items) > 20:
            print("   ... 还有 %d 条" % (len(items) - 20))
    for name, items in hints:
        print("\n--- 提示 · %s：%d 条" % (name, len(items)))
        for it in items[:8]:
            print("   %s" % (str(it)[:140],))
        if len(items) > 8:
            print("   ... 还有 %d 条" % (len(items) - 8))
    return 1


if __name__ == "__main__":
    sys.exit(main())
