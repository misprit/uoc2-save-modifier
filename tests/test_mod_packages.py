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
from pathlib import Path

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "src")
if REPO_SRC not in os.sys.path:
    os.sys.path.insert(0, REPO_SRC)

from save_modifier_core import paths as core_paths   # noqa: E402


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
