# -*- coding: utf-8 -*-
"""T12：总部的「分支等级」与「被压制等级」必须**互不联动**，且写不出负数。

玩家实测到的三个毛病：
* 等级按钮会「循环」：1 级点三次加号 → 2、3、1（第三下回到原点）；
* 等级与压制混着算 ⇒ 两者同时动能算出**负数**的分支等级；
* 压制变化会**显示成等级的变化**（玩家要求：压制只与右侧技能图标联动）。

这里用 node + 假 DOM 真跑 `index.html` 里的函数，验的是**行为**：
  * 显示的等级 = 解锁到几级（0–3），压制**不改**它；
  * 压制范围 = 0 .. 显示等级；
  * 等级到顶就**停住**（不循环）；回到原值就**撤掉待应用**；
  * 写出去的 `level` 恒 ≥ 0（真实等级 − 压制数）。
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import CorePaths, Edit, open_save

from ._fixtures import make_save

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"

FUNCS = ("hqBranchState", "setHqBranchState", "hqBranchLevel", "hqSuppress")

def _add_branch_levels(path, hq_id, levels):
    """给合成存档的某个总部加上 `branch_levels`（fixtures 不带这个字段）。"""
    tmp = path.with_name(path.name + ".rewrite")
    with zipfile.ZipFile(str(path)) as zin, \
            zipfile.ZipFile(str(tmp), "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "hqs.yml":
                rows = yaml.safe_load(data.decode("utf-8"))
                for row in rows:
                    if row.get("id") == hq_id:
                        row["branch_levels"] = levels
                data = yaml.safe_dump(rows, allow_unicode=True,
                                      sort_keys=False).encode("utf-8")
            zout.writestr(item, data)
    os.replace(str(tmp), str(path))

PROBE = r"""
const VIEW = __VIEW__;
let PENDING = [];
const L = (s) => s;
const L2 = (s, ...args) => s.replace(/\{(\d+)\}/g, (_, i) => args[i]);
const branchCn = (b) => b;
const hqBrKey = (id, br) => `hq_branch:${id}:${br}`;
function setPending(kind, key, params, label, value){
  const i = PENDING.findIndex(x => x.kind===kind && x.key===key);
  const e = {kind, key, params, label, value};
  if(i>=0) PENDING[i]=e; else PENDING.push(e);
}
function dropPendingKind(kind, key){
  const i = PENDING.findIndex(x => x.kind===kind && x.key===key);
  if(i>=0) PENDING.splice(i,1);
}
function refreshHqLocal(){}

__FUNCS__

const st = hqBranchState(__ID__, __BR__);
const out = {real:st.real, suppressed:st.suppressed, effective:st.effective,
             level:st.level, pending:PENDING.map(x=>({kind:x.kind, key:x.key,
             params:x.params, label:x.label, value:x.value}))};
