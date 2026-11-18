"""核心库：特种兵 / 国籍 / 战役默认池（U10 口径）。

**测什么**
----------
1. `Catalog.spec_type()` 拿得到攻防装甲火力 / 国籍 / 阵营 / flags；
2. `Catalog.nationality()` 拿得到 `parent_nationality`（游戏判定要用）；
3. `Catalog.spec_can_attach()` **逐条复刻游戏字节码**（`e162`）——
   阵营相同 + 国籍相同或父国籍相同；`captured=True` 跳过；
4. `Catalog.campaign_specialist_pool()` = 商店 ∪ 场景，
   且对「游戏自己用过的」**零假阴性**（`e163`）；
5. `Catalog.specialist_candidates()` 的**三层兜底**（U10 拍板）：
   正常 / 找不到战役包 / 敌国单位交集为空。

⚠️ 依赖游戏安装目录（读游戏包的类型表与战役包）。
找不到游戏目录就整组跳过 —— 不要让核心库回归因为没装游戏而挂掉。
"""

from __future__ import annotations

import unittest


def _catalog():
    from save_modifier_core.catalog import Catalog
    try:
        cat = Catalog()
        cat.spec_type_names()
    except Exception as exc:            # pragma: no cover —— 没装游戏
        raise unittest.SkipTest(f"找不到游戏目录，跳过：{exc}")
    return cat


class SpecialistTypeTest(unittest.TestCase):
    """`spec_type()` / `nationality()` 的字段。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cat = _catalog()

    def test_spec_type_fields(self):
        s = self.cat.spec_type("us_armx_42")
        self.assertIsNotNone(s)
        self.assertEqual(s.faction, "allies")
        self.assertEqual(s.nationality, "us")
        self.assertEqual((s.attack, s.defense, s.armor, s.artillery), (9, 5, 2, 0))
        self.assertEqual(s.flags, ())
        self.assertTrue(s.name_brief.startswith("id_"))

    def test_spec_type_flags(self):
        s = self.cat.spec_type("us_armx_42_opt")
        self.assertEqual(s.flags, ("lci",))
        s2 = self.cat.spec_type("us_towed_arty_42")
        self.assertEqual(set(s2.flags), {"towed", "arty"})

    def test_spec_type_unknown(self):
        self.assertIsNone(self.cat.spec_type("不存在的特种兵"))
        self.assertIsNone(self.cat.spec_type(""))

    def test_specialist_count(self):
        self.assertEqual(len(self.cat.spec_type_names()), 375)

    def test_nationality_parent(self):
        ita = self.cat.nationality("italian")
        self.assertIsNotNone(ita)
        self.assertEqual(ita.faction, "axis")
        self.assertEqual(ita.parent_nationality, "german")
        us = self.cat.nationality("us")
        self.assertIsNone(us.parent_nationality)

    def test_nationality_count(self):
        """实测 40 个国籍，其中 27 个有 parent_nationality（`e163`）。"""
        names = self.cat.nationality_names()
        self.assertEqual(len(names), 40)
        with_parent = [n for n in names
                       if self.cat.nationality(n).parent_nationality]
        self.assertEqual(len(with_parent), 27)


class SpecCanAttachTest(unittest.TestCase):
    """`spec_can_attach()` —— 逐条复刻游戏字节码（`e162`）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cat = _catalog()

    def _count(self, unit_type: str) -> int:
        return sum(1 for n in self.cat.spec_type_names()
                   if self.cat.spec_can_attach(n, unit_type))

    def test_counts_match_bytecode(self):
        """实测：us_arm_42=23 / ger_inf_40=97 / sov_inf_41=61。"""
        self.assertEqual(self._count("us_arm_42"), 23)
        self.assertEqual(self._count("ger_inf_40"), 97)
        self.assertEqual(self._count("sov_inf_41"), 61)

    def test_faction_must_match(self):
        """苏联的单位不能挂美军的特种兵。"""
        self.assertFalse(self.cat.spec_can_attach("us_recon_42", "sov_inf_41"))
        self.assertTrue(self.cat.spec_can_attach("sov_armx_41", "sov_inf_41"))

    def test_parent_nationality(self):
        """意大利单位的父国籍 = german ⇒ 德军特种兵可挂（实测 121 种）。"""
        ita = self.cat.unit_type("ita_alp_39")
        self.assertIsNotNone(ita)
        self.assertEqual(ita.nationality, "italian")
        self.assertTrue(self.cat.spec_can_attach("ger_arty_40", "ita_alp_39"))
        self.assertFalse(self.cat.spec_can_attach("us_recon_42", "ita_alp_39"))
        n = sum(1 for s in self.cat.spec_type_names()
                if self.cat.spec_can_attach(s, "ita_alp_39"))
        self.assertEqual(n, 121)

    def test_captured_skips_checks(self):
        """`captured=True` ⇒ 跳过阵营 / 国籍检查。"""
        self.assertFalse(self.cat.spec_can_attach("ger_recon_41", "us_arm_42"))
        self.assertTrue(self.cat.spec_can_attach("ger_recon_41", "us_arm_42",
                                                  captured=True))


