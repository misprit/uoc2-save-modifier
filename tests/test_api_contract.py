"""核心库对外契约（§0.2 的 8 个函数）—— **冻结测试**。

这个文件的作用是**让接口漂移立刻变成测试失败**：
GUI 那边按本文件里的签名接 core，一旦核心库改了名字、参数或返回结构，
这里第一个报错，而不是等到 GUI 里静默出错。

冻结的东西
----------

1. 8 个对外函数的**名字、参数名、顺序**；
2. 关键返回对象的**属性名**（GUI 直接读这些）；
3. `Edit` 的 11 种编辑类型（多一种少一种都会失败）；
4. 核心包 `__all__` 的**成员名单**（新增公开 API 必须先改这里）。

改了核心库的公开接口 ⇒ **先改这个文件**，再改 GUI。
"""

import inspect
import unittest

import save_modifier_core as core
from save_modifier_core import (Catalog, CommitResult, Edit, Plan, Save,
                                SaveInfo, UndoResult, ValidationResult, View,
                                list_saves, open_save, validate)

from ._fixtures import make_save

import shutil
import tempfile
from pathlib import Path


def sig(obj) -> str:
    """函数签名（参数名与顺序），去掉注解噪音。"""
    s = inspect.signature(obj)
    parts: list[str] = []
    seen_kwonly = False
    for p in s.parameters.values():
        if p.kind is inspect.Parameter.KEYWORD_ONLY and not seen_kwonly:
            parts.append("*")
            seen_kwonly = True
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            parts.append("*" + p.name)
            continue
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            parts.append("**" + p.name)
            continue
        parts.append(p.name if p.default is inspect.Parameter.empty
                     else f"{p.name}={p.default!r}")
    return "(" + ", ".join(parts) + ")"


class TestEightFunctions(unittest.TestCase):
    """§0.2 的 8 个函数。"""

    def test_1_list_saves(self):
        self.assertTrue(callable(core.list_saves))
        self.assertEqual(sig(core.list_saves),
                         "(paths=None, *, include_archived=True)")

    def test_2_open_save(self):
        self.assertTrue(callable(core.open_save))
        self.assertEqual(sig(core.open_save), "(save_id, paths=None)")

    def test_3_view(self):
        self.assertEqual(sig(Save.view), "(self, catalog=None)")

    def test_4_plan_edit(self):
        self.assertEqual(sig(Save.plan_edit), "(self, edits, catalog=None)")

    def test_5_validate(self):
        self.assertTrue(callable(core.validate))
        self.assertEqual(sig(core.validate), "(plan)")

    def test_6_commit(self):
        self.assertEqual(sig(Save.commit), "(self, plan)")

    def test_7_undo(self):
        self.assertEqual(sig(Save.undo), "(self)")

    def test_8_catalog(self):
        """§0.2 第 8 条：`catalog.units()` / `catalog.card_types()` …

        这些是**模块级**函数（`save_modifier_core.catalog`），
        背后是 `Catalog` 类的一个惰性单例 —— GUI 直接
        `from save_modifier_core import catalog` 就能用。
        """
        for name in ("units", "hq_types", "card_types", "spec_types",
                     "fronts", "store_defaults", "default"):
            self.assertTrue(callable(getattr(core.catalog, name)), name)
        self.assertEqual(sig(core.catalog.fronts), "(campaign_id)")
        self.assertEqual(sig(core.catalog.store_defaults),
                         "(campaign_id, front, conference)")
        # Catalog 实例上的候选列表方法
        cat = Catalog()
        for name in ("unit_type_names", "spec_type_names", "card_type_names",
                     "hq_type_names", "general_names", "campaign_ids"):
            self.assertTrue(callable(getattr(cat, name)), name)


