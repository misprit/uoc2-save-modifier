# -*- coding: utf-8 -*-
"""U124：护栏 —— **写盘白名单** + 独立场景的战斗层判定（外部审阅报告 P1-7）。

**两个洞**

1. `plan.py::_layer_of` 原来只认 `games/*/main.yml` ⇒
   **独立场景**的战斗层在 `game/main.yml`（**单数**目录）⇒ 被标成 L1。
2. **写盘没有任何白名单** ⇒ 理论上能往存档里写**任意条目**
   （`document/` 战役文档、`last_conference/` 上次会议检查点、`last_game/` …）——
   那些是**只读**的。

**这些测试守着**

① 白名单 = 根层五张表 + **当前战斗**的那张 `main.yml`；
② `document/` / `last_conference/` / `last_game/` / 别的场景 ⇒ **都不许写**；
③ 碰到白名单外的条目 ⇒ 这一批**被拦住**（有错误、没有可写回的改动）；
④ `_layer_of`：独立场景 `game/main.yml` ⇒ **L3**；根层 ⇒ L1。
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.handlers import Outcome  # noqa: E402
from save_modifier_core import plan as plan_mod  # noqa: E402
from save_modifier_core.plan import (ROOT_WRITABLE, _layer_of,  # noqa: E402
                                    writable_entries)

from ._fixtures import make_save  # noqa: E402


class WriteWhitelistTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u124_wl_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def test_the_whitelist_is_the_five_root_tables_plus_the_current_battle(self):
        with open_save(str(self.save_path), self.paths) as save:
            allowed = writable_entries(save)
        for e in ROOT_WRITABLE:
            self.assertIn(e, allowed)
        self.assertIn("games/avalanche/main.yml", allowed,
                      "当前战斗层的那张 main.yml 要能改（战区资产 / 作战标记）")

    def test_read_only_entries_are_not_writable(self):
        with open_save(str(self.save_path), self.paths) as save:
            allowed = writable_entries(save)
        for e in ("document/main.yml", "document/units.yml",
                  "last_conference/main.yml", "last_conference/units.yml",
                  "last_game/main.yml", "last_game/store.yml",
                  "games/other_scenario/main.yml",
                  "games/avalanche/units.yml"):
            self.assertNotIn(e, allowed, "只读的条目不该能写：%r" % e)

    def test_a_plan_touching_a_forbidden_entry_is_blocked(self):
        """⭐ 模拟某个 handler 改了只读条目 ⇒ 整批**不许写盘**。"""
        def fake_apply(w, e):
            # 模拟某个 handler 改了只读条目（`document/` = 战役文档）
            doc = w.table("document/main.yml", {})
            doc["player_faction"] = "allies"
            w.touch("document/main.yml")
            return Outcome()

        with open_save(str(self.save_path), self.paths) as save:
            with mock.patch.object(plan_mod, "apply_edit", fake_apply):
                plan = save.plan_edit([Edit.progress("prestige", 5)],
                                      catalog=self.catalog)
            self.assertFalse(plan.ok, "写了只读条目居然通过")
            self.assertEqual([], plan.changes)
            self.assertTrue(any("document/main.yml" in e for e in plan.errors),
                            "错误里要点名那个条目：%r" % plan.errors)

    def test_normal_edits_still_work(self):
        """白名单不能把正常功能挡了。"""
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit([Edit.progress("prestige", 5)],
                                  catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            self.assertEqual(["main.yml"], plan.changed_entries)


class LayerOfTest(unittest.TestCase):
    def test_the_standalone_battle_layer_is_l3(self):
        """⭐ 独立场景的战斗层是 `game/main.yml`（**单数**目录）。"""
        self.assertEqual("L3", _layer_of("game/main.yml"))

    def test_the_campaign_battle_layer_is_l3(self):
        self.assertEqual("L3", _layer_of("games/avalanche/main.yml"))

    def test_root_tables_are_l1(self):
        for e in ROOT_WRITABLE:
            self.assertEqual("L1", _layer_of(e), e)

    def test_read_only_entries_are_not_l3(self):
        for e in ("document/main.yml", "last_conference/main.yml",
                  "games/avalanche/units.yml"):
            self.assertEqual("L1", _layer_of(e), e)


if __name__ == "__main__":
    unittest.main()
