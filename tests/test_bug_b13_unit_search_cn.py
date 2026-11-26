# -*- coding: utf-8 -*-
"""B-13：单位搜索要能搜到单位**自己的中文名**。

**社区原话**：「单位搜索似乎不能输入中文？不过就算能输入也不知道能不能正确识别单位名称。」

**根因**：搜索的 haystack 只有 `unitCn(u.type)+u.type+u.name_brief+u.name_full+u.id`，
**不含**服务端现算的 `name_cn` / `full_cn`（`server.py:453-454`）
⇒ 存档里 `name_brief` 存的是**本地化键**（如 `id_xxx_brief`），
   界面上显示的中文名是 `name_cn`
⇒ **列表里看到的中文名拿去搜命中不了**。

**这个测试怎么写的**（U188 的教训：静态断言要把 bug 锁进断言）：
用 **Node 跑 index.html 里那段过滤逻辑的原文**（从源码里抠出来，不是手抄）
⇒ 喂一个带 `name_cn` 的单位，用它的 `name_cn` 去搜 ⇒ 必须命中。
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

#: 从 index.html 抠出「单位列表的过滤」那段（`const list = units.filter(...)`）
FILTER_RE = re.compile(
    r"(const list = units\.filter\(u=>\{.*?\n  \}\);)", re.S)

HARNESS_JS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');

// ---- 从 index.html 里抠出过滤那段（原文，不是手抄）----
const m = html.match(/const list = units\.filter\(u=>\{[\s\S]*?\n  \}\);/);
if (!m) throw new Error('找不到单位过滤逻辑');
const filterSrc = m[0];

// ---- 造环境 ----
const unitCn = (t) => (t === 'us_inf_42' ? '美步兵' : (t || '?'));
const units = JSON.parse(process.argv[3]);
const q = process.argv[4];
const hqf = '';
const UONLY = false;
const inBattle = false;
const battleIds = new Set();

const fn = new Function('units','q','hqf','UONLY','inBattle','battleIds','unitCn',
  filterSrc + '\nreturn list;');
const list = fn(units, q, hqf, UONLY, inBattle, battleIds, unitCn);
console.log(JSON.stringify(list.map(u => u.id)));
"""


def _node_available():
    return shutil.which("node") is not None


def _filter(units, query):
    tmp = tempfile.mkdtemp(prefix="uoc2_b13_")
    try:
        js = os.path.join(tmp, "h.js")
        with io.open(js, "w", encoding="utf-8", newline="") as f:
            f.write(HARNESS_JS)
        r = subprocess.run(["node", js, HTML, json.dumps(units), query],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            raise AssertionError("node 跑失败：%s" % r.stderr[:800])
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestUnitSearchMatchesChineseName(unittest.TestCase):
    """用单位**自己显示的中文名**去搜，必须命中。"""

    UNIT = {
        "id": 1, "type": "us_inf_42",
        "name_brief": "id_us_inf_42_brief",     # ← 存档里存的是**本地化键**
        "name_full": "第 1 步兵连",
        "name_cn": "第 97 装甲营",               # ← 界面上显示的中文名
        "full_cn": "第 97 装甲营（满编）",
    }

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_search_by_displayed_chinese_name_finds_the_unit(self):
        """界面显示的中文名拿去搜 ⇒ 必须能搜到。"""
        got = _filter([self.UNIT], "装甲营")
        self.assertIn(1, got,
                      "用界面显示的中文名（%r）搜不到该单位（B-13）"
                      % self.UNIT["name_cn"])

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_search_by_full_chinese_name_finds_the_unit(self):
        """完整中文名（`full_cn`）也要能搜到。"""
        got = _filter([self.UNIT], "满编")
        self.assertIn(1, got, "用 full_cn 搜不到（B-13）")

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_search_still_works_for_type_and_id(self):
        """⚠️ 修 B-13 **不能**弄坏原有的搜索能力。"""
        self.assertIn(1, _filter([self.UNIT], "美步兵"), "按类型中文名搜不到了")
        self.assertIn(1, _filter([self.UNIT], "us_inf_42"), "按类型 id 搜不到了")
        self.assertIn(1, _filter([self.UNIT], "id_us_inf_42_brief"),
                      "按本地化键搜不到了")
        self.assertIn(1, _filter([self.UNIT], "第 1 步兵连"), "按 name_full 搜不到了")

    @unittest.skipUnless(_node_available(), "本机没有 node")
    def test_non_matching_query_returns_nothing(self):
        """不相关的词不该命中（别把 haystack 放得太宽）。"""
        self.assertEqual([], _filter([self.UNIT], "完全不相关的词"))


if __name__ == "__main__":
    unittest.main()
