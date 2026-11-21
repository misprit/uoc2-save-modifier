# -*- coding: utf-8 -*-
"""U134 / U135 的护栏（外部审阅 P2-1 / P2-2）。

**P2-1**：栈顶可能**撤不了**（存档后来又被改过）⇒
界面不能一直显示「可撤销 N 条」让玩家反复点一个注定失败的按钮。

⇒ 服务端算 `undoable`（从栈顶往下还有几条基准成立）⇒
界面据此**禁用撤销按钮**、标出「已过期」的记录。
⚠️ **不弹栈** —— 玩家把存档从备份还原回来之后，它又能撤了
（仓库护栏 `test_stack_survives_rejected_undo`）。

**P2-2**：写盘 / 撤销之后**撤销栈与备份列表都变了** ⇒ 必须重新拉。

**这些测试守着**

① 栈顶过期 ⇒ `undoable` = 0（且记录**还在**栈里）；
② 栈正常 ⇒ `undoable` = 记录条数；
③ 界面：撤销按钮有 id、按 `undoable` 禁用；
④ 界面：应用 / 撤销之后要**重新拉**撤销栈。
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.undo import baseline_ok, load_stack  # noqa: E402
from save_modifier_core.writer import write_overlay  # noqa: E402
from save_modifier_web import server  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO, "src", "save_modifier_web", "web")


class UndoableCountTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u134_undo_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        # 服务端的 save_id 必须落在**游戏数据目录**之内（U126）
        self._old_app = os.environ.get("UOC2_APPDATA")
        os.environ["UOC2_APPDATA"] = str(self.tmp)
        self.addCleanup(self._restore_app)

    def _restore_app(self):
        if self._old_app is None:
            os.environ.pop("UOC2_APPDATA", None)
        else:
            os.environ["UOC2_APPDATA"] = self._old_app

    def commit(self, value):
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit([Edit.progress("prestige", value)],
                                   catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        return res

    def test_a_fresh_stack_is_fully_undoable(self):
        self.commit(5)
        d = server.api_undo_stack(str(self.save_path))
        self.assertEqual(1, d["count"])
        self.assertEqual(1, d["undoable"], "刚写完的那条应该能撤")
        self.assertTrue(d["undo_available"])

    def test_a_stale_top_record_is_reported_as_not_undoable(self):
        """⭐ 存档后来又被改过 ⇒ 栈顶撤不了 ⇒ 如实报 `undoable = 0`。"""
        self.commit(5)
        # 模拟「游戏自己存了档」（不走撤销栈）
        res = write_overlay(self.save_path, {"main.yml": b"prestige: 999\n"})
        self.assertTrue(res.ok, res.errors)
        d = server.api_undo_stack(str(self.save_path))
        self.assertEqual(1, d["count"], "记录**不许**被悄悄丢掉")
        self.assertEqual(0, d["undoable"], "撤不了的记录不该算进可撤销数")
        self.assertFalse(d["undo_available"])

    def test_the_record_stays_in_the_stack(self):
        """⚠️ 仓库护栏：拒绝撤销**不弹栈** —— 还原备份之后它又能撤了。"""
        self.commit(5)
        write_overlay(self.save_path, {"main.yml": b"prestige: 999\n"})
        records, _ = load_stack(self.save_path)
        self.assertEqual(1, len(records), "撤不了的记录不该被丢掉")
        self.assertFalse(baseline_ok(self.save_path, records[-1]))


class UndoUiTest(unittest.TestCase):
    """界面侧的静态护栏。"""

    @classmethod
    def setUpClass(cls):
        with io.open(os.path.join(WEB, "index.html"),
                     encoding="utf-8", newline="") as f:
            cls.html = f.read()

    def test_the_undo_button_has_an_id(self):
        """按钮要被禁用 ⇒ 得有 id。"""
        self.assertIn('id="btnUndo"', self.html)

    def test_the_button_follows_the_undoable_count(self):
        self.assertIn("undoable", self.html)
        self.assertIn("ub.disabled", self.html)

    def test_expired_records_are_marked(self):
        self.assertIn("已过期，撤不了", self.html)

    def test_the_stack_is_reloaded_after_commit_and_undo(self):
        """P2-2：写盘 / 撤销之后都要重新拉撤销栈。"""
        self.assertIn("function refreshUndoStack(", self.html)
        self.assertIn("await refreshUndoStack();", self.html)
        # 两处调用：commit 之后 + undo 之后
        self.assertGreaterEqual(self.html.count("await refreshUndoStack();"), 2)


if __name__ == "__main__":
    unittest.main()
