# -*- coding: utf-8 -*-
"""B1（R-3 之一）：数量可以**直接键入**。

社区原话：「改数量只能用滚轮而不能输入这一点殊为不便。」

**验的是行为，不是字面量**：
* `bindNumIn` 用 node + 假 DOM 真跑 —— 输入 / 滚轮 / 非法值各走一遍；
* 模板那两处（商店库存、总部兵库数量）用静态断言守住「是输入框、不是滚轮 span」。
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"

PROBE = r"""
const L = (s) => s;
const L2 = (s, ...args) => s.replace(/\{(\d+)\}/g, (_, i) => args[i]);
let dropped = [];
function dropPendingKind(kind, key){ dropped.push([kind, key]); }
function wheelBind(el, fn){
  el.addEventListener("wheel", function(ev){
    ev.preventDefault();
    fn(ev.deltaY > 0 ? -1 : 1);
  }, {passive:false});
}
function fakeEl(value){
  const listeners = {};
  const cls = {};
  let val = (value === undefined) ? "" : String(value);
  return {
    get value(){ return val; },
    set value(v){ val = (v === undefined || v === null) ? "" : String(v); },
    title: "",
    classList: {toggle(n, on){ cls[n] = !!on; }, add(){}, remove(){}},
    addEventListener(t, f){ (listeners[t] = listeners[t] || []).push(f); },
    fire(t, ev){ (listeners[t] || []).forEach(f => f(ev || {})); },
    types(){ return Object.keys(listeners); },
    cls,
  };
}

__FUNCS__

const sc = __SCENARIO__;
const el = fakeEl(sc.value);
let got = null;
bindNumIn(el, {base: sc.base, cur: sc.cur, min: sc.min, max: sc.max,
               wheel: sc.wheel, kind: "k", key: "kk",
               onChange(v){ got = v; }});
const out = {init: el.value, types: el.types(), title: el.title};
if(sc.input !== undefined && sc.input !== null){
  el.value = String(sc.input);
  el.fire("input", {});
}
if(sc.wheelDelta !== undefined && sc.wheelDelta !== null){
  el.fire("wheel", {deltaY: sc.wheelDelta, preventDefault(){}});
}
out.got = got;
out.value = el.value;
out.dropped = dropped;
out.cls = el.cls;
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
class TestBindNumIn(unittest.TestCase):
    def run_scenario(self, scenario):
        source = HTML.read_text(encoding="utf-8")
        program = (PROBE
                   .replace("__SCENARIO__", json.dumps(scenario))
                   .replace("__FUNCS__", extract(source, ("bindNumIn",))))
        r = subprocess.run(["node", "-"], input=program,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_pending_value_is_visible_in_the_box(self):
        """挂起的值要写进输入框（否则玩家看到的是存档原值，不知道自己改过）。"""
        out = self.run_scenario({"base": 5, "cur": 12, "min": 0, "max": None,
                                 "value": ""})
        self.assertEqual("12", out["init"])

    def test_typing_a_number_calls_onchange(self):
        out = self.run_scenario({"base": 5, "cur": None, "min": 0, "max": None,
                                 "value": "5", "input": "37"})
        self.assertEqual(37, out["got"])

    def test_illegal_value_is_rejected_and_pending_dropped(self):
        """商店库存不能填 0（游戏没有售罄标记）⇒ 输入 0 要报错并撤掉待应用。"""
        out = self.run_scenario({"base": 5, "cur": None, "min": 1, "max": None,
                                 "value": "5", "input": "0"})
        self.assertIsNone(out["got"])
        self.assertTrue(out["cls"].get("bad"))
        self.assertEqual([["k", "kk"]], out["dropped"])

    def test_wheel_is_bound_only_when_asked(self):
        """默认**不挂滚轮** ⇒ XP / 移动力 / 价格等既有输入框行为零变化。"""
        out = self.run_scenario({"base": 5, "cur": None, "min": 0, "max": None,
                                 "value": "5"})
        self.assertNotIn("wheel", out["types"])

    def test_wheel_steps_by_one_when_asked(self):
        out = self.run_scenario({"base": 5, "cur": None, "min": 0, "max": None,
                                 "wheel": True, "value": "5", "wheelDelta": 1})
        self.assertIn("wheel", out["types"])
        self.assertEqual("4", out["value"])
        self.assertEqual(4, out["got"])

    def test_wheel_respects_min(self):
        out = self.run_scenario({"base": 1, "cur": None, "min": 1, "max": None,
                                 "wheel": True, "value": "1", "wheelDelta": 1})
        self.assertEqual("1", out["value"])


class TestQuantityControlsAreInputs(unittest.TestCase):
    """模板那两处：数量控件必须是**输入框**（社区反馈的原话是「不能输入」）。"""

    def setUp(self):
        self.html = HTML.read_text(encoding="utf-8")

    def test_store_quantity_is_an_input(self):
        self.assertRegex(self.html,
                         r'<input class="numin" id="st_q_\{13\}_\{14\}_\{15\}" type="text"')
        self.assertNotIn('class="spin" id="st_q_', self.html)

    def test_hq_pool_quantity_is_an_input(self):
        self.assertRegex(self.html,
                         r'<input class="numin" id="fp_q_\{9\}_\{10\}" type="text"')
        self.assertNotIn('class="spin" id="fp_q_', self.html)

    def test_quantity_bindings_use_bind_num_in(self):
        """两处数量都必须用 `bindNumIn`（能键入），且**不许重绘**（重绘 ⇒ 焦点丢失）。"""
        self.assertRegex(self.html,
                         r'bindNumIn\(qEl, \{base:e\.quantity\|\|0')
        self.assertRegex(self.html,
                         r'bindNumIn\(el, \{base:e\.quantity\|\|0')
        # 重绘会把正在输入的框删掉 ⇒ 第二个字打不进去
        store_block = self.html.split("bindNumIn(qEl,")[1].split("}});")[0]
        self.assertNotIn("show(\"store\")", store_block)
        pool_block = self.html.split("bindNumIn(el, {base:e.quantity||0")[1].split("}});")[0]
        self.assertNotIn("refreshHqLocal(", pool_block)


if __name__ == "__main__":
    unittest.main()
