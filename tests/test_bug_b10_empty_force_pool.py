"""B-10：总部兵库为空时仍须提供「加条目」入口。"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestEmptyForcePool(unittest.TestCase):
    def render(self, entries):
        source = HTML.read_text(encoding="utf-8")
        funcs = [re.search(r"^function " + name + r"\(.*?^}", source, re.M | re.S)[0]
                 for name in ("projectedPool", "hqPoolHTML")]
        probe = r"""
const PENDING = [], SEL = {};
const L = String, esc = String, natCn = String, hqEquipCn = String;
const L2 = (s, ...args) => s.replace(/\{(\d+)\}/g, (_, i) => args[i]);
const hqPoolKey = (id, i) => `${id}:${i}`, pendingVal = (_, key, q) => q;
const imgTag = () => '';
console.log(hqPoolHTML({id:7, force_pool:""" + json.dumps(entries) + "}));"
        r = subprocess.run(["node", "-"], input="\n".join(funcs) + probe,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        return r.stdout

    def test_empty_pool_has_add_button(self):
        self.assertRegex(self.render([]), r'<button\b[^>]*onclick="toggleHqPicker\(7\)"[^>]*>加条目</button>')

    def test_nonempty_pool_keeps_row_controls_and_add_button(self):
        html = self.render([{"equipment": "armor", "quantity": 2, "delay": 1}])
        for item in ("共 1 条", "armor", 'id="fp_q_7_0"', 'onclick="hqPoolRemove(7,0)"',
                     'onclick="toggleHqPicker(7)"'):
            self.assertIn(item, html)
