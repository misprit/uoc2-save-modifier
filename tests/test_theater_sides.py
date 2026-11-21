# -*- coding: utf-8 -*-
"""U143：护栏 —— 战区资产的组 = **阵营**（不是"阶段"）。

**曾经的 bug**：编辑器按 `phase`（**当前行动方**）定位组
⇒ **轮到 AI 行动时**，会把**敌方那组**当成"自己的"显示，而且**改的也是它**。

**这些测试守着**

① 玩家的组 = `factions` 里 `player: local` 的下标（**不是** `phase`）；
② 对手那组**也能改**（`side="opponent"`），两侧互不串；
③ 场景参照值取**玩家那一方**（U141 的口径随之修正）；
④ `factions` 缺失（旧存档 / 合成夹具）⇒ 退回旧行为（按 `phase`）—— 不猜。
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
from save_modifier_core.container import (theater_group_index,  # noqa: E402
                                          theater_sides)
from save_modifier_web import server  # noqa: E402

from ._fixtures import dump, make_save  # noqa: E402

#: 战斗 `main.yml` 的追加内容：
#:   factions = {allies: 电脑, axis: 玩家} ⇒ **玩家是下标 1**
#:   phase = 0 ⇒ **当前行动方是电脑**（⇒ 旧的"按 phase 定位"会指错！）
FACTIONS = {"allies": {"deployed": True, "player": "ai"},
            "axis": {"deployed": False, "player": "local"}}

BATTLE = {
    "phase": 0,
    "factions": FACTIONS,
    "theater_assets": [
        # 组 0 = 电脑那一方
        [{"asset": "air_attack", "to_use": 1, "to_use_not_used": 0,
          "uses_total": 5, "uses_turn": 1}],
        # 组 1 = 玩家那一方
        [{"asset": "long_range_recon", "to_use": 2, "to_use_not_used": 1,
          "uses_total": 3, "uses_turn": 2}],
    ],
}

#: 场景设计（**两组 = 两个阵营各一组**，数值不同 ⇒ 参照值能验出取错没）
SCEN = {
    "theater_assets": [
        [{"asset": "air_attack", "uses_total": 9, "uses_turn": 9}],
        [{"asset": "long_range_recon", "uses_total": 4, "uses_turn": 3}],
    ],
}


class TheaterSideTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u143_sides_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(
            self.tmp / "s.usg",
            battle_overrides={"phase": 0, "factions": FACTIONS,
                             "theater_assets": BATTLE["theater_assets"]},
            extra_entries={"document/scenarios/avalanche/main.yml":
                           dump(SCEN)})
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def _save(self):
        return open_save(str(self.save_path), self.paths)

    def _battle(self):
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read("games/avalanche/main.yml"))

    def _plan(self, edits):
        with self._save() as save:
            return save.plan_edit(edits, catalog=self.catalog)


class SideIndexTest(TheaterSideTestBase):
    def test_the_sides_are_read_from_factions(self):
        sides = theater_sides(BATTLE)
        self.assertEqual(2, len(sides))
        self.assertEqual(["allies", "axis"], [s["key"] for s in sides])
        self.assertFalse(sides[0]["is_player"])
        self.assertTrue(sides[1]["is_player"])
        self.assertTrue(sides[0]["is_current"])   # phase=0 ⇒ 当前行动方是 allies

    def test_the_player_index_is_not_the_current_phase(self):
        self.assertEqual(1, theater_group_index(BATTLE, "player"),
                         "玩家的组必须是 player: local 的下标，不是 phase")
        self.assertEqual(0, theater_group_index(BATTLE, "opponent"))
        self.assertEqual(0, theater_group_index(BATTLE, "current"))

    def test_without_factions_it_falls_back_to_phase(self):
        """旧存档 / 合成夹具没有 `factions` ⇒ 退回旧行为（按 phase），**不猜**。"""
        old = {"phase": 1, "theater_assets": [[], []]}
        self.assertEqual(1, theater_group_index(old, "player"))
        self.assertEqual(1, theater_group_index(old, "current"))


class ServerSideDataTest(TheaterSideTestBase):
    def test_the_api_gives_both_sides(self):
        with self._save() as save:
            mine = server._theater_assets_of(save, "player")
            theirs = server._theater_assets_of(save, "opponent")
        self.assertEqual(["long_range_recon"], [a["asset"] for a in mine],
                         "玩家的组被搞成了电脑那组")
        self.assertEqual(["air_attack"], [a["asset"] for a in theirs])

    def test_the_universe_reference_uses_the_player_side(self):
        with self._save() as save:
            universe, _meta = server._theater_universe_of(save, self.catalog)
        by = {u["asset"]: u for u in universe}
        self.assertEqual(4, by["long_range_recon"]["scenario_uses_total"],
                         "参照值取成了电脑那组的设计")
        self.assertEqual(3, by["long_range_recon"]["scenario_uses_turn"])
        self.assertEqual(9, by["air_attack"]["opponent_scenario_uses_total"],
                         "对手那方的参照值不对")

    def test_the_meta_exposes_both_sides(self):
        with self._save() as save:
            _u, meta = server._theater_universe_of(save, self.catalog)
        self.assertEqual(1, meta["player_index"])
        self.assertEqual(0, meta["opponent_index"])
        self.assertEqual(2, len(meta["sides"]))


class EditingTest(TheaterSideTestBase):
    def test_editing_the_opponent_side_only_touches_that_group(self):
        plan = self._plan([Edit.theater_asset("air_attack", to_use=0,
                                             side="opponent")])
        self.assertTrue(plan.ok, plan.errors)
        with self._save() as save:
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        battle = self._battle()
        g0 = battle["theater_assets"][0]
        g1 = battle["theater_assets"][1]
        self.assertEqual(0, g0[0]["to_use"], "电脑那组没被改到")
        self.assertEqual(2, g1[0]["to_use"], "玩家那组被误改了")

    def test_editing_without_a_side_targets_the_player(self):
        plan = self._plan([Edit.theater_asset("long_range_recon", to_use=0)])
        self.assertTrue(plan.ok, plan.errors)
        with self._save() as save:
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        battle = self._battle()
        self.assertEqual(0, battle["theater_assets"][1][0]["to_use"],
                         "默认应该改玩家那组")
        self.assertEqual(1, battle["theater_assets"][0][0]["to_use"],
                         "电脑那组被误改了")

    def test_adding_to_the_opponent_side(self):
        plan = self._plan([Edit.theater_asset_add(
            "air_supply", uses_total=2, uses_turn=1, side="opponent")])
        self.assertTrue(plan.ok, plan.errors)
        with self._save() as save:
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        battle = self._battle()
        self.assertEqual(2, len(battle["theater_assets"][0]),
                         "新增的资产没进电脑那组")
        self.assertEqual(1, len(battle["theater_assets"][1]),
                         "玩家那组被塞了东西")

    def test_the_group_count_never_changes(self):
        """组数恒为 2 ⇒ 增删只动组内项。"""
        plan = self._plan([Edit.theater_asset_remove("air_attack",
                                                    side="opponent")])
        self.assertTrue(plan.ok, plan.errors)
        with self._save() as save:
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(2, len(self._battle()["theater_assets"]))


if __name__ == "__main__":
    unittest.main()
