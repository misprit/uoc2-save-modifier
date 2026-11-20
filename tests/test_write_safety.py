# -*- coding: utf-8 -*-
"""U94：写入安全护栏 —— 全面审查（2026-11-20）把发现的问题固化成回归测试。

**审查方法**（U94 · 见开发上下文 §5.1vvv）：
① 盘点全部 28 个写入 kind（`Edit` ↔ handler ↔ 前端入口）；
② **边界矩阵**：71 个「明显非法」的输入 ⇒ 必须全部被拒；
③ **负数 / 0 专项**：对照**游戏自己的存档 schema**
   （`state/entities/data_validation/*.pyc`）逐字段核；
④ **组合提交**：改 + 删 + 加混在一起 ⇒ 都要生效、都不许错位；
⑤ **字节级完整性**：未改动的条目必须逐字节一致；撤销后必须逐字节还原。

**审出来的三个真问题**（都已修）：
1. **「改总部经验 / 经验目标」** —— 游戏每次战役推进都重算 `xp_target`
   （`campaign._set_hqs_xp_target`）⇒ 手写进去会被覆盖；改 `xp` 还会触发
   游戏自己的「可升级」连锁 ⇒ 按用户决定**整个删掉**（核心库硬拦 + 界面只读）。
2. **兵库条目的 `delay` 负数没拦** —— 游戏的 `force_pool_schema` 要求
   `delay` 是非负整数 ⇒ 写负数**游戏读不了这个存档**。
3. **单位 `uv`（地图坐标）完全没校验** —— 游戏的 `uv_schema` 要求 `[int, int]`，
   写错**存档打不开**；而且界面本来就没有改坐标的入口 ⇒ 删掉这个可写字段。
"""

import io
import os
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

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402

from ._fixtures import make_save  # noqa: E402


class AuditTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u94_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.catalog = Catalog(CorePaths.discover())
        self.save_path = self.make_save()

    def make_save(self):
        p = self.tmp / "s.usg"
        make_save(p, battle_overrides={"phase": 0})
        return p

    def plan(self, edits, catalog=True):
        with open_save(str(self.save_path)) as save:
            return save.plan_edit(edits, catalog=self.catalog if catalog else None)

    def commit(self, edits):
        with open_save(str(self.save_path)) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            return save.commit(plan)

    def entries(self):
        with zipfile.ZipFile(self.save_path) as zf:
            return {n: zf.read(n) for n in zf.namelist()}

    def hq(self, data, hid=5):
        return next(h for h in data if h.get("id") == hid)

    def unit(self, data, uid=1):
        return next(u for u in data if u.get("id") == uid)


# ======================================================================
# ① 删掉「改总部经验 / 经验目标」
# ======================================================================
class TestHqExperienceNotEditable(AuditTestBase):
    """U94：游戏每次战役推进都重算 `xp_target` ⇒ 手改没有意义（会被覆盖），
    改 `xp` 还会触发游戏自己的升级连锁 ⇒ 按用户决定**整个删掉**。"""

    def test_xp_is_blocked(self):
        plan = self.plan([Edit.hq_field(5, "xp", 42)])
        self.assertFalse(plan.ok, "改总部经验竟然通过了")
        self.assertIn("不能手改", plan.errors[0])

    def test_xp_target_is_blocked(self):
        plan = self.plan([Edit.hq_field(5, "xp_target", 100)])
        self.assertFalse(plan.ok)
        self.assertIn("不能手改", plan.errors[0])

    def test_error_explains_the_reason(self):
        """报错要说清楚**为什么**不能改 + 给出替代做法。"""
        plan = self.plan([Edit.hq_field(5, "xp", 42)])
        msg = plan.errors[0]
        self.assertIn("_set_hqs_xp_target", msg)
        self.assertIn("分支等级", msg)

    def test_other_hq_fields_still_work(self):
        """删掉经验**不能**连累别的字段。"""
        plan = self.plan([Edit.hq_field(5, "cp", 4)])
        self.assertTrue(plan.ok, plan.errors)
        res = self.commit([Edit.hq_field(5, "cp", 4)])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("hqs.yml"))
        self.assertEqual(self.hq(data)["cp"], 4)


