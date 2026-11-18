"""本地化查询（`locale.py`）—— 规范 §5.7 / §8.1。

**这是从旧 REPL 复活的一份实现**（`src/save_modifier/translations.py`，
S11 重构 `0444628` 时当"冗余"删掉）—— `e159` 实测过机制正确。

本文件测两件事：

1. **机制**（不依赖游戏包）—— 用临时目录造几个假包，验自然序合并、
   后加载覆盖先加载、`idp_*` 模板不被丢掉、查不到返回空串；
2. **真实包**（有游戏包才跑）—— 中文名真的能查到。
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from save_modifier_core import CorePaths, TranslationStore
from save_modifier_core import locale as loc


def _write_package(root: Path, name: str, strings: dict, files=("strings.yml",)):
    d = root / name / "localization" / "chi"
    d.mkdir(parents=True, exist_ok=True)
    for fname in files:
        lines = []
        for k, v in strings.items():
            if isinstance(v, dict):
                lines.append(f"{k}:")
                for kk, vv in v.items():
                    lines.append(f"  {kk}: {vv!r}")
            else:
                lines.append(f"{k}: {v!r}")
        (d / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestTranslationStoreMechanics(unittest.TestCase):
    """机制 —— 不需要游戏包。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="locale_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_reads_strings_and_ui(self):
        root = self.tmp / "_packages"
        _write_package(root, "base", {"id_a": "甲"}, files=("strings.yml", "ui.yml"))
        _write_package(root, "base", {"id_b": "乙"}, files=("ui.yml",))
        store = TranslationStore(root)
        self.assertEqual(store.get("id_a"), "甲")
        self.assertEqual(store.get("id_b"), "乙")

    def test_missing_key_returns_empty(self):
        store = TranslationStore(None)
        self.assertEqual(store.get("whatever"), "")
        self.assertEqual(store.get("whatever", "x"), "x")

    def test_missing_packages_path_is_not_an_error(self):
        store = TranslationStore(self.tmp / "nope")
        self.assertEqual(len(store), 0)
        self.assertEqual(store.get("id_a"), "")

    def test_later_package_overrides_earlier(self):
        root = self.tmp / "_packages"
        _write_package(root, "aaa", {"id_x": "先"})
        _write_package(root, "zzz", {"id_x": "后"})
        store = TranslationStore(root)
        self.assertEqual(store.get("id_x"), "后")

    def test_natural_order_puts_dlc2_before_dlc10(self):
        """`dlc2` 必须排在 `dlc10` 之前（字典序会排反）。"""
        root = self.tmp / "_packages"
        _write_package(root, "dlc2", {"id_x": "dlc2"})
        _write_package(root, "dlc10", {"id_x": "dlc10"})
        store = TranslationStore(root)
        # 后加载的覆盖先加载的 ⇒ dlc10 的值胜出，说明 dlc10 确实排在后面
        self.assertEqual(store.get("id_x"), "dlc10")

    def test_templates_are_kept(self):
        """⚠️ 旧实现只收 `str` 值，把 22 条 `idp_*` 模板全丢了。"""
        root = self.tmp / "_packages"
        _write_package(root, "base", {
            "idp_x": {"default": "每回合{}次", "1": "每回合1次"}})
        store = TranslationStore(root)
        self.assertTrue(store.is_template("idp_x"))
        self.assertEqual(store.template("idp_x"), "每回合{}次")
        self.assertEqual(store.template("idp_x", 1), "每回合1次")
        self.assertEqual(store.template("idp_x", 99), "每回合{}次")   # 缺省取 default
        self.assertEqual(store.template("idp_x", 1, 3), "每回合1次")

    def test_contains_covers_text_and_templates(self):
        root = self.tmp / "_packages"
        _write_package(root, "base", {"id_a": "甲", "idp_x": {"default": "d"}})
        store = TranslationStore(root)
        self.assertIn("id_a", store)
        self.assertIn("idp_x", store)
        self.assertNotIn("id_zzz", store)

    def test_bad_file_does_not_break_the_rest(self):
        root = self.tmp / "_packages"
        _write_package(root, "base", {"id_a": "甲"})
        bad = root / "broken" / "localization" / "chi"
        bad.mkdir(parents=True)
        (bad / "strings.yml").write_text("a: [1,\n  b: }{", encoding="utf-8")
        store = TranslationStore(root)
        self.assertEqual(store.get("id_a"), "甲")


class TestRealGamePackage(unittest.TestCase):
    """真实游戏包 —— 没有游戏包就跳过。"""

    def setUp(self):
        self.paths = CorePaths.discover()
        if self.paths.game_dir is None:
            self.skipTest("本机没有游戏目录")
        self.store = TranslationStore(self.paths)

    def test_card_titles_resolve(self):
        self.assertEqual(self.store.get("id_card_Ju_87"), "Ju 87")
        self.assertEqual(self.store.get("id_card_THEATER_ASSET"), "战区资产")

    def test_unit_and_specialist_names_resolve(self):
        self.assertTrue(self.store.get("id_aus_inf_41_brief"))
        self.assertTrue(self.store.get("id_bel_arty_towed_40_brief"))

    def test_templates_present(self):
        """实测 22 条参数化模板。"""
        self.assertGreaterEqual(len(self.store.templates), 1)

    def test_total_entry_count(self):
        """实测 16786 键 = 16764 条普通文本 + 22 条模板（`e159`）。"""
        self.assertGreater(len(self.store), 16000)


class TestModuleLevelApi(unittest.TestCase):
    def test_text_and_template_helpers_exist(self):
        for name in ("default", "text", "template", "keys"):
            self.assertTrue(callable(getattr(loc, name)), name)

    def test_text_returns_string(self):
        self.assertIsInstance(loc.text("id_card_Ju_87"), str)


if __name__ == "__main__":
    unittest.main()
