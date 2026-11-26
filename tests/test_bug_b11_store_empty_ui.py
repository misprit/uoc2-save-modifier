# -*- coding: utf-8 -*-
"""B-11 前端侧：商店**列表为空**时，战线/子商店与「上架新商品」入口仍要出现。

⚠️ 为什么单独一个文件：服务端那侧（`store_structure` 字段）由
`test_bug_b11_store_structure.py` 覆盖；这里覆盖的是**前端渲染**那一半
⇒ 同一规则两处实现 ⇒ 断言必须对称。

**怎么验的**：用 **Node 跑 index.html 里的真 `pageStore`**（不手抄），
喂它「存档结构有战线、但条目列表为空」的情形 ⇒ 看它渲染出什么。

⚠️ 依赖处理：把 index.html 里**所有** `function 名(` 声明自动抽成桩，
   再按需覆盖（`projectedStore` / `esc` / `L` 等）⇒ 不用逐个试。
"""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(REPO, "src", "save_modifier_web", "web", "index.html")

#: 需要**真跑**的目标函数
TARGET = "pageStore"

#: 需要**特别桩**的（默认值不对）
#: ⚠️ 桩的 body 里统一用 `a` 当形参名（harness 会按原函数的形参列表拼桩）。
STUBS = {
    # 条目列表：空的（下架全部 / 买空之后）
    "projectedStore": "return [];",
    # 文本
    "esc": "return String(a==null?'':a);",
    "L": "return a;",
    "L2": "return a;",
    "jsq": "return String(a==null?'':a);",
    "natCn": "return a;",
    "specCn": "return a;",
    "hqEquipCn": "return a;",
    "flagCn": "return a;",
    "pendingVal": "return null;",
    "playerSpecs": "return [];",
    "playerFaction": "return '';",
    "allSpecTypes": "return [];",
    "specPickItems": "return [];",
    "spickCellsHTML": "return '';",
    "spickCardHTML": "return '';",
    "natRowHTML": "return '';",
    "specNatGroups": "return [];",
    "spickGroupedHTML": "return '';",
    "spickGroupedMode": "return false;",
    "storeEntryCn": "return '?';",
    "specTex": "return '';",
    "storeKey": "return '';",
    "bindModalSpin": "",
    "bindNumIn": "",
    "bindSpickSearch": "",
    "closeModal": "",
    "openModal": "",
    "show": "",
    "queueEdit": "",
    "setPending": "",
    "pendingEdits": "return [];",
    "paintPending": "",
    "refreshHqLocal": "",
    "pendingAddOf": "return null;",
    "dropPendingByKey": "",
    "patchPendingParams": "",
    "pendingRemoveOf": "return null;",
    "pickStoreFront": "",
    "pickStoreSub": "",
    "storeSet": "",
    "storeRemove": "",
    "storeAddSpec": "",
    "storeAddEquip": "",
    "openStoreAddModal": "",
    "storeAddMode": "",
    "storeAddConfirm": "",
    "spickMatch": "return true;",
    "spickToggleAll": "",
    "spickClearSearch": "",
}

HARNESS_JS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');

function grab(name) {
  const i = html.indexOf('function ' + name + '(');
  if (i < 0) return null;
  let depth = 0, started = false, j = i;
  for (; j < html.length; j++) {
    const c = html[j];
    if (c === '{') { depth++; started = true; }
    else if (c === '}') { depth--; if (started && depth === 0) { j++; break; } }
  }
  return html.slice(i, j);
}

// ---- 造一个假的 VIEW / PENDING / SEL ----
const VIEW = {
  store: [],                       // ← **没有条目**（下架全部 / 买空之后）
  store_structure: {caucasus: ['store', 'elite_store']},
  front_names: {caucasus: '高加索'},
};
const PENDING = [];
const SEL = {storeFront: null, storeSub: null};

// ---- 把 index.html 里所有 `function 名(` 声明自动抽成桩 ----
const STUBS = __STUBS__;
const names = new Set();
const re = /function\s+([A-Za-z_$][\w$]*)\s*\(/g;
let m;
while ((m = re.exec(html)) !== null) names.add(m[1]);

const parts = [];
for (const n of names) {
  if (n === '__TARGET__') continue;
  const body = Object.prototype.hasOwnProperty.call(STUBS, n) ? STUBS[n] : '';
  // ⚠️ 桩的 body 统一用 `a` 当形参名 ⇒ 把原函数的**第一个形参**改名成 a，
  //    其余形参保持原名（body 一般只用第一个）。
  const decl = html.match(new RegExp('function\\s+' + n + '\\s*\\(([^)]*)\\)'));
  let params = '';
  if (decl && decl[1].trim()) {
    const ps = decl[1].split(',').map(s => s.trim());
    if (ps.length) ps[0] = 'a';
    params = ps.join(', ');
  }
  parts.push('function ' + n + '(' + params + '){' + body + '}');
}
const targetSrc = grab('__TARGET__');
if (!targetSrc) throw new Error('找不到目标函数');
parts.push(targetSrc);

const code = 'const VIEW = VIEW_;\nconst PENDING = PENDING_;\nconst SEL = SEL_;\n'
  + parts.join('\n') + '\nreturn __TARGET__;';
const fn = new Function('VIEW_', 'PENDING_', 'SEL_', code);
const target = fn(VIEW, PENDING, SEL);

// ---- 跑 ----
const w = {innerHTML: ''};
target(w);
console.log(JSON.stringify({html: w.innerHTML, front: SEL.storeFront, sub: SEL.storeSub}));
"""


def _node_available():
    return shutil.which("node") is not None


def _render():
    tmp = tempfile.mkdtemp(prefix="uoc2_b11_")
    try:
        js = os.path.join(tmp, "h.js")
        src = HARNESS_JS.replace("__STUBS__", json.dumps(STUBS)).replace(
            "__TARGET__", TARGET)
        with io.open(js, "w", encoding="utf-8", newline="") as f:
            f.write(src)
        r = subprocess.run(["node", js, HTML], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise AssertionError("node 跑失败：%s" % r.stderr[:800])
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestEmptyStoreStillRendersFronts(unittest.TestCase):
    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_empty_store_still_shows_front_and_add_entry(self):
        """条目为空时**不许**渲染「这个存档没有商店数据」的占位。"""
        got = _render()
        html = got["html"]
        self.assertNotIn("这个存档没有商店数据", html,
                         "商店条目为空时误判成「没有商店数据」了（B-11）")

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_empty_store_still_has_a_front_selected(self):
        """战线仍要被选中（且是存档结构里的那条）。"""
        got = _render()
        self.assertEqual("caucasus", got["front"],
                         "条目为空时战线应仍能从存档结构里选出来")

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_empty_store_still_has_the_add_entry_entrypoint(self):
        """仍要有「上架新商品」的入口 —— 否则玩家没法再上架。

        ⚠️ 入口按钮是 `toggleStorePicker()`（内部调 `openStoreAddModal()`），
        不是直接调 `openStoreAddModal` ⇒ 断言按**真实的按钮**来。
        """
        got = _render()
        self.assertIn("toggleStorePicker", got["html"],
                      "商店为空时没有上架入口 ⇒ 玩家没法再上架（B-11）")


if __name__ == "__main__":
    unittest.main()
