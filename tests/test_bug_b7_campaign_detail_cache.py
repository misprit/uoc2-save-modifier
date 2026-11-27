# -*- coding: utf-8 -*-
"""B-7：切换战役存档后，战役页大面积串数据。

**社区原话**：「切换读取不同战役的存档时战役界面的部分信息不更新。
包括路线图（只有标题更新）、废墟（能够识别出不是当前场景，界面显示可以修改，
应用更改时无法生效）、场景名册（除了标题正确，其他都串了）。」

**根因**：`CDETAIL`（`/api/campaign-detail` 的结果）是**模块级全局**，
而「切换存档 / 写盘 / 撤销」这几条路径都**没有让它失效** ⇒
名册、路线图、废墟全都还是**上一个存档**的数据：

* 场景名册：标题来自新 `VIEW`（对），表体 `rosterHTML()` 读 `CDETAIL.roster`（旧存档）；
* 废墟：列表用旧 `CDETAIL.ruins`，场景判定 `ruinSceneIds()` 却用新 `VIEW`
  ⇒ 判成「不在当前场景」却仍给「修复这一座」按钮，真应用时报
  「坐标 %s 不在废墟清单里」；
* 路线图：整块都来自 `CDETAIL` ⇒ 陈旧。

**这个测试怎么写的**（仓库的教训：静态断言只比对写法、不验行为 ⇒ 会把 bug 本身保住）：

① 用 **Node + vm 直接跑 `index.html` 里的真函数**（`openSave` / `doSwitchSaveForce` /
   `reallyApply` / `doUndo` / `rosterHTML` / `ruinsBox`），不手抄；
② `api()` 换成**假服务端**（每个存档各返回一份名册 / 路线图 / 废墟）；
③ 断言的是**界面最终显示什么**（`rosterHTML()` / `ruinsBox()` 的输出）
   与**请求打到了哪个存档**，不是源码字面量。

⚠️ `UOC2_INDEX_HTML` 环境变量只给**反证脚本**用：拿一份「退化副本」跑**同一个**测试，
证明断言真的能红（见 `.scratch/reverse_b7.py`）。
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")
DEFAULT_HTML = os.path.join(WEB, "index.html")

#: 从 index.html 里抽真函数跑（Node）
HARNESS_JS = r"""
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');

function grab(name) {
  const i = html.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('找不到函数 ' + name);
  let depth = 0, started = false, j = i;
  for (; j < html.length; j++) {
    const c = html[j];
    if (c === '{') { depth++; started = true; }
    else if (c === '}') { depth--; if (started && depth === 0) { j++; break; } }
  }
  /* `async function f(` ⇒ 把 `async ` 带上（否则 await 语法直接报错）。 */
  const pre = html.slice(Math.max(0, i - 6), i);
  const prefix = (pre === 'async ') ? 'async ' : '';
  return prefix + html.slice(i, j);
}

function makeEl() {
  return {
    style: {}, innerHTML: '', textContent: '', value: '',
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    addEventListener(){}, removeEventListener(){},
    querySelector(){ return null; }, querySelectorAll(){ return []; },
    focus(){}, blur(){}, setSelectionRange(){},
  };
}

const ctx = {
  console, JSON, Promise, Math, Date, Object, Array, String, Number,
  Boolean, Error, Set, Map, RegExp,
  encodeURIComponent, decodeURIComponent, setTimeout, clearTimeout,
};
ctx.globalThis = ctx;
ctx.document = {
  getElementById: () => makeEl(),
  querySelectorAll: () => [],
  querySelector: () => null,
  addEventListener: () => {},
  createElement: () => makeEl(),
};
vm.createContext(ctx);

const CODE = `
/* ⚠️ 用 var（不是 let/const）—— vm 里顶层 let/const 是**词法绑定**，
   外面拿不到 ctx.VIEWS / ctx.CDETAIL（var 才会挂到上下文对象上）。 */
var VIEW = null;
var CDETAIL = null;
var CDETAIL_TOKEN = 0;
/* openSave 的在途守卫（切换存档时作废旧请求）
   —— 注意：**这整段是 JS 模板字符串**，注释里不能出现反引号！ */
var SAVE_TOKEN = 0;
var CDETAIL_LOADING = false;
var USTACK = null;
var PAGE = "campaign";
var PENDING = [];
var MODAL = null;
var SEL = {};
var CALLS = [];
var VIEWS = {};
var DETAILS = {};
var SHOWN = [];

function encOnce(s){ return encodeURIComponent(String(s ?? "")); }
async function api(path){
  CALLS.push(path);
  if(path.indexOf("/api/view/") === 0)
    return VIEWS[decodeURIComponent(path.slice("/api/view/".length))];
  if(path.indexOf("/api/campaign-detail") === 0){
    const q = path.split("save_id=")[1] || "";
    return DETAILS[decodeURIComponent(q)];
  }
  return {};
}
async function post(path, body){
  CALLS.push(path);
  return {data: {ok: true, warnings: [], summary: "", backup: "bak"}};
}
async function loadCatalog(){ return null; }
async function loadPickers(){ return null; }
async function refreshUndoStack(){ return null; }
async function reload(){ return null; }
function paintHeader(){}
function paintRail(){}
function paintPending(){}
function pendingEdits(){ return PENDING.map(p => ({kind:p.kind, params:p.params})); }
function show(p){ SHOWN.push(p); }
function closeModal(){}
function openModal(){}
function alertModal(){}
function showJsError(e, w){ throw new Error("界面异常: " + e + " @ " + w); }
function L(zh){ return zh; }
function L2(key){
  let s = key;
  const args = Array.prototype.slice.call(arguments, 1);
  args.forEach(function(a, i){ s = s.split("{" + i + "}").join(a); });
  return s;
}
function esc(s){ return String(s ?? ""); }
function specCn(t){ return String(t); }
function specTex(t){ return "tex:" + String(t); }
function surf(x){ return String(x); }
`
  + ["loadCampaignDetail", "invalidateCampaignDetail", "openSave",
     "doSwitchSaveForce", "reallyApply", "doUndo",
     "ruinSceneIds", "ruinIsCurrent", "rosterHTML", "ruinsBox"]
      .map(grab).join("\n");

