# -*- coding: utf-8 -*-
"""B-8：总部改名要同步到**四份**名册（社区反馈「点选场景显示的出场指挥部名字不会改变」）。

**社区原话**
> 「战役界面点选场景显示的出场指挥部名字不会改变，可能会有点混乱，
> 不过改的人自己心里清楚。」

**根因（实测存档结构）**
HQ 名字在存档里有 **4 份副本**：

| # | 条目 | 谁在显示 |
|---|---|---|
| 1 | `hqs.yml`（根表） | 战斗中 |
| 2 | `document/hqs.yml`（战役名册） | 战役地图 / 主界面 |
| 3 | `document/scenarios/<场景>/hqs.yml`（**场景名册**） | 战役界面**点选场景**时显示的「出场指挥部」 |
| 4 | `games/<场景>/hqs.yml`（战斗层） | 战斗层那份总部名单 |

改名以前**只同步了前两份** ⇒ 第 3、4 份仍是旧名 ⇒ 那个界面看起来「没生效」。
用户 2026-11-26 拍板：**改全部 4 处副本**。

⚠️ **各份的字段形态不同**（实测）：
* `document/scenarios/<场景>/hqs.yml` —— **只有 `name_brief`**（14 处；
  没有 `name_full` / `name_super_brief`）⇒ 改名**不能凭空造**那两个字段；
* `games/<场景>/hqs.yml` —— 三种名字字段都有；
  但**当前活动场景**那份是 `list[int]`（只有 id、没有名字）⇒ 里面没有名字可改。

⚠️ **只精确放行这两类 `hqs.yml`** —— `document/` 下其余条目仍然**只读**（U124）。

**这些测试守着**

① 改名 ⇒ **四份都改**；
② 场景名册那份**只有 `name_brief`** ⇒ 改完也不多出 `name_full`；
③ 战斗层那份是 `list[int]` ⇒ 改名**不报错**、那份不动；
④ 写盘白名单：只多放行**这两类** `hqs.yml`，`document/` 其余条目仍只读；
⑤ 存档里**没有**这些副本（独立场景）⇒ 改名照常、不报错。
"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save
from save_modifier_core.plan import writable_entries

from ._fixtures import dump, make_save

#: 场景名册那份：**只有 `name_brief`**（实测形态）
SCENARIO_ROSTER = [{"id": 5, "name_brief": "id_hq_5_brief"}]
#: 战斗层那份（已结束的战斗 = 完整对象）
BATTLE_ROSTER = [{"id": 5, "name_brief": "id_hq_5_brief",
                  "name_full": None, "name_super_brief": None}]
#: 战役名册那份
CAMPAIGN_ROSTER = [{"id": 5, "name_brief": "id_hq_5_brief",
                    "name_full": None, "name_super_brief": None}]

NEW_NAME = "改名实测_B8"


def _by_id(rows, oid):
    for r in rows or []:
        if isinstance(r, dict) and r.get("id") == oid:
            return r
    return None


class HqRenameSyncBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b8_rename_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def make(self, name="s.usg", **kw):
        return make_save(self.tmp / name, **kw)

    def make_full(self, name="full.usg", battle_roster=None):
        """一个**四份副本都在**的存档。"""
        return make_save(
            self.tmp / name,
            extra_entries={
                "document/hqs.yml": dump(CAMPAIGN_ROSTER),
                "document/scenarios/avalanche/hqs.yml": dump(SCENARIO_ROSTER),
                "games/avalanche/hqs.yml": dump(
                    BATTLE_ROSTER if battle_roster is None else battle_roster),
            })

    def commit(self, path, edits):
        with open_save(str(path), self.paths) as save:
            p = save.plan_edit(edits, catalog=self.catalog)
            if not p.ok:
                return p, None
            return p, save.commit(p)

    def read(self, path, entry):
        with zipfile.ZipFile(path) as zf:
            return yaml.safe_load(zf.read(entry))


class TestAllFourCopiesAreRenamed(HqRenameSyncBase):
    """① 四份都改。"""

    def setUp(self):
        super().setUp()
        self.path = self.make_full()

    def test_the_rename_reaches_all_four_copies(self):
        plan, res = self.commit(self.path,
                                [Edit.hq_field(5, "name_brief", NEW_NAME)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        root = _by_id(self.read(self.path, "hqs.yml"), 5)
        campaign = _by_id(self.read(self.path, "document/hqs.yml"), 5)
        scenario = _by_id(self.read(self.path,
                                    "document/scenarios/avalanche/hqs.yml"), 5)
        battle = _by_id(self.read(self.path, "games/avalanche/hqs.yml"), 5)
        self.assertEqual(NEW_NAME, root["name_brief"], "根表没改")
        self.assertEqual(NEW_NAME, campaign["name_brief"], "战役名册没改")
        self.assertEqual(NEW_NAME, scenario["name_brief"],
                         "场景名册没改 ⇒ 战役界面点选场景显示的还是旧名")
        self.assertEqual(NEW_NAME, battle["name_brief"], "战斗层那份没改")

    def test_the_plan_lists_the_copies_it_touched(self):
        plan, _ = self.commit(self.path,
                              [Edit.hq_field(5, "name_brief", NEW_NAME)])
        self.assertTrue(plan.ok, plan.errors)
        for entry in ("hqs.yml", "document/hqs.yml",
                      "document/scenarios/avalanche/hqs.yml",
                      "games/avalanche/hqs.yml"):
            self.assertIn(entry, plan.changed_entries, entry)

    def test_the_scenario_roster_does_not_gain_extra_name_fields(self):
        """⚠️ 场景名册那份**只有 `name_brief`** ⇒ 改名不许凭空造 `name_full`。"""
        self.commit(self.path, [Edit.hq_field(5, "name_brief", NEW_NAME)])
        scenario = _by_id(self.read(self.path,
                                    "document/scenarios/avalanche/hqs.yml"), 5)
        self.assertEqual(NEW_NAME, scenario["name_brief"])
        self.assertNotIn("name_full", scenario,
                         "场景名册那份本来就没有 name_full ⇒ 别造一个")
        self.assertNotIn("name_super_brief", scenario)


class TestIdListBattleLayerIsHarmless(HqRenameSyncBase):
    """③ 战斗层当前活动场景那份是 `list[int]` ⇒ 不报错、不动它。"""

    def test_an_id_list_battle_layer_does_not_break_the_rename(self):
        path = self.make_full(battle_roster=[5, 6])
        plan, res = self.commit(path,
                                [Edit.hq_field(5, "name_brief", NEW_NAME)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual([5, 6], self.read(path, "games/avalanche/hqs.yml"),
                         "那份只有 id、没有名字 ⇒ 不该被改")
        self.assertEqual(NEW_NAME,
                         _by_id(self.read(path, "hqs.yml"), 5)["name_brief"])


class TestWhitelistIsStillNarrow(HqRenameSyncBase):
    """④ 只多放行这两类 `hqs.yml`。"""

    def setUp(self):
        super().setUp()
        self.path = self.make_full()

    def test_the_two_kinds_of_hqs_yml_are_writable(self):
        with open_save(str(self.path), self.paths) as save:
            allowed = writable_entries(save)
        self.assertIn("document/scenarios/avalanche/hqs.yml", allowed)
        self.assertIn("games/avalanche/hqs.yml", allowed)

    def test_the_rest_of_document_stays_read_only(self):
        """⚠️ U124 的结论不变：`document/` 下**其余**条目仍然只读。"""
        with open_save(str(self.path), self.paths) as save:
            allowed = writable_entries(save)
        for e in ("document/main.yml", "document/locale.yml",
                  "document/scenarios/avalanche/main.yml",
                  "document/scenarios/avalanche/units.yml",
                  "last_conference/hqs.yml", "last_game/hqs.yml",
                  "games/avalanche/units.yml"):
            self.assertNotIn(e, allowed, "%s 不该能写" % e)

    def test_only_the_existing_copies_are_writable(self):
        """白名单只放行**存档里真实存在**的那几份。"""
        with open_save(str(self.path), self.paths) as save:
            allowed = writable_entries(save)
        self.assertNotIn("document/scenarios/other/hqs.yml", allowed)
        self.assertNotIn("games/other/hqs.yml", allowed)


class TestSaveWithoutCopies(HqRenameSyncBase):
    """⑤ 没有副本（独立场景存档）⇒ 改名照常。"""

    def test_the_rename_still_works(self):
        path = self.make()
        plan, res = self.commit(path,
                                [Edit.hq_field(5, "name_brief", NEW_NAME)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(NEW_NAME,
                         _by_id(self.read(path, "hqs.yml"), 5)["name_brief"])

    def test_a_hq_that_is_not_in_the_roster_is_not_an_error(self):
        """名册里没有这个 id ⇒ 只改根表、不报错。"""
        path = self.make_full()
        plan, res = self.commit(path,
                                [Edit.hq_field(6, "name_brief", NEW_NAME)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(NEW_NAME,
                         _by_id(self.read(path, "hqs.yml"), 6)["name_brief"])


class TestRealSaveCopy(unittest.TestCase):
    """真实存档的**副本**实测（仓库 `bak/` 里的只读备份）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b8_real_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        repo = Path(__file__).resolve().parents[1]
        cands = sorted((repo / "bak").glob("*.usg"))
        self.src = cands[0] if cands else None
        if self.src is None:
            self.skipTest("仓库里没有 bak/*.usg 备份")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def test_rename_reaches_the_scenario_rosters_of_a_real_save(self):
        path = self.tmp / "real.usg"
        shutil.copy2(self.src, path)
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            scen = [n for n in names
                    if n.startswith("document/scenarios/") and n.endswith("/hqs.yml")]
            if not scen:
                self.skipTest("这份存档没有场景名册")
            roster = yaml.safe_load(zf.read(scen[0])) or []
            hq = next((r for r in roster if isinstance(r, dict)
                       and isinstance(r.get("id"), int)
                       and isinstance(r.get("name_brief"), str)), None)
            if hq is None:
                self.skipTest("场景名册里没有带名字的总部")
        hq_id = hq["id"]
        with open_save(str(path), self.paths) as save:
            plan = save.plan_edit(
                [Edit.hq_field(hq_id, "name_brief", NEW_NAME)],
                catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
            self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(path) as zf:
            after = yaml.safe_load(zf.read(scen[0])) or []
        self.assertEqual(NEW_NAME, _by_id(after, hq_id)["name_brief"],
                         "真实存档的场景名册没改 ⇒ 战役界面点选场景还是旧名")


if __name__ == "__main__":
    unittest.main()