if(__ACTIONS__ && __ACTIONS__.length){
  for(const a of __ACTIONS__){
    if(a[0]==="level") hqBranchLevel(__ID__, __BR__, a[1]);
    else hqSuppress(__ID__, __BR__, a[1]);
  }
  const s2 = hqBranchState(__ID__, __BR__);
  out.after = {real:s2.real, suppressed:s2.suppressed, effective:s2.effective,
               level:s2.level, pending:PENDING.map(x=>({kind:x.kind, key:x.key,
               params:x.params, label:x.label, value:x.value}))};
}
console.log(JSON.stringify(out));
"""


def extract(source, names):
    parts = []
    for name in names:
        m = re.search(r"^function " + name + r"\(.*?^}", source, re.M | re.S)
        assert m, "index.html 里找不到函数 %s" % name
        parts.append(m[0])
    return "\n".join(parts)


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestHqBranchLevels(unittest.TestCase):
    def run_scenario(self, level=1, suppressed=0, actions=()):
        view = {"hqs": [{"id": 7, "branch_levels": {
            "engineering": {"level": level, "suppressed": suppressed}}}]}
        source = HTML.read_text(encoding="utf-8")
        program = (PROBE
                   .replace("__VIEW__", json.dumps(view))
                   .replace("__ID__", "7")
                   .replace("__BR__", json.dumps("engineering"))
                   .replace("__ACTIONS__", json.dumps([list(a) for a in actions]))
                   .replace("__FUNCS__", extract(source, FUNCS)))
        r = subprocess.run(["node", "-"], input=program,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    # ------------------------------------------------ 初始状态

    def test_initial_state(self):
        out = self.run_scenario(level=1, suppressed=0)
        self.assertEqual(1, out["real"])
        self.assertEqual(0, out["suppressed"])
        self.assertEqual(1, out["effective"])

    # ------------------------------------------------ 等级：到顶停住、不循环

    def test_level_raises_and_stops_at_three(self):
        out = self.run_scenario(level=1, actions=[("level", 1)])
        self.assertEqual(2, out["after"]["real"])
        self.assertEqual(1, len(out["after"]["pending"]))

    def test_level_does_not_cycle_back_to_one(self):
        """1 级连点三次加号 ⇒ 2、3、**停住 3**（旧实现会跳回 1）。"""
        out = self.run_scenario(level=1, actions=[("level", 1), ("level", 1)])
        self.assertEqual(3, out["after"]["real"])
        self.assertEqual(3, out["after"]["pending"][0]["params"]["level"])

    def test_level_cannot_exceed_three(self):
        out = self.run_scenario(level=3, actions=[("level", 1)])
        self.assertEqual(3, out["after"]["real"])

    def test_level_back_to_original_drops_pending(self):
        """回到存档原值 ⇒ 待应用里不该留这条（改回原样 = 没改）。"""
        out = self.run_scenario(level=2, actions=[("level", 1), ("level", -1)])
        self.assertEqual([], out["after"]["pending"])

    # ------------------------------------------------ 压制：与显示等级不联动

    def test_suppress_does_not_change_displayed_level(self):
        out = self.run_scenario(level=2, suppressed=0, actions=[("suppress", 1)])
        self.assertEqual(2, out["after"]["real"], "压制不该改显示的等级")
        self.assertEqual(1, out["after"]["suppressed"])
        self.assertEqual(1, out["after"]["effective"], "生效等级要降一级（技能图标联动）")

    def test_suppress_cannot_exceed_level(self):
        """2 级的分支只能有 0/1/2 三种压制情况。"""
        out = self.run_scenario(level=2, actions=[("suppress", 1), ("suppress", 1),
                                                  ("suppress", 1)])
        self.assertEqual(2, out["after"]["suppressed"])

    def test_suppress_change_keeps_one_pending_entry(self):
        """压制 1 → 0 是**真实变化** ⇒ 待应用里要留一条（且解锁到几级不变）。"""
        out = self.run_scenario(level=2, suppressed=1, actions=[("suppress", -1)])
        self.assertEqual(1, len(out["after"]["pending"]))
        p = out["after"]["pending"][0]["params"]
        self.assertEqual(0, p["suppressed"])
        self.assertEqual(3, out["after"]["real"], "解锁到几级不该变")

    def test_suppress_back_to_original_drops_pending(self):
        """加一次压制再减回去 ⇒ 回到原值 ⇒ 撤掉整条待应用。"""
        out = self.run_scenario(level=2, suppressed=1,
                                actions=[("suppress", 1), ("suppress", -1)])
        self.assertEqual([], out["after"]["pending"])

    # ------------------------------------------------ 两者同时动：不出负数

    def test_level_and_suppress_together_never_write_negative(self):
        out = self.run_scenario(level=1, actions=[("suppress", 1), ("level", 1),
                                                  ("level", 1), ("suppress", 1)])
        p = out["after"]["pending"][0]["params"]
        self.assertGreaterEqual(p["level"], 0, "写出去的 level 不能是负数")
        self.assertLessEqual(p["level"] + p["suppressed"], 3)
        self.assertEqual(out["after"]["real"], p["level"] + p["suppressed"])

    def test_lowering_level_pulls_suppression_down(self):
        """把等级降到比压制还低 ⇒ 压制要一起降（否则写出去超范围）。"""
        out = self.run_scenario(level=2, suppressed=2, actions=[("level", -1)])
        p = out["after"]["pending"][0]["params"]
        self.assertEqual(3, p["level"] + p["suppressed"], "解锁到几级 4 → 3")
        self.assertGreaterEqual(p["level"], 0)

    def test_pending_holds_one_paired_edit(self):
        """等级与压制必须落在**同一条**编辑里 ⇒ 顺序无关、不会互相打架。"""
        out = self.run_scenario(level=2, actions=[("suppress", 1), ("level", 1)])
        self.assertEqual(1, len(out["after"]["pending"]))
        p = out["after"]["pending"][0]["params"]
        self.assertIn("level", p)
        self.assertIn("suppressed", p)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestHqMatrixRender(unittest.TestCase):
    """**渲染层**的护栏 —— 状态函数对了，渲染也可能画错。"""

    def render(self, level=2, suppressed=0):
        source = HTML.read_text(encoding="utf-8")
        program = r"""
