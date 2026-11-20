# -*- coding: utf-8 -*-
"""U92：作战标记的**游戏硬约束** —— 「反击」只能挂**装甲机动单位**。

**用户要求**（2026-11-20）：
「在原版游戏中，反击这个技能是只能挂在装甲单位上的。我们的修改器是不是现在允许
突破这个限制？我建议是按照游戏的硬约束，让非装甲单位不能挂反击，
不然有可能出现 bug。」

**取证**（游戏字节码，U92）：

* `state/entities_view/unit.py:45`

  ```python
  armor_mobile = property(lambda self: self.armor
                                           and not self.armor_def
                                           and self.movement == 'mobile')
  ```

* `state/entities_view/unit.py:98` `can_make_elastic_defense` 的
  **第一个条件**就是 `self.armor_mobile`
  ⇒ **非装甲机动单位挂不了「反击」**；
* `can_make_no_retreat` / `can_make_rearguard` **没有**这条条件
  ⇒ 「死守」「后卫部队」任何单位都能挂；
* `state/entities/hq.pyc::HQState.can_unit_elastic_defense`
  = CP 够 + 单位在 HQ 范围内 + `unit.can_make_elastic_defense()`。

**实证**（用户的 `west.usg`，西线大捷第一关）：
`elastic_defense_units = [87, 104]`（87 = 突击炮、104 = 坦克）
两个都是 `movement=mobile` ⇒ 装甲机动；
而同一存档里的死守 / 后卫部队单位是**步兵** ⇒ 印证只有反击有这条限制。

**判定式**（本仓库的实现，照抄游戏）：
`armor and not armor_def and movement == 'mobile'`
⚠️ 摩托化步兵（`ger_mot_41` 等 42 个类型：`movement=mobile` 但 `armor_def=true`）
**不算**装甲机动单位 —— 它们那点装甲是**防御装甲**。

**这些测试守什么**：
① 判定式与游戏一致（类型表层面）；
② 核心库**硬拦**：给非装甲机动单位挂「反击」要报错；
③ 「死守」「后卫部队」**不受**这条限制；
④ 撤除已有标记**不受**限制（存档里原本就有的也不主动清理）；
⑤ 界面把不适用的「反击」按钮**置灰**并说明原因。
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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402
from save_modifier_core.catalog import UnitType  # noqa: E402

from ._fixtures import dump, make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")

#: 装甲机动单位（坦克/装甲师）
ARMORED = "us_arm_42"
#: 步兵（游戏里挂不了反击）
INFANTRY = "us_inf_42"


class ArmorMobileJudgementTest(unittest.TestCase):
    """① 判定式 = `armor and not armor_def and movement == 'mobile'`。"""

    def setUp(self):
        self.catalog = Catalog(CorePaths.discover())
        if not self.catalog.has_unit_type(INFANTRY):
            self.skipTest("本机没有游戏包")

    def test_infantry_is_not_armor_mobile(self):
        t = self.catalog.unit_type(INFANTRY)
        self.assertFalse(t.armor_mobile)
        self.assertFalse(self.catalog.armor_mobile(INFANTRY))

    def test_armored_unit_is_armor_mobile(self):
        t = self.catalog.unit_type(ARMORED)
        self.assertEqual(t.movement, "mobile")
        self.assertTrue(t.armor_mobile)
        self.assertTrue(self.catalog.armor_mobile(ARMORED))

    def test_armor_def_blocks_a_mobile_type(self):
        """摩托化步兵：movement=mobile，但装甲是**防御装甲** ⇒ 不算。"""
        t = UnitType(name="x", armor=4, armor_def=True, movement="mobile")
        self.assertFalse(t.armor_mobile)

    def test_missing_armor_def_is_not_a_blocker(self):
        """类型表里没写 `armor_def` ⇒ 视为 False（不拦）。"""
        t = UnitType(name="x", armor=4, movement="mobile")
        self.assertTrue(t.armor_mobile)

    def test_no_armor_means_no_counterattack(self):
        t = UnitType(name="x", armor=0, movement="mobile")
        self.assertFalse(t.armor_mobile)

    def test_unknown_type_is_not_armor_mobile(self):
        """类型查不到 ⇒ 不许挂（宁可保守）。"""
        self.assertFalse(self.catalog.armor_mobile("不存在的类型"))


class ElasticDefenseConstraintTest(unittest.TestCase):
    """② 核心库：硬拦「给非装甲机动单位挂反击」。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u92_orders_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.catalog = Catalog(CorePaths.discover())
        if not self.catalog.has_unit_type(ARMORED):
            self.skipTest("本机没有游戏包")
        self.save_path = self.make_save()

    def make_save(self):
        """造一个战斗中的存档：单位 1 = 步兵、3 = 装甲师，都在这场战斗里。"""
        p = self.tmp / "s.usg"
        make_save(p, battle_overrides={
            "no_retreat_units": [], "rearguard_units": [],
            "elastic_defense_units": [],
        })
        with zipfile.ZipFile(p) as zf:
            entries = {n: zf.read(n) for n in zf.namelist()}
        units = yaml.safe_load(entries["units.yml"])
        armored = dict(units[0])
        armored["id"] = 3
        armored["type"] = ARMORED
        armored["name_brief"] = "id_us_arm_42_brief"
        units.append(armored)
        entries["units.yml"] = dump(units)
        entries["games/avalanche/units.yml"] = dump([1, 2, 3])
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for n, d in entries.items():
                zf.writestr(n, d)
        return p

    def plan(self, edits, catalog=True):
        with open_save(str(self.save_path)) as save:
            return save.plan_edit(edits, catalog=self.catalog if catalog else None)

    def battle(self):
        with zipfile.ZipFile(self.save_path) as zf:
            return yaml.safe_load(zf.read("games/avalanche/main.yml"))

    # ---- 硬拦 ----
    def test_infantry_cannot_take_elastic_defense(self):
        plan = self.plan([Edit.unit_orders(1, ["elastic_defense"])])
        self.assertFalse(plan.ok, "给步兵挂反击竟然通过了")
        self.assertIn("装甲机动", plan.errors[0])

    def test_error_explains_the_rule(self):
        plan = self.plan([Edit.unit_orders(1, ["elastic_defense"])])
        self.assertFalse(plan.ok)
        msg = plan.errors[0]
        self.assertIn("反击", msg)
        self.assertIn("movement", msg)          # 给出判定依据
        self.assertIn("armor", msg)

    def test_armored_unit_can_take_elastic_defense(self):
        plan = self.plan([Edit.unit_orders(3, ["elastic_defense"])])
        self.assertTrue(plan.ok, plan.errors)
        with open_save(str(self.save_path)) as save:
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        self.assertIn(3, self.battle()["elastic_defense_units"])

    # ---- 别的标记不受这条限制 ----
    def test_other_orders_are_not_restricted(self):
        """「死守」「后卫部队」任何单位都能挂（游戏里没有 armor_mobile 条件）。"""
        plan = self.plan([Edit.unit_orders(1, ["no_retreat", "rearguard"])])
        self.assertTrue(plan.ok, plan.errors)
        with open_save(str(self.save_path)) as save:
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        b = self.battle()
        self.assertIn(1, b["no_retreat_units"])
        self.assertIn(1, b["rearguard_units"])

    def test_removing_is_always_allowed(self):
        """撤除已有标记**不受**限制（存档里原本就有的也不主动清理）。"""
        plan = self.plan([Edit.unit_orders(1, [])])
        self.assertTrue(plan.ok, plan.errors)

    def test_without_catalog_it_is_only_a_warning(self):
        """没有游戏包 ⇒ 判不了 ⇒ 放行，但**必须**给一条警告。"""
        plan = self.plan([Edit.unit_orders(1, ["elastic_defense"])], catalog=False)
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(any("装甲机动" in w for w in plan.warnings), plan.warnings)

    # ---- 视图 ----
    def test_view_carries_armor_mobile(self):
        with open_save(str(self.save_path)) as save:
            v = save.view(catalog=self.catalog)
        byid = {u.id: u for u in v.units}
        self.assertTrue(byid[3].armor_mobile)
        self.assertFalse(byid[1].armor_mobile)


