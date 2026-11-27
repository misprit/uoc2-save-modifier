# -*- coding: utf-8 -*-
"""U111：静态护栏 —— 把这批 bug 的教训**变成会红的测试**。

**为什么要有**：这批 bug（U105–U110）里最要命的都是**静默失败**：
JS 抛了异常，界面不报错、只是不响应 ⇒ 自动化测试**测不出来**。
⇒ 只能静态扫。以下四类各配一条护栏：

1. **`const` 对象 / 数组被当函数调用**（U108 的 `theaterFieldCn`）；
2. **`onclick` 指向的函数不存在**（U110 的注释没闭合）；
3. **遍历活的 HTMLCollection**（U110 的下标错位 + 静默 TypeError）；
4. **`queueEdit` 的 `base` 传成「当前显示值」**（U110 的两个字段）
   —— 改回存档原值撤不掉那条待应用 ⇒ 会留一条「改了等于没改」的待应用，
   写盘还白写一次。

外加两条：
5. 核心库的**每个 kind** 前端都要有引用（漏了 = 改了不显示 —— 卡牌「免费」那类）；
6. **全局 JS 错误提示**必须存在 —— 以后这类失败要让玩家看得见。
"""

import io
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")
CORE = os.path.join(REPO, "src", "save_modifier_core")


def _read(path):
    return io.open(path, encoding="utf-8", newline="").read()


def _code(html):
    """去掉注释（注释里的话不算代码）。"""
    nc = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", nc)


class StaticAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(os.path.join(WEB, "index.html"))
        cls.code = _code(cls.html)

    # ------------------------------------------------ ① 对象被当函数调用
    def test_no_const_object_is_called_as_a_function(self):
        """U108 的 `theaterFieldCn` 是**对象**，却被当函数调 ⇒
        每次操作都抛 TypeError ⇒ 改动**根本没进待应用**。"""
        objs = {}
        for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(\{|\[)",
                            self.code):
            objs[m.group(1)] = m.group(2)
        bad = [n for n in objs
               if re.search(r"(?<![.\w$])%s\s*\(" % re.escape(n), self.code)]
        self.assertEqual([], bad, "这些 const 对象/数组被当函数调用了：%r" % bad)

    # ------------------------------------------------ ② onclick 指向的函数
    def test_every_inline_handler_exists(self):
        handlers = set(re.findall(
            r'on(?:click|change|input|load)\s*=\s*"([A-Za-z_$][\w$]*)\s*\(', self.code))
        defined = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", self.code))
        defined |= set(re.findall(
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function",
            self.code))
        missing = sorted(handlers - defined)
        self.assertEqual([], missing,
                         "这些 onclick 指向的函数**不存在**（多半是被注释掉了）：%r" % missing)

    # ------------------------------------------------ ③ 活的 HTMLCollection
    def test_no_for_each_over_a_live_children_collection(self):
        bad = re.findall(r"forEach\.call\([A-Za-z_$][\w$]*\.children", self.html)
        self.assertEqual([], bad,
                         "这些地方遍历的是**活**的 children 集合（元素被移出 ⇒ 下标错位"
                         " + 静默 TypeError）⇒ 先 Array.from")

    # ------------------------------------------------ ④ queueEdit 的 base
    def test_queue_edit_base_is_the_original_value(self):
        """`queueEdit(kind, key, params, base, value, …)` 的 `base` 必须是
        **存档原值**（它的约定：值等于原值就撤掉这条待应用）。
        传成「当前显示值」⇒ 改回原值撤不掉 ⇒ 留一条「改了等于没改」的待应用。"""
        code = self.code
        bad = []
        for m in re.finditer(r"queueEdit\(", code):
            i = m.end()
            depth = 1
            args = []
            cur = ""
            while i < len(code) and depth:
                ch = code[i]
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth -= 1
                    if depth == 0:
                        args.append(cur.strip())
                        break
                if ch == "," and depth == 1:
                    args.append(cur.strip())
                    cur = ""
                else:
                    cur += ch
                i += 1
            if len(args) < 4:
                continue
            base = args[3]
            if "pendingVal(" in base or base.strip() == "cur":
                bad.append(base)
        self.assertEqual([], bad,
                         "这些 queueEdit 的 base 是「当前显示值」而不是存档原值：%r" % bad)

    # ------------------------------------------------ ⑤ 每个 kind 都被前端引用
    def test_every_core_kind_is_referenced_by_the_frontend(self):
        with io.open(os.path.join(CORE, "edits.py"), encoding="utf-8") as f:
            edits = f.read()
        kinds = re.findall(r'^\s+"([a-z_]+)",\s*#', edits, flags=re.M)
        self.assertGreater(len(kinds), 20, "kind 列表没解析出来")
        front = set(re.findall(r'"([a-z_]+)"', self.code))
        #: T12：界面改走 `hq_branch_level(level, suppressed)` **成对**写入
        #: （顺序无关、不会写出负数）⇒ `hq_branch_suppressed` 不再有单独的前端入口。
        #: 核心库那一侧的语义与 API **保留不动**
        #: （`tests/test_hq_branch_semantics.py` 仍守着它）—— 只是界面不再单独用它。
        #: ⚠️ 这条豁免是**显式**的：新增 kind 时不许顺手加进来（要先问「界面为什么不用它」）。
        ALLOWED_WITHOUT_FRONTEND = {"hq_branch_suppressed"}
        missing = [k for k in kinds
                   if k not in front and k not in ALLOWED_WITHOUT_FRONTEND]
        self.assertEqual([], missing,
                         "这些 kind 前端**完全没提到**（改了可能不显示）：%r" % missing)

    # ------------------------------------------------ ⑥ 全局错误提示
    def test_there_is_a_global_error_handler(self):
        """以后这类静默失败要让玩家**看得见**（U111）。"""
        self.assertIn("window.addEventListener(\"error\"", self.html)
        self.assertIn("window.addEventListener(\"unhandledrejection\"", self.html)
        self.assertIn("function showJsError(", self.html)
        self.assertIn('id="jsErr"', self.html)

    def test_the_error_toast_has_its_words(self):
        import json
        with io.open(os.path.join(WEB, "i18n.json"), encoding="utf-8") as f:
            ui = json.loads(f.read())["ui"]
        for zh in ("界面出错了（这个操作没有生效）",):
            self.assertIn(zh, ui, "词表里缺 %r" % zh)


if __name__ == "__main__":
    unittest.main()
