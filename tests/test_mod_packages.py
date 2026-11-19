# -*- coding: utf-8 -*-
"""U70 —— 包列表与游戏对齐（顺序 + `not_moddable` 整包禁用）。

**字节码依据**（游戏自己的规矩，修改器必须照抄）：

* `paths.pyc::_build_package_list` ⇒ 包列表 = **非官方包**（用户 `_packages` 里的
  每个子目录）→ **官方包**（base / dlc1..dlc10）；容器内用 **`listdir` 原序**
  （不是 sorted！）；官方包名出现在用户目录里会被跳过；
* `paths.pyc::check_not_moddable` ⇒ 游戏根 `packages.yml` 的 `not_moddable` 规则
  一旦命中某个 **mod** 包里的文件，**整个包被禁用**（不是只跳过那个文件）。
"""

import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "src")
if REPO_SRC not in os.sys.path:
    os.sys.path.insert(0, REPO_SRC)

from save_modifier_core import paths as core_paths   # noqa: E402
from save_modifier_core.catalog import Catalog        # noqa: E402
from save_modifier_core.paths import CorePaths         # noqa: E402


SPEC_YML = """faction: axis
nationality: german
name_brief: id_ger_test_spec_brief
name_full: id_ger_test_spec_full
attack: 3
defense: 4
armor: 1
artillery: 2
att_idx: 3
dfe_idx: 2
flags: [arty]
"""


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestPackageOrder(unittest.TestCase):
    """包顺序 = 游戏的顺序。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pkgorder_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.game = self.tmp / "Game"
        self.appdata = self.tmp / "appdata"
        for pkg in ("base", "dlc1", "dlc2", "dlc10"):
            (self.game / "_packages" / pkg / "data").mkdir(parents=True)
        _write(self.game / "packages.yml", "addable: []\nnot_moddable: []\n")
        self.mod = self.appdata / "_packages" / "mymod"
        (self.mod / "data").mkdir(parents=True)

    def packages(self):
        return [p.name for p in core_paths.package_dirs(self.appdata, self.game)]

    def test_mod_package_comes_first(self):
        """非官方包（mod）在官方包**前面** —— 与游戏一致。"""
        self.assertEqual(self.packages()[0], "mymod")

    def test_dlc_packages_are_in_numeric_order(self):
        """官方包按 **数字序**（dlc2 在 dlc10 前面）—— 不是字母序。"""
        names = self.packages()
        self.assertLess(names.index("dlc2"), names.index("dlc10"))
        self.assertLess(names.index("dlc1"), names.index("dlc2"))

    def test_official_package_name_in_user_dir_is_skipped(self):
        """用户目录里叫 `base` 的目录**不算 mod**（官方包名要跳过）。"""
        fake = self.appdata / "_packages" / "base"
        (fake / "data").mkdir(parents=True)
        names = self.packages()
        self.assertEqual(names.count("base"), 1)

    def test_corepaths_packages_uses_the_same_order(self):
        from save_modifier_core.paths import CorePaths
        p = CorePaths.discover(self.appdata, self.game)
        self.assertEqual([x.name for x in p.packages()], self.packages())


class TestNotModdable(unittest.TestCase):
    """`not_moddable` ⇒ 整个 mod 包被禁用（与游戏一致）。"""

    RULES = """
addable:
- ["*", "data", "scenarios", "*"]
not_moddable:
- ["*", "data", "entity_types", "nationalities.yml"]
- ["*", "shaders", "*.yml"]
"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="notmoddable_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.game = self.tmp / "Game"
        self.appdata = self.tmp / "appdata"
        (self.game / "_packages" / "base" / "data").mkdir(parents=True)
        _write(self.game / "packages.yml", self.RULES)
        self.mod = self.appdata / "_packages" / "badmod"
        (self.mod / "data" / "entity_types").mkdir(parents=True)
        _write(self.mod / "data" / "entity_types" / "nationalities.yml", "x: 1\n")

    def packages(self):
        from save_modifier_core.paths import CorePaths
        return [p.name for p in CorePaths.discover(self.appdata, self.game).packages()]

    def test_rules_are_read_from_the_game_root(self):
        rules = core_paths.not_moddable_rules(self.game)
        self.assertEqual(len(rules), 2)
        self.assertIn(["*", "data", "entity_types", "nationalities.yml"], rules)

    def test_a_mod_with_a_not_moddable_file_is_dropped(self):
        """命中 ⇒ **整个包**不出现（游戏是整包禁用，不是只跳过那个文件）。"""
        self.assertNotIn("badmod", self.packages())

    def test_the_rule_is_reported(self):
        d = core_paths.disabled_packages(self.appdata, self.game)
        self.assertTrue(d)
        self.assertIn(str(self.mod), d)

    def test_official_packages_are_never_disabled(self):
        """官方包自己就带着那些文件 ⇒ **永远不禁用**（游戏只查 mod 目录）。"""
        (self.game / "_packages" / "base" / "data" / "entity_types").mkdir(parents=True)
        _write(self.game / "_packages" / "base" / "data" / "entity_types"
               / "nationalities.yml", "x: 1\n")
        self.assertIn("base", self.packages())
        disabled = core_paths.disabled_packages(self.appdata, self.game)
        self.assertNotIn(str(self.game / "_packages" / "base"), disabled)

    def test_a_clean_mod_is_kept(self):
        good = self.appdata / "_packages" / "goodmod"
        (good / "data").mkdir(parents=True)
        self.assertIn("goodmod", self.packages())

    def test_wildcard_rule_matches(self):
        """`["*", "shaders", "*.yml"]` 这种通配也要认。"""
        (self.mod / "shaders").mkdir(parents=True)
        _write(self.mod / "shaders" / "my_shader.yml", "a: 1\n")
        self.assertNotIn("badmod", self.packages())