# ======================================================================
# ② 兵库条目的 delay 必须非负
# ======================================================================
class TestForcePoolDelay(AuditTestBase):
    """U94：游戏的 `force_pool_schema` 里 `delay` 是**非负整数**
    ⇒ 写负数**游戏读不了这个存档**（玩家不易察觉 ⇒ 特别危险）。"""

    def test_negative_delay_is_blocked(self):
        plan = self.plan([Edit.hq_force_pool_add(
            5, {"quantity": 1, "equipment": "infantry", "delay": -1})])
        self.assertFalse(plan.ok, "负 delay 竟然通过了")
        self.assertIn("delay", plan.errors[0])

    def test_non_integer_delay_is_blocked(self):
        plan = self.plan([Edit.hq_force_pool_add(
            5, {"quantity": 1, "equipment": "infantry", "delay": "两"})])
        self.assertFalse(plan.ok)

    def test_zero_delay_is_allowed(self):
        """0 = 立即可用，是合法值。"""
        plan = self.plan([Edit.hq_force_pool_add(
            5, {"quantity": 1, "equipment": "infantry", "delay": 0})])
        self.assertTrue(plan.ok, plan.errors)

    def test_positive_delay_is_allowed(self):
        plan = self.plan([Edit.hq_force_pool_add(
            5, {"quantity": 1, "equipment": "infantry", "delay": 3})])
        self.assertTrue(plan.ok, plan.errors)


# ======================================================================
# ③ 单位坐标 uv 不再可改
# ======================================================================
class TestUnitUvNotEditable(AuditTestBase):
    """U94：`uv` 是单位在地图上的坐标 —— 写错**存档打不开**，
    而且界面本来就没有改坐标的入口 ⇒ 删掉这个可写字段。"""

    def test_uv_is_blocked(self):
        plan = self.plan([Edit.unit_field(1, "uv", [999, 999])])
        self.assertFalse(plan.ok, "改单位坐标竟然通过了")
        self.assertIn("uv", plan.errors[0])

    def test_uv_with_wrong_type_is_blocked(self):
        plan = self.plan([Edit.unit_field(1, "uv", "12,34")])
        self.assertFalse(plan.ok)

    def test_other_unit_fields_still_work(self):
        plan = self.plan([Edit.unit_field(1, "xp", 100)])
        self.assertTrue(plan.ok, plan.errors)


# ======================================================================
# ④ 边界矩阵（浓缩版）：明显非法的输入必须被拒
# ======================================================================
class TestObviousGarbageIsRejected(AuditTestBase):
    """把审查时的边界矩阵固化成回归测试（挑最要命的几类）。"""

    CASES = [
        ("unit_field", {"unit_id": 1, "field": "xp", "value": 9999}, "xp 越界"),
        ("unit_field", {"unit_id": 1, "field": "ap", "value": 9}, "ap 越界"),
        ("unit_field", {"unit_id": 1, "field": "entr", "value": 5}, "entr 越界"),
        ("unit_field", {"unit_id": 1, "field": "supply", "value": 9}, "supply 越界"),
        ("unit_field", {"unit_id": 9999, "field": "xp", "value": 10}, "单位不存在"),
        ("unit_field", {"unit_id": 1, "field": "不存在的字段", "value": 1}, "未知字段"),
        ("hq_field", {"hq_id": 5, "field": "cp", "value": -1}, "cp 负数"),
        ("hq_field", {"hq_id": 5, "field": "max_cp", "value": 99}, "max_cp 越界"),
        ("hq_field", {"hq_id": 5, "field": "supply", "value": 9}, "supply 越界"),
        ("hq_field", {"hq_id": 5, "field": "trucks", "value": 99}, "trucks 越界"),
        ("hq_field", {"hq_id": 9999, "field": "cp", "value": 1}, "总部不存在"),
        ("hq_trucks", {"hq_id": 5, "trucks": 99}, "trucks 越界"),
        ("hq_branch_level", {"hq_id": 5, "branch": "force_pool", "level": 9}, "等级越界"),
        ("hq_branch_level", {"hq_id": 5, "branch": "不存在", "level": 1}, "未知分支"),
        ("hq_force_pool", {"hq_id": 5, "index": 0, "quantity": -1}, "数量负数"),
        ("hq_force_pool", {"hq_id": 5, "index": 999, "quantity": 1}, "index 越界"),
        ("hq_force_pool_remove", {"hq_id": 5, "index": 999}, "index 越界"),
        ("hq_force_pool_add", {"hq_id": 5, "entry": {"quantity": 1}}, "既没 spec 也没 equipment"),
        ("card_add", {"card_type": "不存在的卡", "is_free": False}, "卡牌类型不存在"),
        ("card_add", {"card_type": "air_attack_allies", "is_free": False,
                      "position": 0}, "槽位 0（游戏要正整数）"),
        ("card_set", {"position": 99, "field": "is_free", "value": True}, "槽位越界"),
        ("card_set", {"position": 1, "field": "is_free", "value": "yes"}, "value 非布尔"),
        ("store_set", {"front": "south", "sub": "store", "index": 0, "field": "price",
                       "value": -1}, "价格负数"),
        ("store_set", {"front": "south", "sub": "store", "index": 0,
                       "field": "quantity", "value": 0}, "库存 0"),
        ("store_set", {"front": "south", "sub": "store", "index": 999,
                       "field": "price", "value": 5}, "index 越界"),
        ("level", {"value": "不存在的难度"}, "未知难度"),
        ("progress", {"field": "prestige", "value": -5}, "声望负数"),
        ("theater_asset_add", {"asset": "precision_bombing", "uses_total": 3,
                               "uses_turn": 0}, "uses_turn = 0"),
        ("theater_asset_add", {"asset": "precision_bombing", "uses_total": -1,
                               "uses_turn": 1}, "uses_total 负数"),
        ("unit_orders", {"unit_id": 1, "orders": ["不存在的标记"]}, "未知标记"),
        ("unit_spec_active", {"unit_id": 1, "spec_type": "ger_arty_40", "idx": 0,
                              "value": "yes"}, "value 非布尔"),
        ("unit_spec_active", {"unit_id": 1, "spec_type": "ger_arty_40", "idx": 99,
                              "value": False}, "idx 越界"),
    ]

    def test_all_obvious_garbage_is_rejected(self):
        for kind, params, why in self.CASES:
            with self.subTest(why=why):
                plan = self.plan([Edit(kind, params)])
                self.assertFalse(plan.ok, "%s 竟然通过了" % why)
                self.assertTrue(plan.errors, "%s 被拒绝了但没有原因" % why)