class TestPackageSurface(unittest.TestCase):
    """核心包的公开名单 —— 新增公开 API 必须先改这里。"""

    EXPECTED = {
        "Capabilities", "CardView", "CardWhitelist", "Catalog", "CommitResult",
        "CorePaths", "Edit", "FileChange", "HqView", "Plan", "Save",
        "SaveInfo", "StoreEntryView", "TranslationStore", "UndoRecord",
        "UndoResult", "UnitType", "UnitView", "ValidationResult", "View",
        "catalog", "commit", "list_saves", "locale", "make_backup",
        "open_save", "plan_edit", "resolve_save_id", "stack_path_for",
        "validate",
    }

    def test_all_is_frozen(self):
        self.assertEqual(set(core.__all__), self.EXPECTED,
                         "核心包 __all__ 变了 —— 先更新本文件与 §0.2")

    def test_everything_in_all_exists(self):
        for name in core.__all__:
            self.assertTrue(hasattr(core, name), name)


class TestEditKinds(unittest.TestCase):
    """编辑类型 —— GUI 的下拉框与参数表按这个来。

    ⚠️ 2026-11-18 扩到 20 种（`e153`–`e160` 实证暴露出来的缺口）：
    总部 4 种 + 商店 1 种 + 卡牌货架 3 种 + 手牌字段 1 种。

    ⚠️ 2026-11-18 再 +1 种（U12 / `e165`）：`hq_branch_sp` —— 总部技能的专精次数。
    """

    EXPECTED = {
        "progress", "unit_field", "unit_spec_add", "unit_spec_remove",
        "hq_force_pool", "hq_field", "hq_branch_level", "hq_branch_sp",
        "hq_force_pool_add",
        "hq_force_pool_remove", "card_add", "card_remove", "card_set",
        "store_set", "store_remove", "store_add", "card_store_set",
        "card_store_remove", "card_store_add", "hand_restore", "theater_asset",
    }

    def test_kinds_are_frozen(self):
        from save_modifier_core.edits import EDIT_KINDS
        self.assertEqual(set(EDIT_KINDS), self.EXPECTED)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            Edit("no_such_kind", {})

    def test_factories_exist(self):
        for name in ("progress", "unit_field", "unit_spec_add",
                     "unit_spec_remove", "hq_force_pool", "hq_field",
                     "hq_branch_level", "hq_branch_sp", "hq_force_pool_add",
                     "hq_force_pool_remove", "card_add", "card_remove",
                     "card_set", "store_set", "store_remove", "store_add",
                     "card_store_set", "card_store_remove", "card_store_add",
                     "hand_restore", "theater_asset"):
            self.assertTrue(callable(getattr(Edit, name)), name)

    def test_store_edits_take_sub_store(self):
        """`store.yml` 是两层结构 ⇒ `store_set` / `store_remove` 必须带 `sub`。"""
        self.assertEqual(sig(Edit.store_set),
                         "(front, sub, index, field, value)")
        self.assertEqual(sig(Edit.store_remove), "(front, sub, index)")
        self.assertEqual(sig(Edit.store_add), "(front, sub, entry)")


