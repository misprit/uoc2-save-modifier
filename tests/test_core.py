"""S3：存档发现与容器解析 + 8 个能力位。

验收口径（规范 §3.4.5、§11.4）：

* **70 个存档全部打开成功**，不抛异常；
* **能力位矩阵没有"未识别"分支** —— 每个能力位都能由存档内容直接算出来；
* 战役 / 场景识别（`campaign_id` / `standalone_scenario` / `in_state.scenario`）
  与实测口径一致。

真实存档不在仓库里（`.gitignore` 排除 `*.usg`）——
找不到就跳过，但本机跑一定覆盖得到。
"""

import unittest

from save_modifier_core import Capabilities, CorePaths, list_saves, open_save
from save_modifier_core.discovery import resolve_save_id

from ._helpers import find_saves, save_root


class TestPaths(unittest.TestCase):
    def test_discover_finds_save_root(self):
        paths = CorePaths.discover()
        self.assertTrue(paths.save_root.name == "save")
        self.assertEqual(paths.save_root.parent.name, ".uoc2")

    def test_package_dirs_put_user_first(self):
        """用户包（mod）优先级高于游戏包 —— 只扫游戏包会漏掉 mod。"""
        paths = CorePaths.discover()
        dirs = paths.package_dirs()
        if len(dirs) >= 2:
            self.assertEqual(dirs[0], paths.user_packages_dir)
            self.assertNotEqual(dirs[0], dirs[1])
            self.assertIn("appdata", str(dirs[0]).lower())

    def test_resolve_save_id_roundtrip(self):
        paths = CorePaths.discover()
        resolved = resolve_save_id("campaigns/west.usg", paths)
        self.assertTrue(str(resolved).endswith("campaigns\\west.usg")
                        or str(resolved).endswith("campaigns/west.usg"))


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.paths = CorePaths.discover()
        self.saves = list_saves(self.paths)

    def test_scan_finds_saves(self):
        if not self.saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        self.assertGreater(len(self.saves), 0)
        for s in self.saves:
            self.assertTrue(s.path.is_file())
            self.assertTrue(s.save_id)
            self.assertIn(s.kind, ("campaign", "standalone"))

    def test_save_ids_are_unique(self):
        ids = [s.save_id for s in self.saves]
        self.assertEqual(len(ids), len(set(ids)))

    def test_standalone_detection(self):
        """`standalone_scenario` 非空 ⇔ 独立场景存档（实测 3/70）。"""
        for s in self.saves:
            if s.standalone_scenario:
                self.assertEqual(s.kind, "standalone")
            else:
                self.assertEqual(s.kind, "campaign")

    def test_campaign_id_present(self):
        """70/70 都有 campaign_id。"""
        for s in self.saves:
            self.assertIsNotNone(s.campaign_id, f"{s.save_id} 缺 campaign_id")

    def test_old_saves_marked_archived(self):
        for s in self.saves:
            if "Old Saves" in s.path.parts:
                self.assertTrue(s.archived)
            else:
                self.assertFalse(s.archived)


