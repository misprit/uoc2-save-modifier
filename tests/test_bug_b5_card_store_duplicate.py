# -*- coding: utf-8 -*-
"""B-5：卡牌商店货架**不许出现两张同类型的卡**。

**社区原话**
> 「卡牌商店相关修改的完成度很高，但是能够重复添加同一个伞兵卡这点需要避免。
> （在实际使用中确实可以连续投放两次，会使该单位位移且重置状态和兵力。
> 在游戏中地图上面会显示两个相同兵模，但先前那个不能点选。）」

**根因**
* `_card_store_add` 原来只校验「槽位被占」与「白名单」，**没有同类型判重**
  ⇒ 直接 `append`；
* 白名单也**不看货架**（`catalog.card_whitelist` 只看手牌 / 已召唤过 / 阵营）；
* 前端卡牌选择器的 `dup` 恒为 `""`（货架商品那个是真算的）。

⇒ 同一个 `unit_id` 被写进货架两次 ⇒ 游戏用同一个单位召唤两次
⇒ 地图上两个同款兵模、先那个不能点选。

**这些测试守着**

① 货架上已有某类型卡时，再上架同类型 ⇒ **被拦下**（计划不通过 + 有说明）；
② 召唤卡重复上架 ⇒ 写出去的存档里**不会**出现两条同 `unit_id` 的召唤卡；
③ **不误伤**：不同类型照常能上架；
④ 换牌（`card_store_set`）成货架上已有的类型 ⇒ 同样被拦；
⑤ 「先上一张同类型、再把原来那张下架」= **替换** ⇒ 允许（同 `store_add` 的口径）；
⑥ 前端卡牌选择器的「已有 N」角标**接上真实判定**（不再是恒空的 `""`）。
"""

import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "src" / "save_modifier_web" / "web"

#: 会召唤单位的卡（游戏自己的 `has_unit` 标志）—— 社区报的就是这类
SUMMON_CARD = "tactical_para_german"
#: 夹具 `document/main.yml` 给它登记的可召唤单位 id
SUMMON_UNIT_ID = 718

#: 一个「会议阶段」的货架：槽位 1 放着一张伞兵卡
SHELF = [
    {"card_type": SUMMON_CARD, "is_free": False, "position": 1,
     "unit_id": SUMMON_UNIT_ID, "used": False},
]


class ShelfDuplicateBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b5_shelf_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        if not self.catalog.has_card_type(SUMMON_CARD):
            self.skipTest("本机没有游戏包（缺 %s）" % SUMMON_CARD)
        self.save_path = make_save(self.tmp / "s.usg",
                                   main_overrides={"card_store": list(SHELF)})

    def plan(self, edits, path=None):
        with open_save(str(path or self.save_path), self.paths) as save:
            return save.plan_edit(edits, catalog=self.catalog)

    def read(self, entry, path=None):
        with zipfile.ZipFile(path or self.save_path) as zf:
            return yaml.safe_load(zf.read(entry))

    def whitelist(self):
        with open_save(str(self.save_path), self.paths) as save:
            return self.catalog.card_whitelist(save)


class TestDuplicateCardIsRejected(ShelfDuplicateBase):
    """① 货架上已有同类型 ⇒ 再加被拦下。"""

    def test_adding_the_same_card_type_again_is_rejected(self):
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)])
        self.assertFalse(p.ok, "同一张卡上了两次货架，计划居然通过了")
        self.assertTrue(any("已经有同类型" in e for e in p.errors), p.errors)

    def test_the_rejection_explains_itself(self):
        """错误文案要说清「已经有同类型」和「不能重复上架」。"""
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)])
        self.assertTrue(any("重复上架" in e for e in p.errors), p.errors)

    def test_nothing_is_written_to_the_save(self):
        """被拦下 ⇒ 存档里**不会**多出第二条同 unit_id 的召唤卡。"""
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)])
        self.assertFalse(p.ok)
        shelf = self.read("main.yml")["card_store"]
        same = [c for c in shelf if c.get("card_type") == SUMMON_CARD]
        self.assertEqual(1, len(same), "存档里不该出现两张同类型的召唤卡")
        self.assertEqual(1, len({c.get("unit_id") for c in same}))

    def test_a_rejected_add_leaves_the_save_untouched(self):
        """整个批次不写盘（`plan.ok` 为假 ⇒ 没有可提交的改动）。"""
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)])
        self.assertFalse(p.ok)
        self.assertEqual([], p.changed_entries)


