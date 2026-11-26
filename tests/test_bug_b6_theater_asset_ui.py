# -*- coding: utf-8 -*-
"""B-6：战区资产删除后再加回来，界面不刷新。

**社区原话**：「删除某项资产再添加回去，虽然改动会生效，但界面没有立刻更新。」

**根因（两处，同源）**

① `theaterInCurrent()` **先判 remove 再判 add** ⇒ 重新添加后仍判成「不在当前 phase 里」
   ⇒ 界面走「这个场景当前没有这项战区资产」那一支（不给数值控件、还给一个
   「添加这一项」按钮），而 `theaterCur()` 又取的是 add 的数值
   ⇒ **界面自相矛盾**（社区说的「界面没有立刻更新」）。

② 「添加」这条待应用**挂在了待应用列表的旧位置**（`setPending` 同 key 是**替换**、
   位置不动）⇒ 写盘顺序可能变成 **add → remove** ⇒ 写出来资产又没了，
   界面却说「有」。

**这个测试怎么写的**（仓库的教训：静态断言只比对写法、不验行为 ⇒ 会把 bug 本身保住）：

① 用 **Node + vm 直接跑 `index.html` 里的真函数**（`theaterRemove` /
   `theaterAddConfirm` / `theaterInCurrent` / `theaterCur`），不手抄；
② 把界面产生的**待应用**原样交给**真实核心库**（夹具存档，不碰玩家数据）写盘，
   再读回 `games/<场景>/main.yml` 的 `theater_assets`；
③ 断言的是**界面显示的最终状态 == 写盘后的实际状态**。

⚠️ `UOC2_INDEX_HTML` 环境变量只给**反证脚本**用：拿一份「退化副本」跑**同一个**测试，
证明断言真的能红（见 `.scratch/reverse_b6.py`）。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from save_modifier_core import Catalog, CorePaths, Edit, open_save  # noqa: E402

from ._fixtures import make_save  # noqa: E402

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
  const pre = html.slice(Math.max(0, i - 6), i);
  const prefix = (pre === 'async ') ? 'async ' : '';
  return prefix + html.slice(i, j);
}

const ctx = {console, JSON, Promise, Math, Date, Object, Array, String,
             Number, Boolean, Error, Set, Map, RegExp,
             encodeURIComponent, decodeURIComponent, setTimeout, clearTimeout};
ctx.globalThis = ctx;
ctx.document = {getElementById: () => ({style: {}, innerHTML: ''}),
                querySelectorAll: () => [], querySelector: () => null,
                addEventListener: () => {}};
vm.createContext(ctx);

const CODE = `
/* ⚠️ 顶层用 var —— vm 里 let/const 是词法绑定，外面拿不到。 */
var VIEW = null;
var PENDING = [];
var MODAL = null;
var SEL = {theaterSide: "player"};

function L(zh){ return zh; }
function L2(key){
  let s = key;
  const args = Array.prototype.slice.call(arguments, 1);
  args.forEach(function(a, i){ s = s.split("{" + i + "}").join(a); });
  return s;
}
function esc(s){ return String(s ?? ""); }
function theaterSideLabel(sid){ return sid || "player"; }
function alertModal(m){ throw new Error("alertModal: " + m); }
function closeModal(){}
function show(p){}
function paintPending(){}
`
  + ["setPending", "dropPendingKind", "theaterKey", "theaterAddKey",
     "theaterDelKey", "theaterSide", "theaterSideAssets", "theaterSideAssetsOf",
     "theaterPend", "theaterInCurrent", "theaterCur", "theaterRemove",
     "stageTheaterAssetAdd", "theaterAddConfirm", "theaterCn"]
      .map(grab).join("\n");

vm.runInContext(CODE, ctx);

const cfg = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
ctx.VIEW = cfg.view;

const ASSETS = cfg.assets || [];
for (const st of cfg.steps || []) {
  if (st.op === 'remove') {
    vm.runInContext('theaterRemove', ctx)(st.asset);
  } else if (st.op === 'add') {
    ctx.MODAL = {kind: 'theater', asset: st.asset, side: st.side || 'player',
                 uses_turn: st.uses_turn, uses_total: st.uses_total};
    vm.runInContext('theaterAddConfirm', ctx)();
  }
}

const out = {
  pending: ctx.PENDING.map(p => ({kind: p.kind, key: p.key, params: p.params})),
  in_current: {},
  cur: {},
};
for (const a of ASSETS) {
  out.in_current[a] = vm.runInContext('theaterInCurrent', ctx)(a);
  out.cur[a] = vm.runInContext('theaterCur', ctx)(a);
}
console.log(JSON.stringify(out));
"""


