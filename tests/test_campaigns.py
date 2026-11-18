"""U18：战役只读数据层。

验收口径（规范 §7.8）：

* **索引**（内置 `data/campaign_index.json`，34 KB）：
  14 个战役 / 386 个场景 / 140 场会议；
  每个场景的目录名在游戏包 `scenarios/<id>/` 里**必须存在**；
  每个场景名必须能用游戏包 `locale.yml` 的 locale 键**复核**；
* **游戏包侧**：场景名册（units/hqs/main/locale）、战线商店、
  战线列表、会议列表都能读出来；
* **缺索引 / 缺游戏包都不报错**（降级，不崩）。

游戏没装 / DLC 没买时，涉及游戏包的测试自动跳过；
**索引测试不跳过**（索引是内置的）。
"""

import unittest
from pathlib import Path

from save_modifier_core import CorePaths
from save_modifier_core import campaigns as camp_mod

REPO = Path(__file__).resolve().parents[1]
INDEX_FILE = REPO / "src" / "save_modifier_core" / "data" / "campaign_index.json"


class TestCampaignIndex(unittest.TestCase):
    """内置索引（不依赖游戏包）。"""

    @classmethod
    def setUpClass(cls):
        cls.idx = camp_mod.default_campaign_index()

    def test_index_file_exists(self):
        self.assertTrue(INDEX_FILE.is_file(), "内置索引缺失")
        self.assertLess(INDEX_FILE.stat().st_size, 200 * 1024,
                        "索引超过 200 KB ⇒ 偏离「轻量索引」的约定")

    def test_schema_version(self):
        self.assertEqual(self.idx.data.get("schema_version"),
                         "uoc2-campaign-index/v1")

    def test_campaign_count(self):
        ids = self.idx.campaign_ids()
        self.assertEqual(len(ids), 14)
        self.assertIn("west", ids)
        self.assertIn("stalingrad", ids)

    def test_campaign_names_are_chinese(self):
        self.assertEqual(self.idx.campaign_name("west"), "西线大捷")
        self.assertEqual(self.idx.campaign_name("stalingrad"), "斯大林格勒")

    def test_unknown_campaign_falls_back(self):
        """查不到战役 ⇒ 退回短名，不报错。"""
        self.assertEqual(self.idx.campaign_name("没有这个战役"), "没有这个战役")
        self.assertEqual(self.idx.routes("没有这个战役"), [])
        self.assertEqual(self.idx.conferences("没有这个战役"), ())

    def test_conferences_and_scenes(self):
        cs = self.idx.conferences("west", "historical")
        self.assertTrue(cs)
        first = cs[0]
        self.assertEqual(first.id, "c_43_04")
        self.assertEqual(first.text, "第1次会议")
        self.assertEqual([s.id for s in first.scenes],
                         ["wadi_akarit", "tunis", "husky"])
        self.assertEqual(first.scenes[0].name, "瓦迪阿卡利特")
        self.assertEqual(first.scenes[0].variant, "base")

    def test_variant_marked(self):
        """变体场景要标 variant。"""
        c = self.idx.find_conference("west", "c_43_09")
        self.assertIsNotNone(c)
        variants = {s.id: s.variant for s in c.scenes}
        self.assertEqual(variants.get("volturno_line"), "variant")
        self.assertEqual(variants.get("avalanche"), "base")

    def test_find_across_routes(self):
        """跨路线查找（会议在 historical 和 fantasy 里都可能出现）。"""
        s = self.idx.find_scenario("west", "monte_cassino")
        self.assertIsNotNone(s)
        self.assertEqual(s.name, "卡西诺山战役")

    def test_scenarios_of(self):
        scenes = self.idx.scenarios_of("west", "c_43_04")
        self.assertEqual(len(scenes), 3)

    def test_total_counts(self):
        """索引总量：386 场景 / 140 会议（U18 实测基线）。"""
        n_conf = n_scen = 0
        for cid in self.idx.campaign_ids():
            for r in self.idx.routes(cid):
                for c in self.idx.conferences(cid, r):
                    n_conf += 1
                    n_scen += len(c.scenes)
        self.assertEqual(n_conf, 140)
        self.assertEqual(n_scen, 386)

    def test_missing_index_returns_empty(self):
        """索引文件缺失 ⇒ 空索引，不抛异常。"""
        idx = camp_mod.load_campaign_index(path=Path("不存在的路径.json"))
        self.assertEqual(idx.campaign_ids(), [])
        self.assertEqual(idx.campaign_name("west"), "west")


