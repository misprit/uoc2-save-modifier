# -*- coding: utf-8 -*-
"""T13：单位搜索框**要能打中文** —— 搜索时不能整页重绘。

**根因**：每次 `input` 都 `show("units")`（整页重绘）⇒ **输入框本身被重建**
⇒ 浏览器正在进行的 **IME 组合（拼音 → 汉字）被打断** ⇒ 汉字打不进去。

**护栏**：
① 静态：输入框的 `input` 处理器**不得**调 `show("units")`，必须走
   `refreshUnitsList()`；
② 行为：用 node + 假 DOM 真跑 `refreshUnitsList()` ⇒ 断言它**只**更新
   列表 / 计数 / 详情，**不碰工具栏**（输入框节点原封不动 ⇒ IME 不被打断）。
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestUnitSearchKeepsTheInputBox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def test_search_handler_does_not_repaint_the_page(self):
        """输入框的 input 处理器**不许**整页重绘（那会把输入框重建 ⇒ IME 被打断）。"""
        i = self.source.index('document.getElementById("uq")')
        j = self.source.index('document.getElementById("uhq")', i)
        body = self.source[i:j]
        self.assertNotIn('show("units")', body,
                         "搜索时整页重绘 ⇒ 输入框被重建 ⇒ 中文打不进去")
        self.assertIn("refreshUnitsList()", body)

    def test_refresh_only_touches_list_count_and_detail(self):
        """真跑 `refreshUnitsList()` ⇒ 只更新列表 / 计数 / 详情，**不碰工具栏**。"""
        program = r"""
const VIEW = {units:[{id:1, type:"t", hq_id:2, xp:10},
                      {id:2, type:"t2", hq_id:3, xp:20}], in_battle:false};
const SEL = {units:1};
let UQUERY = "", UHQFILTER = "", UONLY = false;
const L = (s) => s;
const L2 = (s, ...args) => s.replace(/\{(\d+)\}/g, (_, i) => args[i]);
const unitCn = (t) => t;
const esc = (s) => String(s);
function unitRowHTML(u){ return "<row>"+u.id+"</row>"; }
function unitDetailHTML(u){ return "<detail>"+(u?u.id:"none")+"</detail>"; }
function bindUnitControls(){}
function paintPending(){}
const touched = [];
const nodes = {
  urows:   {innerHTML:"", textContent:""},
  ucount:  {innerHTML:"", textContent:""},
  udetail: {innerHTML:"", textContent:""},
  uq:      {innerHTML:"<input id=uq>", textContent:"", value:""},
};
global.document = {getElementById: (id) => nodes[id] || null};
__FUNCS__
refreshUnitsList();
console.log(JSON.stringify({
  rows: nodes.urows.innerHTML,
  count: nodes.ucount.textContent,
  detail: nodes.udetail.innerHTML,
  toolbar: nodes.uq.innerHTML,
}));
"""
        funcs = []
        for name in ("filteredUnits", "refreshUnitsList"):
            m = re.search(r"^function " + name + r"\(.*?^}", self.source, re.M | re.S)
            self.assertIsNotNone(m, "找不到函数 %s" % name)
            funcs.append(m[0])
        program = program.replace("__FUNCS__", "\n".join(funcs))
        r = subprocess.run(["node", "-"], input=program,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        import json
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIn("<row>1</row>", out["rows"], "列表要刷新")
        self.assertIn("<row>2</row>", out["rows"])
        self.assertIn("2", out["count"], "计数要刷新")
        self.assertIn("<detail>1</detail>", out["detail"], "详情要刷新")
        self.assertEqual("<input id=uq>", out["toolbar"],
                         "工具栏（含输入框）不许被重建 —— 否则 IME 组合被打断")

    def test_list_and_count_have_ids(self):
        self.assertIn('id="urows"', self.source)
        self.assertIn('id="ucount"', self.source)


if __name__ == "__main__":
    unittest.main()