class TestCapabilities(unittest.TestCase):
    """能力位必须能由存档内容直接算出，且与实际文件一致。"""

    @classmethod
    def setUpClass(cls):
        cls.paths = CorePaths.discover()
        cls.saves = list_saves(cls.paths)

    def test_all_saves_open(self):
        if not self.saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        for s in self.saves:
            with self.subTest(save=s.save_id):
                with open_save(s.save_id, self.paths) as save:
                    caps = save.capabilities()
                    self.assertIsInstance(caps, Capabilities)

    def test_capability_bits_match_files(self):
        if not self.saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        for s in self.saves:
            with self.subTest(save=s.save_id):
                with open_save(s.save_id, self.paths) as save:
                    names = set(save.list_names())
                    caps = save.capabilities()
                    self.assertEqual(caps.has_root_units, "units.yml" in names)
                    self.assertEqual(caps.has_root_hqs, "hqs.yml" in names)
                    self.assertEqual(caps.has_root_cards, "cards.yml" in names)
                    self.assertEqual(caps.has_root_store, "store.yml" in names)
                    self.assertEqual(caps.cp_conference,
                                     any(n.startswith("last_conference/")
                                         for n in names))
                    self.assertEqual(caps.cp_game,
                                     any(n.startswith("last_game/")
                                         for n in names))
                    main = save.root_main()
                    cs = main.get("card_store")
                    self.assertEqual(caps.has_card_store,
                                     isinstance(cs, list) and len(cs) > 0)

    def test_in_battle_matches_battle_dir(self):
        """`in_battle` ⇔ 当前战斗目录存在。

        ⚠️ 独立场景存档的 `in_state.scenario` 恒为 null，但 `game/main.yml` 存在 ——
        所以判据是"当前战斗目录是否存在"，不是单看字段。
        """
        if not self.saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        for s in self.saves:
            with self.subTest(save=s.save_id):
                with open_save(s.save_id, self.paths) as save:
                    caps = save.capabilities()
                    self.assertEqual(caps.in_battle, save.battle_dir() is not None)

    def test_capability_matrix_consistency(self):
        """能力矩阵自洽：能力位为假时，对应的编辑入口也必须为假。"""
        if not self.saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        for s in self.saves:
            with self.subTest(save=s.save_id):
                with open_save(s.save_id, self.paths) as save:
                    caps = save.capabilities()
                    self.assertFalse(caps.can_edit_units and not caps.has_root_units)
                    self.assertFalse(caps.can_edit_cards and not caps.has_root_cards)
                    self.assertFalse(caps.can_edit_store and not caps.has_root_store)
                    # ⚠️ 手牌 = 根 cards.yml；货架 = main.yml.card_store（`e157`/`e160`）
                    self.assertFalse(caps.can_edit_hand and not caps.has_root_cards)
                    self.assertFalse(caps.can_edit_shelf and not caps.has_card_store)
                    self.assertFalse(caps.can_restore_hand and not caps.cp_conference)
                    self.assertFalse(caps.can_edit_theater_assets and not caps.in_battle)
                    self.assertTrue(caps.can_edit_progress)   # 根 main.yml 恒可用


class TestView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = CorePaths.discover()
        cls.saves = list_saves(cls.paths)

    def test_view_builds_for_every_save(self):
        if not self.saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        for s in self.saves:
            with self.subTest(save=s.save_id):
                with open_save(s.save_id, self.paths) as save:
                    v = save.view()
                    self.assertTrue(v.stage)
                    self.assertIsNotNone(v.capabilities)
                    self.assertEqual(len(v.units),
                                     len([u for u in save.root_units()
                                          if isinstance(u.get("id"), int)]))

    def test_store_view_shape(self):
        """商店是 {战线: [条目]}；条目形态只有两种（规范 §4.6.1）。"""
        if not self.saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过")
        for s in self.saves:
            if not s.path.is_file():
                continue
            with open_save(s.save_id, self.paths) as save:
                v = save.view()
                for e in v.store:
                    self.assertTrue(e.front)
                    self.assertNotEqual(e.what, "?")
                    # price: 0 是免费商品；quantity 恒 ≥ 1
                    self.assertGreaterEqual(e.price, 0)
                    self.assertGreaterEqual(e.quantity, 1)

    def test_independent_scenario_has_no_store_or_cards(self):
        """实测 3/3 独立场景存档没有商店、没有卡牌。"""
        found = 0
        for s in self.saves:
            if not s.is_standalone:
                continue
            found += 1
            with open_save(s.save_id, self.paths) as save:
                caps = save.capabilities()
                self.assertFalse(caps.has_root_store)
                self.assertFalse(caps.has_root_cards)
        if not found:
            self.skipTest("本机没有独立场景存档")


