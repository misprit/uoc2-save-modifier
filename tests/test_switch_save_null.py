# -*- coding: utf-8 -*-
"""切换存档时那条报错：`Cannot read properties of null (reading 'units') (Promise)`。

**根因**：切回启动页时 `VIEW` 被置成 null，而**在途的异步回调**回来后还在读
`VIEW.xxx` / `VIEW._save_id` ⇒ 抛 TypeError ⇒ 被 `unhandledrejection` 抓到。

护栏：
① 行为：node 真跑 `loadPickers()` —— 没有 `VIEW` 时**不许发请求**；
② 行为：node 真跑 `prefetchUnitPools()` —— 同上；
③ 静态：`renderPage` 在 `VIEW` 为空时**不渲染功能页**（回启动页）；
④ 静态：`openSave` 有在途守卫（`SAVE_TOKEN`）⇒ 切换存档时旧请求回来不会覆盖新界面。
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"

PROBE = r"""
let VIEW = __VIEW__;
const PICKCACHE = {};
let requested = 0;
function api(url){ requested++; return Promise.resolve({}); }
function encOnce(s){ return s; }
const PENDING = [];
__FUNCS__
const out = {};
out.result = await loadPickers("");
out.requested = requested;
await prefetchUnitPools(["ger_inf_40"]);
out.requested2 = requested;
console.log(JSON.stringify(out));
"""


def extract(source, names):
    parts = []
    for name in names:
        m = re.search(r"^(?:async )?function " + name + r"\(.*?^}", source, re.M | re.S)
        assert m, "index.html 里找不到函数 %s" % name
        parts.append(m[0])
    return "\n".join(parts)


def body_of(source, marker):
    """从 `marker` 那行到下一个顶层 `function`（没有就到文件末尾）。"""
    i = source.index(marker)
    j = source.find("\nfunction ", i + 10)
    return source[i:j if j > 0 else len(source)]


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestSwitchSaveWithoutView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def run_probe(self):
        program = (PROBE
                   .replace("__VIEW__", "null")
                   .replace("__FUNCS__", extract(self.source,
                                                 ("loadPickers", "prefetchUnitPools"))))
        r = subprocess.run(["node", "--input-type=module", "-"], input=program,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_no_request_without_view(self):
        """没有 `VIEW`（切回启动页了）⇒ **不许发请求**（原来会读 `VIEW._save_id` 崩掉）。"""
        out = self.run_probe()
        self.assertIsNone(out["result"])
        self.assertEqual(0, out["requested"], "loadPickers 不该发请求")
        self.assertEqual(0, out["requested2"], "prefetchUnitPools 不该发请求")

    def test_render_page_returns_to_splash_without_view(self):
        """`renderPage` 在没有存档时**不渲染功能页**（回启动页）。"""
        body = body_of(self.source, "function renderPage(p){")
        self.assertIn("if(!VIEW){", body)
        self.assertIn('getElementById("splash")', body)

    def test_open_save_has_an_inflight_guard(self):
        """切换存档时旧的 `openSave` 还在路上 ⇒ 它回来后不能覆盖新界面。"""
        self.assertIn("let SAVE_TOKEN = 0;", self.source)
        body = body_of(self.source, "async function openSave(sid){")
        self.assertIn("SAVE_TOKEN", body)
        self.assertIn("if(token !== SAVE_TOKEN) return;", body)
        # 切存档时必须**作废**在途请求
        self.assertIn("SAVE_TOKEN++", body_of(self.source, "function doSwitchSaveForce(){"))


if __name__ == "__main__":
    unittest.main()
