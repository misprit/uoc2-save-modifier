"""B-9：重新读取必须丢弃待应用改动，并仍打开当前存档。"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"


@unittest.skipUnless(shutil.which("node"), "本机没有 node")
class TestReloadCurrentForce(unittest.TestCase):
    def test_reload_discards_pending_and_reopens_same_save(self):
        source = HTML.read_text(encoding="utf-8")
        target = re.search(r"^async function doReloadCurrentForce\(.*?^}", source, re.M | re.S)[0]
        probe = """
const VIEW = {_save_id:'campaigns%2FA.usg'};
let PENDING = [{kind:'hq_field'}];
const painted = [], opened = [];
function closeModal() {}
function paintPending() { painted.push(PENDING.length); }
async function openSave(id) { opened.push([id, PENDING.length]); }
doReloadCurrentForce().then(() => console.log(JSON.stringify([PENDING, painted, opened])));
"""
        r = subprocess.run(["node", "-"], input=target + probe, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        pending, painted, opened = json.loads(r.stdout)
        self.assertEqual([], pending, "重新读取后待应用改动仍存在")
        self.assertEqual([0], painted)
        self.assertEqual([["campaigns%2FA.usg", 0]], opened)
