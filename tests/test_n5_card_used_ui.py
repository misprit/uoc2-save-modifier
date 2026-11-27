# -*- coding: utf-8 -*-
"""N-5 + T5：持续卡的「已用 / 未用」—— 状态在**按钮**上，且与待应用**同步**。

**玩家口径（2026-11-27）**：
* 「不再单独显示免费和未使用的状态，都改成一个按钮。每次点按钮切换状态」；
* 「要注意待应用里要和界面显示同步」—— 点一次显示另一状态、待应用里有一条；
  再点一次回到原值、**待应用里应该没有这条**。

**为什么用 node 真跑**：验的是**渲染出来的 HTML** 与**挂起的编辑**，
不是源码里有没有某个字符串（静态断言会把写法锁死、却拦不住行为不对）。
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"

FUNCS = ("cardInfo", "cardCn", "cardImg", "cardTileHTML", "projectedCards",
         "pendingAddOf", "dropPendingKind", "setPending", "queueEdit",
         "cardSetFree", "cardSetUsed", "cardStoreSetFree")

PROBE = r"""
const CATALOG = __CATALOG__;
const VIEW = __VIEW__;
let PENDING = __PENDING__;
const L = (s) => s;
const L2 = (s, ...args) => s.replace(/\{(\d+)\}/g, (_, i) => args[i]);
const esc = (s) => String(s);
const imgTag = () => '';
const show = () => {};
function paintPending(){}

__FUNCS__

