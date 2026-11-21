# -*- coding: utf-8 -*-
"""U107：兵库「加条目」/ 商店「上架」的特种兵候选 —— 同一套逻辑 + 可以展开。

用户报告（2026-11-21）：
> 严重bug。兵库增加条目（上架）功能和商店的上架功能基本彻底坏掉了，
> 里面可选的特种兵完全不对，部分无法正常上架。这里可选上架的应该遵循和单位详情
> 页面挂载特种兵一样的逻辑，显示一部分，然后允许展开。你甚至可以套用一样的ui。

**取证**

1. **游戏的 schema**（`state/entities/data_validation/force_pool.pyc`，U107 字节码实证）：
   * `equipment`   → `In(constants.unit_equipments + (unit_equipment_none,))`
                     = `('armor', 'infantry')`（**全部**游戏兵种）；
   * `nationality` → `nationality_types.id_validation_schema` = `In(全部 40 个国籍 id)`；
   * `spec`        → `specialist_types.id_validation_schema`（全部 375 个）。
   ⇒ ⚠️ **核心库之前拿「本次会议商店在售的兵种 / 国籍」当门 ⇒ 过严** ——
     west 存档里 free_french 的 3 个特种兵游戏明明能读，却被核心库拒了
     ⇒ 玩家「部分无法正常上架」。
2. **实测 west 存档**：玩家 = allies；商店里 13 条特种兵 100% allies；
   HQ 兵库里有 3 条 axis（缴获件）⇒ 商店只卖自己阵营的，兵库可以是缴获的。
3. **界面**：`hqPoolItems` / `storeAddItems` 直接用 `PICK.campaign_pool`
   （45 种，**三个阵营混在一起**）⇒ 玩家挑到敌方的 ⇒ 挂不上 / 上架被拒。

**这些测试守着**

① 核心库：游戏能读的上架**不再被拒**（free_french / 全部兵种 / 全部国籍）；
   游戏读不了的**仍然被拒**（不存在的特种兵 / 兵种 / 国籍）；
   敌方阵营 ⇒ **软警告**而不是硬拦（游戏能读，只是玩家挂不上）；
② 服务端：`/api/pickers` 给出 `player_faction` 与 `player_specs`
   （**用单位页那套** `specialist_candidates` 算的）；
③ 界面：默认只列玩家挂得上的；「显示全部」能展开；商店里挂不上的**灰掉**，
   兵库里只是**标注**（缴获件是合法的）。
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_web import server  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")


class StoreSchemaTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u107_store_"))
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

    def store_entries(self):
        import zipfile

        import yaml
        with zipfile.ZipFile(self.save_path) as zf:
            store = yaml.safe_load(zf.read("store.yml"))
        return (store.get("south") or {}).get("store") or []


class TestStoreAcceptsWhatTheGameAccepts(StoreSchemaTestBase):
    """核心库：门要跟游戏的 schema 一致（U107 之前过严）。"""

    def test_specialist_of_a_nationality_not_sold_here_is_accepted(self):
        """⚠️ **U107 的正题** —— 游戏能读的就别拦。

        `free_french` 不在 west 那次会议的商店国籍里（那儿只有
        canadian / indian / new_zealand / uk / us）⇒ 旧代码会以
        「国籍 'free_french' 游戏里没有」把它拒掉 ⇒ 玩家「部分无法正常上架」。
        游戏自己的 schema 是 `nationality_types.id_validation_schema`
        = **全部 40 个国籍 id** ⇒ free_french 合法。
        """
        if not self.catalog.has_spec_type("ff_spec_42"):
            self.skipTest("本机没有游戏包")
        plan, res = self.commit([Edit.store_add("south", "store", {
            "spec": "ff_spec_42", "nationality": "free_french",
            "price": 8, "quantity": 4})])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        entries = self.store_entries()
        self.assertTrue(any(e.get("spec") == "ff_spec_42" for e in entries),
                        entries)

    def test_both_game_equipments_are_accepted(self):
        """游戏的兵种只有 `armor` / `infantry`（`constants.unit_equipments`）。"""
        for eq in ("armor", "infantry"):
            with self.subTest(eq=eq):
                plan, res = self.commit([Edit.store_add("south", "store", {
                    "equipment": eq, "nationality": "german",
                    "price": 5, "quantity": 2})])
                self.assertTrue(plan.ok, plan.errors)
                self.assertTrue(res.ok, res.errors)

    def test_unknown_equipment_is_still_blocked(self):
        """游戏只有 armor / infantry ⇒ 别的仍然要拦。"""
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "equipment": "cavalry", "nationality": "german",
            "price": 5, "quantity": 2})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("游戏里没有" in e for e in plan.errors), plan.errors)

    def test_unknown_nationality_is_still_blocked(self):
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "equipment": "armor", "nationality": "atlantis",
            "price": 5, "quantity": 2})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("游戏里没有" in e for e in plan.errors), plan.errors)

    def test_unknown_specialist_is_still_blocked(self):
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "spec": "not_a_real_spec", "nationality": "german",
            "price": 5, "quantity": 2})])
        self.assertFalse(plan.ok)
        self.assertTrue(any("游戏里没有" in e for e in plan.errors), plan.errors)

    def test_other_faction_only_warns(self):
        """敌方阵营的：**软警告**（游戏能读），不是硬拦。"""
        if not self.catalog.has_spec_type("us_arty_42"):
            self.skipTest("本机没有游戏包")
        plan, _ = self.commit([Edit.store_add("south", "store", {
            "spec": "us_arty_42", "nationality": "us",
            "price": 8, "quantity": 3})])
        # 合成存档的 document/main.yml 写的是 player_faction: axis
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("阵营" in w for w in plan.warnings), plan.warnings)


class TestPickersPayload(unittest.TestCase):
    """服务端：`/api/pickers` 要给出玩家阵营与「挂得上的」特种兵。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u107_pick_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def test_payload_has_player_faction_and_specs(self):
        d = server.api_pickers(str(self.save_path))
        self.assertEqual(d["player_faction"], "axis",
                         "玩家阵营要来自存档 document/main.yml")
        specs = d["player_specs"]
        self.assertTrue(specs, "player_specs 不该是空的")
        pool = set(d["campaign_pool"])
        self.assertTrue(set(specs) <= pool,
                        "player_specs 必须 ⊆ 战役池")

    def test_player_specs_only_holds_the_player_faction(self):
        """⚠️ 存档里**也有 AI 的单位** ⇒ 不能把敌方的也带进来。"""
        d = server.api_pickers(str(self.save_path))
        fac = d["player_faction"]
        for t in d["player_specs"]:
            st = self.catalog.spec_type(t)
            self.assertIsNotNone(st, t)
            self.assertEqual(st.faction, fac,
                             "%s 不是玩家阵营（%s）的" % (t, fac))


