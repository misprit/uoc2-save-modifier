# -*- coding: utf-8 -*-
"""B-2：兵库「新增兵力」下拉（社区反馈：国籍显示 'this value'、选不了国籍/兵种）。

**这个测试为什么这样写**（U188 的教训：静态断言会把 bug 锁进断言）

* 断言的**不是**源码字面量 —— 断言的是「onchange 处理器**求值后**传给
  `hqPoolEquip` 的到底是什么」。
* 覆盖**所有**出现 `onchange` + `this.value` 的地方（同一规则多处实现 ⇒ 断言要对称），
  还包括 **i18n 词表里那份英文模板**（英文界面渲染的是词表那份，不改它英文照旧坏）。
* 反证：把 bug 放回去（加引号 / 参数交叉）⇒ 必须红在**目标**断言上。
"""
import io
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")


def _read(name):
    with io.open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


#: `onchange="...."` 里的处理器正文（双引号或单引号包住整条属性）
_ONCHANGE_RE = re.compile(r'onchange="([^"]*)"')

#: 一条 onchange 里，`hqPoolEquip(` 的两个实参（按逗号切，够用：这两个都是简单表达式）
_CALL_RE = re.compile(r"hqPoolEquip\(([^,]*),([^)]*)\)")


class TestHqPoolSelectPassesRealValues(unittest.TestCase):
    """兵库下拉的 onchange 必须把**真实选中值**传出去。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")
        with io.open(os.path.join(WEB, "i18n.json"), encoding="utf-8") as f:
            cls.i18n = json.load(f)

    # ---------- ① 源码里不许有「带引号的 this.value」 ----------
    def test_no_quoted_this_value_in_any_onchange(self):
        """`this.value` 外面套引号 ⇒ 它变成**字面串** ⇒ 选什么都没用。

        ⚠️ 覆盖**所有** onchange，不只是兵库那两处 —— 同一规则多处实现，
        断言只覆盖一处就等于没覆盖。
        """
        bad = []
        for attr in _ONCHANGE_RE.findall(self.html):
            if re.search(r"['\"]this\.value['\"]", attr):
                bad.append(attr)
        self.assertEqual([], bad,
                         "onchange 里出现了**带引号**的 this.value（会被当成字面串）：%r" % bad)

    def test_no_quoted_this_value_in_the_english_template(self):
        """英文界面渲染的是 **i18n 词表那份模板** ⇒ 那里也得干净。"""
        bad = []
        for key, val in self.i18n.get("ui", {}).items():
            if not isinstance(val, str):
                continue
            for attr in _ONCHANGE_RE.findall(val):
                if re.search(r"['\"]this\.value['\"]", attr):
                    bad.append((key[:60], attr))
        self.assertEqual([], bad,
                         "i18n 词表的英文模板里有带引号的 this.value：%r" % bad)

    # ---------- ② 两个下拉的参数不能交叉 ----------
    def _pool_calls(self):
        """从兵库那个模态框的模板里，取出两条 hqPoolEquip 调用。"""
        i = self.html.find('onchange="hqPoolEquip(')
        assert i > 0, "没找到兵库下拉的 onchange"
        chunk = self.html[i - 400:i + 600]
        return _CALL_RE.findall(chunk)

    def test_equip_select_passes_new_type_and_keeps_nationality(self):
        """**兵种**下拉：第一个实参 = 新选的兵种，第二个 = **当前国籍**（不变）。"""
        calls = self._pool_calls()
        self.assertEqual(2, len(calls), "应恰好有两条 hqPoolEquip 调用，实得 %d" % len(calls))
        eq_arg, nat_arg = calls[0]
        self.assertRegex(eq_arg.strip(), r"^this\.value$",
                         "兵种下拉第一个实参应是 this.value（新选的兵种），实得 %r" % eq_arg)
        # 第二个实参 = 当前国籍的占位符（{0}）⇒ 它必须是**占位符**，
        # 不能是字面串，也不能是兵种占位符
        self.assertIn("{0}", nat_arg,
                      "兵种下拉的第二个实参应是当前国籍占位符 {0}，实得 %r" % nat_arg)
        self.assertNotIn("{2}", nat_arg,
                         "兵种下拉传了兵种占位符 {2} ⇒ 国籍会被写成兵种")

    def test_nationality_select_passes_new_nationality_and_keeps_type(self):
        """**国籍**下拉：第一个实参 = **当前兵种**（不变），第二个 = 新选的国籍。"""
        calls = self._pool_calls()
        eq_arg, nat_arg = calls[1]
        self.assertIn("{2}", eq_arg,
                      "国籍下拉的第一个实参应是当前兵种占位符 {2}，实得 %r" % eq_arg)
        self.assertRegex(nat_arg.strip(), r"^this\.value$",
                         "国籍下拉第二个实参应是 this.value（新选的国籍），实得 %r" % nat_arg)

    # ---------- ③ 候选源不能是「本次会议在售」 ----------
    def test_nationality_candidates_come_from_the_game_catalog(self):
        """国籍候选要取**游戏定义过的全部**（CATALOG.nationalities），
        不是「本次会议商店在售的」（store_universe）——
        后者是**商店**的校验口径，对兵库来说过严（U107 的同款教训）。"""
        i = self.html.find("const equipNats =")
        self.assertGreater(i, 0, "没找到 equipNats 的定义")
        line = self.html[i:self.html.find("\n", i)]
        self.assertIn("CATALOG.nationalities", line,
                      "国籍候选应取 CATALOG.nationalities，实得 %r" % line)
        self.assertNotIn("store_universe", line,
                         "国籍候选仍在用 store_universe（本次会议在售）⇒ 选不全")

    def test_equipment_candidates_come_from_the_game_catalog(self):
        """兵种候选同理，取全部兵种。"""
        i = self.html.find("const equipTypes =")
        self.assertGreater(i, 0, "没找到 equipTypes 的定义")
        line = self.html[i:self.html.find("\n", i)]
        self.assertIn("equipment_cn", line,
                      "兵种候选应取 VIEW.equipment_cn 的全部，实得 %r" % line)
        self.assertNotIn("store_universe", line,
                         "兵种候选仍在用 store_universe ⇒ 选不全")


if __name__ == "__main__":
    unittest.main()
