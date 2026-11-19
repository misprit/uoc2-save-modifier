"""U64：难度（根 `main.yml.level`）—— 改难度 + **手牌上限冲突硬拦**。

**游戏怎么存难度**（字节码实证）
* 存档**根 `main.yml`** 的 `level` 字段（字符串）；
  `campaign_data_validation.pyc::campaign_schema`
  ⇒ `Required('level', default='normal'): In(play_levels)`；
* `state/constants.pyc`：`play_levels = ('easy','normal','classic','hard')`；
* **难度决定手牌上限**：`card_deck_limit = {easy:5, normal:5, classic:4, hard:3}`
  （货架 `card_store_limit` 四个难度恒为 5）。

⇒ 手牌张数超过新难度的上限时**必须拦住**（让玩家先删手牌）。
"""

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save


def _cards(n: int) -> list:
    """造 n 张手牌。"""
    return [{"card_type": "air_attack_allies", "is_free": True, "position": i + 1,
             "unit_id": None, "used": False} for i in range(n)]


class TestLevelEdit(unittest.TestCase):
    """U64 —— 难度的编辑与硬拦。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="level_test_"))
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

    def level_of(self, path):
        with zipfile.ZipFile(path) as zf:
            return yaml.safe_load(zf.read("main.yml")).get("level")

    # ------------------------------------------------------------------ 正常路径

    def test_level_is_written_to_root_main(self):
        """改难度 → 写根 `main.yml` 的 `level`。"""
        path = self.make(main_overrides={"level": "hard"})
        plan, res = self.commit(path, [Edit.level("easy")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.level_of(path), "easy")

    def test_all_four_levels_are_accepted(self):
        """游戏常量 `play_levels` 的四个值都要能写。"""
        for lv in ("easy", "normal", "classic", "hard"):
            path = self.make("lv_%s.usg" % lv, main_overrides={"level": "normal"})
            plan, res = self.commit(path, [Edit.level(lv)])
            self.assertTrue(plan.ok, (lv, plan.errors))
            self.assertEqual(self.level_of(path), lv)

    def test_unknown_level_is_rejected(self):
        """难度只能是那四个。"""
        path = self.make()
        plan = self.plan(path, [Edit.level("impossible")])
        self.assertFalse(plan.ok)
        self.assertIn("难度", plan.errors[0])

    # ------------------------------------------------------------------ 手牌冲突

    def test_hand_over_limit_blocks_the_change(self):
        """**手牌比新上限多 ⇒ 硬拦**，让玩家先删手牌。"""
        # 5 张手牌 → 改「困难」（上限 3）必须被拦
        path = self.make("over.usg", main_overrides={"level": "normal"},
                         cards_override=_cards(5))
        plan = self.plan(path, [Edit.level("hard")])
        self.assertFalse(plan.ok)
        self.assertIn("请先删手牌", plan.errors[0])
        # 存档没被动
        self.assertEqual(self.level_of(path), "normal")

    def test_classic_limit_is_four(self):
        """经典的手牌上限是 4 —— 4 张能改，5 张不能。"""
        ok = self.make("ok4.usg", main_overrides={"level": "normal"},
                       cards_override=_cards(4))
        plan, res = self.commit(ok, [Edit.level("classic")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(self.level_of(ok), "classic")

        bad = self.make("bad5.usg", main_overrides={"level": "normal"},
                        cards_override=_cards(5))
        plan = self.plan(bad, [Edit.level("classic")])
        self.assertFalse(plan.ok)
        self.assertIn("请先删手牌", plan.errors[0])

    def test_hand_within_limit_is_allowed(self):
        """手牌不超过新上限 ⇒ 放行。"""
        path = self.make("within.usg", main_overrides={"level": "normal"},
                         cards_override=_cards(2))
        plan, res = self.commit(path, [Edit.level("hard")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.level_of(path), "hard")

    def test_relaxing_the_level_is_always_allowed(self):
        """**放宽**难度（上限变大）永远不受手牌数量影响。"""
        path = self.make("relax.usg", main_overrides={"level": "hard"},
                         cards_override=_cards(5))
        plan, res = self.commit(path, [Edit.level("easy")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(self.level_of(path), "easy")
