# -*- coding: utf-8 -*-
"""U104：单位详情的**候选池按单位类型取** —— 切单位立刻换成正确的候选。

**用户反馈**：
「单位详情中可用特种兵的刷新不及时，例如我选择一个美国单位，应该显示美国合法的
特种兵，切换到一个德国单位，可选特种兵应该跟着变。现在可选特种兵变化的刷新的
节奏似乎很奇怪，不是我切换了要编辑的单位就直接刷新成正确的候选。」

**根因（两处）**
1. `/api/pickers?unit_type=X` 的 `specialists_for_unit` 是**按单位类型**算的，
   但界面读的是**全局** `PICK`（= 最后一次拉的那份）
   ⇒ 切到别的阵营的单位时显示的是**上一个单位**的候选；
2. U82 把「选单位」改成局部刷新后，`pickUnit` **不再触发** `loadPickers(cur.type)`
   ⇒ 没人去拉新类型的池子；
   而且 `pageUnits` 里是「缓存里有就不重拉」
   ⇒ 类型已缓存时**连异步纠正都不会发生** ⇒ 候选池一直错。
   ⇒ 这就是「节奏很奇怪」：有时过一会儿自己对了，有时一直错。

**改法**
* `unitPoolFor(u)`：候选池**按 `u.type`** 从 `PICKCACHE` 取；
* `ensureUnitPool(u)`：这个类型的池没缓存就拉，到位后只重画当前详情；
* `prefetchUnitPools(types)`：进单位页时**一次**拉齐所有类型
  （服务端批量算，13 种类型 352 ms vs 逐个拉 13×370 ms）
  ⇒ 切单位是**同步即时**的。

**实测**（Edge + CDP，1600×1000 宽窗口）：
切到美国单位 ⇒ 9 个美国候选（M4谢尔曼 / 美国工兵 …）；
切到德国单位 ⇒ 9 个德国候选（三G突击炮 / 虎I …）；
切回美国（类型已缓存）⇒ 仍是美国候选；**等待 0 ms**（不 sleep）也已是正确候选。
"""

import io
import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)
WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")


def _body(text, start, end=None):
    i = text.index(start)
    if end:
        j = text.index(end, i)
    else:
        k = text.find("\nfunction ", i + len(start))
        j = k if k > 0 else len(text)
    return text[i:j]


def _code(text):
    import re
    s = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    s = re.sub(r"(?m)^\s*//.*$", "", s)
    return s


class UnitPoolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.server = io.open(os.path.join(REPO_SRC, "save_modifier_web", "server.py"),
                             encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    # ---------------------------------------------------- 候选池按类型取
    def test_unit_pool_for_reads_the_type_cache(self):
        body = _body(self.html, "function unitPoolFor(u)")
        self.assertIn("PICKCACHE[t]", body)
        self.assertIn("specialists_for_unit", body)

    def test_pool_never_comes_from_the_global_pick(self):
        """全局 `PICK` 只是「最后一次拉的那份」⇒ 不许拿它当单位候选池。"""
        body = _code(_body(self.html, "function unitDetailHTML(u)"))
        self.assertNotIn("PICK && PICK.specialists_for_unit", body)
        self.assertIn("unitPoolFor(u)", body)

    def test_full_pool_still_uses_the_type_table(self):
        """「显示所有特种兵」走 catalog（类型表）⇒ 不受候选池影响。"""
        body = _body(self.html, "function unitDetailHTML(u)")
        self.assertIn("fullPoolHTML(u, specs)", body)

    def test_missing_pool_shows_a_reading_state(self):
        """没拉到就说「正在读取」，不拿别的单位的池子糊弄。"""
        body = _code(_body(self.html, "function unitDetailHTML(u)"))
        self.assertIn("else if(!pool)", body)
        self.assertIn("正在读取这个单位类型的可用特种兵", body)

    # ---------------------------------------------------- 切单位 ⇒ 换池子
    def test_pick_unit_ensures_the_pool(self):
        body = _body(self.html, "function pickUnit(id)")
        self.assertIn("ensureUnitPool(cur)", body)

    def test_page_ensures_and_prefetches(self):
        body = _body(self.html, "function pageUnits(w)")
        self.assertIn("ensureUnitPool(cur)", body)
        self.assertIn("prefetchUnitPools(", body)

    def test_prefetch_uses_one_batch_request(self):
        body = _body(self.html, "function prefetchUnitPools(types)")
        self.assertIn("unit_types=", body)
        self.assertIn("specialists_by_unit", body)
        self.assertIn("PICKCACHE[t] = {specialists_for_unit: sp}", body)

    def test_ensure_pool_guards_the_selected_unit(self):
        body = _body(self.html, "function ensureUnitPool(u)")
        self.assertIn("SEL.units===uid", body)
        self.assertIn("refreshUnitLocal(uid)", body)

    # ---------------------------------------------------- 服务端批量
    def test_server_supports_batch_unit_types(self):
        self.assertIn("specialists_by_unit", self.server)
        self.assertIn("unit_types", self.server)
        self.assertIn('q.get("unit_types")', self.server)

    def test_batch_computes_each_type(self):
        """批量参数 ⇒ 每个类型各算一份候选池。"""
        self.assertIn("catalog.specialist_candidates(t, campaign_id=campaign_id)", self.server)

    # ---------------------------------------------------- 词表
    def test_reading_state_is_translated(self):
        key = "正在读取这个单位类型的可用特种兵…"
        self.assertIn(key, self.table["ui"])
        self.assertTrue(self.table["ui"][key])


if __name__ == "__main__":
    unittest.main()
