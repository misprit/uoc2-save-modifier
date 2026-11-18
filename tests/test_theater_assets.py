"""S9：战区资产（`theater_assets`）—— **唯一的 L3 写入白名单**。

**验收口径**（规范 §6.2b、§7.2 W8、§10 第 52/53/55/57 条）：

* **只在当前进行中的战斗里可改** —— 战斗外改会被 `Game.new` 重算覆盖，
  必须**禁用**并说明原因（不是让用户白改）；
* 写回时**只改 `theater_assets` 这一个键**，该文件其余键
  （`ar_ord` / `turn` / `scores` …）**逐字节原样保留**；
* **历史战斗的快照永远不许写**；
* **不会凭空新增**资产条目（场景没有这个资产就报错）；
* 游戏内的「重置会议」**撤不掉**它 ⇒ 必须用修改器自己的撤销（提示文案）。
"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save
from save_modifier_core.packing import list_entries

from ._fixtures import make_save


def _no_battle_state(**over):
    state = {
        "completed": False, "conference": "c_43_09", "front": None,
        "scenario": None, "variant": None, "segment_finished": True,
        "lost_scenario": None,
        "fronts": {"south": {"approved_plan": None, "played_segments": [],
                             "segment": "s_43_09_south", "situation_idx": 2,
                             "supply_value": [100, 100],
                             "tmp_approved_plan": None}},
    }
    state.update(over)
    return state


class TheaterAssetTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="theater_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def make(self, name="s.usg", **kw):
        return make_save(self.tmp / name, **kw)

    def open(self, path):
        return open_save(str(path), self.paths)

    def plan(self, path, edits):
        with self.open(path) as save:
            return save.plan_edit(edits, catalog=self.catalog)

    def commit(self, path, edits):
        with self.open(path) as save:
            p = save.plan_edit(edits, catalog=self.catalog)
            if not p.ok:
                return p, None
            return p, save.commit(p)


class TestTheaterAssetInBattle(TheaterAssetTestBase):
    def setUp(self):
        super().setUp()
        self.save_path = self.make()

    def test_set_to_use(self):
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("air_attack", to_use=5)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("games/avalanche/main.yml"))
        self.assertEqual(data["theater_assets"][0][0]["to_use"], 5)

    def test_only_theater_assets_key_changes(self):
        """同一个文件里，其余键必须逐字节原样 —— 不能整表替换。"""
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("air_attack", to_use=5)])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("games/avalanche/main.yml"))
        self.assertEqual(data["ar_ord"], 190)
        self.assertEqual(data["turn"], 3)
        self.assertEqual(data["scores"], {"casualties": 0})
        self.assertEqual(data["theater_assets"][0][1]["asset"], "naval_bombardment")

    def test_l3_entry_is_flagged(self):
        plan = self.plan(self.save_path,
                            [Edit.theater_asset("air_attack", to_use=5)])
        self.assertEqual(plan.changes[0].layer, "L3")
        self.assertTrue(plan.changes[0].is_l3_exception)

    def test_no_other_entries_change(self):
        """L3 之外的一切都不能动。"""
        before = list_entries(self.save_path)
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("air_attack", to_use=5)])
        self.assertTrue(res.ok, res.errors)
        after = list_entries(self.save_path)
        changed = [n for (n, h1), (_, h2) in zip(before, after) if h1 != h2]
        self.assertEqual(changed, ["games/avalanche/main.yml"])

    def test_unknown_asset_is_rejected(self):
        """场景里没有的资产**不会凭空新增**。"""
        plan = self.plan(self.save_path,
                            [Edit.theater_asset("not_a_real_asset", to_use=3)])
        self.assertFalse(plan.ok)
        self.assertIn("不会凭空新增", plan.errors[0])

    def test_negative_to_use_is_rejected(self):
        plan = self.plan(self.save_path,
                            [Edit.theater_asset("air_attack", to_use=-1)])
        self.assertFalse(plan.ok)

    def test_warns_that_game_cannot_undo_it(self):
        plan = self.plan(self.save_path,
                            [Edit.theater_asset("air_attack", to_use=5)])
        self.assertTrue(any("重置会议" in w for w in plan.warnings), plan.warnings)


class TestTheaterAssetOutOfBattle(TheaterAssetTestBase):
    def test_out_of_battle_is_blocked(self):
        """战斗外改必被下次开打覆盖 —— 必须禁用。"""
        p = self.make("out.usg", main_overrides={"in_state": _no_battle_state()})
        plan = self.plan(p, [Edit.theater_asset("air_attack", to_use=5)])
        self.assertFalse(plan.ok)
        self.assertIn("不在战斗中", plan.errors[0])

    def test_capability_bit_is_false_out_of_battle(self):
        p = self.make("out2.usg", main_overrides={"in_state": _no_battle_state()})
        with self.open(p) as save:
            caps = save.capabilities()
        self.assertFalse(caps.in_battle)
        self.assertFalse(caps.can_edit_theater_assets)
        self.assertIn("战斗", caps.unavailable_reason("theater_assets"))


class TestArchiveNeverWritten(TheaterAssetTestBase):
    def test_snapshot_entries_are_not_in_the_plan(self):
        """历史战斗的快照永远不许写 —— 只写当前战斗的 main.yml。"""
        p = self.make("arch.usg", extra_entries={
            "games/avalanche/archive/turn_01_foo/units.yml": b"- {id: 1}\n",
        })
        plan, res = self.commit(p, [Edit.theater_asset("air_attack", to_use=9)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.changed, ["games/avalanche/main.yml"])
        with zipfile.ZipFile(p) as zf:
            self.assertIn("games/avalanche/archive/turn_01_foo/units.yml",
                          zf.namelist())


class TestTheaterAssetThreeFields(TheaterAssetTestBase):
    """U20：三个字段（**当前可用 / 本场景剩余 / 每回合恢复**）都能单独改。

    **合法范围**（游戏字节码取证 —— `lib/uoc2/` 反汇编）：

    | 字段 | 游戏里的含义 | 游戏的 voluptuous schema | 合法范围 |
    |---|---|---|---|
    | `to_use` | 当前剩余可用次数 | `All(int, Range(min=0))` | 0 – ∞ |
    | `uses_total` | 本场景剩余总次数（`None` = 无限） | `Or(None, All(int, Range(min=0)))` | 0 – ∞ 或 None |
    | `uses_turn` | 每回合恢复次数 | `All(int, Range(min=1))` | 1 – ∞ |

    **跨字段不变式**：`to_use ≤ uses_total`（`uses_total` 有限时）——
    游戏每用一次资产就让 `uses_total` 减 1（`Game.spend_theater_asset`），
    减成负数会让存档校验失败 ⇒ 必须硬拦。
    """

    def setUp(self):
        super().setUp()
        self.save_path = self.make()

    def assets(self, path=None):
        with zipfile.ZipFile(path or self.save_path) as zf:
            data = yaml.safe_load(zf.read("games/avalanche/main.yml"))
        return {it["asset"]: it for grp in data["theater_assets"] for it in grp}

    # ---------------------------------------------------------- 单独改每个字段

    def test_only_to_use_changes(self):
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("long_range_recon", to_use=2)])
        self.assertTrue(res.ok, res.errors)
        a = self.assets()["long_range_recon"]
        self.assertEqual(a["to_use"], 2)
        self.assertEqual(a["uses_total"], 2)   # 没传 ⇒ 不动
        self.assertEqual(a["uses_turn"], 1)

    def test_only_uses_turn_changes(self):
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("long_range_recon", uses_turn=3)])
        self.assertTrue(res.ok, res.errors)
        a = self.assets()["long_range_recon"]
        self.assertEqual(a["uses_turn"], 3)
        self.assertEqual(a["to_use"], 1)
        self.assertEqual(a["uses_total"], 2)

    def test_only_uses_total_changes(self):
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("long_range_recon", uses_total=5)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.assets()["long_range_recon"]["uses_total"], 5)

    def test_uses_total_can_be_set_back_to_infinite(self):
        """`uses_total=None` = 无限 —— 改器必须能把有限值改回无限。"""
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("long_range_recon", uses_total=None)])
        self.assertTrue(res.ok, res.errors)
        self.assertIsNone(self.assets()["long_range_recon"]["uses_total"])

    def test_all_three_at_once(self):
        plan, res = self.commit(self.save_path, [Edit.theater_asset(
            "long_range_recon", to_use=2, uses_total=6, uses_turn=3)])
        self.assertTrue(res.ok, res.errors)
        a = self.assets()["long_range_recon"]
        self.assertEqual((a["to_use"], a["uses_total"], a["uses_turn"]), (2, 6, 3))

    # ---------------------------------------------------------------- 硬范围

    def test_to_use_zero_is_allowed(self):
        plan, res = self.commit(self.save_path,
                                [Edit.theater_asset("long_range_recon", to_use=0)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.assets()["long_range_recon"]["to_use"], 0)

    def test_negative_to_use_is_rejected(self):
        plan = self.plan(self.save_path,
                         [Edit.theater_asset("long_range_recon", to_use=-1)])
        self.assertFalse(plan.ok)

    def test_uses_turn_zero_is_rejected(self):
        """`uses_turn` 的 schema 是 `Range(min=1)` ⇒ 写 0 存档直接打不开。"""
        plan = self.plan(self.save_path,
                         [Edit.theater_asset("long_range_recon", uses_turn=0)])
        self.assertFalse(plan.ok)
        self.assertIn("uses_turn", plan.errors[0])

    def test_negative_uses_total_is_rejected(self):
        plan = self.plan(self.save_path,
                         [Edit.theater_asset("long_range_recon", uses_total=-1)])
        self.assertFalse(plan.ok)
        self.assertIn("uses_total", plan.errors[0])

    # -------------------------------------------------------- 跨字段不变式

    def test_to_use_over_uses_total_is_rejected(self):
        """`to_use > uses_total` ⇒ 用一次后 `uses_total` 变负 ⇒ 存档打不开。"""
        plan = self.plan(self.save_path,
                         [Edit.theater_asset("long_range_recon", to_use=3)])
        self.assertFalse(plan.ok)
        self.assertIn("不能大于", plan.errors[0])

    def test_lowering_uses_total_below_to_use_is_rejected(self):
        plan = self.plan(self.save_path,
                         [Edit.theater_asset("long_range_recon", uses_total=0)])
        self.assertFalse(plan.ok)

    def test_uses_turn_over_uses_total_warns(self):
        plan = self.plan(self.save_path,
                         [Edit.theater_asset("long_range_recon", uses_turn=9)])
        self.assertTrue(plan.ok)
        self.assertTrue(any("大于" in w for w in plan.warnings), plan.warnings)

    def test_to_use_over_uses_turn_warns_when_infinite(self):
        plan = self.plan(self.save_path, [Edit.theater_asset(
            "air_attack", to_use=9, uses_total=None, uses_turn=2)])
        self.assertTrue(plan.ok)
        self.assertTrue(any("大于" in w for w in plan.warnings), plan.warnings)

    # ---------------------------------------------------------- phase 分组

    def test_phase_selects_the_right_group(self):
        """`theater_assets` 按 **phase 分组** ⇒ 必须改当前 phase 那一组。"""
        p = self.make("phase.usg", battle_overrides={
            "phase": 1,
            "theater_assets": [[], [
                {"asset": "air_attack", "to_use": 1, "to_use_not_used": None,
                 "uses_total": None, "uses_turn": 1},
            ]],
        })
        plan, res = self.commit(p, [Edit.theater_asset("air_attack", to_use=4)])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(p) as zf:
            data = yaml.safe_load(zf.read("games/avalanche/main.yml"))
        self.assertEqual(data["theater_assets"][0], [])           # 第 0 组没动
        self.assertEqual(data["theater_assets"][1][0]["to_use"], 4)

    # ---------------------------------------------------------------- 其它

    def test_no_change_touches_nothing(self):
        plan = self.plan(self.save_path,
                         [Edit.theater_asset("long_range_recon", to_use=1)])
        self.assertEqual(plan.changes, [])

    def test_describe_lists_every_changed_field(self):
        d = Edit.theater_asset("long_range_recon", to_use=2, uses_turn=3).describe()
        self.assertIn("当前可用 → 2", d)
        self.assertIn("每回合恢复 → 3", d)
        self.assertNotIn("本场景剩余", d)
        d2 = Edit.theater_asset("long_range_recon", uses_total=None).describe()
        self.assertIn("本场景剩余 → 无限", d2)


if __name__ == "__main__":
    unittest.main()