# ======================================================================
# ⑤ 组合提交：改 + 删 + 加混着来
# ======================================================================
class TestCombinedEdits(AuditTestBase):
    """删条目会让后面的下标前移 ⇒ 组合提交必须**顺序无关**。"""

    def test_change_then_delete(self):
        """改第 0 条数量 + 删第 1 条。"""
        res = self.commit([Edit.hq_force_pool(5, 0, 99),
                           Edit.hq_force_pool_remove(5, 1)])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("hqs.yml"))
        pool = self.hq(data)["force_pool"]
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["quantity"], 99)

    def test_delete_then_change(self):
        """删第 0 条 + 改第 1 条数量（另一种顺序，结果必须一样）。"""
        res = self.commit([Edit.hq_force_pool_remove(5, 0),
                           Edit.hq_force_pool(5, 1, 88)])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("hqs.yml"))
        pool = self.hq(data)["force_pool"]
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["quantity"], 88)

    def test_add_delete_and_change_together(self):
        res = self.commit([
            Edit.hq_force_pool_add(5, {"quantity": 7, "equipment": "infantry",
                                      "nationality": "german"}),
            Edit.hq_force_pool_remove(5, 0),
            Edit.hq_force_pool(5, 1, 55),
        ])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("hqs.yml"))
        self.assertEqual(len(self.hq(data)["force_pool"]), 2)

    def test_same_field_twice_keeps_the_last(self):
        res = self.commit([Edit.unit_field(1, "xp", 100),
                           Edit.unit_field(1, "xp", 200)])
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            data = yaml.safe_load(zf.read("units.yml"))
        self.assertEqual(self.unit(data)["xp"], 200)


# ======================================================================
# ⑥ 字节级完整性 + 撤销
# ======================================================================
class TestWriteIntegrity(AuditTestBase):
    """没改动的条目必须**逐字节**一致；撤销后必须**逐字节**还原。"""

    def test_untouched_entries_are_byte_identical(self):
        before = self.entries()
        res = self.commit([Edit.unit_field(1, "xp", 321)])
        after = self.entries()
        for name, raw in before.items():
            if name in res.changed:
                continue
            self.assertEqual(after.get(name), raw,
                             "没标记改动的条目 %s 内容变了" % name)

    def test_backup_is_a_byte_copy_of_the_original(self):
        before = self.entries()
        res = self.commit([Edit.unit_field(1, "xp", 321)])
        self.assertTrue(res.backup)
        bak = {}
        with zipfile.ZipFile(res.backup) as zf:
            for n in zf.namelist():
                bak[n] = zf.read(n)
        self.assertEqual(set(bak), set(before))
        for n in before:
            self.assertEqual(bak[n], before[n], "备份与原存档不一致：%s" % n)

    def test_undo_restores_every_byte(self):
        before = self.entries()
        self.commit([Edit.unit_field(1, "xp", 321)])
        with open_save(str(self.save_path)) as save:
            u = save.undo()
        self.assertTrue(getattr(u, "ok", False), getattr(u, "errors", []))
        after = self.entries()
        self.assertEqual(set(after), set(before))
        for n in before:
            self.assertEqual(after[n], before[n],
                             "撤销后 %s 没还原" % n)

    def test_save_still_opens_after_write(self):
        self.commit([Edit.unit_field(1, "xp", 321)])
        with open_save(str(self.save_path)) as save:
            v = save.view(catalog=self.catalog)
        self.assertEqual(self.unit(v.units and
                                   [u.__dict__ for u in v.units])["xp"], 321)


if __name__ == "__main__":
    unittest.main()
