# -*- coding: utf-8 -*-
"""T-新功能：单位明细页「显示所有特种兵」候选池的搜索框 —— 护栏测试。

**痛点**：375 个特种兵只能逐组翻（国籍分组默认折叠）。

**这些测试守着**：
① 候选池里有搜索框；
② 搜索按「中文名 / type id / 国籍 / 特性」过滤（**每次查询各出一个结果**）；
③ **搜到的分组自动展开**（否则搜到了却藏在折叠组里）；
④ 没搜索词时分组**仍然默认折叠**（别把既有观感改了）；
⑤ 搜不到时有明确提示；
⑥ 搜索时**只重画池体**，输入框节点不动 ⇒ 中文输入法不被打断（T13 的教训）；
⑦ 搜到的**不可挂**条目也要显示（标灰）—— 搜索是「找卡」，不是「找能挂的卡」。

用 node 真跑 `index.html` 里的函数（抽真函数 ⇒ 验的是真逻辑，不是抄的逻辑）。
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"

FUNCS = ("specNatGroups", "spickMatch", "specAttachCheck", "specCanAttach",
         "specPoolItem", "fullPoolHTML", "fullPoolBodyHTML", "setPoolQuery",
         "poolQueryChanged", "poolGroupOpen")

PROBE = r"""
const CATALOG = {
  spec_types: {
    panzer_ger: {cn:"突击炮", full:"突击炮（德）", faction:"axis", nationality:"german",
                 attack:10, defense:2, armor:5, artillery:0, flags:["fast"]},
    sniper_sov: {cn:"狙击手", full:"狙击手（苏）", faction:"allies", nationality:"soviet",
                 attack:8, defense:1, armor:1, artillery:0, flags:["sniper"]},
    para_german: {cn:"伞兵", full:"伞兵（德）", faction:"axis", nationality:"german",
                  attack:3, defense:2, armor:1, artillery:0, flags:["paratrooper"]},
  },
  unit_types: {ger_tank: {faction:"axis", nationality:"german", max_spec:3}},
  nationalities: {german:{cn:"德国", short:"德", faction:"axis", parent:null},
                  soviet:{cn:"苏联", short:"苏", faction:"allies", parent:null}},
};
const SEL = {units:7, poolOpen:{}};
const VIEW = {units:[{id:7, type:"ger_tank", max_spec:3, specs:[]}]};
const L = (s) => s;
const L2 = (s, ...args) => { let out=s; args.forEach((a,i)=>{ out=out.split("{"+i+"}").join(a); }); return out; };
const esc = (s) => String(s==null?"":s);
const specCn = (t) => ((CATALOG.spec_types||{})[t]||{}).cn || t;
const natCn = (n) => ((CATALOG.nationalities||{})[n]||{}).cn || n;
const flagCn = (f) => f;
const facCn = (f) => f;
const specTex = (t) => 'specs/' + t + '.png';
const imgTag = () => "<img>";
function specTipHTML(){ return ""; }
function projectedSpecs(){ return []; }
/* 假 DOM：记录每个节点被改过几次 */
const nodes = {
  poolbody: {innerHTML:"", _writes:0},
  poolq: {value:"", innerHTML:"", _writes:0},
};
global.document = {
  getElementById(id){
    if(!nodes[id]) nodes[id] = {innerHTML:"", value:"", _writes:0};
    const n = nodes[id];
    return {
      get innerHTML(){ return n.innerHTML; },
      set innerHTML(v){ n.innerHTML = v; n._writes++; },
      get value(){ return n.value; },
      set value(v){ n.value = v; n._writes++; },
    };
  }
};
global.setTimeout = (fn) => fn();      /* 去抖：测试里立即执行 */
global.clearTimeout = () => {};

__FUNCS__

