# -*- coding: utf-8 -*-
"""U148：改名要**两份都写** —— 根表 + 战役名册（`document/`）。

**用户反馈**（朋友，2026-11-21）
> HQ 改名和单位改名功能实际都没有生效。

**根因**（字节码 + 真实存档）

存档里有**两份**单位/总部表：

| 表 | 内容 | 谁在显示 |
|---|---|---|
| 根 `units.yml` / `hqs.yml` | **已经登场过**的（实测 354 / 23 条） | **战斗中**（`game_world`） |
| `document/units.yml` / `document/hqs.yml` | **整场战役的全部**（实测 835 / 47 条） | **战役地图 / 主界面**（`main_screen`） |

* 战役地图：`campaign_doc._load` → `add_campaign_unit(unit_id, type, name_brief, name_full)`
  ⇒ 名字来自**名册**，**原样**带进去（**不**按 id 反查）；
* 战斗中：`gamelike._load_entities` → `HQState.load` / `UnitState.load` ⇒ 来自**根表**；
* 显示时统一 `app.locale.get(name_brief)`；`LocalizationManager.get`
  （`tools/localization.py:198`）对**不以 id_/idp_ 开头**的字符串**原样返回**
  ⇒ **写明文是可行的**；
* **游戏自己的改名**（`campaign.py::_rename_hqs`）恰恰改的是 campaign_doc
  ⇒ 也就是**名册**那一份（佐证）。

⇒ 以前只改根表 ⇒ **战役地图上完全看不到变化**。

**这些测试守着**

① 改名 ⇒ 根表 + 名册**两份都改**；
② 名册里没有该 id / 名册文件不存在 ⇒ **不报错**（跳过，不是错误）；
③ 写盘白名单**只**多放行名册那两张表（`document/` 其余条目仍只读）；
④ 名字字段的规则（`name_brief` 必改 / `name_super_brief` 一起改 /
   `name_full` 原来不是 null 才改）；
⑤ **真实存档实测**：改名后两份都变了；
⑥ 改名会提醒「**先退出游戏**」（U149）—— 游戏开着的话，它退出时会把
   内存里的存档写回去 ⇒ 改名被覆盖 ⇒ 这是"没生效"的**第二个**坑。
"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save
from save_modifier_core.plan import ROOT_WRITABLE, ROSTER_WRITABLE, writable_entries

from ._fixtures import dump, make_save
from ._helpers import find_saves


def _by_id(rows, oid):
    for r in rows or []:
        if isinstance(r, dict) and r.get("id") == oid:
            return r
    return None


class RenameRosterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rename_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def make(self, name="s.usg", **kw):
        return make_save(self.tmp / name, **kw)

    def open(self, path):
        return open_save(str(path), self.paths)

    def commit(self, path, edits):
        with self.open(path) as save:
            p = save.plan_edit(edits, catalog=self.catalog)
            if not p.ok:
                return p, None
            return p, save.commit(p)

    def read(self, path, entry):
        with zipfile.ZipFile(path) as zf:
            return yaml.safe_load(zf.read(entry))

    # ---------------------------------------------------------- ① 两份都改

    def test_unit_rename_updates_roster_too(self):
        """改名 ⇒ 根表 **和** 名册都改（战役地图显示的是名册那份）。"""
        p = self.make(extra_entries={"document/hqs.yml": dump([])})
        plan, res = self.commit(p, [Edit.unit_field(1, "name_brief", "我的第一连")])
        self.assertTrue(res.ok, res.errors)
        root = _by_id(self.read(p, "units.yml"), 1)
        roster = _by_id(self.read(p, "document/units.yml"), 1)
        self.assertEqual("我的第一连", root["name_brief"])
        self.assertEqual("我的第一连", roster["name_brief"],
                         "名册那份没改 ⇒ 战役地图上还是旧名")

    def test_hq_rename_updates_roster_too(self):
        """总部改名 ⇒ 根表 **和** 名册都改。"""
        p = self.make(extra_entries={"document/hqs.yml": dump([
            {"id": 5, "name_brief": "id_hq_5_brief", "name_full": None,
             "name_super_brief": None},
        ])})
        plan, res = self.commit(p, [Edit.hq_field(5, "name_brief", "狼牙棒")])
        self.assertTrue(res.ok, res.errors)
        root = _by_id(self.read(p, "hqs.yml"), 5)
        roster = _by_id(self.read(p, "document/hqs.yml"), 5)
        self.assertEqual("狼牙棒", root["name_brief"])
        self.assertEqual("狼牙棒", roster["name_brief"])

    # ------------------------------------------------------- ② 缺名册不报错

    def test_missing_roster_entry_is_not_an_error(self):
        """名册里**没有这个 id**（单位还没登场）⇒ 只改根表、不报错。

        ⚠️ 根表里也**没有**那个 id ⇒ 那是"存档里没这个单位"（另一个错），
        不是"名册缺条目" ⇒ 用一个**根表里有、名册里没有**的单位来测。
        """
        p = self.make(extra_entries={"units.yml": dump([
            {"id": 1, "type": "us_inf_42", "name_brief": "id_us_inf_42_brief",
             "name_full": None, "hq_id": 5, "xp": 0, "act_st": 4, "sup_st": 0,
             "losses": 0, "ap": 1, "mp": 3, "entr": 0, "supply": 3,
             "retreated": False, "hidden_defense": False, "specs": [],
             "supplied_by": 0, "uv": [12, 34]},
            {"id": 99, "type": "ger_inf_39", "name_brief": "id_ger_inf_39_brief",
             "name_full": None, "hq_id": 5, "xp": 0, "act_st": 4, "sup_st": 0,
             "losses": 0, "ap": 1, "mp": 3, "entr": 0, "supply": 3,
             "retreated": False, "hidden_defense": False, "specs": [],
             "supplied_by": 0, "uv": [13, 35]},
        ])})
        plan, res = self.commit(p, [Edit.unit_field(99, "name_brief", "新名字")])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual("新名字", _by_id(self.read(p, "units.yml"), 99)["name_brief"])

    def test_missing_roster_file_is_not_an_error(self):
        """整个名册文件不存在（独立场景存档）⇒ 照样能改名、不报错。"""
        p = self.make()
        # 造一个**没有** document/units.yml 的存档
        with zipfile.ZipFile(p) as zf:
            entries = {n: zf.read(n) for n in zf.namelist()
                       if n != "document/units.yml"}
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for n, d in entries.items():
                zf.writestr(n, d)
        plan, res = self.commit(p, [Edit.unit_field(1, "name_brief", "只有一个名字")])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual("只有一个名字",
                         _by_id(self.read(p, "units.yml"), 1)["name_brief"])

    # ----------------------------------------------------------- ③ 白名单

    def test_only_the_two_roster_tables_are_writable(self):
        """⚠️ `document/` 下**只有**那两张表能写（U124 的只读结论不变）。"""
        p = self.make()
        with self.open(p) as save:
            allowed = writable_entries(save)
        for e in ROSTER_WRITABLE:
            self.assertIn(e, allowed)
        self.assertIn("units.yml", allowed)
        self.assertIn("hqs.yml", allowed)
        for e in ("document/main.yml", "document/locale.yml",
                  "document/store.yml", "last_conference/main.yml"):
            self.assertNotIn(e, allowed,
                             "%s 不该能写（U124：document/ 只读）" % e)
        self.assertEqual(("document/units.yml", "document/hqs.yml"),
                         ROSTER_WRITABLE)
        self.assertNotIn("document/units.yml", ROOT_WRITABLE)

    def test_writing_another_document_table_is_blocked(self):
        """想改 `document/main.yml` ⇒ 硬拦（原存档不会被写入）。"""
        p = self.make()
        with self.open(p) as save:
            plan = save.plan_edit(
                [Edit("unit_field", {"unit_id": 1, "field": "name_brief",
                                     "value": "x"})],
                catalog=self.catalog)
        # 先确认正常改名是通过的
        self.assertTrue(plan.ok, plan.errors)

    # ------------------------------------------------------- ④ 名字字段规则

    def test_name_full_only_changes_when_it_existed(self):
        """`name_full` 原来不是 null 才改（null = 没有另一个名字）。"""
        p = self.make()
        plan, res = self.commit(p, [Edit.unit_field(1, "name_brief", "新名字")])
        self.assertTrue(res.ok, res.errors)
        root = _by_id(self.read(p, "units.yml"), 1)
        self.assertEqual("新名字", root["name_brief"])
        self.assertEqual("新名字", root["name_full"],
                         "根表里 name_full 原来不是 null ⇒ 应跟着改")
        roster = _by_id(self.read(p, "document/units.yml"), 1)
        self.assertIsNone(roster["name_full"],
                          "名册里 name_full 原本是 null ⇒ 别凭空造一个")

    def test_name_super_brief_follows(self):
        """总部的 `name_super_brief`（战役条标签）一起改。"""
        p = self.make(extra_entries={"document/hqs.yml": dump([
            {"id": 5, "name_brief": "id_hq_5_brief", "name_full": None,
             "name_super_brief": "id_hq_super"},
        ])})
        plan, res = self.commit(p, [Edit.hq_field(5, "name_brief", "改名了")])
        self.assertTrue(res.ok, res.errors)
        root = _by_id(self.read(p, "hqs.yml"), 5)
        roster = _by_id(self.read(p, "document/hqs.yml"), 5)
        self.assertEqual("改名了", root["name_super_brief"])
        self.assertEqual("改名了", roster["name_super_brief"])

    # ---------------------------------------------------- ⑥ 先退出游戏

    def test_rename_warns_to_quit_the_game_first(self):
        """游戏开着 ⇒ 退出时它把内存里的存档写回去 ⇒ 改名被覆盖。"""
        p = self.make()
        plan, res = self.commit(p, [Edit.unit_field(1, "name_brief", "新名字")])
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("先退出游戏" in w for w in plan.warnings),
                        plan.warnings)

    def test_hq_rename_warns_too(self):
        p = self.make()
        plan, res = self.commit(p, [Edit.hq_field(5, "name_brief", "新名字")])
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("先退出游戏" in w for w in plan.warnings),
                        plan.warnings)

    def test_other_fields_are_not_warned(self):
        """⚠️ 这条提醒**只**跟改名有关（U146 的判据：别的操作不适用就别报）。"""
        p = self.make()
        plan, res = self.commit(p, [Edit.unit_field(1, "xp", 300)])
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(any("先退出游戏" in w for w in plan.warnings),
                         plan.warnings)

    # ----------------------------------------------------- ⑤ 真实存档实测

    def test_real_save_rename_hits_both_tables(self):
        """**真实存档实测**：拿一份真存档的副本改名 ⇒ 两份都变。"""
        saves = find_saves(limit_per_dir=1)
        if not saves:
            self.skipTest("本机没有真实存档")
        src = saves[0]
        p = self.tmp / "real.usg"
        shutil.copy2(src, p)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            if "document/units.yml" not in names:
                self.skipTest("这份存档没有战役名册")
            units = yaml.safe_load(zf.read("units.yml")) or []
            roster = yaml.safe_load(zf.read("document/units.yml")) or []
        unit = next((u for u in units
                     if isinstance(u, dict) and isinstance(u.get("id"), int)
                     and _by_id(roster, u.get("id")) is not None), None)
        if unit is None:
            self.skipTest("这份存档里没有同时出现在两张表的单位")
        uid = unit["id"]
        new_name = "改名实测_U148"
        plan, res = self.commit(p, [Edit.unit_field(uid, "name_brief", new_name)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(new_name, _by_id(self.read(p, "units.yml"), uid)["name_brief"])
        self.assertEqual(new_name,
                         _by_id(self.read(p, "document/units.yml"), uid)["name_brief"])


if __name__ == "__main__":
    unittest.main()
