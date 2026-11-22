# -*- coding: utf-8 -*-
"""U153：护栏 —— hotseat（双 `player: local`）的第二方战区资产**必须可达**。

**曾经的 bug**：`theater_group_index()` 靠 `is_player` 布尔去找「对手那一方」
⇒ hotseat 里**两边都是玩家** ⇒ 找不到 ⇒ 退回第 0 组
⇒ 两个页签都改第 0 组（**改错条目**），第二方那组永远改不到。

**这些测试守着**

① 双 local：`player` ⇒ 第 0 组、`opponent` ⇒ 第 1 组（**两者不重合**）；
② 玩家那一方在下标 1 时（`factions` 顺序颠倒）也照样分得开；
③ 正常存档（local / ai）的老行为**不变**；
④ 界面页签按**组下标**对齐（不再用 `is_player` 布尔）；
⑤ 双 local 时页签用**阵营名**（两个「你这一方」没法分）。
"""

import io
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
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.container import theater_group_index  # noqa: E402
from save_modifier_web import server  # noqa: E402

from ._fixtures import make_save  # noqa: E402

#: hotseat：**两边都是玩家**
HOTSEAT = {"allies": {"deployed": True, "player": "local"},
           "soviet": {"deployed": True, "player": "local"}}

#: hotseat 的另一种顺序（玩家那一方在**下标 1**）
HOTSEAT_FLIPPED = {"allies": {"deployed": True, "player": "local"},
                   "soviet": {"deployed": True, "player": "local"}}

#: 正常存档：玩家 local / 对手 ai
NORMAL = {"allies": {"deployed": True, "player": "local"},
          "axis": {"deployed": False, "player": "ai"}}

#: 两边都是 ai（观战 / 合成夹具）⇒ 也不能让 player 与 opponent 重合
BOTH_AI = {"allies": {"deployed": True, "player": "ai"},
           "axis": {"deployed": False, "player": "ai"}}

GROUPS = [
    [{"asset": "air_attack", "to_use": 1, "to_use_not_used": 0,
      "uses_total": 5, "uses_turn": 1}],
    [{"asset": "long_range_recon", "to_use": 2, "to_use_not_used": 1,
      "uses_total": 3, "uses_turn": 2}],
]


def battle(factions, phase=0):
    return {"phase": phase, "factions": factions, "theater_assets": GROUPS}


class HotseatGroupIndexTest(unittest.TestCase):
    """① 后端：双 local 时两侧的组**不重合**。"""

    def test_both_local_sides_get_different_groups(self):
        d = battle(HOTSEAT)
        self.assertEqual(0, theater_group_index(d, "player"))
        self.assertEqual(1, theater_group_index(d, "opponent"),
                         "双 local 时对手那一方仍是第 0 组 ⇒ 第二方改不到")

    def test_the_player_side_is_still_the_first_local_one(self):
        """玩家那一方 = 第一个 `player: local`（顺序颠倒时它在下标 1）。"""
        d = battle(HOTSEAT_FLIPPED)
        self.assertEqual(0, theater_group_index(d, "player"))
        self.assertEqual(1, theater_group_index(d, "opponent"))

    def test_a_normal_save_keeps_the_old_behaviour(self):
        """③ 正常存档（local / ai）的老行为**一个字都不能变**。"""
        d = battle(NORMAL)
        self.assertEqual(0, theater_group_index(d, "player"))
        self.assertEqual(1, theater_group_index(d, "opponent"))
        self.assertEqual(0, theater_group_index(d, "current"))

    def test_two_ai_sides_do_not_collapse_into_one_group(self):
        d = battle(BOTH_AI)
        self.assertNotEqual(theater_group_index(d, "player"),
                            theater_group_index(d, "opponent"))

    def test_a_number_addresses_the_group_directly(self):
        """数字 side = 组下标（给外部 GUI 一个无歧义的寻址方式）。"""
        d = battle(HOTSEAT)
        self.assertEqual(1, theater_group_index(d, "1"))
        self.assertEqual(0, theater_group_index(d, "0"))
        self.assertEqual(1, theater_group_index(d, 1))

    def test_an_out_of_range_number_does_not_guess(self):
        d = battle(HOTSEAT)
        self.assertEqual(0, theater_group_index(d, "7"))


class HotseatServerDataTest(unittest.TestCase):
    """② 服务端给的两侧数据必须是**两组不同的东西**。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u153_hotseat_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(
            self.tmp / "s.usg",
            battle_overrides={"phase": 0, "factions": HOTSEAT,
                              "theater_assets": GROUPS})
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def _save(self):
        return open_save(str(self.save_path), self.paths)

    def test_the_two_sides_carry_different_assets(self):
        with self._save() as save:
            mine = server._theater_assets_of(save, "player")
            theirs = server._theater_assets_of(save, "opponent")
        self.assertEqual(["air_attack"], [a["asset"] for a in mine])
        self.assertEqual(["long_range_recon"], [a["asset"] for a in theirs],
                         "两侧拿到的是同一组 ⇒ hotseat 的第二方不可达")

    def test_the_meta_points_at_two_different_groups(self):
        with self._save() as save:
            _u, meta = server._theater_universe_of(save, self.catalog)
        self.assertNotEqual(meta["player_index"], meta["opponent_index"],
                            "player_index 与 opponent_index 重合 ⇒ 两个页签指向同一组")
        self.assertEqual(0, meta["player_index"])
        self.assertEqual(1, meta["opponent_index"])

    def test_editing_the_second_side_only_touches_the_second_group(self):
        """③ 改「另一方」⇒ 只动第 1 组（第一方一个字节都不能动）。"""
        with self._save() as save:
            plan = save.plan_edit(
                [Edit.theater_asset("long_range_recon", to_use=0,
                                    side="opponent")],
                catalog=self.catalog)
        self.assertTrue(plan.ok, plan.errors)
        with self._save() as save:
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("games/avalanche/main.yml"))
        self.assertEqual(1, data["theater_assets"][0][0]["to_use"],
                         "第一方那组被误改了")
        self.assertEqual(0, data["theater_assets"][1][0]["to_use"])


class HotseatFrontendTest(unittest.TestCase):
    """④⑤ 界面：页签按组下标对齐；双 local 时用阵营名。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    def test_the_tabs_are_aligned_by_group_index(self):
        self.assertIn("function theaterSideId(sd)", self.html)
        self.assertIn("const sid = theaterSideId(sd);", self.html)
        self.assertNotIn('const sid = sd.is_player ? "player" : "opponent";',
                         self.html,
                         "页签还在用 is_player 布尔 ⇒ hotseat 两个页签会折叠成一个")

    def test_the_side_id_falls_back_to_the_group_indexes(self):
        self.assertIn("meta.player_index", self.html)
        self.assertIn("meta.opponent_index", self.html)

    def test_both_local_tabs_use_the_faction_name(self):
        self.assertIn("function theaterDualLocal()", self.html)
        self.assertIn("facCn(k)", self.html,
                      "双 local 时两个页签都叫「你这一方」⇒ 分不清")