class CampaignPoolTest(unittest.TestCase):
    """战役默认池 = 商店 ∪ 场景（`e163`）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cat = _catalog()

    def test_pool_size(self):
        """实测：base/west 商店 18 + 场景 27 ⇒ 并集 45。"""
        pool = self.cat.campaign_specialist_pool("west")
        self.assertEqual(len(pool), 45)

    def test_store_part_is_player_faction_only(self):
        """**商店部分**只卖玩家一方阵营（场景部分含敌国单位 ⇒ 不纯净）。

        ⚠️ 战役默认池 = 商店 ∪ 场景，**场景里双方单位都有** ⇒ 池本身不是阵营纯净的；
        阵营纯净的是「商店」这一半。真正保证"只出现我方"的是 **e162 规则**。
        """
        from save_modifier_core import CorePaths, yamlio
        cdir = self.cat.campaign_dir("west")
        self.assertIsNotNone(cdir)
        store: set[str] = set()
        for cf in sorted(cdir.rglob("conferences/*.yml")):
            data = yamlio.load(cf.read_bytes())
            if not isinstance(data, dict):
                continue
            for sub in ("store", "elite_store"):
                for e in (data.get(sub) or []):
                    if isinstance(e, dict) and e.get("spec"):
                        store.add(str(e["spec"]))
        facs = {self.cat.spec_type(n).faction for n in store}
        self.assertEqual(facs, {"allies"}, f"商店里出现了敌国阵营：{facs}")

    def test_candidates_for_player_unit_are_player_faction_only(self):
        """**玩家方单位**的候选里只有玩家方阵营的（规则保证了这一点）。"""
        cands, _ = self.cat.specialist_candidates("us_arm_42", "west")
        facs = {self.cat.spec_type(n).faction for n in cands}
        self.assertEqual(facs, {"allies"})

    def test_pool_covers_game_used(self):
        """**零假阴性**：场景里游戏自己挂过的特种兵都在池里。"""
        from save_modifier_core import CorePaths, yamlio
        cdir = self.cat.campaign_dir("west")
        self.assertIsNotNone(cdir)
        used: set[str] = set()
        for uf in sorted(cdir.rglob("scenarios/*/units.yml")):
            data = yamlio.load(uf.read_bytes())
            if not isinstance(data, list):
                continue
            for u in data:
                if isinstance(u, dict):
                    for s in (u.get("specs") or []):
                        if isinstance(s, dict) and s.get("type"):
                            used.add(str(s["type"]))
        pool = self.cat.campaign_specialist_pool("west")
        miss = {n for n in used
                if self.cat.spec_type(n) is not None
                and self.cat.spec_type(n).faction == "allies"} - pool
        self.assertEqual(miss, set(), f"口径漏掉了：{sorted(miss)}")

    def test_pool_is_cached(self):
        a = self.cat.campaign_specialist_pool("west")
        b = self.cat.campaign_specialist_pool("west")
        self.assertIs(a, b, "同一战役应返回同一个缓存对象")

    def test_unknown_campaign(self):
        self.assertEqual(self.cat.campaign_specialist_pool("没有这个战役"), set())
        self.assertEqual(self.cat.campaign_specialist_pool(None), set())


class CandidatesTest(unittest.TestCase):
    """三层兜底（U10 拍板）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cat = _catalog()

    def test_normal(self):
        """正常：战役默认池 ∩ 规则 = 9 种（base/west / us_arm_42）。"""
        cands, scope = self.cat.specialist_candidates("us_arm_42", "west")
        self.assertEqual(scope, "campaign")
        self.assertEqual(len(cands), 9)
        for n in cands:
            self.assertTrue(self.cat.spec_can_attach(n, "us_arm_42"))

    def test_no_campaign_fallback(self):
        """找不到战役包 ⇒ 放宽成「仅规则」+ 标签。"""
        cands, scope = self.cat.specialist_candidates("us_arm_42", None)
        self.assertEqual(scope, "no_campaign")
        self.assertEqual(len(cands), 23)

    def test_empty_intersection_fallback(self):
        """敌国单位 ⇒ 交集为空 ⇒ 放宽成「仅规则」+ 标签。"""
        cands, scope = self.cat.specialist_candidates("us_arm_42", "berlin")
        self.assertEqual(scope, "empty_intersection")
        self.assertEqual(len(cands), 23)

    def test_candidates_are_sorted(self):
        cands, _ = self.cat.specialist_candidates("us_arm_42", "west")
        self.assertEqual(cands, sorted(cands))


if __name__ == "__main__":
    unittest.main()