class TestOtherCardsStillWork(ShelfDuplicateBase):
    """③ 不误伤：不同类型照常能上架。"""

    def test_a_different_card_type_can_still_be_listed(self):
        wl = self.whitelist()
        allowed = [n for n in wl.allowed if n != SUMMON_CARD]
        if not allowed:
            self.skipTest("本机没有别的可上架卡")
        p = self.plan([Edit.card_store_add(2, allowed[0])])
        self.assertTrue(p.ok, p.errors)

    def test_the_same_card_can_be_listed_in_another_save(self):
        """判重只看**本存档的货架** —— 另一份存档的货架上没有同款就能上架。"""
        other = make_save(self.tmp / "other.usg", main_overrides={"card_store": [
            {"card_type": "air_attack_allies", "is_free": False, "position": 1,
             "unit_id": None, "used": False}]})
        p = self.plan([Edit.card_store_add(2, SUMMON_CARD)], path=other)
        self.assertTrue(p.ok, p.errors)


class TestReplaceIsNotADuplicate(ShelfDuplicateBase):
    """⑤ 「上一张同类型 + 把原来那张下架」= 替换 ⇒ 允许。"""

    def test_add_then_remove_the_old_one_is_allowed(self):
        edits = [Edit.card_store_add(2, SUMMON_CARD),
                 Edit.card_store_remove(1)]
        p = self.plan(edits)
        self.assertTrue(p.ok, p.errors)

    def test_remove_then_add_the_same_one_is_allowed(self):
        edits = [Edit.card_store_remove(1),
                 Edit.card_store_add(2, SUMMON_CARD)]
        p = self.plan(edits)
        self.assertTrue(p.ok, p.errors)


class TestReplaceCardCannotDuplicate(ShelfDuplicateBase):
    """④ 换牌成货架上已有的类型 ⇒ 同样被拦。"""

    def test_replacing_with_a_type_already_on_the_shelf_is_rejected(self):
        wl = self.whitelist()
        allowed = [n for n in wl.allowed if n != SUMMON_CARD]
        if not allowed:
            self.skipTest("本机没有别的可上架卡")
        # 先把槽位 2 填上一张别的卡，再试着把它换成货架上已有的伞兵卡
        p = self.plan([Edit.card_store_add(2, allowed[0]),
                       Edit.card_store_set(2, card_type=SUMMON_CARD)])
        self.assertFalse(p.ok, "换牌换成了货架上已有的类型，计划居然通过了")
        self.assertTrue(any("已经有同类型" in e for e in p.errors), p.errors)

    def test_replacing_a_card_with_its_own_type_is_allowed(self):
        """换牌成**它自己**的类型 = 什么都没改 ⇒ 允许。"""
        p = self.plan([Edit.card_store_set(1, card_type=SUMMON_CARD)])
        self.assertTrue(p.ok, p.errors)


class TestFrontendShowsTheDuplicate(unittest.TestCase):
    """⑥ 前端：卡牌选择器的「已有 N」角标接上真实判定。"""

    @classmethod
    def setUpClass(cls):
        with io.open(WEB / "index.html", encoding="utf-8") as f:
            cls.html = f.read()
        with io.open(WEB / "i18n.json", encoding="utf-8") as f:
            cls.table = json.load(f)

    def _body(self):
        i = self.html.index("function renderCardPickerModal(")
        return self.html[i:i + 3000]

    def test_the_picker_reads_the_real_shelf(self):
        body = self._body()
        self.assertIn('projectedCards(VIEW.shelf, "shelf")', body,
                      "卡牌选择器没有按货架的真实内容算重复数")

    def test_the_duplicate_badge_is_not_a_constant_empty_string(self):
        """`dup` 不能再恒为 `""` —— 要按货架上同类型的张数算。"""
        body = self._body()
        self.assertNotIn('dup:"", title:', body,
                         "卡牌选择器的 dup 还是恒空")
        self.assertIn("dupOf(t)", body)

    def test_the_badge_text_is_in_the_ui_table(self):
        self.assertIn("已有 ", self.table["ui"])


if __name__ == "__main__":
    unittest.main()