const out = {};
const u = VIEW.units[0];
out.full = fullPoolHTML(u, []);
out.body = fullPoolBodyHTML(u, [], "");
/* ⚠️ **每次查询各出一个结果** —— 早前三个用例共用一个字段 ⇒ 断言互相打架（假红）。 */
SEL.poolQuery = "";
out.qName = fullPoolBodyHTML(u, [], "伞兵");     /* 按中文名 */
out.qNat  = fullPoolBodyHTML(u, [], "德国");     /* 按国籍中文名 */
out.qId   = fullPoolBodyHTML(u, [], "panzer_ger"); /* 按 type id */
out.qFlag = fullPoolBodyHTML(u, [], "fast");     /* 按特性 */
out.qOther= fullPoolBodyHTML(u, [], "sniper_sov"); /* 阵营不可挂的那个 */
out.nomatch = fullPoolBodyHTML(u, [], "不存在的特种兵");
/* setPoolQuery：只应重画 poolbody，不动 poolq */
nodes.poolbody.innerHTML = "旧内容"; nodes.poolbody._writes = 0;
nodes.poolq.value = "伞兵"; nodes.poolq._writes = 0;
setPoolQuery("伞兵");
out.bodyWrites = nodes.poolbody._writes;
out.searchWrites = nodes.poolq._writes;
out.bodyAfter = nodes.poolbody.innerHTML;
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestPoolSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = HTML.read_text(encoding="utf-8")
        funcs = []
        for name in FUNCS:
            m = re.search(r"^function " + name + r"\(.*?^}", source, re.M | re.S)
            assert m, "index.html 里找不到函数 %s" % name
            funcs.append(m[0])
        program = PROBE.replace("__FUNCS__", "\n".join(funcs))
        r = subprocess.run(["node", "-"], input=program, capture_output=True,
                           text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr[-2000:]
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_pool_has_a_search_box(self):
        self.assertIn('id="poolq"', self.out["full"])
        self.assertIn("搜索特种兵", self.out["full"])

    def test_search_filters_by_chinese_name(self):
        """按**中文名**搜「伞兵」⇒ 只剩伞兵那一类（图标格里没有文字 ⇒ 看 type id）。"""
        body = self.out["qName"]
        self.assertIn("para_german", body)
        self.assertNotIn("sniper_sov", body)
        self.assertNotIn("panzer_ger", body)

    def test_search_filters_by_nationality_name(self):
        """按**国籍中文名**搜「德国」⇒ 只留德国的那几个。"""
        body = self.out["qNat"]
        self.assertIn("para_german", body)
        self.assertIn("panzer_ger", body)
        self.assertNotIn("sniper_sov", body)

    def test_search_filters_by_type_id(self):
        """按 **type id** 搜 `panzer_ger` ⇒ 只剩它。"""
        body = self.out["qId"]
        self.assertIn("panzer_ger", body)
        self.assertNotIn("para_german", body)
        self.assertNotIn("sniper_sov", body)

    def test_search_matches_trait_flag(self):
        """按**特性**搜 `fast` ⇒ 命中带该特性的卡。"""
        body = self.out["qFlag"]
        self.assertIn("panzer_ger", body)
        self.assertNotIn("sniper_sov", body)

    def test_search_shows_even_unattachable(self):
        """搜到**不可挂**的（阵营不同）也要显示 —— 搜索是找卡，不是找能挂的卡。"""
        body = self.out["qOther"]
        # 不可挂的条目 onclick 是 void 0（不写 type id）⇒ 用分组 id + 标灰类判定
        self.assertIn("togglePoolGroup('soviet')", body)
        self.assertIn("blocked", body, "不可挂的要标灰")
        self.assertIn("void 0", body, "不可挂的不能点")

    def test_matched_group_is_expanded(self):
        """搜到的分组**自动展开** —— 否则搜到了却藏在折叠组里看不见。"""
        body = self.out["qName"]
        self.assertNotIn('style="display:none"', body,
                         "有搜索词时分组必须展开")

    def test_groups_stay_collapsed_without_query(self):
        """没有搜索词时**仍然默认折叠**（别把既有观感改了）。"""
        self.assertIn('style="display:none"', self.out["body"])

    def test_no_match_shows_a_hint(self):
        self.assertIn("没有匹配", self.out["nomatch"])

    def test_search_only_redraws_the_pool_body(self):
        """只重画池体 ⇒ 输入框节点不动 ⇒ 中文输入法不被打断（T13 的教训）。"""
        self.assertGreaterEqual(self.out["bodyWrites"], 1)
        self.assertEqual(0, self.out["searchWrites"],
                         "搜索时不该重画输入框（会打断中文输入法）")


if __name__ == "__main__":
    unittest.main()