vm.runInContext(CODE, ctx);

const cfg = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
Object.assign(ctx.VIEWS, cfg.views || {});
Object.assign(ctx.DETAILS, cfg.details || {});

(async () => {
  for (const st of (cfg.steps || [])) {
    if (st.op === "openSave") {
      await vm.runInContext('openSave', ctx)(st.sid);
    } else if (st.op === "doSwitchSaveForce") {
      vm.runInContext('doSwitchSaveForce', ctx)();
    } else if (st.op === "reallyApply") {
      await vm.runInContext('reallyApply', ctx)();
    } else if (st.op === "doUndo") {
      await vm.runInContext('doUndo', ctx)();
    } else if (st.op === "setDetail") {
      ctx.DETAILS[st.sid] = st.detail;
    } else if (st.op === "loadDetail") {
      /* 模拟「玩家打开战役页」⇒ 战役详情被取回来（旧写法就是在这里取的，
         而且**只取一次**，换存档也不重取 ⇒ 串数据）。 */
      await vm.runInContext('loadCampaignDetail()', ctx);
    }
    /* 让已经发出去的请求（战役详情）落地 */
    await new Promise(r => setTimeout(r, 0));
  }
  await new Promise(r => setTimeout(r, 0));
  const out = {
    calls: ctx.CALLS,
    shown: ctx.SHOWN,
    cdetail: ctx.CDETAIL,
    token: ctx.CDETAIL_TOKEN,
    roster: vm.runInContext('rosterHTML()', ctx),
    ruins: vm.runInContext('ruinsBox()', ctx),
  };
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def _html_path():
    """默认跑仓库里的 index.html；反证脚本用 `UOC2_INDEX_HTML` 指到退化副本。"""
    return os.environ.get("UOC2_INDEX_HTML") or DEFAULT_HTML


def _node_available():
    return shutil.which("node") is not None


def _run(cfg):
    """跑一遍前端，返回 {calls, cdetail, roster, ruins, ...}。"""
    tmp = tempfile.mkdtemp(prefix="uoc2_b7_")
    try:
        js = os.path.join(tmp, "h.js")
        with io.open(js, "w", encoding="utf-8", newline="") as f:
            f.write(HARNESS_JS)
        cfgp = os.path.join(tmp, "cfg.json")
        with io.open(cfgp, "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(cfg, ensure_ascii=False))
        r = subprocess.run(["node", js, _html_path(), cfgp],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            raise AssertionError("node 跑失败：%s" % r.stderr[-2000:])
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


VIEW_A = {
    "_save_id": "saveA",
    "campaign_position": {"scenario_id": "sc1", "available_scenes": [{"id": "sc1"}]},
    "hqs": [], "units": [],
}
VIEW_B = {
    "_save_id": "saveB",
    "campaign_position": {"scenario_id": "sc2", "available_scenes": [{"id": "sc2"}]},
    "hqs": [], "units": [],
}
DETAIL_A = {
    "roster": {"map_name": "A战役地图", "units": [], "hqs": [], "turn_seq": []},
    "route": [{"id": "routeA", "text": "A会议", "scenes": []}],
    "ruins": [{"uv": [1, 2], "scenarios": ["sc1"], "latest": True}],
    "front_names": {"f1": "A战线"},
}
DETAIL_B = {
    "roster": {"map_name": "B战役地图", "units": [], "hqs": [], "turn_seq": []},
    "route": [{"id": "routeB", "text": "B会议", "scenes": []}],
    "ruins": [{"uv": [9, 9], "scenarios": ["sc2"], "latest": True}],
    "front_names": {"f1": "B战线"},
}


@unittest.skipUnless(_node_available(), "本机没有 node")
class CampaignDetailCacheTest(unittest.TestCase):
    """战役详情必须**跟着存档走**。"""

    def _cfg(self, steps, details=None):
        return {
            "views": {"saveA": VIEW_A, "saveB": VIEW_B},
            "details": details or {"saveA": DETAIL_A, "saveB": DETAIL_B},
            "steps": steps,
        }

    def _detail_calls(self, calls):
        return [c for c in calls if c.startswith("/api/campaign-detail")]

    # ------------------------------------------------------------ 切换存档

    def test_switching_to_another_save_refetches_the_detail(self):
        """换存档 ⇒ 战役详情必须**重新取**，而且取的是**新存档**的那份。"""
        got = _run(self._cfg([{"op": "openSave", "sid": "saveB"}]))
        calls = self._detail_calls(got["calls"])
        self.assertTrue(calls, "换存档后根本没有重新取战役详情")
        self.assertIn("saveB", calls[-1],
                      "重新取的战役详情不是新存档的那份：%r" % calls)
        self.assertIsNotNone(got["cdetail"], "战役详情是空的")

    def test_the_roster_comes_from_the_new_save(self):
        """**场景名册**：整张表必须来自新存档（社区反馈：除了标题其他都串了）。

        步骤 = 旧写法里真实发生过的顺序：打开 A → **进过战役页**（详情被取回来）
        → 换到 B ⇒ 界面上必须已经是 B 的名册。
        """
        got = _run(self._cfg([
            {"op": "openSave", "sid": "saveA"},
            {"op": "loadDetail"},
            {"op": "openSave", "sid": "saveB"},
        ]))
        self.assertIn("B战役地图", got["roster"],
                      "名册表体不是新存档的（还是上一个存档的）")
        self.assertNotIn("A战役地图", got["roster"],
                         "名册表体里还留着上一个存档的内容")

    def test_the_route_and_the_ruins_come_from_the_new_save(self):
        """**路线图 / 废墟**：同样必须来自新存档。"""
        got = _run(self._cfg([
            {"op": "openSave", "sid": "saveA"},
            {"op": "loadDetail"},
            {"op": "openSave", "sid": "saveB"},
        ]))
        detail = got["cdetail"] or {}
        self.assertEqual("routeB", (detail.get("route") or [{}])[0].get("id"),
                         "路线图还是上一个存档的")
        self.assertIn("(9, 9)", got["ruins"],
                      "废墟列表不是新存档的")
        self.assertNotIn("(1, 2)", got["ruins"],
                         "废墟列表里还留着上一个存档的废墟")

    def test_switching_saves_invalidates_the_cached_detail(self):
        """切换存档时缓存的战役详情必须**作废**（不能留着旧存档的数据）。"""
        got = _run(self._cfg([
            {"op": "openSave", "sid": "saveA"},
            {"op": "doSwitchSaveForce"},
        ]))
        self.assertIsNone(got["cdetail"],
                          "切换存档后旧的战役详情还留在缓存里")

    # -------------------------------------------------- 写盘 / 撤销之后

    def test_writing_to_disk_refetches_the_detail(self):
        """**写盘后**废墟清单要跟着变（修完废墟后不能还显示旧的）。"""
        after = {
            "roster": {"map_name": "A战役地图", "units": [], "hqs": [], "turn_seq": []},
            "route": [{"id": "routeA", "text": "A会议", "scenes": []}],
            "ruins": [],
            "front_names": {"f1": "A战线"},
        }
        got = _run(self._cfg([
            {"op": "openSave", "sid": "saveA"},
            {"op": "setDetail", "sid": "saveA", "detail": after},
            {"op": "reallyApply"},
        ], details={"saveA": DETAIL_A}))
        calls = self._detail_calls(got["calls"])
        self.assertGreaterEqual(len(calls), 2,
                                "写盘后没有重新取战役详情：%r" % calls)
        self.assertEqual([], (got["cdetail"] or {}).get("ruins"),
                         "写盘后废墟清单还是旧的")

    def test_undo_refetches_the_detail(self):
        """**撤销后**同样要重取（撤销把存档换回旧内容了）。"""
        after = dict(DETAIL_A)
        after["ruins"] = []
        got = _run(self._cfg([
            {"op": "openSave", "sid": "saveA"},
            {"op": "setDetail", "sid": "saveA", "detail": after},
            {"op": "doUndo"},
        ], details={"saveA": DETAIL_A}))
        calls = self._detail_calls(got["calls"])
        self.assertGreaterEqual(len(calls), 2,
                                "撤销后没有重新取战役详情：%r" % calls)
        self.assertEqual([], (got["cdetail"] or {}).get("ruins"),
                         "撤销后废墟清单还是旧的")

    # ------------------------------------------------------ 不能无限循环

    def test_opening_a_save_requests_the_detail_only_once(self):
        """重取不能变成「取一次就再取一次」的无限循环。

        ⚠️ 这里只查**重复**（≤ 1 次）；「有没有取」由上面那条断言管 ——
        否则「压根没取」也会被算成重复。
        """
        got = _run(self._cfg([{"op": "openSave", "sid": "saveB"}]))
        calls = self._detail_calls(got["calls"])
        self.assertLessEqual(len(calls), 1,
                             "同一个存档请求了 %d 次战役详情（会变成来回重取）"
                             % len(calls))


if __name__ == "__main__":
    unittest.main()
