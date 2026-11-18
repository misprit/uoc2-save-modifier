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


if __name__ == "__main__":
    unittest.main()