class TestSpecPickerUi(unittest.TestCase):
    """界面：默认只列玩家挂得上的，「显示全部」能展开。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    @staticmethod
    def _body(html, start, end):
        i = html.index(start)
        j = html.index(end, i + len(start))
        return html[i:j]

    def test_shared_item_builder_exists(self):
        """两个选择器走**同一套**逻辑。"""
        self.assertIn("function specPickItems(", self.html)
        body = self._body(self.html, "function specPickItems(", "/* U107：切换「显示全部」 */")
        self.assertIn("playerSpecs()", body)
        self.assertIn("MODAL.all", body)

    def test_default_list_is_the_player_ones(self):
        """默认列表 = **玩家挂得上的那批**（直接取 `playerSpecs()`）。"""
        body = self._body(self.html, "function specPickItems(", "/* U107：切换「显示全部」 */")
        self.assertIn("ok ? ok.slice()", body,
                      "默认必须只列玩家挂得上的")

    def test_show_all_covers_every_specialist_type(self):
        """⭐ **U113**：「显示全部」= **游戏定义过的全部**特种兵
        （与单位页的「显示所有特种兵」同一套范围）。

        以前只给**战役池**（west 才 45 种）⇒ 比单位页能挂的（97 种）少一大截
        ⇒ 用户以为「很多种挂不上 / 买不了」。
        """
        body = self._body(self.html, "function specPickItems(",
                          "/* U107：切换「显示全部」 */")
        self.assertIn("all ? allSpecTypes()", body)
        self.assertIn("function allSpecTypes()", self.html)
        self.assertIn("Object.keys(cat)", self.html)

    def test_nothing_is_blocked_anymore(self):
        """**U113**：不再灰掉 —— 核心库的门已经是「游戏定义过的全集」
        （U107 改的）⇒ 游戏本来就接受 ⇒ 灰掉反而是多余的拦截。
        挂不上的只在**悬停**里写明原因。"""
        body = self._body(self.html, "function specPickItems(",
                          "/* U107：切换「显示全部」 */")
        self.assertIn("blocked: false", body)
        self.assertNotIn("forStore && !usable", body)

    def test_both_pickers_use_the_shared_builder(self):
        self.assertIn("return specPickItems(projectedPool(h), false);", self.html)
        self.assertIn("const specs = specPickItems(have, true);", self.html)

    def test_show_all_toggle(self):
        self.assertIn("function spickToggleAll()", self.html)
        self.assertIn("spickToggleAll()", self.html)
        self.assertIn('id="spick_all"', self.html)

    def test_player_faction_helper(self):
        self.assertIn("function playerFaction()", self.html)
        self.assertIn("function playerSpecs()", self.html)

    def test_english_words_exist(self):
        ui = self.table["ui"]
        for zh in ("不是玩家阵营", "挂不到玩家的任何单位上"):
            self.assertIn(zh, ui, "词表里缺 %r" % zh)


if __name__ == "__main__":
    unittest.main()
