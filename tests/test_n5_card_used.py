"""N-5：手牌 `used` 只允许 persistent 卡型。"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import CorePaths, Edit, open_save

from ._fixtures import make_save


class FakeCatalog:
    def __init__(self, definitions):
        self.definitions = definitions

    def card_type(self, name):
        return self.definitions.get(name)


class TestCardUsedPersistent(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="n5_card_used_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = make_save(self.tmp / "synthetic.usg", cards_override=[
            {"card_type": "persistent_card", "is_free": True,
             "position": 1, "unit_id": None, "used": False},
            {"card_type": "ordinary_card", "is_free": True,
             "position": 2, "unit_id": None, "used": False},
            {"card_type": "missing_card", "is_free": True,
             "position": 3, "unit_id": None, "used": False},
        ])
        self.paths = CorePaths.discover()

    def plan(self, edit, catalog):
        with open_save(str(self.path), self.paths) as save:
            return save.plan_edit([edit], catalog=catalog)

    def test_persistent_card_used_can_be_changed(self):
        catalog = FakeCatalog({"persistent_card": {"persistent": True}})
        plan = self.plan(Edit.card_set(1, "used", True), catalog)
        self.assertTrue(plan.ok, plan.errors)

    def test_nonpersistent_card_used_is_rejected(self):
        catalog = FakeCatalog({"ordinary_card": {"persistent": False}})
        plan = self.plan(Edit.card_set(2, "used", True), catalog)
        self.assertFalse(plan.ok)
        self.assertIn("不是 persistent", plan.errors[0])

    def test_missing_card_definition_used_is_rejected(self):
        plan = self.plan(Edit.card_set(3, "used", True), FakeCatalog({}))
        self.assertFalse(plan.ok)
        self.assertIn("没有游戏定义", plan.errors[0])

    def test_is_free_keeps_original_behavior_without_catalog(self):
        plan = self.plan(Edit.card_set(1, "is_free", False), None)
        self.assertTrue(plan.ok, plan.errors)

    def test_used_requires_boolean(self):
        catalog = FakeCatalog({"persistent_card": {"persistent": True}})
        plan = self.plan(Edit.card_set(1, "used", 1), catalog)
        self.assertFalse(plan.ok)
        self.assertIn("True / False", plan.errors[0])

    def test_used_without_catalog_is_rejected(self):
        """没有游戏包目录 ⇒ 无从判断卡型是不是持续卡 ⇒ 必须拒绝（不能放行）。"""
        plan = self.plan(Edit.card_set(1, "used", True), None)
        self.assertFalse(plan.ok)
        self.assertIn("没有游戏包目录", plan.errors[0])

    def test_commit_writes_used_into_cards_yml(self):
        """**写盘层面**也要验：改完 `cards.yml` 里那张卡的 `used` 真的变成 True。"""
        catalog = FakeCatalog({"persistent_card": {"persistent": True}})
        with open_save(str(self.path), self.paths) as save:
            plan = save.plan_edit([Edit.card_set(1, "used", True)], catalog=catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
            self.assertTrue(res.ok, getattr(res, "errors", None))
        with zipfile.ZipFile(str(self.path)) as zf:
            cards = yaml.safe_load(zf.read("cards.yml"))
        row = next(c for c in cards if c.get("position") == 1)
        self.assertIs(True, row.get("used"))
        # 其它槽位**不受影响**
        other = next(c for c in cards if c.get("position") == 2)
        self.assertIs(False, other.get("used"))


if __name__ == "__main__":
    unittest.main()
