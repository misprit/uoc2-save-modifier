# -*- coding: utf-8 -*-
"""U161：护栏 —— 待应用明细 / 应用结果要标出「是哪一方」。

**曾经的 bug**（审阅报告 P2-2）：两边都有「空袭」时，两边的待应用明细是
**字面完全相同**的两行 ⇒ 在「应用 N 处改动」确认框里点「移除」
分不清删的是哪一方 ⇒ 可能只应用了一边，而玩家以为两边都改了。

**这些测试守着**

① 前端的待应用 label 带**阵营名**（不是「战区资产 空袭 …」这种裸描述）；
② 前端有待应用项时按**当前这一方**取阵营名；
③ 核心库的 summary / 报错 / 警告里说**阵营名**，不再只说「第 N 组」；
④ 核心库取不到阵营名时退回「第 N 组」（**不猜**）。
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
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.container import theater_side_cn  # noqa: E402

from ._fixtures import make_save  # noqa: E402

#: hotseat：两边都是玩家 ⇒ 阵营名必须能把两边分开
FACTIONS = {"allies": {"deployed": True, "player": "local"},
            "soviet": {"deployed": True, "player": "local"}}

GROUPS = [
    [{"asset": "air_attack", "to_use": 1, "to_use_not_used": 0,
      "uses_total": 5, "uses_turn": 1}],
    [{"asset": "air_attack", "to_use": 2, "to_use_not_used": 1,
      "uses_total": 3, "uses_turn": 2}],
]


class SideNameTest(unittest.TestCase):
    """③④ 核心库：阵营名取得到就取，取不到才退回「第 N 组」。"""

    def test_the_side_name_is_the_faction_name(self):
        d = {"phase": 0, "factions": FACTIONS, "theater_assets": GROUPS}
        self.assertEqual("盟军", theater_side_cn(d, 0))
        self.assertEqual("苏联", theater_side_cn(d, 1))

    def test_it_falls_back_to_the_group_number(self):
        """取不到 ⇒ 退回「第 N 组」（**不猜**）。"""
        d = {"phase": 0, "theater_assets": GROUPS}
        self.assertEqual("第 0 组", theater_side_cn(d, 0))


class SummaryMentionsTheSideTest(unittest.TestCase):
    """③ 核心库的摘要 / 报错里说阵营名。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u161_side_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(
            self.tmp / "s.usg",
            battle_overrides={"phase": 0, "factions": FACTIONS,
                              "theater_assets": GROUPS})
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def _plan(self, edits):
        with open_save(str(self.save_path), self.paths) as save:
            return save.plan_edit(edits, catalog=self.catalog)

    def test_the_edit_summary_names_the_side(self):
        plan = self._plan([Edit.theater_asset("air_attack", to_use=0,
                                             side="opponent")])
        self.assertTrue(plan.ok, plan.errors)
        notes = " ".join(plan.notes)
        self.assertIn("苏联", notes, "摘要里要看出改的是哪一方")
        self.assertNotIn("第 1 组", notes)

    def test_the_error_names_the_side(self):
        """删一个这一方没有的资产 ⇒ 报错里也说阵营名。"""
        plan = self._plan([Edit.theater_asset_remove("air_supply",
                                                     side="opponent")])
        self.assertFalse(plan.ok)
        self.assertIn("苏联", " ".join(plan.errors))

    def test_the_add_summary_names_the_side(self):
        plan = self._plan([Edit.theater_asset_add("air_supply", uses_total=2,
                                                  uses_turn=1, side="opponent")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertIn("苏联", " ".join(plan.notes))


class PendingLabelTest(unittest.TestCase):
    """①② 前端：待应用 label 带阵营名。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    def test_the_helper_exists(self):
        self.assertIn("function theaterSideLabel(sid)", self.html)
        self.assertIn("facCn(k)", self.html)

    def test_the_pending_labels_carry_the_side(self):
        self.assertIn('L2("{0}：战区资产 {1} {2}", theaterSideLabel()',
                      self.html)
        self.assertIn('L2("{0}：删除战区资产 {1}（当前可用 {2}，本场景剩余 {3}）"',
                      self.html)
        self.assertIn('L2("{0}：添加战区资产 {1}（每回合恢复 {2}，本场景剩余 {3}）"',
                      self.html)

    def test_the_old_bare_labels_are_gone(self):
        self.assertNotIn('L2("战区资产 {0} {1}", theaterCn(asset)', self.html)
        self.assertNotIn('L2("删除战区资产 {0}（当前可用 {1}，本场景剩余 {2}）"',
                         self.html)

    def test_the_add_label_uses_the_side_recorded_in_the_modal(self):
        """弹窗里记的那一方（切了页签也不串）。"""
        self.assertIn("theaterSideLabel(M.side)", self.html)


if __name__ == "__main__":
    unittest.main()
