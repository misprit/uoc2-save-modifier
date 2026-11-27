# -*- coding: utf-8 -*-
"""U112：总部的「压制 / 等级」必须按**游戏的语义**来。

**游戏的语义**（`branch_suppress`，e166 字节码）：

    压制 N 级 ⇒ **生效等级 −N**、被压制数 **+N**，
    而「真实等级 = 等级 + 被压制」**不变**。

⚠️ **界面之前是反的**（把两个数当独立的）：
* 点「压制 +1」⇒ 生效等级不变、被压制 +1 ⇒ 真实等级**反而变大** ⇒ 白送一级；
* 「压制 +1」再「等级 +1」能写出「等级 3 + 被压制 1 = 4」
  ⇒ **游戏读档会失败**（硬上限 = 解锁到几级 ≤ 3）。

**这些测试守着**
① 核心库：压制 ⇒ 生效等级自动下调、真实等级不变；
② 核心库：**不管有没有传 suppressed**，都要查「等级 + 被压制 ≤ 3」
   （界面那条「只改等级」的路以前绕过了 ⇒ 能写出打不开的存档）；
③ 界面：压制按钮走核心库**专门的** `hq_branch_suppressed`；
④ 界面：显示用**投影**（按待应用的先后顺序重放）。
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
import zipfile

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")

#: 合成存档里 hq 5 的 `operations` 分支：等级 2、被压制 0
BRANCH = "operations"
HQ = 5


class BranchSemanticsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u112_branch_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def commit(self, edits):
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            if not plan.ok:
                return plan, None
            return plan, save.commit(plan)

    def branch(self):
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        h = [x for x in hqs if x.get("id") == HQ][0]
        return h["branch_levels"][BRANCH]


class TestSuppressSemantics(BranchSemanticsTestBase):
    def test_suppress_lowers_the_effective_level(self):
        """压制 1 级 ⇒ 生效等级 2→1、被压制 0→1、**真实等级不变**。"""
        plan, res = self.commit([Edit.hq_branch_suppressed(HQ, BRANCH, 1)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        node = self.branch()
        self.assertEqual(1, node["level"], "生效等级应下调一级")
        self.assertEqual(1, node["suppressed"], "被压制数应 +1")
        self.assertEqual(2, node["level"] + node["suppressed"], "真实等级应不变")

    def test_raising_the_level_above_the_limit_is_rejected(self):
        """⚠️ 被压制 1 时把等级提到 3 ⇒ 3+1=4 > 3 ⇒ **游戏读档会失败** ⇒ 必须拦。"""
        plan, _ = self.commit([Edit.hq_branch_suppressed(HQ, BRANCH, 1)])
        self.assertTrue(plan.ok, plan.errors)
        plan, _ = self.commit([Edit.hq_branch_level(HQ, BRANCH, 3)])
        self.assertFalse(plan.ok, "等级 3 + 被压制 1 超上限，必须被拦")
        self.assertTrue(any("超过上限" in e for e in plan.errors), plan.errors)

    def test_the_limit_is_checked_without_passing_suppressed(self):
        """⚠️ 界面那条「只改等级」的路**不传 suppressed** ⇒ 也必须查上限
        （以前只在传了 suppressed 时才查 ⇒ 能写出打不开的存档）。"""
        plan, _ = self.commit([Edit.hq_branch_suppressed(HQ, BRANCH, 1)])
        self.assertTrue(plan.ok, plan.errors)
        plan, _ = self.commit([Edit.hq_branch_level(HQ, BRANCH, 3)])
        self.assertFalse(plan.ok)
        plan, res = self.commit([Edit.hq_branch_level(HQ, BRANCH, 2)])
        self.assertTrue(plan.ok, plan.errors)
        node = self.branch()
        self.assertEqual(2, node["level"])
        self.assertEqual(1, node["suppressed"])
        self.assertEqual(3, node["level"] + node["suppressed"], "刚好到上限")

    def test_suppress_cannot_exceed_the_real_level(self):
        """压制数不能超过真实等级（游戏会拒）。"""
        plan, _ = self.commit([Edit.hq_branch_suppressed(HQ, BRANCH, 3)])
        self.assertFalse(plan.ok)
        self.assertTrue(any("超过" in e for e in plan.errors), plan.errors)


class TestBranchUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    def test_branch_level_and_suppression_are_written_as_one_paired_edit(self):
        """⚠️ T12（玩家 2026-11-27 实测后的口径）：等级与压制必须**成对**写成
        **一条** `hq_branch_level`（带 `suppressed`）。

        为什么不再单独走 `hq_branch_suppressed`：
        两条 edit 的**先后顺序**会互相影响（先等级后压制 / 先压制后等级
        算出的 level 不一样）⇒ 玩家实测到「两者同时互动能产生负数的分支等级」。
        成对写 ⇒ 顺序无关 ⇒ `level = 解锁到几级 − 被压制数` 恒 ≥ 0。

        核心库那一侧的 `hq_branch_suppressed` 语义**保留不动**
        （`TestSuppressSemantics` 仍守着它）—— 只是界面不再单独用它。
        """
        i = self.html.index("function setHqBranchState(")
        j = self.html.index("function hqBranchLevel(", i)
        body = self.html[i:j]
        self.assertIn('"hq_branch_level"', body)
        self.assertIn("suppressed:suppressed", body)
        self.assertIn("real - suppressed", body,
                      "写盘时 level = 解锁到几级 − 被压制数（恒 ≥ 0）")

    def test_the_projection_exists_and_replays_pending_edits(self):
        self.assertIn("function hqBranchState(", self.html)
        i = self.html.index("function hqBranchState(")
        j = self.html.index("function hqBranchLevel(", i)
        body = self.html[i:j]
        self.assertIn("PENDING.forEach", body, "投影必须按待应用的先后顺序重放")
        self.assertIn("real - suppressed", body,
                      "压制后生效等级 = 真实等级 − 被压制数（游戏的语义）")

    def test_the_matrix_uses_the_projection(self):
        i = self.html.index("function hqMatrixHTML(")
        j = self.html.index("\nfunction ", i + 10)
        body = self.html[i:j]
        self.assertIn("hqBranchState(", body)

    def test_the_level_button_respects_the_limit(self):
        """等级（= 解锁到几级）必须夹在 **0–3**（游戏的硬上限）。"""
        i = self.html.index("function hqBranchLevel(")
        j = self.html.index("function hqSuppress(", i)
        body = self.html[i:j]
        self.assertIn("if(real>3) real=3", body)
        self.assertIn("if(real<0) real=0", body)
        self.assertIn("if(sup>real) sup = real", body,
                      "压制不能超过等级")


if __name__ == "__main__":
    unittest.main()