class TestCampaignDataAgainstGame(unittest.TestCase):
    """游戏包侧（需要装游戏）。"""

    @classmethod
    def setUpClass(cls):
        cls.paths = CorePaths.discover()
        cls.idx = camp_mod.default_campaign_index()
        cls.cd = camp_mod.CampaignData(cls.paths, cls.idx)
        cls.skip = not cls.paths.packages()

    def setUp(self):
        if self.skip:
            self.skipTest("本机没找到游戏包目录，跳过")

    def test_campaign_dir_found(self):
        d = self.cd.campaign_dir("west")
        self.assertIsNotNone(d)
        self.assertTrue((d / "scenarios").is_dir())

    def test_scenario_dirs_match_index(self):
        """索引里每个场景，游戏包必须有对应目录（U18：386/386）。"""
        bad = []
        for cid in self.idx.campaign_ids():
            for r in self.idx.routes(cid):
                for c in self.idx.conferences(cid, r):
                    for s in c.scenes:
                        if self.cd.scenario_dir(cid, s.id) is None:
                            bad.append((cid, s.id))
        self.assertEqual(bad, [], "索引里有游戏包不存在的场景")

    def test_scenario_names_verified_by_locale(self):
        """场景名必须能用游戏包 locale.yml 的键复核出来。"""
        from save_modifier_core import yamlio
        bad = []
        for cid in self.idx.campaign_ids():
            for r in self.idx.routes(cid):
                for c in self.idx.conferences(cid, r):
                    for s in c.scenes:
                        d = self.cd.scenario_dir(cid, s.id)
                        if d is None:
                            continue
                        lp = d / "locale.yml"
                        if not lp.is_file():
                            bad.append((cid, s.id, "无 locale.yml"))
                            continue
                        ld = yamlio.load(lp.read_bytes()) or {}
                        key = ld.get("scenario_name")
                        got = self.cd.locale.get(str(key)) if key else ""
                        if got != s.name:
                            bad.append((cid, s.id, key, s.name, got))
        self.assertEqual(bad, [], "场景名与游戏包 locale 不一致")

    def test_roster_reads_units_and_hqs(self):
        r = self.cd.roster("west", "monte_cassino")
        self.assertIsNotNone(r)
        self.assertEqual(r.name, "卡西诺山战役")
        self.assertTrue(r.units, "场景单位为空")
        self.assertTrue(r.hqs, "场景 HQ 为空")
        self.assertEqual(r.base_num_turns, 6)
        self.assertIsInstance(r.start, str)
        # 单位名是 locale 键 ⇒ 能查到中文名
        u = r.units[0]
        self.assertTrue(self.cd.locale.get(str(u.get("name_brief"))))

    def test_roster_missing_returns_none(self):
        self.assertIsNone(self.cd.roster("west", "没有这个场景"))

    def test_store_reads_items(self):
        st = self.cd.store("west", "italy", "c_43_04")
        self.assertIsNotNone(st)
        self.assertTrue(st.items)
        # 条目结构：spec XOR equipment
        for e in st.items:
            self.assertTrue(("spec" in e) ^ ("equipment" in e))

    def test_store_missing_returns_none(self):
        self.assertIsNone(self.cd.store("west", "italy", "c_99_99"))

    def test_fronts_and_conferences(self):
        self.assertEqual(self.cd.fronts("west"), ["france", "italy"])
        confs = self.cd.conferences_of_front("west", "italy")
        self.assertIn("c_43_04", confs)

    def test_index_conferences_exist_in_game_package(self):
        """索引里每场会议，游戏包 fronts/*/conferences/ 必须有对应 yml。"""
        bad = []
        for cid in self.idx.campaign_ids():
            for r in self.idx.routes(cid):
                for c in self.idx.conferences(cid, r):
                    if not c.id:
                        continue
                    found = any(
                        (self.cd.campaign_dir(cid) / "fronts" / fr / "conferences"
                         / (c.id + ".yml")).is_file()
                        for fr in self.cd.fronts(cid))
                    if not found:
                        bad.append((cid, c.id))
        self.assertEqual(bad, [], "索引里有游戏包不存在的会议")


if __name__ == "__main__":
    unittest.main()
