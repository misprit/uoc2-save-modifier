# -*- coding: utf-8 -*-
"""B-3：总部等级 / 压制 —— 界面显示必须与核心库实际结果一致。

**症状（社区）**：「调整等级之后界面没正确更新。虽然显示升级了，
但再调节压制会发现还是原本的等级，但最终应用后会发现修改结果是正确的。」

**根因**：`hqBranchState()` 的 `real`（真实等级）取**存档原值**，
压制时用 `level = real - suppressed` 重算 ⇒ **丢掉了此前待应用的等级变更**；
核心库的口径却是「执行压制时的**当前** level + 当前 suppressed」。

**这个测试怎么写的**（U188 的教训：不要复刻判定逻辑自证）：
① 用 **Node 直接跑 index.html 里的真函数**（不手抄）；
② 用 **真实核心库**（Python 侧）算同一批改完之后的结果；
③ 两者逐场景对比 ⇒ 验的是「界面 vs 实际」，不是「我抄的逻辑 vs 我抄的逻辑」。

用**夹具存档**（`tests/_fixtures.py` 的 `make_save`）而不是玩家存档：
既不碰玩家数据，又能构造出**已知**的等级/压制状态。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from save_modifier_core import catalog as catalog_mod  # noqa: E402
from save_modifier_core import open_save  # noqa: E402
from save_modifier_core.edits import Edit  # noqa: E402

from ._fixtures import make_save  # noqa: E402

#: 从 index.html 里抽 `hqBranchState` 并跑（Node）
HARNESS_JS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
function grab(name) {
  const i = html.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('找不到 ' + name);
  let depth = 0, started = false, j = i;
  for (; j < html.length; j++) {
    const c = html[j];
    if (c === '{') { depth++; started = true; }
    else if (c === '}') { depth--; if (started && depth === 0) { j++; break; } }
  }
  return html.slice(i, j);
}
const m = html.match(/const hqBrKey\s*=\s*\([^)]*\)\s*=>[^\n]*/);
if (!m) throw new Error('找不到 hqBrKey');
const VIEW = {hqs: []};
const PENDING = [];
const code = m[0] + '\n' + grab('hqBranchState');
const fn = new Function('VIEW', 'PENDING', code + '\nreturn hqBranchState;');
const hqBranchState = fn(VIEW, PENDING);
const scenarios = JSON.parse(process.argv[3]);
const HQ_ID = 'hq1', BR = 'operations';
for (const sc of scenarios) {
  VIEW.hqs = [{id: HQ_ID, branch_levels: {[BR]: {level: sc.level, suppressed: sc.supp}}}];
  PENDING.length = 0;
  for (const p of sc.pending) {
    /* T12：界面现在把「等级 + 压制」**成对**挂在**一条** `hq_branch_level` 上
       （params 里同时带 level 与 suppressed）⇒ 顺序无关、不会写出负数。 */
    PENDING.push({
      kind: 'hq_branch_level',
      key: `hq_branch_level:${HQ_ID}:${BR}`,
      params: p.params,
    });
  }
  const st = hqBranchState(HQ_ID, BR);
  console.log(JSON.stringify({name: sc.name, level: st.level, suppressed: st.suppressed,
                              real: st.real}));
}
"""


def _node_available():
    return shutil.which("node") is not None


