# -*- coding: utf-8 -*-
"""N-5 前端：持续卡才有「已使用 / 未使用」开关。

**为什么用 node 真跑**：手牌卡的渲染是一串模板 + 投影逻辑，
静态断言源码字面量会把「写法」锁死、却拦不住「渲染结果不对」
⇒ 这里把 `index.html` 里的真函数抽出来跑，验的是**渲染出来的 HTML**。
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
         "cardSetUsed")

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

const scenario = __SCENARIO__;
let out = {};
if(scenario.kind === "tile"){
  out.html = cardTileHTML(scenario.card, scenario.mode);
}
if(scenario.kind === "pending"){
  PENDING = scenario.pending;
  const proj = projectedCards(VIEW.hand, "hand");
  out.used = proj.length ? !!proj[0].used : null;
}
if(scenario.kind === "toggle"){
  PENDING = scenario.pending || [];
  cardSetUsed(scenario.position, scenario.used);
  out.pending = PENDING.map(x => ({kind:x.kind, key:x.key, params:x.params,
                                  value:x.value, label:x.label}));
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

    # -------------------------------------------------- 渲染

    def test_persistent_hand_card_shows_used_line(self):
        html = self.tile({"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False})
        self.assertIn("usedline", html)
        self.assertIn('onclick="cardSetUsed(1,true)"', html)
        self.assertIn("未使用", html)

    def test_used_card_shows_used_state_and_toggles_back(self):
        html = self.tile({"card_type": "tactical_para_german", "position": 2,
                          "is_free": True, "used": True})
        self.assertIn("usedline used", html)
        self.assertIn('onclick="cardSetUsed(2,false)"', html)
        self.assertIn("已使用", html)

    def test_non_persistent_card_has_no_used_line(self):
        html = self.tile({"card_type": "air_attack_allies", "position": 1,
                          "is_free": False, "used": False})
        self.assertNotIn("usedline", html)
        self.assertNotIn("cardSetUsed", html)

    def test_shelf_card_has_no_used_line(self):
        """货架上的卡不是手牌 ⇒ 不给「已使用」开关。"""
        html = self.tile({"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False}, mode="shelf")
        self.assertNotIn("usedline", html)

    # -------------------------------------------------- 投影

    def test_pending_used_is_reflected_in_projection(self):
        view = {"hand": [{"card_type": "tactical_para_german", "position": 1,
                          "is_free": False, "used": False}], "shelf": []}
        pending = [{"kind": "card_set", "key": "card_set_used:1",
                    "params": {"position": 1, "field": "used", "value": True},
                    "label": "x", "value": True}]
        out = self.run_scenario({"kind": "pending", "pending": pending}, view=view)
        self.assertIs(True, out["used"])

    # -------------------------------------------------- 挂起改动

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
        """两处改的是**同一槽位的不同字段** ⇒ key 必须分开，否则一条会顶掉另一条。"""
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
        # 那条「加卡」待应用**原样留着**（不能被误删）⇒ 只断言没有新增 card_set
        self.assertEqual([], [e for e in out["pending"] if e["kind"] == "card_set"])
        self.assertEqual(1, len(out["pending"]))


class TestCatalogPersistentFlag(unittest.TestCase):
    """前端要判断「这张卡是不是持续卡」⇒ 服务端得把 `persistent` 带出来。"""

    def test_catalog_payload_exposes_persistent_flag(self):
        try:
            from save_modifier_web import server
            payload = server._catalog_payload()
        except Exception as exc:      # 没装游戏包 ⇒ 本机跑不了，跳过而不是红
            self.skipTest("拿不到游戏包目录：%s" % (exc,))
        types = payload.get("card_types") or {}
        self.assertTrue(types, "card_types 是空的")
        for name, d in types.items():
            self.assertIn("persistent", d, "卡型 %s 少了 persistent 标记" % name)
            self.assertIsInstance(d["persistent"], bool)
        self.assertTrue(any(d["persistent"] for d in types.values()),
                        "游戏包里应当有 persistent 卡型（实测 19 / 39）")


if __name__ == "__main__":
    unittest.main()
