# -*- coding: utf-8 -*-
"""U123：护栏 —— 条目 **YAML 解析失败**时整批不许写盘（外部审阅报告 P1-5）。

**漏洞**

`plan.py::Work.table()` 原来是这样：

```python
try:
    value = yamlio.load(raw)
except Exception:
    value = default          # ← 静默
```

`default` 一般是 `{}` / `[]` ⇒ **解析失败的条目被当成「空表」**
⇒ handler 在这个空表上改 ⇒ `touch(entry)` ⇒ 写盘时把**残缺内容**
写回存档（原来的内容**全没了**）。

**这些测试守着**

① 条目解析失败 ⇒ `plan.ok` 为假、**有错误说明**、**没有任何可写回的改动**；
② 提交**不会**碰到存档文件（一个字节都不改）；
③ **条目根本不存在**（`raw is None`）**不算**解析失败 ——
   那是「这个存档本来就没有这张表」，不该拦着玩家改别的东西。
"""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.plan import Work  # noqa: E402

from ._fixtures import make_save  # noqa: E402

BROKEN_STORE = b"south:\n  store: [ {equipment: infantry, \n"   # 少一个 }


class BrokenYamlGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u123_yaml_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg",
                                   extra_entries={"store.yml": BROKEN_STORE})
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def test_a_broken_entry_blocks_the_whole_batch(self):
        """⭐ 解析失败 ⇒ 这一批**不许写盘**。"""
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(
                [Edit.store_set("south", "store", 0, "price", 99)],
                catalog=self.catalog)
            self.assertFalse(plan.ok, "解析失败的存档居然通过了计划")
            self.assertEqual([], plan.changes,
                             "解析失败时不该有任何可写回的改动")
            self.assertTrue(any("解析失败" in e for e in plan.errors),
                            "错误说明里要写清是哪个文件解析失败：%r" % plan.errors)

    def test_the_error_names_the_broken_entry(self):
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(
                [Edit.store_set("south", "store", 0, "price", 99)],
                catalog=self.catalog)
            self.assertTrue(any("store.yml" in e for e in plan.errors),
                            "错误里要点名文件：%r" % plan.errors)

    def test_the_save_file_is_not_touched(self):
        """提交前先看一眼存档的字节 ⇒ 改完必须**一模一样**。"""
        before = self.save_path.read_bytes()
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(
                [Edit.store_set("south", "store", 0, "price", 99)],
                catalog=self.catalog)
            self.assertFalse(plan.ok)
        self.assertEqual(before, self.save_path.read_bytes(),
                         "存档被动过了")

    def test_the_broken_content_is_still_untouched_in_the_zip(self):
        """坏文件的内容也得原样留着（别偷偷替换成空表）。"""
        with zipfile.ZipFile(self.save_path) as zf:
            self.assertEqual(BROKEN_STORE, zf.read("store.yml"))


class MissingEntryIsNotAnErrorTest(unittest.TestCase):
    """条目**不存在** ≠ 解析失败 —— 不该拦着玩家。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u123_ok_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()

    def test_a_missing_entry_is_not_a_parse_error(self):
        with open_save(str(self.save_path), self.paths) as save:
            w = Work(save)
            value = w.table("no_such_entry.yml", {})
            self.assertEqual({}, value)
            self.assertEqual([], w.parse_errors,
                             "「没有这个条目」不该算解析失败")


if __name__ == "__main__":
    unittest.main()