const VIEW = {hqs:[{id:7, branch_levels:{engineering:{level:__LEVEL__, suppressed:__SUP__}},
                  branches:{engineering:[{action:"a", level:1, cost:1}]}}]};
let PENDING = [];
const L = (s) => s;
const L2 = (s, ...args) => s.replace(/\{(\d+)\}/g, (_, i) => args[i]);
const esc = (s) => String(s);
const BRANCHES = ["engineering"];
const branchCn = (b) => b;
const hqBrKey = (id, br) => `hq_branch:${id}:${br}`;
function hqSkillHTML(){ return ""; }
function setPending(kind, key, params, label, value){
  const i = PENDING.findIndex(x => x.kind===kind && x.key===key);
  const e = {kind, key, params, label, value};
  if(i>=0) PENDING[i]=e; else PENDING.push(e);
}
function dropPendingKind(kind, key){
  const i = PENDING.findIndex(x => x.kind===kind && x.key===key);
  if(i>=0) PENDING.splice(i,1);
}
function refreshHqLocal(){}
__FUNCS__
console.log(hqMatrixHTML(VIEW.hqs[0]));
"""
        program = (program.replace("__LEVEL__", str(level))
                          .replace("__SUP__", str(suppressed))
                          .replace("__FUNCS__", extract(source, ("hqBranchState",
                                                                "hqMatrixHTML"))))
        r = subprocess.run(["node", "-"], input=program,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        return r.stdout.strip()

    def test_rendered_level_is_unlock_level_not_effective(self):
        """存档：等级 2、被压制 1 ⇒ 解锁到 3 级、生效 2 级。
        ⇒ **显示的等级必须是 3**（不是 2 —— 那是生效等级，会被压制拉低）。"""
        html = self.render(level=2, suppressed=1)
        lvctl = html.split('class="lvctl"')[1].split("</div>")[0]
        self.assertIn("<b>3</b>", lvctl)

    def test_rendered_suppression_is_shown(self):
        html = self.render(level=2, suppressed=1)
        supctl = html.split('class="supctl"')[1].split("</div>")[0]
        self.assertIn("<b", supctl)
        self.assertIn(">1</b>", supctl)


class TestHqBranchPairedWrite(unittest.TestCase):
    """核心库侧：`Edit.hq_branch_level(hq_id, branch, level, suppressed)` 成对写入。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t12_branch_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = make_save(self.tmp / "synthetic.usg")
        _add_branch_levels(self.path, 5, {"engineering": {"level": 1, "suppressed": 0}})
        self.paths = CorePaths.discover()

    def plan(self, edit):
        with open_save(str(self.path), self.paths) as save:
            return save.plan_edit([edit])

    def test_paired_write_is_accepted(self):
        plan = self.plan(Edit.hq_branch_level(5, "engineering", 2, 1))
        self.assertTrue(plan.ok, plan.errors)

    def test_paired_write_beyond_three_is_rejected(self):
        """解锁到几级 = level + suppressed ≤ 3（游戏硬上限，超了读档会失败）。"""
        plan = self.plan(Edit.hq_branch_level(5, "engineering", 3, 1))
        self.assertFalse(plan.ok)
        self.assertIn("3", plan.errors[0])

    def test_commit_writes_both_fields(self):
        with open_save(str(self.path), self.paths) as save:
            plan = save.plan_edit([Edit.hq_branch_level(5, "engineering", 2, 1)])
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
            self.assertTrue(res.ok, getattr(res, "errors", None))
        with zipfile.ZipFile(str(self.path)) as zf:
            hqs = yaml.safe_load(zf.read("hqs.yml"))
        node = next(r for r in hqs if r.get("id") == 5)["branch_levels"]["engineering"]
        self.assertEqual(2, node["level"])
        self.assertEqual(1, node["suppressed"])
