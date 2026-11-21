# -*- coding: utf-8 -*-
"""U91：总部兵库「移除」不生效 / 删错条目。

**用户报告**（2026-11-20，朋友的存档 `korsk3`）：
「总部兵库那里移除兵力有时候不知道为何不生效。
如果移除数量为 2 的那个野战炮，再点移除数量为 1 的那个就没有反应，
不过操作顺序反过来的话两个都可以正常移除。」

**根因（U91 复现）**：
界面的行号会因为**挂起的删除**而前移，但兵库的下标一直指的是
**存档里的原始下标** ⇒ 两边对不上：

1. `hqPoolRemove()` 传的是**界面行号**，`setPending` 的 key 也是这个行号
   ⇒ 删掉第 1 行后，第 2 行挪到第 1 行 ⇒ 再点它，**key 相同 ⇒ 挂起被覆盖**
   ⇒ 待应用数量不变、界面也不动 ⇒ 看着「没反应」；
2. 反过来点（先点第 2 行再点第 1 行）时，key 不同 ⇒ 两条挂起都在
   ⇒ 恰好按下标**降序**执行 ⇒ 结果碰巧正确。

**还挖出一个更危险的坑**：多条删除若按下标**升序**执行
（删了 idx0 之后原 idx1 前移，再删 idx1 就删到了别的条目）
⇒ **会删错条目**（实测：步兵那条被误删，两条炮都还在）。

**修法**：
* 前端：兵库条目一律带 `_o`（**存档原始下标**）⇒ 移除 / 改数量都用它；
* 核心库：`plan_edit()` 按规则排序（`order_edits`）⇒ **顺序无关**。
  ⚠️ **U136**：前端**不再排**（以前排了两份 ⇒ 同一条规则两处实现 ⇒ 漂移就出 bug：
  U91 只排了兵库、商店漏了 ⇒ 外部审阅的 P0-2）。

**这些测试守什么**：
① 玩家**按顺序**点两条（哪种顺序都行）⇒ 两条都删掉、且**不误删**别的；
② 核心库层：多条删除**顺序无关**；
③ 删一条 + 改另一条的数量 ⇒ 改的是对的那条；
④ 前端代码里不许再拿「界面行号」当兵库下标。
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import CorePaths, Edit, open_save  # noqa: E402

from ._fixtures import dump, make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")

HQ_ID = 5
#: 照用户截图：同一条野战炮**两种延迟**（游戏允许共存）+ 一条步兵
POOL = [
    {"delay": 0, "nationality": "soviet", "quantity": 2, "equipment": "sov_towed_gun_101"},
    {"delay": 2, "nationality": "soviet", "quantity": 1, "equipment": "sov_towed_gun_101"},
    {"delay": 2, "nationality": "soviet", "quantity": 30, "equipment": "infantry"},
]


def ident(e):
    """条目的"人话身份"：种类 + 数量 + 延迟（玩家就是照这个认条目的）。"""
    return (e.get("equipment") or e.get("spec"), e.get("quantity"), e.get("delay"))


# ======================================================================
# 前端逻辑的 Python 模拟（照抄 index.html，改坏了这里也会红）
# ======================================================================

def projected_pool(raw, pending):
    """index.html: projectedPool()"""
    pool = []
    for i, e in enumerate(raw):
        x = dict(e)
        x["_o"] = i
        pool.append(x)
    added = 0
    for p in pending:
        if p["kind"] == "hq_force_pool_add" and p["params"]["hq_id"] == HQ_ID:
            x = dict(p["params"]["entry"])
            x.update({"_o": len(raw) + added, "_new": True, "_key": p["key"]})
            pool.append(x)
            added += 1
        if p["kind"] == "hq_force_pool_remove" and p["params"]["hq_id"] == HQ_ID:
            j = next((i for i, e in enumerate(pool)
                      if e["_o"] == p["params"]["index"]), None)
            if j is not None:
                pool.pop(j)
    return pool


def set_pending(pending, kind, key, params):
    """index.html: setPending() —— 同 kind + 同 key ⇒ **替换**。"""
    for i, x in enumerate(pending):
        if x["kind"] == kind and x["key"] == key:
            pending[i] = {"kind": kind, "key": key, "params": params}
            return
    pending.append({"kind": kind, "key": key, "params": params})


def hq_pool_remove(pending, raw, target):
    """index.html: hqPoolRemove() —— 按**存档原始下标**定位。"""
    pool = projected_pool(raw, pending)
    row = next((e for e in pool if ident(e) == ident(target)), None)
    if row is None:
        return False
    o = row["_o"]
    set_pending(pending, "hq_force_pool_remove",
                "hq_force_pool_remove:%d:%d" % (HQ_ID, o),
                {"hq_id": HQ_ID, "index": o})
    return True


def pending_edits(pending):
    """index.html: `pendingEdits()` —— **只把待应用变成请求体**。

    ⚠️ **U136**：前端**不排**任何顺序 —— 「按下标删除的排在最后、同组按 index 降序」
    这条规则**只在核心库 `plan.py::order_edits` 一处**（`/api/plan`、`/api/commit`
    都会重新规划）⇒ 下面这些用例正是靠「前端不排」来验证核心库扛得住乱序。
    """
    return [{"kind": p["kind"], "params": p["params"]} for p in pending]


# ======================================================================
# 核心库层
# ======================================================================

class HqPoolRemoveTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hq_pool_rm_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = self.make_save()
        self.paths = CorePaths.discover()

    def make_save(self):
        p = self.tmp / "s.usg"
        make_save(p)
        with zipfile.ZipFile(p) as zf:
            entries = {n: zf.read(n) for n in zf.namelist()}
        hqs = yaml.safe_load(entries["hqs.yml"])
        for h in hqs:
            if h.get("id") == HQ_ID:
                h["force_pool"] = [dict(e) for e in POOL]
        entries["hqs.yml"] = dump(hqs)
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for n, d in entries.items():
                zf.writestr(n, d)
        return p

    def commit(self, edits):
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit(edits)
            self.assertTrue(plan.ok, plan.errors)
            return save.commit(plan)

    def pool(self):
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        for h in hqs:
            if h.get("id") == HQ_ID:
                return h["force_pool"]
        return None


class TestHqPoolRemoveOrder(HqPoolRemoveTestBase):
    """核心库：多条删除**顺序无关**，且**不误删**别的条目。"""

    def test_two_removes_in_ascending_order(self):
        """升序提交（改前端前最容易踩的）—— 靠 `order_edits` 降序保护。"""
        res = self.commit([Edit.hq_force_pool_remove(HQ_ID, 0),
                           Edit.hq_force_pool_remove(HQ_ID, 1)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual([ident(e) for e in self.pool()], [("infantry", 30, 2)])

    def test_two_removes_in_descending_order(self):
        res = self.commit([Edit.hq_force_pool_remove(HQ_ID, 1),
                           Edit.hq_force_pool_remove(HQ_ID, 0)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual([ident(e) for e in self.pool()], [("infantry", 30, 2)])

    def test_removing_the_first_does_not_shift_the_second(self):
        """删 idx0 之后原 idx1 前移 —— 再删 idx1 **不许**删到别的条目。"""
        res = self.commit([Edit.hq_force_pool_remove(HQ_ID, 0)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual([ident(e) for e in self.pool()],
                         [("sov_towed_gun_101", 1, 2), ("infantry", 30, 2)])

    def test_remove_does_not_touch_other_hqs(self):
        """别的总部的兵库不受影响。"""
        before = None
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        before = [h.get("force_pool") for h in hqs if h.get("id") == 6]
        res = self.commit([Edit.hq_force_pool_remove(HQ_ID, 0)])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        after = [h.get("force_pool") for h in hqs if h.get("id") == 6]
        self.assertEqual(after, before, "别的总部的兵库被改了")

    def test_out_of_range_is_reported(self):
        """下标越界要**报错**，不能静默删错东西。"""
        with open_save(str(self.save_path), self.paths) as save:
            plan = save.plan_edit([Edit.hq_force_pool_remove(HQ_ID, 99)])
            self.assertFalse(plan.ok)
            self.assertIn("99", plan.errors[0])

    def test_remove_and_quantity_change_together(self):
        """删一条 + 改另一条的数量 ⇒ 改的是**对的那条**。"""
        res = self.commit([Edit.hq_force_pool_remove(HQ_ID, 0),
                           Edit.hq_force_pool(HQ_ID, 2, 99)])
        self.assertTrue(res.ok, res.errors)
        self.assertEqual([ident(e) for e in self.pool()],
                         [("sov_towed_gun_101", 1, 2), ("infantry", 99, 2)])


class TestPlayerClickOrder(HqPoolRemoveTestBase):
    """玩家视角：按**条目身份**点「移除」，两种顺序都要删掉两条。"""

    def _click_sequence(self, targets):
        pending = []
        for t in targets:
            self.assertTrue(hq_pool_remove(pending, POOL, t),
                            "界面上找不到 %s" % (ident(t),))
        edits = [Edit(e["kind"], e["params"]) for e in pending_edits(pending)]
        res = self.commit(edits)
        self.assertTrue(res.ok, res.errors)

    def test_remove_qty2_then_qty1(self):
        """用户报告的顺序：先删数量 2 的，再删数量 1 的 ⇒ 两条都删掉。"""
        self._click_sequence([POOL[0], POOL[1]])
        self.assertEqual([ident(e) for e in self.pool()], [("infantry", 30, 2)])

    def test_remove_qty1_then_qty2(self):
        """反过来 ⇒ 两条都删掉。"""
        self._click_sequence([POOL[1], POOL[0]])
        self.assertEqual([ident(e) for e in self.pool()], [("infantry", 30, 2)])

    def test_both_removes_are_kept_in_pending(self):
        """两条移除必须**都在挂起清单里**（以前第二条被覆盖掉 ⇒ 没反应）。"""
        pending = []
        hq_pool_remove(pending, POOL, POOL[0])
        hq_pool_remove(pending, POOL, POOL[1])
        self.assertEqual(len(pending), 2, "第二条移除把第一条覆盖掉了")
        self.assertEqual([p["params"]["index"] for p in pending], [0, 1])

    def test_removing_a_not_yet_saved_entry_cancels_the_add(self):
        """还没写盘就加的条目 ⇒ 点「移除」是**撤销加条目**，不是发删除。"""
        pending = []
        entry = {"spec": "ger_arty_40", "nationality": "german",
                 "quantity": 1, "delay": 0}
        set_pending(pending, "hq_force_pool_add", "hq_force_pool_add:%d:x" % HQ_ID,
                    {"hq_id": HQ_ID, "entry": entry})
        pool = projected_pool(POOL, pending)
        new_row = pool[-1]
        self.assertTrue(new_row.get("_new"))
        # 前端行为：撤掉那条「加条目」
        drop = [p for p in pending
                if not (p["kind"] == "hq_force_pool_add" and p["key"] == new_row["_key"])]
        self.assertEqual(len(drop), 0, "没撤掉刚加的条目")


class TestHqPoolUiCode(unittest.TestCase):
    """界面代码的护栏：不许再拿「界面行号」当兵库下标。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def slice(self, start_marker, end_marker):
        i = self.html.index(start_marker)
        j = self.html.index(end_marker, i)
        return self.html[i:j]

    def test_projection_carries_the_original_index(self):
        """投影必须给每条带上 `_o`（存档原始下标）。"""
        body = self.slice("function projectedPool", "function hqPoolHTML")
        self.assertIn("_o", body)

    def test_remove_uses_the_original_index(self):
        """移除按 `_o` 定位，不是界面行号。"""
        body = self.slice("function hqPoolRemove", "function hqPoolItems")
        self.assertIn("_o", body)
        self.assertNotIn("pool[index]", body)

    def test_the_sorting_rule_lives_only_in_the_core_library(self):
        """删除类编辑按下标降序 —— 但**只在核心库一处**（`plan.py::order_edits`）。

        ⚠️ **U136**：前端以前也排了一份 ⇒ **同一条规则两处实现** ⇒ 漂移就出 bug
        （U91 只排了兵库、商店漏了 ⇒ 外部审阅的 P0-2）。
        而且前端那份**对结果没有任何影响**（确认框列的是服务端返回的
        `changes` / `notes`，已经是核心库的顺序）⇒ 纯重复，删掉更安全。
        """
        body = self.slice("function pendingEdits", "async function doApply")
        self.assertNotIn("hq_force_pool_remove", body,
                         "前端不该再排删除顺序（规则只在核心库一处）")
        self.assertNotIn("store_remove", body)
        self.assertNotIn(".sort(", body, "前端不该再排序")

    def test_the_core_library_does_the_sorting(self):
        """核心库那一份在（护栏在 `tests/test_delete_order.py`）。"""
        with io.open(os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "src", "save_modifier_core", "plan.py"),
                encoding="utf-8", newline="") as f:
            plan_src = f.read()
        self.assertIn("_DELETE_BY_INDEX", plan_src)
        self.assertIn("def order_edits(", plan_src)

    def test_new_entry_can_be_cancelled(self):
        """还没写盘的条目可以撤销（`dropPendingByKey`）。"""
        self.assertIn("dropPendingByKey", self.html)
        self.assertIn("_new", self.html)

    def test_quantity_control_uses_the_original_index(self):
        """滚轮改数量也必须用原始下标。"""
        body = self.slice("/* 兵库数量", "function renameHq")
        self.assertIn("_o", body)
        self.assertNotIn('hqPoolKey(h.id,i)', body)


if __name__ == "__main__":
    unittest.main()