def _html_path():
    """默认跑仓库里的 index.html；反证脚本用 `UOC2_INDEX_HTML` 指到退化副本。"""
    return os.environ.get("UOC2_INDEX_HTML") or DEFAULT_HTML


def _node_available():
    return shutil.which("node") is not None


def _run(cfg):
    """跑一遍前端，返回 {pending, in_current, cur}。"""
    tmp = tempfile.mkdtemp(prefix="uoc2_b6_")
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


#: 界面看到的存档原值（与夹具存档里 `games/avalanche/main.yml` 的第 0 组一致）
VIEW = {
    "theater_assets": [
        {"asset": "air_attack", "to_use": 1, "to_use_not_used": None,
         "uses_total": None, "uses_turn": 1},
    ],
    "theater_assets_opponent": [],
    "theater_cn": {},
}


def _edits_from_pending(pending):
    """界面产生的待应用 ⇒ 核心库的编辑（**顺序照旧**）。"""
    edits = []
    for p in pending:
        prm = p.get("params") or {}
        if p["kind"] == "theater_asset_remove":
            edits.append(Edit.theater_asset_remove(prm.get("asset"),
                                                    side=prm.get("side")))
        elif p["kind"] == "theater_asset_add":
            edits.append(Edit.theater_asset_add(prm.get("asset"),
                                                 uses_total=prm.get("uses_total"),
                                                 uses_turn=prm.get("uses_turn"),
                                                 side=prm.get("side")))
        elif p["kind"] == "theater_asset":
            edits.append(Edit.theater_asset(prm.get("asset"),
                                             to_use=prm.get("to_use"),
                                             uses_total=prm.get("uses_total"),
                                             uses_turn=prm.get("uses_turn"),
                                             side=prm.get("side")))
    return edits


class _CoreRun(object):
    """在**夹具存档**上真写盘一次（不碰玩家数据）。"""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uoc2_b6c_"))
        self.path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def group(self):
        """存档里当前那一组的战区资产。"""
        with zipfile.ZipFile(self.path) as zf:
            data = yaml.safe_load(zf.read("games/avalanche/main.yml"))
        return data["theater_assets"][0]

    def apply(self, pending):
        """按界面给的顺序写盘，返回第 0 组的战区资产列表。"""
        edits = _edits_from_pending(pending)
        if not edits:
            # 没有待应用 ⇒ 不写盘（核心库会回「没有需要写入的改动」）
            return self.group()
        with open_save(str(self.path), self.paths) as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            assert plan.ok, "核心库拒绝了这批改动：%s" % plan.errors
            res = save.commit(plan)
            if not res.ok:
                if getattr(res, "nothing_to_do", False):
                    raise AssertionError(
                        "写盘**什么也没改**（这一批改动净效果为零 ⇒ 待应用的顺序错了）")
                raise AssertionError("写盘失败：%s" % (res.errors or res.summary))
        return self.group()


