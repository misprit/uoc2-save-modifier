# -*- coding: utf-8 -*-
"""U27：Web GUI 界面层（本地 HTTP 桥）—— 只读接口 + 安全边界。

**为什么有这些测试**：界面层是**唯一**能被本机其它进程/网页碰到的一层
（它开了个 HTTP 端口）⇒ 令牌校验与**目录穿越**必须有测试守着。
"""

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_web import server  # noqa: E402


class WebGuiTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server._Handler.token = "unit-test-token"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server._Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def get(self, path, token=True):
        req = urllib.request.Request(self.url(path))
        if token:
            req.add_header("X-Token", server._Handler.token)
        return urllib.request.urlopen(req, timeout=30).read()

    def get_json(self, path, token=True):
        return json.loads(self.get(path, token).decode("utf-8"))


class TestReadApi(WebGuiTestBase):
    def test_saves_endpoint_lists_saves(self):
        data = self.get_json("/api/saves")
        self.assertIn("saves", data)
        self.assertGreater(len(data["saves"]), 0)
        row = data["saves"][0]
        for k in ("save_id", "name", "kind", "mtime", "size"):
            self.assertIn(k, row)

    def test_view_endpoint_returns_units_and_features(self):
        data = self.get_json("/api/saves")
        sid = data["saves"][0]["save_id"]
        v = self.get_json("/api/view/" + urllib.request.quote(sid))
        self.assertIn("units", v)
        self.assertIn("hqs", v)
        self.assertIn("_features", v)
        names = {f["name"] for f in v["_features"]}
        self.assertTrue({"units", "hqs", "store", "theater_assets"} <= names)
        # 可用性必须来自 can_edit_*，而不是「原因文案非空」
        for f in v["_features"]:
            self.assertIn("ok", f)
            if f["ok"]:
                self.assertEqual(f["reason"], "")

    def test_unknown_save_returns_500_not_crash(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/view/" + urllib.request.quote("不存在的存档.usg"))
        self.assertEqual(cm.exception.code, 500)


class TestSecurity(WebGuiTestBase):
    def test_api_requires_token(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/saves", token=False)
        self.assertEqual(cm.exception.code, 403)

    def test_wrong_token_is_rejected(self):
        req = urllib.request.Request(self.url("/api/saves"))
        req.add_header("X-Token", "wrong-token")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(cm.exception.code, 403)

    def test_static_path_traversal_is_blocked(self):
        """`/../server.py` 之类**不能**把源码读出去。"""
        for p in ("/../server.py", "/..%2fserver.py", "/web/../../server.py"):
            try:
                body = self.get(p, token=False)
            except urllib.error.HTTPError as exc:
                self.assertIn(exc.code, (403, 404), p)
                continue
            self.assertNotIn(b"def run(", body, p)

    def test_index_page_is_served(self):
        body = self.get("/", token=False)
        self.assertIn("存档修改器".encode("utf-8"), body)


class TestWriteApi(WebGuiTestBase):
    """写操作：plan / commit / undo。

    ⚠️ **只用副本** —— `open_save()` 接受绝对路径，
    所以这里传的是**副本的绝对路径**，绝不碰用户的真存档。
    """

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        self.tmp = Path(tempfile.mkdtemp(prefix="webwrite_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        src = None
        for info in list_saves():
            p = str(info.path)
            if "BACKUP" not in p and p.endswith(".usg"):
                src = p
                break
        if src is None:
            self.skipTest("本机没有存档")
        self.copy = str(self.tmp / "copy.usg")
        shutil.copyfile(src, self.copy)

    def post(self, path, body):
        import json
        import urllib.request
        req = urllib.request.Request(
            self.url(path),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "X-Token": server._Handler.token},
            method="POST")
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    def test_plan_commit_undo_roundtrip(self):
        """改声望 → 提交 → 撤销 → 复原。"""
        view = self.get_json("/api/view/" + urllib.request.quote(self.copy))
        old = view.get("prestige") or 0
        new = old + 7

        plan = self.post("/api/plan", {
            "save_id": self.copy,
            "edits": [{"kind": "progress",
                        "params": {"field": "prestige", "value": new}}]})
        self.assertTrue(plan["ok"], plan.get("errors"))
        self.assertTrue(plan["changes"], plan)
        self.assertTrue(any("prestige" in n for n in plan["notes"]), plan["notes"])

        # plan **不碰磁盘**
        v1 = self.get_json("/api/view/" + urllib.request.quote(self.copy))
        self.assertEqual(v1.get("prestige"), old, "plan 阶段不该改存档")

        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "progress",
                        "params": {"field": "prestige", "value": new}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        self.assertIn("main.yml", cm["changed"])
        self.assertIsInstance(cm["summary"], str)      # 必须是字符串，不是方法对象

        v2 = self.get_json("/api/view/" + urllib.request.quote(self.copy))
        self.assertEqual(v2.get("prestige"), new)

        un = self.post("/api/undo", {"save_id": self.copy})
        self.assertTrue(un["ok"], un.get("errors"))
        v3 = self.get_json("/api/view/" + urllib.request.quote(self.copy))
        self.assertEqual(v3.get("prestige"), old, "撤销后应复原")

    def test_illegal_edit_is_rejected_with_error(self):
        """越界值 ⇒ errors（不进磁盘）。"""
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_field",
                        "params": {"hq_id": 5, "field": "cp", "value": 999}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])

    def test_unknown_kind_is_rejected(self):
        """非法编辑类型 ⇒ 400 + 结构化错误（不能是 500）。"""
        import json
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post("/api/commit", {
                "save_id": self.copy,
                "edits": [{"kind": "rm_rf", "params": {}}]})
        self.assertEqual(cm.exception.code, 400)
        body = json.loads(cm.exception.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        self.assertTrue(body["errors"])

    def test_post_requires_token(self):
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            self.url("/api/plan"),
            data=json.dumps({"save_id": self.copy, "edits": []}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(cm.exception.code, 403)


class TestSurfaces(WebGuiTestBase):
    """贴图代理 —— http 页面**不能**直接读 `file:///`（同源策略会拦掉）。

    ⇒ 游戏贴图必须走 `GET /surfaces/<相对路径>`，由服务端从游戏包读出来。
    """

    def test_unit_surface_is_served(self):
        body = self.get("/surfaces/unit/ger_inf_42/sheet_L.png")
        self.assertTrue(body.startswith(b"\x89PNG"), "不是 PNG")

    def test_specialist_surface_is_served(self):
        body = self.get("/surfaces/specialist/ger_arty_40/hq_action_icon.png")
        self.assertTrue(body.startswith(b"\x89PNG"), "不是 PNG")

    def test_theater_surface_is_served(self):
        body = self.get("/surfaces/theater/air_attack_neutral.png")
        self.assertTrue(body.startswith(b"\x89PNG"), "不是 PNG")

    def test_path_traversal_is_blocked(self):
        """贴图代理也不能被 `..` 钻出去。"""
        import urllib.error
        for p in ("/surfaces/../../secret", "/surfaces/unit/../../../etc/passwd"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.get(p)
            self.assertIn(cm.exception.code, (403, 404), p)

    def test_missing_surface_is_404(self):
        """查不到 ⇒ 404（界面退化成占位方块，§5.6，不报错）。"""
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/surfaces/unit/definitely_not_a_type/sheet_L.png")
        self.assertEqual(cm.exception.code, 404)


class TestPathEncoding(WebGuiTestBase):
    """U31：**前端只编码一次**（`encOnce` 幂等）+ 服务端 `unquote` 一次。

    ⚠️ 曾经的 bug：表格模板已经 `encodeURIComponent` 过一次，`openSave` 里又编码一次
    ⇒ `%20` → `%2520`、斜杠 → `%252F` ⇒ 服务端解一次后仍是编码串
    ⇒ **含空格的路径（`Old Saves/…`）打不开**。
    """

    @staticmethod
    def enc_once(raw):
        """复刻前端的 `encOnce()`。"""
        from urllib.parse import quote, unquote
        try:
            if unquote(raw) != raw:
                return raw                 # 已编码 => 原样
        except Exception:
            pass
        # JS 的 encodeURIComponent 不编码 ' ! ~ * ( ) —— 但我们额外把 ' 转 %27
        # （单引号会破坏 JS 字面量）⇒ 这里照做。
        return quote(raw, safe="!~*()").replace("'", "%27")

    def test_plain_id_roundtrip(self):
        from urllib.parse import unquote
        raw = "campaigns/Stalingrad.usg"
        self.assertEqual(unquote(self.enc_once(raw)), raw)

    def test_id_with_spaces_roundtrip(self):
        """`Old Saves/…` —— 就是打不开的那一类。"""
        from urllib.parse import unquote
        raw = "Old Saves/Stalingrad/Stalingrad-Conference3-2.usg"
        self.assertEqual(unquote(self.enc_once(raw)), raw)

    def test_id_with_chinese_roundtrip(self):
        from urllib.parse import unquote
        raw = "Old Saves/Victory in the West/困难难度-史实线/west-f.usg"
        self.assertEqual(unquote(self.enc_once(raw)), raw)

    def test_single_quote_is_escaped(self):
        """`encodeURIComponent` **不编码单引号** ⇒ 会破坏 JS 字面量。"""
        enc = self.enc_once("Player's save.usg")
        self.assertNotIn("'", enc)

    def test_already_encoded_is_not_encoded_again(self):
        """★ 核心断言：已编码的输入**不能再编码一次**（那就是原来的 bug）。"""
        from urllib.parse import quote, unquote
        raw = "Old Saves/Stalingrad/Stalingrad-Conference3-2.usg"
        once = quote(raw, safe="!~*()").replace("'", "%27")   # 模拟模板里 encodeURIComponent
        twice = self.enc_once(once)                # openSave 里再来一次
        self.assertEqual(twice, once, "被二次编码了")
        self.assertEqual(unquote(twice), raw)

    def _get_view(self, sid):
        import json
        import urllib.request
        enc = self.enc_once(sid)
        req = urllib.request.Request(self.url("/api/view/" + enc))
        req.add_header("X-Token", server._Handler.token)
        body = urllib.request.urlopen(req, timeout=60).read()
        return json.loads(body.decode("utf-8"))

    def test_server_side_handles_absolute_path_with_spaces(self):
        """**副本的绝对路径**（带空格）⇒ 服务端能打开。

        ⚠️ 副本**不在存档根下** ⇒ `save_id` 必须用**绝对路径**
        （`open_save()` 接受绝对路径）。只读 GET，不写任何东西。
        """
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        tmp = Path(tempfile.mkdtemp(prefix="web enc "))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        src = None
        for info in list_saves():
            p = str(info.path)
            if "BACKUP" not in p and p.endswith(".usg"):
                src = p
                break
        if src is None:
            self.skipTest("本机没有存档")
        copy = str(tmp / "copy usg.usg")
        shutil.copyfile(src, copy)
        data = self._get_view(copy)
        self.assertIn("units", data)
        self.assertIn("_features", data)

    def test_server_side_handles_archived_save_id(self):
        """**归档存档**的 save_id（`Old Saves/…`，含空格）⇒ 能打开。

        这是用户实际点的那一类（63 个归档存档）⇒ **只读** GET。
        """
        from save_modifier_core import list_saves
        olds = [i.save_id for i in list_saves() if "Old Saves" in i.save_id]
        if not olds:
            self.skipTest("本机没有归档存档")
        sid = olds[0]
        self.assertIn(" ", sid, "这个用例要的就是含空格的 save_id")
        data = self._get_view(sid)
        self.assertIn("units", data)
        self.assertIn("_features", data)


if __name__ == "__main__":
    unittest.main()