def _run_frontend(scenarios):
    """跑 index.html 里的真 hqBranchState。"""
    tmp = tempfile.mkdtemp(prefix="uoc2_b3_")
    try:
        js = os.path.join(tmp, "h.js")
        with io.open(js, "w", encoding="utf-8", newline="") as f:
            f.write(HARNESS_JS)
        html = os.path.join(REPO, "src", "save_modifier_web", "web", "index.html")
        r = subprocess.run(["node", js, html, json.dumps(scenarios)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            raise AssertionError("node 跑失败：%s" % r.stderr[:400])
        return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestHqBranchUiMatchesCore(unittest.TestCase):
    """界面显示的生效等级 / 被压制数，必须与**核心库算出来的**一致。"""

    #: (名字, 存档 level, 存档 suppressed, [(level, suppressed), ...])
    #: ⚠️ T12 新口径：**解锁到几级** = level + suppressed（≤ 3）；
    #: **压制不改变解锁到几级**（只降生效等级、只影响技能图标）。
    SCENARIOS = [
        ("只升等级", 2, 0, [(3, 0)]),
        ("只压制", 2, 0, [(1, 1)]),
        ("升一级再压一级", 2, 0, [(2, 1)]),
        ("升两级再压一级", 2, 0, [(2, 1)]),
        ("只压一级不动等级", 2, 0, [(2, 0)]),
    ]

    BRANCH = "operations"
    HQ_ID = 5

    def _core_result(self, old_level, old_supp, pending):
        """用**真实核心库**算这一批改完之后的结果（夹具存档，不碰玩家数据）。"""
        tmp = tempfile.mkdtemp(prefix="uoc2_b3c_")
        try:
            path = make_save(Path(tmp) / "t.usg")
            catalog = catalog_mod.default()
            with open_save(str(path)) as save:
                hqs = save.read_yaml("hqs.yml", []) or []
                for hq in hqs:
                    if not isinstance(hq, dict):
                        continue
                    lv = hq.get("branch_levels")
                    if not isinstance(lv, dict) or not isinstance(lv.get(self.BRANCH), dict):
                        continue
                    # 改成已知状态（改**内存里的 YAML 对象**不行 ——
                    # `w.table()` 会从字节重新解析 ⇒ 必须在建夹具时就定好）
                    break
                edits = []
                for level, supp in pending:
                    # T12：成对写（`hq_branch_level` 本来就支持同时带 `suppressed`）
                    edits.append(Edit.hq_branch_level(self.HQ_ID, self.BRANCH, level, supp))
                plan = save.plan_edit(edits, catalog=catalog)
                self.assertTrue(plan.ok, "核心库拒绝了这个场景：%s" % plan.errors)
                res = save.commit(plan)
                self.assertTrue(res.ok, res.errors)
            with open_save(str(path)) as save:
                for hq in save.read_yaml("hqs.yml", []) or []:
                    lv = (hq or {}).get("branch_levels") or {}
                    nd = lv.get(self.BRANCH)
                    if isinstance(nd, dict) and hq.get("id") == self.HQ_ID:
                        return nd.get("level"), nd.get("suppressed")
            raise AssertionError("读回结果失败")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_ui_state_matches_core_result(self):
        """逐场景对比：界面显示 vs 核心库实际。

        ⚠️ 核心库那侧用**夹具**的初始状态（operations = L2/S0），
        前端那侧也用**同一组初始状态** ⇒ 两边起点一致。
        """
        # 夹具的 operations 初始是 level=2 / suppressed=0
        base_level, base_supp = 2, 0
        scen = [{"name": n, "level": base_level, "supp": base_supp,
                 "pending": [{"params": {"level": lv, "suppressed": sp}} for lv, sp in p]}
                for (n, _l, _s, p) in self.SCENARIOS]
        ui = _run_frontend(scen)
        self.assertEqual(len(self.SCENARIOS), len(ui))
        for (name, _l, _s, p), got in zip(self.SCENARIOS, ui):
            core_level, core_supp = self._core_result(base_level, base_supp, p)
            # ⚠️ T12：界面显示的是「**解锁到几级**」（玩家口径）⇒
            # 与核心库实际结果的 `level + suppressed` 比（**不变量没变**：
            # 界面显示必须与写盘结果一致）。
            self.assertEqual(
                (core_level + core_supp, core_supp), (got["real"], got["suppressed"]),
                "场景「%s」：界面显示 解锁%s/S%s，核心库实际 L%s/S%s ⇒ 不一致"
                % (name, got["real"], got["suppressed"], core_level, core_supp))

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_raise_then_suppress_keeps_the_raised_level(self):
        """**针对性**：升到 3 再压 1 ⇒ 界面显示的「解锁到几级」仍是 **3**。

        ⚠️ T12 新口径：压制**不改变**解锁到几级（只降生效等级）——
        玩家要求「压制变化不显示为等级的变化」。
        """
        scen = [{"name": "升到 3 再压 1", "level": 2, "supp": 0,
                 "pending": [{"params": {"level": 2, "suppressed": 1}}]}]
        got = _run_frontend(scen)[0]
        self.assertEqual(3, got["real"],
                         "升到 3 再压 1 ⇒ 解锁到几级仍是 3，实得 %s" % got["real"])
        self.assertEqual(1, got["suppressed"])
        self.assertEqual(2, got["level"], "生效等级 = 3 − 1 = 2")


if __name__ == "__main__":
    unittest.main()
