# -*- coding: utf-8 -*-
"""U97：软警告（黄色提示）的**语义**护栏 —— 重点是「同一批编辑」造成的误报。

**背景**：U96 抓到一类 bug —— 同一批编辑是**依次执行**的，
handler 执行到某条时别的字段还没改（**中间态**）⇒ 用它判定会**误报**。
U96 修的是单位的「兵力上限」；U97 把同类的检查在核心库里**统一**修掉，
并清掉两条**永远触发不了**的死警告（U94 禁改 xp / xp_target 之后）。

**这些测试守什么**

1. 同一批里同时改 CP 与 CP 上限 ⇒ **不该**报「CP 超过上限」（两种顺序都测）；
2. 真的超限（只改 CP 不改上限）⇒ **必须**报；
3. 降低上限而当前 CP 高于它 ⇒ **必须**报；
4. 降上限时若同批也把 CP 降下来 ⇒ **不该**报；
5. `xp` / `xp_target` 现在报的是「不能手改」（U94 的口径），不是旧的两条死警告。
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

from ._fixtures import make_save  # noqa: E402

HQ = 5          # fixtures 的总部 5：cp=4, max_cp=5


class WarningSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u97_warn_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.catalog = Catalog(CorePaths.discover())
        self.save_path = self.tmp / "s.usg"
        make_save(self.save_path)

    def plan(self, edits):
        with open_save(str(self.save_path)) as save:
            return save.plan_edit(edits, catalog=self.catalog)

    def hq(self):
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        return next(h for h in hqs if h.get("id") == HQ)

    @staticmethod
    def cp_warnings(plan):
        return [w for w in plan.warnings if "CP" in w and "上限" in w]

    # ---------- ① 同批改 CP + 上限 ⇒ 不该误报 ----------
    def test_cp_and_max_cp_together_do_not_warn(self):
        """玩家把 CP 与 CP 上限一起提到 9 ⇒ 最终合法 ⇒ 不该报「超过上限」。"""
        for label, edits in (
            ("上限在前", [Edit.hq_field(HQ, "max_cp", 9),
                          Edit.hq_field(HQ, "cp", 9)]),
            ("CP 在前", [Edit.hq_field(HQ, "cp", 9),
                        Edit.hq_field(HQ, "max_cp", 9)]),
        ):
            with self.subTest(order=label):
                plan = self.plan(edits)
                self.assertTrue(plan.ok, plan.errors)
                self.assertEqual(self.cp_warnings(plan), [],
                                 "%s 误报了：%s" % (label, self.cp_warnings(plan)))

    def test_lowering_limit_with_cp_together_does_not_warn(self):
        """同时把上限降到 3、CP 降到 2 ⇒ 最终合法 ⇒ 不该报。"""
        for label, edits in (
            ("上限在前", [Edit.hq_field(HQ, "max_cp", 3),
                          Edit.hq_field(HQ, "cp", 2)]),
            ("CP 在前", [Edit.hq_field(HQ, "cp", 2),
                        Edit.hq_field(HQ, "max_cp", 3)]),
        ):
            with self.subTest(order=label):
                plan = self.plan(edits)
                self.assertTrue(plan.ok, plan.errors)
                self.assertEqual(self.cp_warnings(plan), [],
                                 "%s 误报了：%s" % (label, self.cp_warnings(plan)))

    # ---------- ② 真的超限 ⇒ 必须报 ----------
    def test_really_over_the_limit_warns(self):
        plan = self.plan([Edit.hq_field(HQ, "cp", 9)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(self.cp_warnings(plan),
                        "真的超限了却没提醒：%s" % plan.warnings)

    def test_lowering_limit_below_current_cp_warns(self):
        plan = self.plan([Edit.hq_field(HQ, "max_cp", 3)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(self.cp_warnings(plan),
                        "降上限会让 CP 被截断却没提醒：%s" % plan.warnings)

    def test_warning_mentions_the_repair(self):
        """警告要说清后果：游戏读档时按上限截断（`HQState._repair_data`）。"""
        plan = self.plan([Edit.hq_field(HQ, "cp", 9)])
        self.assertTrue(self.cp_warnings(plan))
        self.assertTrue(any("截断" in w for w in self.cp_warnings(plan)),
                        self.cp_warnings(plan))

    # ---------- ③ xp / xp_target 的口径（U94 之后） ----------
    def test_xp_reports_cannot_be_edited(self):
        plan = self.plan([Edit.hq_field(HQ, "xp", 10)])
        self.assertFalse(plan.ok)
        self.assertIn("不能手改", plan.errors[0])
        self.assertFalse(any("欠账" in w for w in plan.warnings),
                         "不该再出现旧的『欠账』警告")

    def test_xp_target_reports_cannot_be_edited(self):
        plan = self.plan([Edit.hq_field(HQ, "xp_target", 10)])
        self.assertFalse(plan.ok)
        self.assertIn("不能手改", plan.errors[0])


if __name__ == "__main__":
    unittest.main()
