# -*- coding: utf-8 -*-
"""U139：护栏 —— 「对**还没写盘的新条目**做修改」这一类问题。

**机制**（外部审阅的新 P1）：

核心库只认存档里**真实存在**的东西。前端给「待上架 / 待加卡」的行发
「改已有条目」的编辑（`store_set(index=-1)` / `card_set(position)` /
`card_store_set(position)` / `card_remove(position)` /
`card_store_remove(position)`）⇒ 核心库报错 ⇒ **整批改动都被拦下**，
玩家只看到一条含内部下标 `-1` 的错误。

⇒ 规则：**改那条「新增」待应用本身**（改它的 entry / is_free / card_type），
或**撤掉**它。

**这些测试守着**

① API 侧：负下标的 `store_set` **确实**会让整批被拒（含那条上架）；
② API 侧：把调好的价格**放进「上架」的 entry** ⇒ 一条编辑就够、写进去也对；
③ 前端侧：商店 / 货架 / 手牌这 7 条路径**都**有「先看有没有待上架」的分支。
"""

import io
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths  # noqa: E402
from save_modifier_web import server  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")

ARMOR = {"equipment": "armor", "nationality": "german", "price": 10, "quantity": 2}


class PendingNewRowApiTest(unittest.TestCase):
    """API 侧：这条路的**契约**。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u139_pending_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        # 服务端的 save_id 必须落在**游戏数据目录**之内（U126）
        self._old_app = os.environ.get("UOC2_APPDATA")
        os.environ["UOC2_APPDATA"] = str(self.tmp)
        self.addCleanup(self._restore_app)
        self._old_bak = os.environ.get("UOC2_BAK_DIR")
        os.environ["UOC2_BAK_DIR"] = str(self.tmp / "bak")
        self.addCleanup(self._restore_bak)

    def _restore_app(self):
        if self._old_app is None:
            os.environ.pop("UOC2_APPDATA", None)
        else:
            os.environ["UOC2_APPDATA"] = self._old_app

    def _restore_bak(self):
        if self._old_bak is None:
            os.environ.pop("UOC2_BAK_DIR", None)
        else:
            os.environ["UOC2_BAK_DIR"] = self._old_bak

    def _store(self):
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read("store.yml"))["south"]["store"]

    def _commit(self, edits):
        return server.api_commit({"save_id": str(self.save_path),
                                  "edits": edits})

    def test_a_negative_index_store_set_blocks_the_whole_batch(self):
        """⭐ 旧前端的写法 ⇒ **整批**（含那条上架）都写不进去。"""
        res = self._commit([
            {"kind": "store_add", "params": {"front": "south", "sub": "store",
                                             "entry": dict(ARMOR)}},
            {"kind": "store_set", "params": {"front": "south", "sub": "store",
                                             "index": -1, "field": "price",
                                             "value": 20}},
        ])
        self.assertFalse(res["ok"], "负下标的 store_set 不该被接受")
        self.assertTrue(any("-1" in e for e in res["errors"]), res["errors"])
        self.assertEqual([], [e for e in self._store()
                              if e.get("equipment") == "armor"],
                         "整批被拦 ⇒ 连那条上架也没写进去")

    def test_the_add_alone_carries_the_adjusted_price(self):
        """✅ 改法：把调好的价格**放进「上架」的 entry** ⇒ 一条编辑就够。"""
        entry = dict(ARMOR)
        entry["price"] = 20
        res = self._commit([
            {"kind": "store_add", "params": {"front": "south", "sub": "store",
                                             "entry": entry}},
        ])
        self.assertTrue(res["ok"], res["errors"])
        added = [e for e in self._store() if e.get("equipment") == "armor"]
        self.assertEqual(1, len(added))
        self.assertEqual(20, added[0]["price"], "调好的价格要写进去")


class PendingNewRowUiCodeTest(unittest.TestCase):
    """前端侧：这 7 条路径**都**要先看「有没有待上架的那条」。"""

    @classmethod
    def setUpClass(cls):
        with io.open(os.path.join(WEB, "index.html"),
                     encoding="utf-8", newline="") as f:
            cls.html = f.read()

    def _fn(self, name):
        i = self.html.index("function %s(" % name)
        j = self.html.index("\n}\n", i)
        return self.html[i:j]

    def test_the_helper_exists(self):
        self.assertIn("function pendingAddOf(", self.html)

    def test_the_store_page_guards_new_rows(self):
        body = self._fn("pageStore")
        self.assertIn("index < 0", body,
                      "商店页没识别「待上架的行」（负数下标）")
        self.assertIn("setNewEntry", body)
        self.assertIn('patchPendingParams("store_add"', body)

    def test_the_card_handlers_guard_new_rows(self):
        for fn, kind in (("cardSetFree", "card_add"),
                         ("cardRemove", "card_add"),
                         ("cardStoreSetFree", "card_store_add"),
                         ("cardStoreSet", "card_store_add"),
                         ("cardStoreRemove", "card_store_add")):
            body = self._fn(fn)
            self.assertIn("pendingAddOf(", body,
                          "%s 没先看有没有待上架/待加的那条" % fn)
            self.assertIn('"%s"' % kind, body,
                          "%s 找错了待应用 kind" % fn)

    def test_the_store_row_never_sends_a_negative_index_to_the_core(self):
        """负下标的 `store_set` 只允许出现在**待上架分支之外**的说明里。"""
        body = self._fn("pageStore")
        guard = body.index("if(isNew)")
        # 真正的 queueEdit 必须在守卫之后
        self.assertGreater(body.index('queueEdit("store_set"'), guard,
                           "守卫之前就 queueEdit 了 ⇒ 负下标会被发出去")
        self.assertTrue(re.search(r"if\(isNew\)\{\s*setNewEntry\(", body),
                        "待上架行的改价必须走 setNewEntry")


if __name__ == "__main__":
    unittest.main()