const out = {};
const sc = __SCENARIO__;
if(sc.kind === "tile"){
  out.html = cardTileHTML(sc.card, sc.mode);
}
if(sc.kind === "toggle"){
  PENDING = sc.pending || [];
  cardSetUsed(sc.position, sc.used);
  out.pending = PENDING.map(x => ({kind:x.kind, key:x.key, params:x.params,
                                  value:x.value, label:x.label}));
}
if(sc.kind === "toggle_free"){
  PENDING = sc.pending || [];
  cardSetFree(sc.position, sc.free);
  out.pending = PENDING.map(x => ({kind:x.kind, key:x.key, params:x.params,
                                  value:x.value, label:x.label}));
}
if(sc.kind === "projection"){
  PENDING = sc.pending || [];
  const proj = projectedCards(VIEW.hand, "hand");
  out.cards = proj.map(c => ({position:c.position, used:!!c.used, is_free:!!c.is_free}));
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
class TestCardUsedUI(unittest.TestCase):
    CATALOG = {"card_types": {
        "tactical_para_german": {"persistent": True, "cn": "伞兵", "subtitle": "空降"},
        "air_attack_allies": {"persistent": False, "cn": "空袭", "subtitle": ""},
    }}

    def run_scenario(self, scenario, catalog=None, view=None):
        source = HTML.read_text(encoding="utf-8")
        program = (PROBE
                   .replace("__CATALOG__", json.dumps(catalog or self.CATALOG))
                   .replace("__VIEW__", json.dumps(view if view is not None else
                                                   {"hand": [], "shelf": []}))
                   .replace("__PENDING__", "[]")
                   .replace("__SCENARIO__", json.dumps(scenario))
                   .replace("__FUNCS__", extract(source, FUNCS)))
        r = subprocess.run(["node", "-"], input=program,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def tile(self, card, mode="hand"):
        return self.run_scenario({"kind": "tile", "card": card, "mode": mode})["html"]

    # -------------------------------------------------- 渲染：状态在按钮上

    def test_persistent_hand_card_has_used_button(self):
        html = self.tile({"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False})
        self.assertIn("cardSetUsed(1,true)", html, "未使用 ⇒ 点了要变成已使用")
        self.assertIn("未用", html, "按钮上显示当前状态")

    def test_used_card_button_toggles_back(self):
        html = self.tile({"card_type": "tactical_para_german", "position": 2,
                          "is_free": True, "used": True})
        self.assertIn("cardSetUsed(2,false)", html, "已使用 ⇒ 点了要变成未使用")
        self.assertIn("已用", html)

    def test_non_persistent_card_has_no_used_button(self):
        html = self.tile({"card_type": "air_attack_allies", "position": 1,
                          "is_free": False, "used": False})
        self.assertNotIn("cardSetUsed", html)

    def test_shelf_card_has_no_used_button(self):
        html = self.tile({"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False}, mode="shelf")
        self.assertNotIn("cardSetUsed", html)

    def test_status_is_not_a_separate_line(self):
        """状态**不再单独占一行**（玩家要求：都改成按钮）。"""
        html = self.tile({"card_type": "tactical_para_german", "position": 1,
                          "is_free": True, "used": False})
        self.assertNotIn("freeline", html)
        self.assertNotIn("usedline", html)

    def test_free_button_shows_current_state(self):
        """免费 / 收费也是**按钮**（按钮上就是当前状态）。"""
        html = self.tile({"card_type": "tactical_para_german", "position": 1,
                          "is_free": True, "used": False})
        self.assertIn("cardSetFree(1,false)", html, "当前免费 ⇒ 点了要变收费")
        self.assertIn("免费", html)
        self.assertNotIn("freeline", html)

    # -------------------------------------------------- 挂起与同步

    def test_pending_used_is_reflected_in_projection(self):
        view = {"hand": [{"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False}], "shelf": []}
        pending = [{"kind": "card_set", "key": "card_set_used:1",
                    "params": {"position": 1, "field": "used", "value": True},
                    "label": "x", "value": True}]
        out = self.run_scenario({"kind": "projection", "pending": pending}, view=view)
        self.assertIs(True, out["cards"][0]["used"])

    def test_card_set_used_queues_used_field(self):
        view = {"hand": [{"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False}], "shelf": []}
        out = self.run_scenario({"kind": "toggle", "position": 1, "used": True,
                                 "pending": []}, view=view)
        self.assertEqual(1, len(out["pending"]))
        e = out["pending"][0]
        self.assertEqual("card_set", e["kind"])
        self.assertEqual("used", e["params"]["field"])
        self.assertEqual(1, e["params"]["position"])
        self.assertIs(True, e["params"]["value"])

    def test_card_set_used_key_differs_from_is_free_key(self):
        """两处改的是**同一槽位的不同字段** ⇒ key 必须分开。"""
        view = {"hand": [{"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False}], "shelf": []}
        out = self.run_scenario({"kind": "toggle", "position": 1, "used": True,
                                 "pending": []}, view=view)
        self.assertEqual("card_set_used:1", out["pending"][0]["key"])

    def test_card_set_used_ignores_pending_add(self):
        """待加的卡还没写盘 ⇒ 存档里没有这张卡 ⇒ 不挂 used 改动。"""
        view = {"hand": [], "shelf": []}
        pending = [{"kind": "card_add", "key": "card_add:1",
                    "params": {"card_type": "tactical_para_german", "position": 1,
                               "is_free": False},
                    "label": "x"}]
        out = self.run_scenario({"kind": "toggle", "position": 1, "used": True,
                                 "pending": pending}, view=view)
        self.assertEqual([], [e for e in out["pending"] if e["kind"] == "card_set"])
        self.assertEqual(1, len(out["pending"]))

    # -------------------------------------------------- 界面 ↔ 待应用 同步

    def test_toggling_back_to_the_stored_value_drops_the_pending(self):
        """⭐ 玩家明确要求：点一次改了、再点一次回到原值 ⇒ **待应用里不该留这条**。

        ⚠️ 这条曾经是 **bug**：`cardSetUsed` 的 `base` 取的是**投影值**（含挂起）
        ⇒ 再点一次时「目标值 == 投影值 ≠ 存档原值」⇒ 撤不掉。
        """
        view = {"hand": [{"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False}], "shelf": []}
        # 先点一次 ⇒ 挂起 used=true
        first = self.run_scenario({"kind": "toggle", "position": 1, "used": True,
                                   "pending": []}, view=view)
        self.assertEqual(1, len(first["pending"]))
        # 再点一次（回到存档原值 false）⇒ 待应用被撤掉
        second = self.run_scenario({"kind": "toggle", "position": 1, "used": False,
                                    "pending": first["pending"]}, view=view)
        self.assertEqual([], second["pending"],
                         "回到存档原值 ⇒ 待应用里不该留这条")

    def test_free_toggle_back_to_stored_value_drops_the_pending(self):
        """免费 / 收费 同样要能撤掉（它一直是对的 ⇒ 这条是回归护栏）。"""
        view = {"hand": [{"card_type": "tactical_para_german", "position": 1,
                          "is_free": True, "used": False}], "shelf": []}
        first = self.run_scenario({"kind": "toggle_free", "position": 1, "free": False,
                                   "pending": []}, view=view)
        self.assertEqual(1, len(first["pending"]))
        second = self.run_scenario({"kind": "toggle_free", "position": 1, "free": True,
                                    "pending": first["pending"]}, view=view)
        self.assertEqual([], second["pending"])


if __name__ == "__main__":
    unittest.main()
