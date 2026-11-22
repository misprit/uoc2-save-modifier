# -*- coding: utf-8 -*-
"""U145：商店 / 兵库「上架新特种」的候选列表按**阵营 → 国籍**分组（可折叠）。

**用户反馈**
> 商店和兵库上架新特种显示全部的选择界面没有分国籍折叠，
> 选显示全部的话就会直接罗列全部特种，而且排序也是乱七八糟。
> 按照单位明细里显示全部的组织逻辑修改。

**改法**：与单位明细页「显示所有特种兵」**共用同一套**分组逻辑
（`specNatGroups()`）—— 同一条规则只留一处（U136 的教训）。

**这些测试守着**

① 分组规则**只有一处实现**（单位明细页与商店/兵库都调 `specNatGroups`）；
② 分组规则本身（阵营顺序 / 国籍顺序 / 组内顺序）；
③ 分组视图**只在**「显示全部」+ **特种兵**模式下启用；
④ 折叠状态存在 `MODAL.poolOpen` 里（重绘 / 搜索都不丢）。
"""

import io
import os
import unittest

WEB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "save_modifier_web", "web")


def group_specs(items, usable, first_fac, nat_cn, spec_cn):
    """**照抄** `index.html` 的 `specNatGroups()`（改坏了两边都会红）。

    * `items`：`[{"id": 类型id, "faction":…, "nationality":…}, …]`
    * `usable(item)` → 布尔（「本方挂得上的？」）
    * `first_fac`：排最前的阵营 id
    """
    facs = {}
    for it in items:
        facs.setdefault(it.get("faction") or "?", []).append(it)
    fac_keys = sorted(facs, key=lambda f: (0 if f == first_fac else 1, f))
    out = []
    for f in fac_keys:
        nats = {}
        for it in facs[f]:
            nats.setdefault(it.get("nationality") or "?", []).append(it)
        nat_keys = sorted(nats, key=lambda n: (
            -sum(1 for it in nats[n] if usable(it)),
            nat_cn(n)))
        out.append({
            "fac": f,
            "nats": [{"nat": n,
                      "items": sorted(nats[n], key=lambda it: spec_cn(it["id"]))}
                     for n in nat_keys],
        })
    return out


class SpecPickerGroupsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()

    @staticmethod
    def _body(html, start, end):
        i = html.index(start)
        j = html.index(end, i + len(start))
        return html[i:j]

    # ------------------------------------------------- ① 规则只有一处实现

    def test_shared_grouping_function_exists(self):
        self.assertIn("function specNatGroups(", self.html)

    def test_both_pages_use_the_same_grouping(self):
        """⚠️ **U136 的教训**：同一条规则两处实现 ⇒ 迟早漂移。
        单位明细页与商店/兵库**必须**都走 `specNatGroups()`。"""
        units = self._body(self.html, "function fullPoolHTML(",
                           "function poolGroupOpen(")
        self.assertIn("specNatGroups(", units)

        pick = self._body(self.html, "function spickGroupedHTML(",
                          "function spickGroupOpen(")
        self.assertIn("specNatGroups(", pick)

        # 旧的"各写各的"代码不许再出现
        self.assertNotIn("facs[f]=facs[f]||[]", units)
        self.assertNotIn("nats[n]=nats[n]||[]", units)

    # --------------------------------------------------------- ② 分组规则

    def test_grouping_order_rules(self):
        body = self._body(self.html, "function specNatGroups(",
                          "function facCn(")
        self.assertIn("if(a===firstFac) return -1;", body)   # 本方阵营排最前
        self.assertIn("if(cb!==ca) return cb-ca;", body)      # 可用多的排前面
        self.assertIn('natCn(a).localeCompare(natCn(b),"zh")', body)
        self.assertIn('specCn(x.id).localeCompare(specCn(y.id),"zh")', body)

    def test_python_mirror_of_the_order(self):
        """照抄一遍：阵营（本方最前）→ 国籍（可用多的在前）→ 组内按中文名。"""
        items = [
            {"id": "a", "faction": "axis", "nationality": "german"},
            {"id": "b", "faction": "allies", "nationality": "uk"},
            {"id": "c", "faction": "allies", "nationality": "german"},
            {"id": "d", "faction": "axis", "nationality": "german"},
            {"id": "e", "faction": "allies", "nationality": "fr"},
            {"id": "f", "faction": "allies", "nationality": "uk"},
        ]
        # uk 有 **2 个**可用的、german 1 个、fr 0 个
        usable = {"b", "c", "f"}
        nat_cn = {"uk": "英国", "fr": "法国", "german": "德国"}
        spec_cn = {"a": "阿", "b": "乙", "c": "丙", "d": "丁", "e": "戊",
                   "f": "己"}
        groups = group_specs(items, lambda it: it["id"] in usable, "allies",
                             lambda k: nat_cn.get(k, k),
                             lambda k: spec_cn.get(k, k))
        # ① 阵营：玩家（allies）排最前
        self.assertEqual(["allies", "axis"], [g["fac"] for g in groups])
        allies = groups[0]
        # ② 国籍：可用的多的排前面（uk 2 个 > german 1 个 > fr 0 个）
        self.assertEqual(["uk", "german", "fr"],
                         [n["nat"] for n in allies["nats"]])
        # ③ 组内：按特种兵中文名排
        self.assertEqual(["b", "f"],
                         [it["id"] for it in allies["nats"][0]["items"]])

    # ------------------------------------------------------- ③ 什么时候分组

    def test_grouped_only_in_show_all_spec_mode(self):
        body = self._body(self.html, "function spickGroupedMode(",
                          "/* 分组视图")
        self.assertIn("MODAL.all", body)
        self.assertIn('MODAL.mode!=="equip"', body)

    def test_flat_list_still_exists_for_the_default_view(self):
        """默认视图（玩家挂得上的）保持平铺 —— 与单位明细页一致。"""
        body = self._body(self.html, "function spickCellsHTML(",
                          "/* 什么时候用分组视图")
        self.assertIn("spickGroupedMode()", body)
        self.assertIn("spickMatch(", body)

    # --------------------------------------------------------- ④ 折叠状态

    def test_group_state_lives_in_modal(self):
        body = self._body(self.html, "function spickGroupOpen(",
                          "function spickToggleGroup(")
        self.assertIn("MODAL.poolOpen", body)

    def test_toggle_redraws_the_grid_in_place(self):
        body = self._body(self.html, "function spickToggleGroup(",
                          "function bindSpickSearch(")
        self.assertIn("MODAL._spickRefresh", body)

    def test_search_keeps_a_refresh_handle(self):
        body = self._body(self.html, "function bindSpickSearch(",
                          "/* 详情卡（复用 .slot 样式")
        self.assertIn("MODAL._spickRefresh = apply;", body)

    def test_search_auto_expands_groups(self):
        """搜索时**自动展开**有结果的组 —— 否则输入关键词却什么都看不见。"""
        body = self._body(self.html, "function spickGroupedHTML(",
                          "/* 国籍组的折叠状态")
        self.assertIn("const open = q ? true : spickGroupOpen(n.nat);", body)

    def test_both_modals_start_with_a_fresh_state(self):
        # 兵库：MODAL = {…, all:false, poolOpen:{},   /* 注释 */}
        self.assertIn("all:false, poolOpen:{},", self.html)
        # 商店：MODAL = {…, all:false,\n    poolOpen:{}};
        self.assertIn("poolOpen:{}};", self.html)


if __name__ == "__main__":
    unittest.main()