class RealSaveEvidenceTest(unittest.TestCase):
    """② 实证：用户存档里挂着反击的单位，**确实**都是装甲机动单位。"""

    COPY = (r"D:\MiniMax\_analysis\appdata_u89\.uoc2\save\campaigns\west.usg")

    def test_user_save_matches_the_rule(self):
        if not os.path.exists(self.COPY):
            self.skipTest("没有用户的 west.usg 副本")
        catalog = Catalog(CorePaths.discover())
        if not catalog.has_unit_type("ger_pz_42"):
            self.skipTest("本机没有游戏包")
        with zipfile.ZipFile(self.COPY) as zf:
            names = zf.namelist()
            units = yaml.safe_load(zf.read("units.yml"))
            battle = None
            for n in names:
                if n.startswith("games/") and n.endswith("/main.yml"):
                    battle = yaml.safe_load(zf.read(n))
                    break
        if not battle:
            self.skipTest("这个副本里没有战斗层")
        byid = {u.get("id"): u for u in units}
        ids = battle.get("elastic_defense_units") or []
        self.assertTrue(ids, "用户的存档里没有反击单位？")
        for uid in ids:
            u = byid.get(uid)
            self.assertIsNotNone(u, "单位 %s 不在 units.yml 里" % uid)
            self.assertTrue(catalog.armor_mobile(u.get("type")),
                            "单位 %s（%s）不是装甲机动单位 ⇒ 游戏不会给它反击"
                            % (uid, u.get("type")))


class UiGuardTest(unittest.TestCase):
    """③ 界面：不适用时把「反击」按钮置灰并说明原因。"""

    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def test_there_is_a_helper(self):
        self.assertIn("function unitArmorMobile", self.html)

    def test_button_is_disabled_for_non_armored_units(self):
        self.assertIn('k==="elastic_defense" && !armorMobile', self.html)

    def test_toggle_also_blocks(self):
        """点按钮那条路也要拦（前端绕过界面时）。"""
        self.assertIn('key==="elastic_defense" && cur.indexOf(key)<0 && !unitArmorMobile(u)',
                      self.html)

    def test_existing_order_can_still_be_removed(self):
        """已经挂着反击的单位，按钮仍可点掉（只拦**新增**）。"""
        self.assertIn("&& !on", self.html)

    def test_css_has_a_disabled_style(self):
        self.assertIn(".orderbtn.dis", self.html)

    def test_explanation_is_translated(self):
        ui = self.table["ui"]
        self.assertIn("「{0}」只能挂装甲机动单位（游戏硬约束）", ui)


if __name__ == "__main__":
    unittest.main()