if __name__ == "__main__":
    unittest.main()


# =====================================================================
# U71：Steam 标准创意工坊目录里的 mod 静态数据
# =====================================================================


class TestWorkshopMods(unittest.TestCase):
    """U71 —— 创意工坊里的 mod（**还没解压进游戏目录**）也要能读。

    用户要求：「把这个 Steam 标准的 Mod 文件夹下，玩家装的 Mod 里面的
    类似特种兵这种静态的，我们修改器要用到的信息，你得纳入进来。
    不然你声称你能够兼容其他 Mod 的数据，就是一个伪的宣称。」
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wshop_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.lib = self.tmp / "SteamLibrary"
        self.item = (self.lib / "steamapps" / "workshop" / "content" / "809230"
                     / "12345")
        self.item.mkdir(parents=True)
        self.game = self.tmp / "Game"
        (self.game / "_packages" / "base" / "data").mkdir(parents=True)
        _write(self.game / "packages.yml", "addable: []\nnot_moddable: []\n")
        self.appdata = self.tmp / "appdata"
        (self.appdata / "_packages").mkdir(parents=True)

    def _make_zip_mod(self, spec_name="ger_test_spec", body=None):
        z = self.item / "my_mod-1.0.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(
                "_packages/mymod/data/entity_types/specialists/%s.yml" % spec_name,
                body if body is not None else SPEC_YML)
            zf.writestr("_packages/mymod/data/entity_types/nationalities.yml",
                        "ger_test:\n  faction: axis\n  short: german\n")
        return z

    def _catalog(self):
        return Catalog(CorePaths.discover(self.appdata, self.game))

    def test_workshop_zip_package_is_found(self):
        """创意工坊里还没解压的 zip ⇒ 也要被认成一个包。"""
        self._make_zip_mod()
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            srcs = core_paths.workshop_package_sources()
            names = [(x["kind"], x["pkg"]) for x in srcs]
            self.assertIn(("zip", "mymod"), names)

    def test_specialist_from_workshop_zip_is_readable(self):
        """mod 里的**特种兵**（静态信息）能被读到 —— 这是修改器要用的东西。"""
        self._make_zip_mod()
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            cat = self._catalog()
            spec = cat.spec_type("ger_test_spec")
            self.assertIsNotNone(spec, "创意工坊 mod 里的特种兵没读到")
            self.assertEqual(spec.attack, 3)
            self.assertEqual(spec.defense, 4)

    def test_nationality_from_workshop_zip_is_readable(self):
        self._make_zip_mod()
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            cat = self._catalog()
            nat = cat.nationality("ger_test")
            self.assertIsNotNone(nat, "创意工坊 mod 里的国籍没读到")
            self.assertEqual(nat.faction, "axis")
            self.assertEqual(nat.short, "german")

    def test_extracted_workshop_folder_is_read(self):
        """已解压的创意工坊 mod（`_packages/<包>/…` 目录）⇒ 直接当包用。"""
        d = (self.item / "_packages" / "mymod" / "data" / "entity_types"
             / "specialists")
        _write(d / "ger_test_spec.yml", SPEC_YML)
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            srcs = core_paths.workshop_package_sources()
            self.assertIn(("dir", "mymod"), [(x["kind"], x["pkg"]) for x in srcs])

    def test_disk_packages_win_over_workshop_zip(self):
        """⚠️ **磁盘包优先** —— 游戏真正在用的数据不能被「没安装的 mod」盖掉。"""
        self._make_zip_mod(spec_name="ger_shared",
                           body=SPEC_YML.replace("attack: 3", "attack: 9"))
        _write(self.appdata / "_packages" / "mymod" / "data" / "entity_types"
               / "specialists" / "ger_shared.yml",
               SPEC_YML.replace("attack: 3", "attack: 1"))
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            cat = self._catalog()
            spec = cat.spec_type("ger_shared")
            self.assertIsNotNone(spec)
            self.assertEqual(spec.attack, 1, "磁盘包应当赢过创意工坊里没安装的 zip")


# =====================================================================
# U73：创意工坊里的「裸文件包」（普通 mod 的实际形态）
# =====================================================================


class TestWorkshopBarePackage(unittest.TestCase):
    """U73 —— 普通 mod 是**裸文件**（不需要解压）。

    用户补充：「大部分 mod 里面都是裸的文件，比如说一个裸的特种兵信息是不需要解压的。
    由于官方文件不允许正常的 mod 修改游戏引擎，所以我的这个特殊 mod 需要用手动替代的
    方式来生效，但一般的 mod 是可以直接生效的。」

    ⇒ 机制坐实：Steam 创意工坊只是**分发渠道**（场景编辑器把「包」上传上去，
    `edit_ctrl.pyc::_update_workshop_item` ⇒ `set_item_content_dir(self._package_path)`）
    ⇒ 下载到 `workshop/content/809230/<itemid>/` 的就是**包的裸文件**；
    而普通 mod 生效靠的是游戏的**用户包机制**
    （`%LOCALAPPDATA%\.uoc2\_packages\<名字>\` 的裸文件，游戏当包加载）。

    ⇒ 修改器要认三种形态：**裸文件** / `_packages/<包名>/` / **压缩包**。
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wsbare_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.lib = self.tmp / "SteamLibrary"
        self.item = (self.lib / "steamapps" / "workshop" / "content" / "809230"
                     / "777")
        self.item.mkdir(parents=True)
        self.game = self.tmp / "Game"
        (self.game / "_packages" / "base" / "data").mkdir(parents=True)
        _write(self.game / "packages.yml", "addable: []\nnot_moddable: []\n")
        self.appdata = self.tmp / "appdata"
        (self.appdata / "_packages").mkdir(parents=True)

    def _catalog(self):
        return Catalog(CorePaths.discover(self.appdata, self.game))

    def test_bare_package_in_item_dir_is_read(self):
        """**裸文件**：项目目录本身就是包 ⇒ 特种兵能被读到。"""
        _write(self.item / "data" / "entity_types" / "specialists"
               / "ger_bare_spec.yml", SPEC_YML)
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            cat = self._catalog()
            spec = cat.spec_type("ger_bare_spec")
            self.assertIsNotNone(spec, "裸文件包里的特种兵没读到")
            self.assertEqual(spec.attack, 3)

    def test_bare_package_needs_a_package_marker(self):
        """不是包的东西（没有 main.yml / data / scenarios…）⇒ 不当包。"""
        _write(self.item / "readme.txt", "hello")
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            srcs = core_paths.workshop_package_sources()
            self.assertEqual([s for s in srcs if s["kind"] == "dir"], [])

    def test_package_in_subdir_is_read(self):
        """`_packages/<包名>/…` 形态 ⇒ 也能读到。"""
        _write(self.item / "_packages" / "mymod" / "data" / "entity_types"
               / "specialists" / "ger_sub_spec.yml", SPEC_YML)
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            cat = self._catalog()
            spec = cat.spec_type("ger_sub_spec")
            self.assertIsNotNone(spec, "子目录包里的特种兵没读到")
            self.assertEqual(spec.defense, 4)

    def test_zip_with_package_at_root_is_read(self):
        """压缩包**根本身**是包 ⇒ 也能读到。"""
        import zipfile
        z = self.item / "my_mod.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("data/entity_types/specialists/ger_zip_spec.yml", SPEC_YML)
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            cat = self._catalog()
            spec = cat.spec_type("ger_zip_spec")
            self.assertIsNotNone(spec, "压缩包（根是包）里的特种兵没读到")
            self.assertEqual(spec.attack, 3)

    def test_disk_packages_still_win(self):
        """⚠️ 磁盘包优先（创意工坊里没安装的只是参考数据）。"""
        _write(self.item / "data" / "entity_types" / "specialists"
               / "ger_shared.yml", SPEC_YML.replace("attack: 3", "attack: 9"))
        _write(self.appdata / "_packages" / "mymod" / "data" / "entity_types"
               / "specialists" / "ger_shared.yml",
               SPEC_YML.replace("attack: 3", "attack: 1"))
        from unittest import mock
        with mock.patch.object(core_paths, "steam_libraries", return_value=[self.lib]):
            spec = self._catalog().spec_type("ger_shared")
            self.assertIsNotNone(spec)
            self.assertEqual(spec.attack, 1, "磁盘包应当赢过没安装的创意工坊 mod")


