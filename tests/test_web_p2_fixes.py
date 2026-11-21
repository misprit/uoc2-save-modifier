# -*- coding: utf-8 -*-
"""U127 / U128 / U129 / U130 的护栏（前端四个 P2 问题）。

* **U127**（P2-18）：总部分支名的翻译必须**调用时**做，不能模块级求值；
* **U128**（P2-9）：候选池读取失败**不许静默**；
* **U129**（P2-10）：改名后左侧列表要**跟着显示新名字**；
* **U130**（P2-8）：数值输入框不许**吞掉第一次合法输入**。
"""

import io
import os
import re
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


def _read():
    with io.open(os.path.join(WEB, "index.html"),
                 encoding="utf-8", newline="") as f:
        return f.read()


def _code(html):
    nc = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", nc)


class BranchNameI18nTest(unittest.TestCase):
    """U127：分支名的翻译不能是模块级求值。"""

    @classmethod
    def setUpClass(cls):
        cls.code = _code(_read())

    def test_branch_cn_is_not_a_module_level_map(self):
        """`const BRANCH_CN = {…L(…)}` ⇒ 加载那一刻就定型了。"""
        self.assertIsNone(re.search(r"const\s+BRANCH_CN\s*=", self.code),
                          "BRANCH_CN 还是模块级求值（切语言后不跟着变）")

    def test_branch_cn_is_a_function(self):
        self.assertIn("function branchCn(", self.code)
        m = re.search(r"function branchCn\(br\)\{(.*?)\n\}", self.code, flags=re.S)
        self.assertIsNotNone(m)
        self.assertIn('L("工程")', m.group(1))
        self.assertIn('L("兵库")', m.group(1))

    def test_every_branch_name_use_goes_through_the_function(self):
        self.assertNotIn("BRANCH_CN[", self.code,
                         "还有地方直接读 BRANCH_CN（旧的模块级表）")


class PickerErrorVisibleTest(unittest.TestCase):
    """U128：候选池读取失败要**看得见**。"""

    @classmethod
    def setUpClass(cls):
        cls.code = _code(_read())

    def test_the_failure_is_remembered(self):
        self.assertIn("let PICKERR", self.code)

    def test_load_pickers_failures_are_not_swallowed(self):
        self.assertIsNone(
            re.search(r"loadPickers\([^)]*\)[\s\S]{0,200}?\.catch\(\(\)=>\{}\)",
                      self.code),
            "loadPickers 的失败又被吞掉了（界面会永远停在「正在读取…」）")

    def test_load_pickers_failures_are_handled(self):
        hits = re.findall(r"loadPickers\([^)]*\)[\s\S]{0,200}?\.catch\(([^)]*)=>",
                          self.code)
        self.assertTrue(hits, "loadPickers 的失败必须有人接")

    def test_the_pool_area_shows_the_error(self):
        self.assertIn("特种兵候选池读取失败：", self.code)


class RenameEchoTest(unittest.TestCase):
    """U129：改名（待应用）要立刻在界面上体现。"""

    @classmethod
    def setUpClass(cls):
        cls.code = _code(_read())

    def _slice(self, start, end):
        i = self.code.index(start)
        j = self.code.index(end, i)
        return self.code[i:j]

    def test_the_unit_list_row_uses_the_pending_name(self):
        body = self._slice("function unitRowHTML", "function unitBadgesHTML")
        self.assertIn("pendingVal(", body,
                      "单位列表行的名字没走 pendingVal ⇒ 改名后看着还是旧的")

    def test_the_unit_detail_uses_the_pending_name(self):
        body = self._slice("function unitDetailHTML", "function pageUnits")
        self.assertIn("pendingVal(", body)

    def test_the_hq_row_and_detail_use_the_pending_name(self):
        self.assertIn("pendingVal(",
                      self._slice("function hqRowHTML", "function hqDetailHTML"))
        self.assertIn("pendingVal(",
                      self._slice("function hqDetailHTML", "function pageHqs"))

    def test_the_local_refresh_updates_the_row_name(self):
        body = self._slice("function refreshUnitLocal", "function unitDetailHTML")
        self.assertIn(".unm", body,
                      "局部刷新没更新列表行里的名字（只刷了徽章）")


class BindNumInTest(unittest.TestCase):
    """U130：数值输入框不许吞掉第一次合法输入。"""

    @classmethod
    def setUpClass(cls):
        cls.code = _code(_read())

    def _body(self):
        i = self.code.index("function bindNumIn(")
        j = self.code.index("function queueEdit(", i)
        return self.code[i:j]

    def test_init_is_consumed_at_the_very_beginning(self):
        """`init = false` 必须**在**「值非法就 return」**之前**。"""
        body = self._body()
        self.assertIn("const isInit = init;", body)
        self.assertIn("init = false;", body)
        self.assertLess(body.index("init = false;"), body.index("if(bad)"),
                        "init 还是在校验之后才置 false ⇒ 第一次合法输入会被吞")

    def test_the_initial_call_still_does_not_fire_the_callback(self):
        """U38 的教训：初始化就回调 ⇒ 无限递归。必须保住。"""
        body = self._body()
        self.assertIn("if(isInit) return;", body)
        self.assertNotIn("if(init){ init = false; return; }", body)


if __name__ == "__main__":
    unittest.main()
