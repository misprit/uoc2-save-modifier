# -*- coding: utf-8 -*-
"""T5 续：新加的持续卡也能**一次落盘**标成「已使用」。

玩家 2026-11-27 反馈：新加的持续卡，「是否已使用」按钮**点不动**
（要等加卡先落盘才能改），而「是否免费」加完就能改 ⇒ 两个功能不对称。

根因：`Edit.card_add` 当时**没有 `used` 参数**、`_card_add` 写死 `"used": False`
⇒ 新加的卡没有任何通路口能标成已使用 ⇒ 界面点那个按钮**完全没反应**。
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from save_modifier_core import Catalog, CorePaths, Edit, open_save

from ._fixtures import make_save

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "src/save_modifier_web/web/index.html"

#: 游戏包里的持续卡 —— 必须是**既持续又不召唤单位**的卡型
#: （伞兵是召唤卡 ⇒ 被 U187 硬拦，根本加不到手牌）
PERSISTENT = "espionage_soviet"
#: 非持续卡（`persistent=False`）
ORDINARY = "air_attack_allies"


class TestCardAddUsed(unittest.TestCase):
    """核心库：`card_add(..., used=True)`。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t5_add_used_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = make_save(self.tmp / "synthetic.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def cards(self):
        with zipfile.ZipFile(str(self.path)) as zf:
            return yaml.safe_load(zf.read("cards.yml"))

    def commit(self, edit):
        with open_save(str(self.path), self.paths) as save:
            plan = save.plan_edit([edit], catalog=self.catalog)
            if not plan.ok:
                return plan, None
            return plan, save.commit(plan)

    def test_persistent_card_can_be_added_as_used(self):
        """持续卡 + `used=True` ⇒ 写盘后那张卡的 `used` 真的是 True。"""
        plan, res = self.commit(Edit.card_add(PERSISTENT, used=True))
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(res.ok, res.errors)
        row = next(c for c in self.cards() if c.get("card_type") == PERSISTENT)
        self.assertIs(True, row.get("used"))

    def test_ordinary_card_cannot_be_added_as_used(self):
        """非持续卡标成「已使用」没有意义 ⇒ **必须被拒**。"""
        plan, _ = self.commit(Edit.card_add(ORDINARY, used=True))
        self.assertFalse(plan.ok)
        self.assertIn("持续卡", plan.errors[0])

    def test_used_must_be_boolean(self):
        plan, _ = self.commit(Edit.card_add(PERSISTENT, used="maybe"))
        self.assertFalse(plan.ok)
        self.assertIn("True / False", plan.errors[0])

    def test_default_is_not_used(self):
        """默认仍是「未使用」（向后兼容：不传 used 的老调用不变）。"""
        plan, res = self.commit(Edit.card_add(PERSISTENT))
        self.assertTrue(plan.ok, plan.errors)
        row = next(c for c in self.cards() if c.get("card_type") == PERSISTENT)
        self.assertIs(False, row.get("used"))


FUNCS = ("cardInfo", "cardCn", "cardImg", "cardTileHTML", "projectedCards",
         "pendingAddOf", "dropPendingKind", "setPending", "queueEdit",
         "cardSetFree", "cardSetUsed", "patchPendingParams")

PROBE = r"""
const CATALOG = {card_types:{
  espionage_soviet:{persistent:true, cn:"间谍", subtitle:"侦察"},
  air_attack_allies:{persistent:false, cn:"空袭", subtitle:""}}};
const VIEW = {hand:[], shelf:[]};
let PENDING = __PENDING__;
const L = (s)=>s;
const L2 = (s,...a)=>s.replace(/\{(\d+)\}/g,(_,i)=>a[i]);
const esc = (s)=>String(s);
const imgTag = ()=>'';
const show = ()=>{};
function paintPending(){}
__FUNCS__
const out = {};
cardSetUsed(1, __USED__);
out.pending = PENDING.map(x=>({kind:x.kind, key:x.key, params:x.params}));
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestNewCardUsedButton(unittest.TestCase):
    """前端：新加的卡点「已用」⇒ 改**那条加卡待应用**（与「免费」同一套机制）。"""

    def toggle(self, used, pending=None):
        if pending is None:
            pending = [{"kind": "card_add", "key": "card_add:1",
                        "params": {"card_type": "espionage_soviet", "position": 1,
                                   "is_free": False, "used": False},
                        "label": "加卡"}]
        source = HTML.read_text(encoding="utf-8")
        funcs = []
        for name in FUNCS:
            m = re.search(r"^(?:async )?function " + name + r"\(.*?^}", source, re.M | re.S)
            if m:
                funcs.append(m[0])
        program = (PROBE.replace("__PENDING__", json.dumps(pending))
                          .replace("__USED__", "true" if used else "false")
                          .replace("__FUNCS__", "\n".join(funcs)))
        r = subprocess.run(["node", "-"], input=program,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_new_card_can_be_marked_used_in_the_same_batch(self):
        """⭐ 新加的持续卡点「已用」⇒ 加卡那条待应用带上 `used=true`
        ⇒ **一次落盘**就能标成已使用（不用先加再改）。"""
        out = self.toggle(True)
        self.assertEqual(1, len(out["pending"]))
        self.assertEqual("card_add", out["pending"][0]["kind"])
        self.assertIs(True, out["pending"][0]["params"]["used"])

    def test_new_card_can_be_toggled_back(self):
        """再点一次 ⇒ 回到 false（仍是那一条加卡待应用，不多出一条）。"""
        pending = [{"kind": "card_add", "key": "card_add:1",
                    "params": {"card_type": "espionage_soviet", "position": 1,
                               "is_free": False, "used": True},
                    "label": "加卡"}]
        out = self.toggle(False, pending)
        self.assertEqual(1, len(out["pending"]))
        self.assertIs(False, out["pending"][0]["params"]["used"])


if __name__ == "__main__":
    unittest.main()
