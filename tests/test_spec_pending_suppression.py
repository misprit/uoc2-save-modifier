# -*- coding: utf-8 -*-
"""U105：**新增的**特种兵也要能调「压制 / 恢复」——
存档里原有的特种兵和我们新增的用**同一套逻辑**、**同一个 UI 卡片**。

用户原话（2026-11-21）：
> 单位详情我们添加的新特种兵没有压制调节功能，还是旧版的，
> 应该读取到的存档里原有的特种兵和我们新增的用一套逻辑修改，用同样的 ui 卡片。

**为什么这么实现**：
游戏里特种兵条目只有 4 个字段 `type / active / captured / idx`，
**没有独立的 suppressed 字段** —— 「被压制」就是 `active=False`（U84 字节码实证）。
所以「新增时就压着」与「先挂再压着」写出来的存档**完全一样**：

* 核心库：`Edit.unit_spec_add(..., active=False)` ⇒ 写盘时直接落 `active: false`；
* 界面：新增件（还没写盘）的压制状态挂在**那条「加特种」的待应用**上，
  写盘时一起生效 ⇒ 与存档里原有的走**同一套逻辑**、**同一张卡片**。

**这些测试守着**：
① 核心库：新挂的可以一上来就是被压制的（且**字段集合不变**）；
② 两条路径写出来的存档**逐字节一样**（不许出现「写法不同、结果不同」）；
③ 界面：新增件**也有**压制按钮（不再是「只有 idx≥0 的才有」）。
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

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")


class PendingSuppressionTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="spec_pending_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        if not self.catalog.has_spec_type("us_arty_42"):
            self.skipTest("本机没有游戏包")

    def open(self):
        return open_save(str(self.save_path), self.paths)

    def commit(self, edits):
        with self.open() as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            if not plan.ok:
                return plan, None
            return plan, save.commit(plan)

    def units(self):
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read("units.yml"))


class TestAddSuppressed(PendingSuppressionTestBase):
    """核心库：新挂的特种兵可以**一上来就是被压制的**。"""

    def test_add_suppressed_writes_active_false(self):
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42", active=False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        spec = self.units()[0]["specs"][1]
        self.assertFalse(spec["active"], "新挂的特种兵应该是被压制的")
        self.assertEqual(set(spec.keys()), {"active", "captured", "idx", "type"},
                         "特种兵条目必须正好是这 4 个字段")

    def test_add_default_is_active(self):
        """默认仍是**活跃** —— 别把原来的行为改坏。"""
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42")])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(self.units()[0]["specs"][1]["active"])

    def test_non_boolean_active_is_rejected(self):
        plan, _ = self.commit([Edit.unit_spec_add(1, "us_arty_42", active="no")])
        self.assertFalse(plan.ok)
        self.assertIn("布尔", plan.errors[0])

    def test_same_bytes_as_add_then_suppress(self):
        """⚠️ **两条路径必须写出同一个存档** ——
        「新增时就压着」与「先挂再压着」不能有差别。"""
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42", active=False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        direct = self.units()

        # 另一份存档：先挂（活跃），再压制
        self.save_path = make_save(self.tmp / "s2.usg")
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42")])
        self.assertTrue(plan.ok, plan.errors)
        plan, res = self.commit([Edit.unit_spec_active(1, "us_arty_42", 1, False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        two_step = self.units()

        self.assertEqual(direct, two_step,
                         "「新增即被压制」与「先挂再压制」写出来的存档必须一致")

    def test_warning_explains_recovery(self):
        """压制要提示：游戏会按恢复步数把它恢复（免得玩家以为永久）。"""
        plan, _ = self.commit([Edit.unit_spec_add(1, "us_arty_42", active=False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("恢复" in w for w in plan.warnings), plan.warnings)

    def test_summary_says_suppressed(self):
        plan, _ = self.commit([Edit.unit_spec_add(1, "us_arty_42", active=False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("新增即被压制" in s for s in plan.notes),
                        plan.notes)

    def test_other_units_untouched(self):
        before = self.units()[1]
        plan, res = self.commit([Edit.unit_spec_add(1, "us_arty_42", active=False)])
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(self.units()[1], before, "别的单位被改动了")


class TestPendingSuppressionUi(unittest.TestCase):
    """界面：新增件与存档里原有的**用同一张卡片、同一个按钮**。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    @staticmethod
    def _body(html, start, end):
        return html[html.index(start):html.index(end)]

    def test_pending_slot_also_gets_the_button(self):
        """新增件（临时负数 idx）**也要有**压制按钮 —— 不再按 idx 分支。"""
        body = self._body(self.html, "function specSlotHTML",
                          "function toggleSpecSuppressed")
        self.assertNotIn("const btn = (s.idx>=0)", body,
                         "压制按钮不能只给存档里原有的（新增件必须也有）")
        self.assertIn("toggleSpecSuppressed", body)

    def test_one_toggle_handler_for_both(self):
        """同一个入口处理两种件（新增件走「改那条加特种的待应用」）。"""
        body = self._body(self.html, "function toggleSpecSuppressed",
                          "function refreshSpecSlots")
        self.assertIn("patchPendingParams", body)
        self.assertIn("_pending", body)
        self.assertIn("unit_spec_active", body)

    def test_projected_specs_read_pending_active(self):
        """新增件的压制状态从「加特种」那条待应用的参数读。"""
        body = self._body(self.html, "function projectedSpecs",
                          "function specSupKey")
        self.assertIn("_params", body)
        self.assertIn("active", body)

    def test_slot_id_is_stable(self):
        """槽位标识：存档里已有的 s:<idx> / 新增件 p:<待应用 key>。"""
        self.assertIn("function specSlotId(", self.html)
        body = self._body(self.html, "function specSlotId(", "function bloodPipsHTML")
        self.assertIn("_pending", body)
        self.assertIn("p:", body)

    def test_pending_params_helper_exists(self):
        self.assertIn("function patchPendingParams(", self.html)

    def test_english_words_exist(self):
        ui = self.table["ui"]
        self.assertIn("（新增即被压制）", ui, "词表里缺 %r" % "（新增即被压制）")
        err = self.table["errors"]
        key = "单位 {unit_id} 加特种 {spec_type}（槽位 {free}，新增即被压制）"
        self.assertIn(key, err, "errors 词表里缺新增的摘要模板")


if __name__ == "__main__":
    unittest.main()
