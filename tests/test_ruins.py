"""U183：核心库只读 API —— 废墟清单 `Save.ruined_cities()`。

**测什么**
----------
1. 权威清单 = 根 `main.yml` 的 `destroyed_cities`（**顺序 = 摧毁时间序**）；
2. 「影响哪些场景」= `games/<场景>/cities.yml` 快照里**实际出现**的那些场景；
3. `latest` 指向清单最后一项（= 最新变成废墟的那座）；
4. 清单里**同一个坐标出现多次** ⇒ 结果去重，但 `occurrences` 记着次数；
5. 快照里有**清单外**的坐标 ⇒ 不算废墟（清单才是权威）；
6. 坏数据（坐标不是两元素 / `map` 不是列表 / 条目形状不对）⇒ **跳过不崩**；
7. 真实存档上的不变量：**清单最后一项 100% 能定位到至少一个场景快照**。

（机制出处见 `docs/开发上下文.md` §5.1bn / §5.1bo / §5.1bp，
证据脚本 `docs/证据脚本/e167_ruins_mapobjects.py` 与 `e168_ruins_survey.py`。）
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from save_modifier_core import open_save

from ._fixtures import dump, make_save


def cities_entry(uvs) -> bytes:
    """造一个 `games/<场景>/cities.yml` 的内容。

    真实形状（`e167` 字节码）：`map: [[x, y], {in_repair: false}]`。
    """
    return dump({"map": [[list(uv), {"in_repair": False}] for uv in uvs]})


class RuinedCitiesTest(unittest.TestCase):
    """`Save.ruined_cities()`。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ruins_"))
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)

    def _make(self, **kw):
        path = make_save(self.tmp / "s.usg", **kw)
        return path

    # ---------------------------------------------------------------- 基础

    def test_empty_list_gives_empty_result(self):
        path = self._make(main_overrides={"destroyed_cities": []})
        with open_save(str(path)) as save:
            self.assertEqual(save.ruined_cities(), [])

    def test_no_key_gives_empty_result(self):
        path = self._make(main_overrides={"destroyed_cities": None})
        with open_save(str(path)) as save:
            self.assertEqual(save.ruined_cities(), [])

    def test_one_city_one_scenario(self):
        path = self._make(
            main_overrides={"destroyed_cities": [[380, 208]]},
            extra_entries={"games/avalanche/cities.yml": cities_entry([(380, 208)])},
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual(len(rs), 1)
        self.assertEqual(rs[0].uv, (380, 208))
        self.assertEqual(rs[0].scenarios, ("avalanche",))
        self.assertEqual(rs[0].index, 0)
        self.assertTrue(rs[0].latest)
        self.assertEqual(rs[0].occurrences, 1)

    def test_order_is_destruction_order(self):
        """清单顺序 = 摧毁时间序 ⇒ `index` 按它排，`latest` 是最后一项。"""
        path = self._make(
            main_overrides={"destroyed_cities": [[346, 171], [373, 184], [380, 208]]},
            extra_entries={
                "games/avalanche/cities.yml": cities_entry([(346, 171), (373, 184)]),
                "games/voronezh/cities.yml": cities_entry([(346, 171)]),
                "games/fischreiher/cities.yml": cities_entry([(373, 184)]),
            },
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual([r.uv for r in rs], [(346, 171), (373, 184), (380, 208)])
        self.assertEqual([r.index for r in rs], [0, 1, 2])
        self.assertEqual([r.latest for r in rs], [False, False, True])
        # 影响场景 = 快照里**实际出现**的那些场景
        self.assertEqual(rs[0].scenarios, ("avalanche", "voronezh"))
        self.assertEqual(rs[1].scenarios, ("avalanche", "fischreiher"))
        # 清单里有、但没有任何场景快照收录 ⇒ 影响场景为空
        self.assertEqual(rs[2].scenarios, ())

    def test_scenarios_are_sorted(self):
        path = self._make(
            main_overrides={"destroyed_cities": [[10, 10]]},
            extra_entries={
                "games/zeta/cities.yml": cities_entry([(10, 10)]),
                "games/alpha/cities.yml": cities_entry([(10, 10)]),
            },
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual(rs[0].scenarios, ("alpha", "zeta"))

    # ---------------------------------------------------------------- 重复与杂项

    def test_duplicate_coordinates_are_merged(self):
        """「重打上一场」后再摧毁一次会 append 第二次 ⇒ 清单里可能有重复。"""
        path = self._make(
            main_overrides={"destroyed_cities": [[380, 208], [100, 100], [380, 208]]},
            extra_entries={"games/avalanche/cities.yml": cities_entry([(380, 208)])},
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual([r.uv for r in rs], [(380, 208), (100, 100)])
        self.assertEqual(rs[0].occurrences, 2)
        self.assertEqual(rs[1].occurrences, 1)
        # 去重后最后一项 = (100, 100)
        self.assertTrue(rs[1].latest)
        self.assertFalse(rs[0].latest)

    def test_snapshot_only_coordinate_is_not_a_ruin(self):
        """快照里有、清单里没有的坐标**不算废墟** —— 清单才是权威。"""
        path = self._make(
            main_overrides={"destroyed_cities": [[380, 208]]},
            extra_entries={
                "games/avalanche/cities.yml": cities_entry([(380, 208), (999, 999)]),
            },
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual([r.uv for r in rs], [(380, 208)])
        self.assertEqual(rs[0].scenarios, ("avalanche",))

    def test_broken_snapshot_does_not_crash(self):
        """坏数据只跳过那一项，不许把整个存档读炸。"""
        path = self._make(
            main_overrides={"destroyed_cities": [[380, 208]]},
            extra_entries={
                "games/avalanche/cities.yml": dump({"map": [
                    [380, 208],                       # 坐标不是列表
                    [[1, 2, 3], {"in_repair": False}],  # 坐标不是两元素
                    "不是列表",
                ]}),
                "games/broken/cities.yml": dump({"map": "不是列表"}),
                "games/nomap/cities.yml": dump({"别的键": 1}),
            },
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual([r.uv for r in rs], [(380, 208)])
        self.assertEqual(rs[0].scenarios, ())

    def test_broken_campaign_list_does_not_crash(self):
        path = self._make(
            main_overrides={"destroyed_cities": ["不是列表", [1], [2, 3], None]},
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual([r.uv for r in rs], [(2, 3)])

    def test_standalone_scenario_save(self):
        """独立场景存档：没有 `games/`，清单照读，影响场景为空。"""
        path = self._make(
            main_overrides={"destroyed_cities": [[380, 208]],
                            "standalone_scenario": "normandy_breakout"},
        )
        with open_save(str(path)) as save:
            rs = save.ruined_cities()
        self.assertEqual([r.uv for r in rs], [(380, 208)])
        self.assertEqual(rs[0].scenarios, ())


class RuinedCitiesRealSaveTest(unittest.TestCase):
    """真实存档上的不变量。"""

    def test_latest_ruin_is_in_some_scenario_snapshot(self):
        """**清单最后一项 100% 能定位到至少一个场景快照**（`e168` 实测 55/55）。"""
        from ._helpers import pick_save

        info = pick_save(
            lambda i: _has_ruins(i.save_id),
            reason="本机没有带废墟清单的存档",
        )
        with open_save(info.save_id) as save:
            rs = save.ruined_cities()
            self.assertTrue(rs, "这个存档应该有废墟")
            self.assertTrue(rs[-1].latest)
            self.assertTrue(rs[-1].scenarios,
                            "最新变成废墟的那座必须能在某个场景快照里找到")


def _has_ruins(save_id: str) -> bool:
    from save_modifier_core import open_save as _open

    try:
        with _open(save_id) as sv:
            raw = sv.root_main().get("destroyed_cities")
            return bool(raw)
    except Exception:
        return False


if __name__ == "__main__":
    unittest.main()