@unittest.skipUnless(_node_available(), "本机没有 node")
class TheaterAssetReAddUiTest(unittest.TestCase):
    """删了又加回来 ⇒ 界面与写盘结果必须一致。"""

    def setUp(self):
        self.core = _CoreRun()
        self.addCleanup(self.core.close)

    # ------------------------------------------------ 存档里本来就有这一项

    def test_re_adding_a_deleted_asset_shows_it_again(self):
        """**界面**：删掉再加回来 ⇒ 这一项要显示成「有」（可编辑），不是「没有」。"""
        got = _run({
            "view": VIEW,
            "assets": ["air_attack"],
            "steps": [
                {"op": "remove", "asset": "air_attack"},
                {"op": "add", "asset": "air_attack",
                 "uses_turn": 2, "uses_total": 3},
            ],
        })
        self.assertTrue(got["in_current"]["air_attack"],
                        "删掉又加回来，界面仍显示「这个场景当前没有这项战区资产」")
        cur = got["cur"]["air_attack"]
        self.assertEqual(2, cur["uses_turn"], "显示的每回合恢复不是加回来时填的值")
        self.assertEqual(3, cur["uses_total"], "显示的本场景剩余不是加回来时填的值")
        self.assertEqual(2, cur["to_use"], "显示的当前可用不是 min(每回合恢复, 本场景剩余)")

    def test_the_remove_must_be_applied_before_the_add(self):
        """**写盘顺序**：remove 必须在 add 前面（核心库的 add 要求组里没有同名）。"""
        got = _run({
            "view": VIEW,
            "assets": ["air_attack"],
            "steps": [
                {"op": "remove", "asset": "air_attack"},
                {"op": "add", "asset": "air_attack",
                 "uses_turn": 2, "uses_total": 3},
            ],
        })
        kinds = [p["kind"] for p in got["pending"]]
        self.assertIn("theater_asset_remove", kinds, "删除的待应用不见了")
        self.assertIn("theater_asset_add", kinds, "加回来的待应用不见了")
        self.assertLess(kinds.index("theater_asset_remove"),
                        kinds.index("theater_asset_add"),
                        "写盘顺序反了（add→remove ⇒ 核心库会先报「已经有战区资产」）")

    def test_the_written_result_matches_what_the_screen_shows(self):
        """**界面 vs 实际**：写盘后这一项必须还在，且是加回来时填的那些数。"""
        got = _run({
            "view": VIEW,
            "assets": ["air_attack"],
            "steps": [
                {"op": "remove", "asset": "air_attack"},
                {"op": "add", "asset": "air_attack",
                 "uses_turn": 2, "uses_total": 3},
            ],
        })
        items = self.core.apply(got["pending"])
        it = next((x for x in items if x.get("asset") == "air_attack"), None)
        self.assertIsNotNone(it, "写盘后这一项没了（界面却说它有）")
        self.assertEqual(2, it["uses_turn"])
        self.assertEqual(3, it["uses_total"])
        self.assertEqual(2, it["to_use"], "写盘的当前可用与界面显示的不一致")

    # -------------------------------------------- 存档里本来没有这一项

    def test_add_then_delete_then_add_again_shows_it_in_the_ui(self):
        """加 → 删 → 再加回来 ⇒ 界面显示**有**这一项。"""
        got = _run({
            "view": VIEW,
            "assets": ["flying_artillery"],
            "steps": [
                {"op": "add", "asset": "flying_artillery",
                 "uses_turn": 1, "uses_total": 2},
                {"op": "remove", "asset": "flying_artillery"},
                {"op": "add", "asset": "flying_artillery",
                 "uses_turn": 4, "uses_total": 5},
            ],
        })
        self.assertTrue(got["in_current"]["flying_artillery"],
                        "加回来之后界面仍显示「没有这一项」")

    def test_add_then_delete_then_add_again_writes_it_to_the_save(self):
        """加 → 删 → 再加回来 ⇒ **写盘后**这一项必须还在（不能被顺序吃掉）。"""
        got = _run({
            "view": VIEW,
            "assets": ["flying_artillery"],
            "steps": [
                {"op": "add", "asset": "flying_artillery",
                 "uses_turn": 1, "uses_total": 2},
                {"op": "remove", "asset": "flying_artillery"},
                {"op": "add", "asset": "flying_artillery",
                 "uses_turn": 4, "uses_total": 5},
            ],
        })
        items = self.core.apply(got["pending"])
        it = next((x for x in items if x.get("asset") == "flying_artillery"), None)
        self.assertIsNotNone(it, "写盘后这一项没了（待应用的顺序把它吃掉了）")
        self.assertEqual(4, it["uses_turn"], "写盘的不是最后加的那组数")
        self.assertEqual(5, it["uses_total"])
        self.assertEqual(4, it["to_use"])

    def test_deleting_something_that_was_only_just_added_leaves_nothing(self):
        """加进来又删掉 ⇒ 净效果是**没有**（不能把写盘搞成报错）。"""
        got = _run({
            "view": VIEW,
            "assets": ["flying_artillery"],
            "steps": [
                {"op": "add", "asset": "flying_artillery",
                 "uses_turn": 1, "uses_total": 2},
                {"op": "remove", "asset": "flying_artillery"},
            ],
        })
        self.assertFalse(got["in_current"]["flying_artillery"],
                         "加完又删了，界面仍显示有这一项")
        self.assertEqual([], got["pending"],
                         "加进来又删掉 ⇒ 净效果应当是**没有待应用**"
                         "（留着一条 remove 会被核心库拒绝）")
        items = self.core.apply(got["pending"])
        self.assertIsNone(next((x for x in items
                                 if x.get("asset") == "flying_artillery"), None),
                          "写盘后这一项还在")

    # ------------------------------------------------------------ 对照组

    def test_plain_add_of_a_new_asset_still_works(self):
        """对照组：只是加一项（没删过）⇒ 行为不变。"""
        got = _run({
            "view": VIEW,
            "assets": ["precision_bombing"],
            "steps": [
                {"op": "add", "asset": "precision_bombing",
                 "uses_turn": 1, "uses_total": None},
            ],
        })
        self.assertTrue(got["in_current"]["precision_bombing"])
        items = self.core.apply(got["pending"])
        it = next((x for x in items if x.get("asset") == "precision_bombing"), None)
        self.assertIsNotNone(it)
        self.assertIsNone(it["uses_total"], "「无限」写成了数字")
        self.assertEqual(1, it["to_use"])


if __name__ == "__main__":
    unittest.main()