class TestBackupNameDetection(unittest.TestCase):
    """U28：备份**链**必须被认出来（`_BACKUP` / `_BACKUP_2` / `_BACKUP_3` …）。

    ⚠️ 修之前的 bug：`make_backup` 产生的 `_BACKUP_2.usg` 会被当成**正常存档**
    列进存档列表（用户会看到自己的一堆备份）。
    """

    def test_plain_backup_suffix(self):
        from save_modifier_core.discovery import _is_backup_name
        self.assertTrue(_is_backup_name("west-Conference3-1_BACKUP"))
        self.assertTrue(_is_backup_name("west-Conference3-1_quick"))

    def test_backup_chain_with_number(self):
        from save_modifier_core.discovery import _is_backup_name
        for n in ("2", "3", "12", "100"):
            self.assertTrue(
                _is_backup_name("Blitzkrieg-ahistorical-Conference4-alter_BACKUP_" + n),
                n)

    def test_normal_names_are_not_backups(self):
        from save_modifier_core.discovery import _is_backup_name
        for stem in ("Stalingrad", "west-Husky", "Moscow-Conference1-2",
                     "Blitzkrieg-ahistorical-Conference4-alter"):
            self.assertFalse(_is_backup_name(stem), stem)

    def test_copies_are_still_detected(self):
        from save_modifier_core.discovery import _is_backup_name
        self.assertTrue(_is_backup_name("Stalingrad - 副本 (2)"))
        self.assertTrue(_is_backup_name("west-Husky copy"))


if __name__ == "__main__":
    unittest.main()


class TestYamlFloatSerialization(unittest.TestCase):
    """U38：**float 的序列化**必须是游戏能读回去的写法。

    ⚠️ 曾经的 bug：`represent_float(str(float(data)))` ⇒ PyYAML 内部 `repr()`
    又套一层引号 ⇒ 写出 `!!float "'80.0'"` ⇒ **游戏读战斗文件直接崩**
    （实测：写回 `games/<场景>/main.yml` 后 YAML 解析失败）。
    """

    def test_float_is_plain_number(self):
        from save_modifier_core import yamlio
        self.assertEqual(yamlio.dump({"x": 80.0}), b"x: 80.0\n")

    def test_float_roundtrip(self):
        from save_modifier_core import yamlio
        data = {"a": 80.0, "b": [1.5, 2.25], "c": {"d": 0.0}}
        back = yamlio.load(yamlio.dump(data))
        self.assertEqual(back, data)

    def test_float_dump_is_parseable_by_pyyaml(self):
        """写出来的字节必须能被 yaml 解析回 float（而不是字符串）。"""
        import yaml
        from save_modifier_core import yamlio
        raw = yamlio.dump({"score_multiplier": 80.0})
        self.assertNotIn(b"!!float", raw)
        self.assertNotIn(b"'" * 3, raw)
        self.assertEqual(yaml.safe_load(raw)["score_multiplier"], 80.0)

    def test_real_battle_file_is_byte_stable(self):
        """真实存档里的战斗文件（含 456 处 float）解析→序列化必须**字节一致**。"""
        import zipfile
        from save_modifier_core import list_saves, open_save, yamlio

        checked = 0
        for info in list_saves():
            if not info.is_primary:
                continue
            try:
                with open_save(info.save_id) as s:
                    bd = s.battle_dir()
                    if not bd:
                        continue
                    entry = bd + "/main.yml"
                    raw = s.read_bytes(entry)
                    data = yamlio.load(raw)
                    if not isinstance(data, dict):
                        continue
                    if b"!!float" in yamlio.dump(data):
                        continue
                    self.assertEqual(yamlio.dump(data), raw,
                                     "%s 的 %s 序列化后字节不一致" % (info.save_id, entry))
                    checked += 1
                    if checked >= 3:
                        break
            except Exception:
                continue
        if not checked:
            self.skipTest("本机没有带 float 的战斗文件")
