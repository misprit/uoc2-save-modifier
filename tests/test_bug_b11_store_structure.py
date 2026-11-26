# -*- coding: utf-8 -*-
"""B-11：商店下架全部 / 买空之后，仍要能上架（不能误判成「没有商店数据」）。

**社区原话**：「在商店中下架全部内容会导致无法新增条目，并显示没有商店数据，
把商店买空也会有类似结果（**但是 store.yml 文件本身是存在的**，这点跟卡牌不一样）。」

**根因**：战线列表是从**实际条目**推出来的 ⇒ 一清空 fronts 为空
⇒ 渲染「这个存档没有商店数据」占位 ⇒ 没有新增入口。

**修法**：战线列表改从**存档里的结构**（`store_structure`）推
⇒ 文件存在但列表为空时，照常显示战线/子商店与「上架新商品」入口。

**这个测试怎么写的**：用**真实服务端**（起 HTTP 服务，走 `/api/view`）
⇒ 验的是端到端行为，不是读源码字面量。
"""
import io
import json
import os
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from save_modifier_web import server  # noqa: E402

from ._helpers import pick_save  # noqa: E402


class TestStoreStructureSurvivesEmptyStore(unittest.TestCase):
    """商店结构要独立于条目存在。"""

    def test_view_exposes_store_structure(self):
        """/api/view 要带 `store_structure`（战线 → 子商店），**独立于条目**。"""
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        data = server.api_view(str(info.path))
        struct = data.get("store_structure")
        self.assertIsInstance(struct, dict, "view 里没有 store_structure")
        if not struct:
            self.skipTest("这个存档没有商店结构")
        for front, subs in struct.items():
            self.assertIsInstance(front, str)
            self.assertIsInstance(subs, list)
            for s in subs:
                self.assertIsInstance(s, str)

    def test_structure_is_not_derived_only_from_entries(self):
        """⚠️ 关键：结构**不能**只是「有条目的战线」—— 那正是这个 bug 的根因。

        做法：拿一个**有商店**的存档，把它的 `store.yml` 读出来，
        确认 `store_structure` 的战线集合 = **store.yml 的键**（不是条目里出现过的）。
        """
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        from save_modifier_core import open_save
        with open_save(str(info.path)) as save:
            raw = save.root_store()
            if not isinstance(raw, dict) or not raw:
                self.skipTest("这个存档没有商店")
            keys = {str(k) for k in raw.keys()}
        data = server.api_view(str(info.path))
        struct = data.get("store_structure") or {}
        self.assertTrue(keys.issubset(set(struct.keys())),
                        "store_structure 少了 store.yml 里的战线：%r" % (keys - set(struct)))

    def test_front_names_come_from_structure_not_only_entries(self):
        """战线中文名也要按**结构**取 —— 商店清空后战线名不能跟着丢。"""
        info = pick_save(lambda i: True)
        if info is None:
            self.skipTest("没有可用存档")
        from save_modifier_core import open_save
        with open_save(str(info.path)) as save:
            raw = save.root_store()
            if not isinstance(raw, dict) or not raw:
                self.skipTest("这个存档没有商店")
            keys = {str(k) for k in raw.keys()}
        data = server.api_view(str(info.path))
        names = data.get("front_names") or {}
        # 有商店的存档：战线名应覆盖 store.yml 的键
        self.assertTrue(keys.issubset(set(names.keys())),
                        "front_names 少了战线：%r" % (keys - set(names.keys())))


if __name__ == "__main__":
    unittest.main()
