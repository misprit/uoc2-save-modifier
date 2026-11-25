"""U184：写入路径 —— `Edit.city_restore`（修复一座被摧毁的城市）。

**测什么**
----------
1. **三处一起改**（规范 §6.5.3）：根 `main.yml` 的 `destroyed_cities`、
   每个场景的 `games/<场景>/cities.yml`、同格要塞的 `games/<场景>/forts.yml`；
2. **重复坐标** ⇒ 清单里**所有**出现都被删；
3. **删空** ⇒ `cities.yml` 写成 `map: []`（与「文件不存在」等价，e167 字节码）；
4. **战斗中硬拦**（能力位 `in_battle`）—— 改了会被游戏从内存重写覆盖回去；
5. **只改同格要塞** —— 异格的要塞（城市没被摧毁但要塞被单独打掉）不许动；
6. `restore_forts=False` ⇒ 不动要塞；
7. **端到端**：plan → commit → 回读 ZIP 验证三处都改了，**其它条目逐字节不变**；
8. **写盘白名单**：`games/*/cities.yml` 与 `forts.yml` 放行，`games/**` 其余条目仍然拦。

（机制出处见 `docs/开发上下文.md` §5.1bn / §5.1bo / §5.1bp，
证据脚本 `docs/证据脚本/e167_ruins_mapobjects.py` 与 `e168_ruins_survey.py`。）
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from save_modifier_core import Edit, open_save

from ._fixtures import dump, make_save


def cities_entry(uvs) -> bytes:
    """`games/<场景>/cities.yml` 的内容（真实形状见 e167）。"""
    return dump({"map": [[list(uv), {"in_repair": False}] for uv in uvs]})


def forts_entry(rows) -> bytes:
    """`games/<场景>/forts.yml` 的内容：`rows` = [(uv, functional), …]。"""
    return dump({"map": [[list(uv), {"functional": fn}] for uv, fn in rows]})


#: **不在战斗里**的 `in_state`（`in_state.scenario` 非空 = 战斗中）。
IDLE_STATE = {
    "completed": False,
    "conference": "c_43_09",
    "front": "south",
    "scenario": None,
    "variant": None,
    "segment_finished": True,
    "lost_scenario": None,
    "fronts": {},
}


class CityRestoreTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="city_restore_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _save(self, *, destroyed=None, cities=None, forts=None, in_battle=False,
              extra=None):
        """造一个存档。

        `cities` / `forts` = `{场景: 内容bytes}`。
        """
        entries = dict(extra or {})
        for sc, content in (cities or {}).items():
            entries["games/%s/cities.yml" % sc] = content
        for sc, content in (forts or {}).items():
            entries["games/%s/forts.yml" % sc] = content
        state = dict(IDLE_STATE)
        if in_battle:
            state["scenario"] = "avalanche"
        return make_save(
            self.tmp / "s.usg",
            main_overrides={
                "destroyed_cities": destroyed if destroyed is not None else [],
                "in_state": state,
            },
            extra_entries=entries,
        )

    def _read(self, path, entry):
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read(entry)
        import yaml
        return yaml.safe_load(raw.decode("utf-8"))

    def _read_raw(self, path, entry) -> bytes:
        with zipfile.ZipFile(path, "r") as zf:
            return zf.read(entry)


class TestCityRestore(CityRestoreTestBase):
    """计划里的改动。"""

    def test_three_places_are_changed(self):
        path = self._save(
            destroyed=[[380, 208]],
            cities={"avalanche": cities_entry([(380, 208)])},
            forts={"avalanche": forts_entry([((380, 208), False),
                                             ((500, 500), False)])},
        )
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
        self.assertTrue(plan.ok, plan.errors)
        self.assertIn("main.yml", plan.changed_entries)
        self.assertIn("games/avalanche/cities.yml", plan.changed_entries)
        self.assertIn("games/avalanche/forts.yml", plan.changed_entries)

    def test_in_battle_is_refused(self):
        """战斗中改了会被游戏从内存重写覆盖回去 ⇒ 硬拦。"""
        path = self._save(destroyed=[[380, 208]], in_battle=True)
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
        self.assertFalse(plan.ok)
        self.assertTrue(plan.errors)
        self.assertIn("战斗中", " ".join(plan.errors))

    def test_coordinate_not_in_list_is_refused(self):
        path = self._save(destroyed=[[1, 1]])
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
        self.assertFalse(plan.ok)
        self.assertIn("不在废墟清单里", " ".join(plan.errors))

    def test_bad_uv_is_refused(self):
        path = self._save(destroyed=[[380, 208]])
        for bad in ([1], "380,208", [380, -1], [380, "208"], None):
            with open_save(str(path)) as save:
                plan = save.plan_edit([Edit.city_restore(bad)])
            self.assertFalse(plan.ok, bad)
            self.assertIn("两个非负整数", " ".join(plan.errors))

    def test_empty_list_is_refused(self):
        path = self._save(destroyed=[])
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
        self.assertFalse(plan.ok)


class TestCityRestoreCommit(CityRestoreTestBase):
    """真的写盘以后是什么样。"""

    def test_commit_changes_all_three_places(self):
        path = self._save(
            destroyed=[[380, 208]],
            cities={"avalanche": cities_entry([(380, 208), (400, 300)])},
            forts={"avalanche": forts_entry([((380, 208), False),
                                             ((500, 500), False)])},
        )
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)

        # ① 战役清单
        self.assertEqual(self._read(path, "main.yml")["destroyed_cities"], [])
        # ② 场景快照
        cities = self._read(path, "games/avalanche/cities.yml")["map"]
        self.assertEqual([c[0] for c in cities], [[400, 300]])
        # ③ 同格要塞恢复；**异格要塞不动**
        forts = self._read(path, "games/avalanche/forts.yml")["map"]
        by_uv = {tuple(f[0]): f[1] for f in forts}
        self.assertIs(by_uv[(380, 208)]["functional"], True)
        self.assertIs(by_uv[(500, 500)]["functional"], False)

    def test_commit_removes_all_duplicates(self):
        path = self._save(
            destroyed=[[380, 208], [100, 100], [380, 208]],
            cities={"avalanche": cities_entry([(380, 208)])},
        )
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self._read(path, "main.yml")["destroyed_cities"],
                         [[100, 100]])

    def test_commit_across_several_scenarios(self):
        """同一座城出现在多个场景的快照里 ⇒ **每个都要改**（否则永久残留）。"""
        path = self._save(
            destroyed=[[380, 208]],
            cities={"avalanche": cities_entry([(380, 208)]),
                    "edelweiss": cities_entry([(380, 208)]),
                    "other": cities_entry([(111, 222)])},
            forts={"avalanche": forts_entry([((380, 208), False)]),
                   "edelweiss": forts_entry([((380, 208), False)])},
        )
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        for sc in ("avalanche", "edelweiss"):
            self.assertEqual(self._read(path, "games/%s/cities.yml" % sc)["map"], [])
            forts = self._read(path, "games/%s/forts.yml" % sc)["map"]
            self.assertIs(forts[0][1]["functional"], True)
        # 无关场景原样不动
        self.assertEqual(
            [c[0] for c in self._read(path, "games/other/cities.yml")["map"]],
            [[111, 222]])

    def test_empty_snapshot_becomes_empty_map(self):
        """删空 ⇒ 写 `map: []`（与「文件不存在」完全等价，e167 字节码）。"""
        path = self._save(
            destroyed=[[380, 208]],
            cities={"avalanche": cities_entry([(380, 208)])},
        )
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self._read(path, "games/avalanche/cities.yml"),
                         {"map": []})

    def test_restore_forts_false_leaves_forts_alone(self):
        path = self._save(
            destroyed=[[380, 208]],
            cities={"avalanche": cities_entry([(380, 208)])},
            forts={"avalanche": forts_entry([((380, 208), False)])},
        )
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208),
                                                      restore_forts=False)])
            self.assertTrue(plan.ok, plan.errors)
            self.assertNotIn("games/avalanche/forts.yml", plan.changed_entries)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        forts = self._read(path, "games/avalanche/forts.yml")["map"]
        self.assertIs(forts[0][1]["functional"], False)

    def test_other_entries_are_byte_identical(self):
        """**只改该改的** —— 其它条目逐字节不变（§7.2 W7）。"""
        path = self._save(
            destroyed=[[380, 208]],
            cities={"avalanche": cities_entry([(380, 208)])},
        )
        before = {}
        with zipfile.ZipFile(path, "r") as zf:
            for n in zf.namelist():
                before[n] = zf.read(n)
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        after = {}
        with zipfile.ZipFile(path, "r") as zf:
            for n in zf.namelist():
                after[n] = zf.read(n)
        self.assertEqual(set(before), set(after), "条目清单变了")
        changed = {n for n in before if before[n] != after[n]}
        self.assertEqual(changed, {"main.yml", "games/avalanche/cities.yml"})


class TestRuinSnapshotWhitelist(CityRestoreTestBase):
    """写盘白名单：`games/*/cities.yml` 与 `forts.yml` 放行，其余仍拦。"""

    def test_only_the_two_snapshot_tables_are_writable(self):
        from save_modifier_core.plan import writable_entries

        path = self._save(
            destroyed=[[380, 208]],
            cities={"avalanche": cities_entry([(380, 208)])},
            forts={"avalanche": forts_entry([((380, 208), False)])},
        )
        with open_save(str(path)) as save:
            allowed = writable_entries(save)
        self.assertIn("games/avalanche/cities.yml", allowed)
        self.assertIn("games/avalanche/forts.yml", allowed)
        # `games/**` 的其它条目仍然只读
        self.assertNotIn("games/avalanche/main.yml", allowed)
        self.assertNotIn("games/avalanche/units.yml", allowed)
        self.assertNotIn("games/avalanche/ar_list.yml", allowed)

    def test_snapshot_tables_are_marked_as_l3(self):
        path = self._save(destroyed=[[380, 208]],
                          cities={"avalanche": cities_entry([(380, 208)])})
        with open_save(str(path)) as save:
            plan = save.plan_edit([Edit.city_restore((380, 208))])
        for c in plan.changes:
            if c.entry.endswith("cities.yml"):
                self.assertEqual(c.layer, "L3")
                self.assertTrue(c.is_l3_exception)


class TestCityRestoreRealSave(CityRestoreTestBase):
    """真实存档（**副本**）上的端到端。

    ⚠️ **玩家真存档绝不可写** ⇒ 这里先复制到临时目录再操作（规范 §6 边界）。
    """

    def _real_save_copy(self):
        from ._helpers import pick_save
        from save_modifier_core import open_save as _open

        def _ok(info):
            try:
                with _open(info.save_id) as sv:
                    rs = sv.ruined_cities()
                    return bool(rs) and not sv.capabilities().in_battle
            except Exception:
                return False

        info = pick_save(_ok, reason="本机没有「有废墟且不在战斗中」的存档")
        dst = self.tmp / "copy.usg"
        shutil.copy2(str(info.path), str(dst))
        return info, dst

    def test_real_save_end_to_end(self):
        from save_modifier_core import Edit, open_save

        info, dst = self._real_save_copy()
        with open_save(str(dst)) as save:
            rs = save.ruined_cities()
            self.assertTrue(rs)
            target = rs[-1]          # 最新变成废墟的那座
            self.assertTrue(target.scenarios, "最新那座必须落在某个场景快照里")
            before_entries = {}
            with zipfile.ZipFile(str(dst), "r") as zf:
                for n in zf.namelist():
                    before_entries[n] = zf.read(n)

            plan = save.plan_edit([Edit.city_restore(target.uv)])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
            self.assertTrue(res.ok, res.errors)

        # 回读：① 清单里没有它了；② 那些场景的快照里也没有了
        with open_save(str(dst)) as save:
            after = save.ruined_cities()
            self.assertNotIn(target.uv, [r.uv for r in after])
        for sc in target.scenarios:
            data = self._read(dst, "games/%s/cities.yml" % sc)
            for item in data.get("map") or []:
                self.assertNotEqual(tuple(item[0]), target.uv,
                                    "场景 %s 的快照里还留着这座废墟" % sc)

        # 只改该改的条目
        with zipfile.ZipFile(str(dst), "r") as zf:
            after_entries = {n: zf.read(n) for n in zf.namelist()}
        self.assertEqual(set(before_entries), set(after_entries))
        changed = {n for n in before_entries
                   if before_entries[n] != after_entries[n]}
        expect = {"main.yml"}
        for sc in target.scenarios:
            expect.add("games/%s/cities.yml" % sc)
        self.assertTrue(changed <= (expect | {
            "games/%s/forts.yml" % sc for sc in target.scenarios}),
            "改动了不该改的条目：%s" % (changed - expect))


if __name__ == "__main__":
    unittest.main()
