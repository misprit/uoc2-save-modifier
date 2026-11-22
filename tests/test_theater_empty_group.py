# -*- coding: utf-8 -*-
"""U156：护栏 —— 某一方的战区资产组**是空的**时，参照值不许拿另一方的。

**曾经的 bug**：`document_theater_assets(phase)` / `scenario_theater_assets(..., phase=)`
在「请求的那一组是空的」时**退回拍平**（后一组覆盖前一组）
⇒ 玩家那一方没有这项资产时，「场景定义」参照值其实来自**对手那一方**。

**这些测试守着**

① 请求的那一组**是空的** ⇒ 返回 `{}`（不是拍平）；
② 请求的那一组**有内容** ⇒ 照常返回那一组（老行为不变）；
③ 不给 phase ⇒ 仍然拍平（公开 API 的旧行为，兼容）；
④ 服务端给两方的参照值**互不串**（玩家那方空 ⇒ 不带对手那方的数）。
"""

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

from save_modifier_core import CorePaths, open_save  # noqa: E402

from ._fixtures import dump, make_save  # noqa: E402

#: 正常存档：玩家 local / 对手 ai
FACTIONS = {"allies": {"deployed": True, "player": "local"},
            "axis": {"deployed": False, "player": "ai"}}

#: 场景设计：**玩家那一方是空的**，对手那一方才有 air_attack
SCEN_EMPTY_PLAYER = {
    "theater_assets": [
        [],
        [{"asset": "air_attack", "uses_total": 4, "uses_turn": 3}],
    ],
}

#: 场景设计：玩家那一方有 air_attack（对照组）
SCEN_FULL_PLAYER = {
    "theater_assets": [
        [{"asset": "air_attack", "uses_total": 9, "uses_turn": 9}],
        [{"asset": "air_attack", "uses_total": 4, "uses_turn": 3}],
    ],
}


class EmptyGroupReferenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u156_empty_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()

    def _make(self, scen):
        return make_save(
            self.tmp / "s.usg",
            battle_overrides={
                "phase": 0, "factions": FACTIONS,
                "theater_assets": [[], [{"asset": "air_attack", "to_use": 1,
                                         "to_use_not_used": 0, "uses_total": 4,
                                         "uses_turn": 1}]]},
            extra_entries={"document/scenarios/avalanche/main.yml": dump(scen)})

    def _save(self, path):
        return open_save(str(path), self.paths)

    def test_an_empty_group_returns_nothing(self):
        """① 请求的那一组是空的 ⇒ `{}`（不是拍平）。"""
        p = self._make(SCEN_EMPTY_PLAYER)
        with self._save(p) as save:
            got = save.document_theater_assets(0)
        self.assertEqual({}, got,
                         "玩家那一方是空的 ⇒ 参照值不能是对手那方的")

    def test_a_non_empty_group_is_returned_as_before(self):
        """② 有内容的那一组照常返回。"""
        p = self._make(SCEN_FULL_PLAYER)
        with self._save(p) as save:
            got = save.document_theater_assets(0)
        self.assertEqual(9, got["air_attack"]["uses_total"])

    def test_without_a_phase_it_still_flattens(self):
        """③ 不给 phase ⇒ 仍然拍平（公开 API 的旧行为，兼容）。"""
        p = self._make(SCEN_FULL_PLAYER)
        with self._save(p) as save:
            got = save.document_theater_assets()
        self.assertEqual(4, got["air_attack"]["uses_total"],
                         "拍平 = 后一组覆盖前一组（旧行为）")

    def test_the_two_groups_have_different_references(self):
        """④ 两组各取各的，互不串。

        ⚠️ 不在这里断言「服务端最终显示什么」—— 存档自带的那份为空时，
        服务端会**回退到游戏包里的场景设计**（那才是这一方真正的设计），
        数值取决于本机有没有装游戏 ⇒ 断言它会变成环境依赖。
        """
        p = self._make(SCEN_EMPTY_PLAYER)
        with self._save(p) as save:
            mine = save.document_theater_assets(0)
            theirs = save.document_theater_assets(1)
        self.assertEqual({}, mine)
        self.assertEqual(4, theirs["air_attack"]["uses_total"],
                         "对手那一方该拿到自己那组的参照值")


if __name__ == "__main__":
    unittest.main()