class TestReturnShapes(unittest.TestCase):
    """返回对象上 GUI 会直接读的属性。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="api_contract_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")

    def test_view_attributes(self):
        with open_save(str(self.save_path)) as save:
            v = save.view()
        self.assertIsInstance(v, View)
        for attr in ("save", "capabilities", "stage", "prestige", "score",
                     "units", "hqs", "cards", "hand", "shelf", "store",
                     "battle_turn", "warnings"):
            self.assertTrue(hasattr(v, attr), attr)

    def test_hand_and_shelf_are_not_the_same_thing(self):
        """⚠️ 手牌 = `cards.yml`；货架 = `main.yml.card_store`（别搞反）。

        `e157`/`e160` 实证：手牌张数上限 = `card_deck_limit`，
        货架格数 = `card_store_limit` —— 实测存档手牌 4 张、货架 5 张。
        """
        with open_save(str(self.save_path)) as save:
            v = save.view()
        self.assertEqual([c.card_type for c in v.hand], ["air_attack_allies"])
        self.assertEqual(v.shelf, [])
        # `cards` 是 `hand` 的旧名
        self.assertEqual(v.cards, v.hand)

    def test_plan_attributes(self):
        with open_save(str(self.save_path)) as save:
            plan = save.plan_edit([Edit.progress("prestige", 10)])
        self.assertIsInstance(plan, Plan)
        for attr in ("save_id", "path", "changes", "notes", "errors",
                     "warnings", "ok", "changed_entries", "summary"):
            self.assertTrue(hasattr(plan, attr), attr)

    def test_validation_result_attributes(self):
        with open_save(str(self.save_path)) as save:
            plan = save.plan_edit([Edit.progress("prestige", 10)])
        res = validate(plan)
        self.assertIsInstance(res, ValidationResult)
        for attr in ("ok", "errors", "warnings", "summary"):
            self.assertTrue(hasattr(res, attr), attr)

    def test_commit_result_attributes(self):
        with open_save(str(self.save_path)) as save:
            plan = save.plan_edit([Edit.progress("prestige", 10)])
            res = save.commit(plan)
        self.assertIsInstance(res, CommitResult)
        for attr in ("ok", "nothing_to_do", "path", "backup", "changed",
                     "errors", "warnings", "report", "summary"):
            self.assertTrue(hasattr(res, attr), attr)

    def test_undo_result_attributes(self):
        with open_save(str(self.save_path)) as save:
            res = save.undo()
        self.assertIsInstance(res, UndoResult)
        for attr in ("ok", "nothing_to_do", "path", "backup", "restored",
                     "errors", "warnings", "summary"):
            self.assertTrue(hasattr(res, attr), attr)

    def test_save_info_attributes(self):
        with open_save(str(self.save_path)) as save:
            info = save.info
        self.assertIsInstance(info, SaveInfo)
        for attr in ("save_id", "path", "kind", "archived", "is_primary",
                     "campaign_id", "scenario", "standalone_scenario",
                     "mtime", "size", "name", "display_name", "is_standalone"):
            self.assertTrue(hasattr(info, attr), attr)


class TestAuxiliaryApi(unittest.TestCase):
    """8 个函数之外的**辅助**（GUI 用它们决定按钮是否可点）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="api_aux_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")

    def test_undo_available_and_peek(self):
        with open_save(str(self.save_path)) as save:
            self.assertEqual(sig(Save.undo_available), "(self)")
            self.assertEqual(sig(Save.undo_peek), "(self)")
            self.assertFalse(save.undo_available())
            self.assertIsNone(save.undo_peek())
            plan = save.plan_edit([Edit.progress("prestige", 11)])
            save.commit(plan)
            self.assertTrue(save.undo_available())
            self.assertIsNotNone(save.undo_peek())

    def test_undo_count(self):
        """GUI 的 Rail 要显示"撤销栈 N 条"。"""
        with open_save(str(self.save_path)) as save:
            self.assertEqual(sig(Save.undo_count), "(self)")
            self.assertEqual(save.undo_count(), 0)
            plan = save.plan_edit([Edit.progress("prestige", 11)])
            save.commit(plan)
            self.assertEqual(save.undo_count(), 1)

    def test_capabilities_helper_properties(self):
        """能力位矩阵 —— GUI 的启用/禁用全看它。"""
        with open_save(str(self.save_path)) as save:
            caps = save.capabilities()
        for attr in ("can_edit_progress", "can_edit_units", "can_edit_hqs",
                     "can_edit_force_pool", "can_edit_cards",
                     "can_edit_store", "can_edit_hand", "can_edit_shelf",
                     "can_restore_hand", "can_edit_theater_assets",
                     "can_undo_in_game"):
            self.assertTrue(hasattr(caps, attr), attr)
        self.assertEqual(sig(type(caps).unavailable_reason), "(self, feature)")


if __name__ == "__main__":
    unittest.main()
