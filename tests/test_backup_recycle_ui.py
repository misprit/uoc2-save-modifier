# -*- coding: utf-8 -*-
"""R1：概览备份管理只提交服务端 preview 返回的 id。"""
import json
import re
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/index.html"
I18N = Path(__file__).resolve().parents[1] / "src/save_modifier_web/web/i18n.json"


def _fn(source, name):
    m = re.search(r"^(?:async )?function " + re.escape(name) + r"\(.*?^}", source, re.M | re.S)
    if not m:
        raise AssertionError("missing function " + name)
    return m.group(0)


@unittest.skipUnless(__import__("shutil").which("node"), "本机没有 node")
class BackupRecycleUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.i18n = json.loads(I18N.read_text(encoding="utf-8"))["ui"]

    def test_preview_ids_are_used_and_path_is_not_constructed(self):
        self.assertIn("/api/backups/preview?save_id=", self.html)
        self.assertIn("/api/backups/recycle", self.html)
        self.assertIn("ids:ids", _fn(self.html, "backupRecycle"))
        self.assertNotIn("/api/backups/recycle?", self.html)
        self.assertNotRegex(_fn(self.html, "backupRecycle"), r"path|\.bak|backup_path")

    def test_node_stub_posts_selected_ids_and_guards_stale_save(self):
        funcs = "\n".join(_fn(self.html, n) for n in ("backupSummary", "backupRecycle"))
        # backupRecycle's dependencies are deliberately stubbed; no real HTTP is used.
        probe = r'''
let VIEW={_save_id:'save-A'}, BACKUP_MGMT={token:1,sid:'save-A',items:[
 {id:'id-1',name:'evil<one>.bak',size:10}, {id:'id-2',name:'two.bak',size:20}],
 selected:new Set(['id-1','id-2']),busy:false};
let posted=null, loaded=0, modal=[];
const document={querySelector:()=>({disabled:false})};
function post(path,body){posted={path,body}; return Promise.resolve({status:200,data:{ok:true,completed:['id-1'],failed:'id-2',remaining:['id-2'],errors:['bad <id-2>']}})}
function loadUndoStack(){loaded++; return Promise.resolve()}
function openModal(x){modal.push(x)}
function closeModal(){}
function L(x){return x}
function L2(x,...args){return String(x).replace(/\{(\d+)\}/g,(_,i)=>String(args[Number(i)]??""))}
function esc(x){return String(x).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function backupSize(x){return String(x)}
''' + funcs + r'''
backupRecycle().then(()=>console.log(JSON.stringify({posted,loaded,remaining:BACKUP_MGMT.items.map(x=>x.id),html:modal[0]})));
'''
        r = subprocess.run(["node", "-"], input=probe, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual("/api/backups/recycle", out["posted"]["path"])
        self.assertEqual({"save_id": "save-A", "ids": ["id-1", "id-2"]}, out["posted"]["body"])
        self.assertEqual(1, out["loaded"])
        self.assertEqual(["id-2"], out["remaining"])
        self.assertIn("two.bak", out["html"])
        self.assertIn("&lt;id-2&gt;", out["html"])

    def test_reentry_is_blocked_until_request_finishes(self):
        funcs = _fn(self.html, "backupRecycle")
        probe = r'''
let VIEW={_save_id:'save-A'}, BACKUP_MGMT={sid:'save-A',items:[],selected:new Set(['id-1']),busy:false};
let calls=0, resolvePost; const document={querySelector:()=>({disabled:false})};
function post(){calls++; return new Promise(r=>{resolvePost=r})} function loadUndoStack(){return Promise.resolve()}
function openModal(){} function closeModal(){} function L(x){return x} function L2(x,...a){return String(x).replace(/\{(\d+)\}/g,(_,i)=>String(a[Number(i)]??""))} function esc(x){return String(x)}
''' + funcs + r'''
const p1=backupRecycle(); const p2=backupRecycle();
if(calls!==1) throw Error('reentry sent a second request');
resolvePost({status:200,data:{completed:[],failed:null,remaining:['id-1'],errors:[]}});
Promise.all([p1,p2]).then(()=>console.log('REENTRY_OK'));
'''
        r = subprocess.run(["node", "-"], input=probe, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("REENTRY_OK", r.stdout)

    def test_cancel_does_not_send(self):
        funcs = _fn(self.html, "backupRecycle")
        probe = r'''
let VIEW={_save_id:'save-A'}, BACKUP_MGMT={sid:'save-A',items:[],selected:new Set(),busy:false};
let calls=0; const document={querySelector:()=>({disabled:false})};
function post(){calls++; return Promise.resolve({status:200,data:{}})} function openModal(){} function closeModal(){} function loadUndoStack(){return Promise.resolve()}
function L(x){return x} function L2(x,...a){return String(x).replace(/\{(\d+)\}/g,(_,i)=>String(a[Number(i)]??""))} function esc(x){return String(x)}
''' + funcs + r'''
backupRecycle().then(()=>{if(calls!==0) throw Error('cancel sent request'); console.log('CANCEL_OK')});
'''
        r = subprocess.run(["node", "-"], input=probe, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("CANCEL_OK", r.stdout)

    def test_new_ui_literals_have_english_translations(self):
        for text in ("管理备份", "确认回收备份", "回收结果", "未尝试"):
            self.assertIn(text, self.i18n)


if __name__ == "__main__":
    unittest.main()
