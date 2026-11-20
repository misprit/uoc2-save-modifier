# -*- coding: utf-8 -*-
"""U83：显示名的回退链 —— **当前语言 → 英文 → 内部 id / 文件名**。

**为什么有这些测试**：朋友反馈他的 mod 加了新特种兵、**只做了英文翻译**
⇒ 游戏里显示的是他改的文件名（游戏底层本来就是英文），
而修改器退到的是内部 id / 目录名（更难看）。

⚠️ **改动必须"看不见"** —— 游戏自带资源 chi / eng **100% 覆盖**
（实测各 16776 键，差集为 0）⇒ 第一级永远命中 ⇒ 现有显示一个字符都不变。
所以这里既守**回退链本身**，也守**"游戏自带内容不走英文回退"**。
"""

import os
import sys
import unittest

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_web import server  # noqa: E402


class _FakeStore(object):
    """最小可用的 `TranslationStore` 替身。"""

    def __init__(self, data):
        self._data = data

    def get(self, key, default=""):
        return self._data.get(key, default)


class NameLookupTest(unittest.TestCase):
    """U83：回退链。"""

    def setUp(self):
        self._orig = server._tr_store
        stores = {
            "chi": _FakeStore({"id_x": "中文名", "id_both": "两边都有"}),
            "eng": _FakeStore({"id_x": "English Name",
                               "id_both": "Both Languages",
                               "id_only_en": "Only English"}),
        }
        server._tr_store = lambda loc: stores[loc]

    def tearDown(self):
        server._tr_store = self._orig

    def test_current_language_wins(self):
        pick = server._name_lookup("chi")
        self.assertEqual(pick("id_x", "fallback"), "中文名")

    def test_falls_back_to_english(self):
        """中文查不到 ⇒ 退到**英文**（mod 只做了英文翻译的情况）。"""
        pick = server._name_lookup("chi")
        self.assertEqual(pick("id_only_en", "fallback"), "Only English")

    def test_falls_back_to_internal_id(self):
        """两边都没有 ⇒ 退到内部 id / 文件名（跟旧行为一致）。"""
        pick = server._name_lookup("chi")
        self.assertEqual(pick("id_nothing", "my_mod_unit"), "my_mod_unit")

    def test_empty_key_returns_fallback(self):
        pick = server._name_lookup("chi")
        self.assertEqual(pick("", "fb"), "fb")
        self.assertEqual(pick(None, "fb"), "fb")

    def test_english_ui_uses_english_first(self):
        """英文界面：表本身就是英文，查不到就退内部 id（不重复查英文）。"""
        pick = server._name_lookup("eng")
        self.assertEqual(pick("id_x", "fb"), "English Name")
        self.assertEqual(pick("id_nothing", "fb"), "fb")

    def test_lookup_does_not_query_english_store_when_ui_is_english(self):
        """英文界面下不该再查一遍英文表（省一次查表）。"""
        calls = []
        orig = server._tr_store

        def spy(loc):
            calls.append(loc)
            return orig(loc)

        server._tr_store = spy
        try:
            server._name_lookup("eng")
        finally:
            server._tr_store = orig
        self.assertEqual(calls, ["eng"])


class BuiltinNamesUnchangedTest(unittest.TestCase):
    """游戏自带的名字**必须**还是第一级（当前语言）命中 ⇒ 不受 U83 影响。"""

    def test_builtin_specialists_use_the_current_language(self):
        from save_modifier_core import Catalog, CorePaths

        try:
            paths = CorePaths.discover()
            cat0 = Catalog(paths)
            names = cat0.spec_type_names()
        except Exception as exc:                      # 没装游戏 ⇒ 没法验
            self.skipTest("读不到游戏目录：%s" % exc)
        if not names:
            self.skipTest("本机没有游戏包")

        cat = server._catalog_payload()
        specs = cat.get("spec_types") or {}
        self.assertTrue(specs, "目录里没有特种兵")

        lang = server.data_language()
        tr = server._tr_store(lang)
        checked = 0
        for name in names:
            st = cat0.spec_type(name)
            key = getattr(st, "name_brief", None)
            if not key:
                continue
            expected = tr.get(key, "") or name
            self.assertEqual(specs.get(name, {}).get("cn"), expected,
                             "游戏自带特种兵 %s 的名字变了（不该走英文回退）" % name)
            checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
