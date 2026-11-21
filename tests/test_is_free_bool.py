# -*- coding: utf-8 -*-
"""U131：护栏 —— `is_free` 别用 `bool()` 强转（外部审阅报告 P2-12）。

**漏洞**

`bool("false")` 是 **True** ⇒ 「改成收费」会被写成「**改成免费**」
（货架上的 `is_free=True` = 价格 0 = 白嫖）。

⇒ `_as_bool()`：只认真 bool / 0-1 整数 / 明确写着 true-false 的字符串；
认不出来就**报错**（不许默默当成 False）。

**这些测试守着**

① `_as_bool` 的各种输入；
② 加卡 / 上架时传字符串 `"false"` ⇒ 写进存档的是 **False**；
③ 传 `"maybe"` 这种认不出来的 ⇒ **报错**（不许猜）。
"""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.handlers import _as_bool  # noqa: E402

from ._fixtures import make_save  # noqa: E402


class AsBoolTest(unittest.TestCase):
    def test_real_booleans(self):
        self.assertIs(True, _as_bool(True))
        self.assertIs(False, _as_bool(False))

    def test_none_is_false(self):
        self.assertIs(False, _as_bool(None))

    def test_strings(self):
        self.assertIs(False, _as_bool("false"))
        self.assertIs(False, _as_bool("False"))
        self.assertIs(False, _as_bool("FALSE"))
        self.assertIs(False, _as_bool("  false  "))
        self.assertIs(False, _as_bool("0"))
        self.assertIs(False, _as_bool("no"))
        self.assertIs(True, _as_bool("true"))
        self.assertIs(True, _as_bool("True"))
        self.assertIs(True, _as_bool("1"))
        self.assertIs(True, _as_bool("yes"))

    def test_ints(self):
        self.assertIs(False, _as_bool(0))
        self.assertIs(True, _as_bool(1))

    def test_unrecognisable_values_return_none(self):
        """认不出来 ⇒ `None`（由调用方报错，**不许猜**）。"""
        for bad in ("maybe", "tru", 2, -1, [], {}, 1.5):
            self.assertIsNone(_as_bool(bad), "不该认：%r" % (bad,))


class IsFreeInTheSaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u131_free_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def _commit(self, edits):
        """真的**写盘**（`plan_edit` 不碰磁盘 ⇒ 要 commit 之后才看得到）。"""
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            if not plan.ok:
                return plan, None
            res = save.commit(plan)
            self.assertTrue(res.ok, res.errors)
            return plan, res

    def _cards(self):
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read("cards.yml"))

    def test_adding_a_card_with_the_string_false_stays_paid(self):
        """⭐ `"false"` 之前会被 `bool()` 变成 True（= 白嫖）。"""
        plan, _ = self._commit([Edit.card_add("air_attack_allies",
                                              is_free="false", position=3)])
        self.assertTrue(plan.ok, plan.errors)
        cards = self._cards()
        added = cards[-1]           # 槽位是核心库自动挑的 ⇒ 取最后一张
        self.assertIs(False, added["is_free"],
                      "字符串 \"false\" 被当成了 True（= 免费）")

    def test_adding_a_card_with_the_string_true_is_free(self):
        plan, _ = self._commit([Edit.card_add("air_attack_allies",
                                              is_free="true", position=3)])
        self.assertTrue(plan.ok, plan.errors)
        cards = self._cards()
        added = cards[-1]
        self.assertIs(True, added["is_free"])

    def test_an_unrecognisable_value_is_rejected(self):
        plan, _ = self._commit([Edit.card_add("air_attack_allies",
                                              is_free="maybe", position=3)])
        self.assertFalse(plan.ok, "认不出来的值不该被默默当成 False")
        self.assertTrue(any("is_free" in e for e in plan.errors),
                        "错误里要点名 is_free：%r" % plan.errors)


if __name__ == "__main__":
    unittest.main()
