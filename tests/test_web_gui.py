# -*- coding: utf-8 -*-
"""U27：Web GUI 界面层（本地 HTTP 桥）—— 只读接口 + 安全边界。

**为什么有这些测试**：界面层是**唯一**能被本机其它进程/网页碰到的一层
（它开了个 HTTP 端口）⇒ 令牌校验与**目录穿越**必须有测试守着。
"""

import io
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


class TestNumericControls(unittest.TestCase):
    """U32：数值控件的交互规则 —— **按大小分两类 + 滚轮统一用 Alt 键**。

    用户四轮拍板：
    ① Ctrl+滚轮在 Edge 里会让窗口比例乱缩放 ⇒ 禁掉；
    ② 分数/声望直接允许输入；
    ③ 「滚动调整还要，你要换个键」⇒ 换 Alt；
    ④ 大数字可编辑，小数字（个位数）滚轮更方便。

    这些是**界面层**的规则，核心库不变 ⇒ 用「读前端源码」的方式锁死。
    """

    @classmethod
    def setUpClass(cls):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src", "save_modifier_web", "web", "index.html")
        cls.html = io.open(p, encoding="utf-8").read()

    def test_ctrl_wheel_zoom_is_blocked(self):
        """Ctrl+滚轮 = Edge 页面缩放 ⇒ 必须全局 preventDefault。"""
        self.assertIn("if(e.ctrlKey) e.preventDefault();", self.html)

    def test_wheel_requires_alt_key(self):
        """调值必须按住 Alt —— 普通滚轮不改值（防手滑）。"""
        self.assertIn("if(!ev.altKey) return;", self.html)
        self.assertIn("function altWheel(el, fn)", self.html)

    def test_big_numbers_are_editable_inputs(self):
        """大数字（声望/分数）= 可直接编辑的输入框。"""
        self.assertIn('class="num"', self.html)
        self.assertIn('inputmode="numeric"', self.html)
        self.assertIn("el.value = base;", self.html)

    def test_hint_text_mentions_alt_wheel(self):
        self.assertIn("Alt+滚轮 ±1", self.html)
        self.assertNotIn("回车或点别处生效", self.html)

    def test_no_bare_wheel_wording_left(self):
        """不允许残留「滚轮可调」这类已被覆盖的旧表述。"""
        self.assertNotIn("滚轮可调", self.html)
        self.assertNotIn("Ctrl+滚轮 ±", self.html)


class TestCatalogApi(WebGuiTestBase):
    """U33：游戏包目录 + 选择器候选 + 视图扩展。

    ⚠️ **中文名只能来自游戏包 locale** —— 这里断言「查得到中文」，
    不是断言「自己翻译对了」（规范 §5.7）。
    """

    def test_catalog_has_unit_spec_card_nationality(self):
        cat = self.get_json("/api/catalog")
        for k in ("unit_types", "spec_types", "card_types", "nationalities"):
            self.assertIn(k, cat)
            self.assertGreater(len(cat[k]), 0, k)

    def test_catalog_names_are_localized(self):
        """抽查：德军步兵 / 盟军步兵 / 一张卡 —— 中文名非空且不是内部 id。"""
        cat = self.get_json("/api/catalog")
        ut = cat["unit_types"]
        found = 0
        for name, info in ut.items():
            cn = info.get("cn") or ""
            self.assertTrue(cn, name)
            if cn != name:
                found += 1
        self.assertGreater(found, 0, "一个中文名都没翻出来？")

    def test_pickers_returns_candidates(self):
        """选择器：按单位类型给特种兵候选 + 战役池 + 商店可上架范围。"""
        import urllib.parse
        from save_modifier_core import list_saves

        sid = None
        for info in list_saves():
            if info.is_primary and info.campaign_id:
                sid = info.save_id
                break
        if sid is None:
            self.skipTest("本机没有战役存档")
        q = urllib.parse.quote(sid, safe="")
        pk = self.get_json("/api/pickers?save_id=" + q)
        self.assertIn("specialists_for_unit", pk)
        self.assertIn("campaign_pool", pk)
        self.assertIn("store_universe", pk)
        self.assertIn("cards", pk)
        # 商店范围用的是**单数键**（equipment / nationality / spec）
        for k in ("equipment", "nationality", "spec"):
            self.assertIn(k, pk["store_universe"])

    def test_view_has_theater_assets_and_names(self):
        """视图要带战区资产、战役位置、中文名。"""
        import urllib.parse
        from save_modifier_core import list_saves

        sid = None
        for info in list_saves():
            if info.is_primary:
                sid = info.save_id
                break
        if sid is None:
            self.skipTest("本机没有存档")
        v = self.get_json("/api/view/" + urllib.parse.quote(sid, safe=""))
        self.assertIn("theater_assets", v)
        self.assertIn("campaign_position", v)
        self.assertIn("card_whitelist", v)
        for u in (v.get("units") or [])[:5]:
            self.assertIn("name_cn", u)
        for h in (v.get("hqs") or [])[:5]:
            self.assertIn("name_cn", h)


class TestUnitWriteApi(WebGuiTestBase):
    """U34：单位页的写操作（改名 / 兵力 / 经验 / 特种兵挂卸）。"""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        self.tmp = Path(tempfile.mkdtemp(prefix="webunit_"))
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

    def _view(self):
        import urllib.parse
        return self.get_json("/api/view/" + urllib.parse.quote(self.copy))

    def test_unit_xp_edit_roundtrip(self):
        """改经验 → 提交 → 撤销 → 复原。"""
        v0 = self._view()
        units = v0.get("units") or []
        if not units:
            self.skipTest("这个存档没有单位")
        u = units[0]
        old = u.get("xp") or 0
        new = min(400, old + 11)

        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "unit_field",
                       "params": {"unit_id": u["id"], "field": "xp", "value": new}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))

        v1 = self._view()
        u1 = next(x for x in v1["units"] if x["id"] == u["id"])
        self.assertEqual(u1.get("xp"), new)

        un = self.post("/api/undo", {"save_id": self.copy})
        self.assertTrue(un["ok"], un.get("errors"))
        v2 = self._view()
        u2 = next(x for x in v2["units"] if x["id"] == u["id"])
        self.assertEqual(u2.get("xp"), old, "撤销后应复原")

    def test_unit_rename_is_accepted(self):
        """改名：写的是玩家起的明文（不是 locale 键）。"""
        v0 = self._view()
        units = v0.get("units") or []
        if not units:
            self.skipTest("这个存档没有单位")
        u = units[0]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "unit_field",
                       "params": {"unit_id": u["id"], "field": "name_brief",
                                  "value": "测试改名"}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        u1 = next(x for x in v1["units"] if x["id"] == u["id"])
        self.assertEqual(u1.get("name_brief"), "测试改名")

    def test_out_of_range_xp_is_rejected(self):
        """经验超范围（游戏 schema 是 0–400）⇒ 必须硬拦，不写盘。"""
        v0 = self._view()
        units = v0.get("units") or []
        if not units:
            self.skipTest("这个存档没有单位")
        u = units[0]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "unit_field",
                       "params": {"unit_id": u["id"], "field": "xp", "value": 9999}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])

    def test_unit_spec_add_and_remove(self):
        """挂一个特种兵 → 再卸掉。"""
        v0 = self._view()
        units = v0.get("units") or []
        target = None
        for u in units:
            if u.get("type") and not u.get("specs"):
                target = u
                break
        if target is None:
            self.skipTest("没有可挂特种兵的单位")
        # 从目录里挑一个该单位类型可挂的
        cat = self.get_json("/api/catalog")
        spec = None
        for name in cat["spec_types"]:
            st = cat["spec_types"][name]
            ut = cat["unit_types"].get(target["type"]) or {}
            if st.get("nationality") == ut.get("nationality"):
                spec = name
                break
        if spec is None:
            self.skipTest("目录里没有同国籍的特种兵")

        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "unit_spec_add",
                       "params": {"unit_id": target["id"], "spec_type": spec}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        u1 = next(x for x in v1["units"] if x["id"] == target["id"])
        self.assertTrue(any(s.get("type") == spec for s in (u1.get("specs") or [])))

        cm2 = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "unit_spec_remove",
                       "params": {"unit_id": target["id"], "spec_type": spec}}]})
        self.assertTrue(cm2["ok"], cm2.get("errors"))
        v2 = self._view()
        u2 = next(x for x in v2["units"] if x["id"] == target["id"])
        self.assertFalse(any(s.get("type") == spec for s in (u2.get("specs") or [])))


class TestHqWriteApi(WebGuiTestBase):
    """U35：总部的写操作。**只用副本**（绝不碰用户真存档）。"""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        self.tmp = Path(tempfile.mkdtemp(prefix="webhq_"))
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

    def _view(self):
        import urllib.parse
        return self.get_json("/api/view/" + urllib.parse.quote(self.copy))

    def _first_hq(self):
        v = self._view()
        hqs = v.get("hqs") or []
        if not hqs:
            self.skipTest("这个存档没有总部")
        return v, hqs[0]

    def test_hq_cp_and_supply_roundtrip(self):
        """CP / 补给 / 上限 都是硬范围 —— 改 → 撤销 → 复原。"""
        v, h = self._first_hq()
        old_cp = h.get("cp") or 0
        new_cp = (old_cp + 1) if old_cp < 9 else old_cp - 1
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_field",
                       "params": {"hq_id": h["id"], "field": "cp", "value": new_cp}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        h1 = next(x for x in v1["hqs"] if x["id"] == h["id"])
        self.assertEqual(h1.get("cp"), new_cp)
        un = self.post("/api/undo", {"save_id": self.copy})
        self.assertTrue(un["ok"], un.get("errors"))
        v2 = self._view()
        h2 = next(x for x in v2["hqs"] if x["id"] == h["id"])
        self.assertEqual(h2.get("cp"), old_cp)

    def test_hq_out_of_range_is_rejected(self):
        """CP 超上限 / 卡车超上限 / 补给超上限 ⇒ 必须硬拦（U25 的老规矩）。"""
        v, h = self._first_hq()
        for field, value in (("cp", 99), ("max_cp", 99), ("supply", 9),
                             ("trucks", 99)):
            cm = self.post("/api/commit", {
                "save_id": self.copy,
                "edits": [{"kind": "hq_field",
                           "params": {"hq_id": h["id"], "field": field,
                                      "value": value}}]})
            self.assertFalse(cm["ok"], "%s=%s 应该被拦" % (field, value))
            self.assertTrue(cm["errors"])

    def test_hq_trucks(self):
        """补给卡车 1–5（0 不行）。"""
        v, h = self._first_hq()
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_trucks",
                       "params": {"hq_id": h["id"], "trucks": 3}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        h1 = next(x for x in v1["hqs"] if x["id"] == h["id"])
        self.assertEqual(h1.get("trucks"), 3)
        bad = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_trucks",
                       "params": {"hq_id": h["id"], "trucks": 0}}]})
        self.assertFalse(bad["ok"])

    def test_hq_branch_level(self):
        """分支等级 0–3；等级 + 压制 ≤ 3。"""
        v, h = self._first_hq()
        bl = h.get("branch_levels") or {}
        if not bl:
            self.skipTest("这个存档没有 branch_levels")
        br = sorted(bl)[0]
        cur = (bl[br] or {}).get("level") or 0
        new = 3 if cur != 3 else 2
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_branch_level",
                       "params": {"hq_id": h["id"], "branch": br, "level": new}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        h1 = next(x for x in v1["hqs"] if x["id"] == h["id"])
        self.assertEqual((h1["branch_levels"][br] or {}).get("level"), new)
        bad = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_branch_level",
                       "params": {"hq_id": h["id"], "branch": br, "level": 9}}]})
        self.assertFalse(bad["ok"])

    def test_hq_force_pool_quantity_and_add(self):
        """兵库：改数量 / 加一条（国籍自动跟着特种兵类型走）。"""
        v, h = self._first_hq()
        pool = h.get("force_pool") or []
        if pool:
            cm = self.post("/api/commit", {
                "save_id": self.copy,
                "edits": [{"kind": "hq_force_pool",
                           "params": {"hq_id": h["id"], "index": 0,
                                      "quantity": (pool[0].get("quantity") or 0) + 2}}]})
            self.assertTrue(cm["ok"], cm.get("errors"))
            v1 = self._view()
            h1 = next(x for x in v1["hqs"] if x["id"] == h["id"])
            self.assertEqual((h1["force_pool"][0] or {}).get("quantity"),
                             (pool[0].get("quantity") or 0) + 2)
        # 加一条：挑一个目录里有的特种兵
        cat = self.get_json("/api/catalog")
        spec = sorted(cat["spec_types"])[0]
        nat = (cat["spec_types"][spec] or {}).get("nationality") or ""
        cm2 = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_force_pool_add",
                       "params": {"hq_id": h["id"],
                                  "entry": {"spec": spec, "nationality": nat,
                                            "quantity": 1, "delay": 0}}}]})
        self.assertTrue(cm2["ok"], cm2.get("errors"))
        v2 = self._view()
        h2 = next(x for x in v2["hqs"] if x["id"] == h["id"])
        self.assertTrue(any(e.get("spec") == spec for e in (h2.get("force_pool") or [])))

    def test_hq_view_has_skills_generals(self):
        """视图要带技能 / 将领 / 装备的中文名（U35）。"""
        v, h = self._first_hq()
        self.assertIn("skills", v)
        self.assertIn("generals", v)
        self.assertIn("equipment_cn", v)
        for a, cn in (v.get("skills") or {}).items():
            self.assertTrue(cn, a)


def _quote(path):
    import urllib.parse
    return urllib.parse.quote(path, safe="")


class TestCardStoreWriteApi(WebGuiTestBase):
    """U36：卡牌页的写操作（手牌 / 货架）。**只用副本**。"""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        self.tmp = Path(tempfile.mkdtemp(prefix="webcard_"))
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

    def _view(self):
        import urllib.parse
        return self.get_json("/api/view/" + urllib.parse.quote(self.copy))

    def test_catalog_has_card_images(self):
        """卡牌贴图要能解析出**真实存在**的相对路径（U36）。"""
        cat = self.get_json("/api/catalog")
        n = 0
        for name, info in (cat.get("card_types") or {}).items():
            rel = info.get("image_resolved") or ""
            self.assertTrue(rel, name)
            self.assertTrue(rel.endswith(".png"), name)
            n += 1
        self.assertGreater(n, 0)

    def test_card_add_and_remove(self):
        """加一张到手牌 → 再移除。"""
        cat = self.get_json("/api/catalog")
        wl = self.get_json("/api/pickers?save_id=" + _quote(self.copy))
        allowed = wl.get("cards", {}).get("allowed") or []
        if not allowed:
            self.skipTest("这个存档没有可上架的卡")
        ct = allowed[0]
        v0 = self._view()
        hand = v0.get("hand") or []
        used = {c.get("position") for c in hand}
        limit = v0.get("hand_limit") or 5
        pos = next((p for p in range(1, limit + 1) if p not in used), None)
        if pos is None:
            self.skipTest("手牌满了")
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "card_add",
                       "params": {"card_type": ct, "position": pos}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        h1 = v1.get("hand") or []
        self.assertTrue(any(c.get("card_type") == ct for c in h1))

        cm2 = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "card_remove", "params": {"position": pos}}]})
        self.assertTrue(cm2["ok"], cm2.get("errors"))
        v2 = self._view()
        h2 = v2.get("hand") or []
        self.assertFalse(any(c.get("position") == pos for c in h2))

    def test_card_add_out_of_range_position_is_rejected(self):
        """槽位超上限 ⇒ 必须拦（写了游戏也读不到，U25）。"""
        v = self._view()
        wl = self.get_json("/api/pickers?save_id=" + _quote(self.copy))
        allowed = wl.get("cards", {}).get("allowed") or []
        if not allowed:
            self.skipTest("这个存档没有可上架的卡")
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "card_add",
                       "params": {"card_type": allowed[0], "position": 99}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])

    def test_card_not_in_whitelist_is_rejected(self):
        """不在白名单里的卡 ⇒ 不许上架。"""
        cat = self.get_json("/api/catalog")
        wl = self.get_json("/api/pickers?save_id=" + _quote(self.copy))
        allowed = set(wl.get("cards", {}).get("allowed") or [])
        blocked = [k for k in (cat.get("card_types") or {}) if k not in allowed]
        if not blocked:
            self.skipTest("没有被屏蔽的卡")
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "card_add",
                       "params": {"card_type": blocked[0], "position": 1}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])


class TestStoreWriteApi(WebGuiTestBase):
    """U37：商店页的写操作（价格 / 库存 / 下架）。**只用副本**。"""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        self.tmp = Path(tempfile.mkdtemp(prefix="webstore_"))
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

    def _view(self):
        import urllib.parse
        return self.get_json("/api/view/" + urllib.parse.quote(self.copy))

    def test_store_price_and_quantity(self):
        v = self._view()
        store = v.get("store") or []
        if not store:
            self.skipTest("这个存档没有商店")
        e = store[0]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "store_set",
                       "params": {"front": e["front"], "sub": e["sub"], "index": 0,
                                  "field": "price", "value": 7}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        s1 = v1.get("store") or []
        hit = [x for x in s1 if x["front"] == e["front"] and x["sub"] == e["sub"]]
        self.assertEqual(hit[0].get("price"), 7)

    def test_store_quantity_zero_is_rejected(self):
        """库存 0 = 「售罄」，游戏没有这个标记 ⇒ 必须拦（下架要删条目）。"""
        v = self._view()
        store = v.get("store") or []
        if not store:
            self.skipTest("这个存档没有商店")
        e = store[0]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "store_set",
                       "params": {"front": e["front"], "sub": e["sub"], "index": 0,
                                  "field": "quantity", "value": 0}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])

    def test_store_negative_price_is_rejected(self):
        v = self._view()
        store = v.get("store") or []
        if not store:
            self.skipTest("这个存档没有商店")
        e = store[0]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "store_set",
                       "params": {"front": e["front"], "sub": e["sub"], "index": 0,
                                  "field": "price", "value": -1}}]})
        self.assertFalse(cm["ok"])

    def test_store_duplicate_is_rejected(self):
        """同一个商店里重复条目 ⇒ 硬拦（U23 用户口径）。"""
        v = self._view()
        store = v.get("store") or []
        if not store:
            self.skipTest("这个存档没有商店")
        e = store[0]
        entry = {"spec": e.get("spec"), "equipment": e.get("equipment"),
                 "nationality": e.get("nationality"),
                 "price": 99, "quantity": 1}
        entry = {k: v2 for k, v2 in entry.items() if v2 is not None}
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "store_add",
                       "params": {"front": e["front"], "sub": e["sub"], "entry": entry}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])


class TestTheaterWriteApi(WebGuiTestBase):
    """U38：战区资产（唯一的 L3 写入例外）。**只用副本**。"""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves, open_save

        self.tmp = Path(tempfile.mkdtemp(prefix="webtheater_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        src = None
        for info in list_saves():
            if not info.is_primary:
                continue
            try:
                with open_save(info.save_id) as s:
                    bm = s.battle_main()
                    if isinstance(bm, dict) and bm.get("theater_assets"):
                        src = str(info.path)
                        break
            except Exception:
                continue
        if src is None:
            self.skipTest("本机没有正在战斗的存档")
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

    def _view(self):
        import urllib.parse
        return self.get_json("/api/view/" + urllib.parse.quote(self.copy))

    def test_theater_assets_present_with_names(self):
        v = self._view()
        ta = v.get("theater_assets") or []
        self.assertTrue(ta)
        cn = v.get("theater_cn") or {}
        for a in ta:
            self.assertIn(a["asset"], cn)
            self.assertTrue(cn[a["asset"]])

    def test_theater_to_use_edit(self):
        """改「当前可用」→ 提交 → 撤销 → 复原。"""
        v = self._view()
        a = (v.get("theater_assets") or [])[0]
        new = (a.get("to_use") or 0) + 1
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "theater_asset",
                       "params": {"asset": a["asset"], "to_use": new,
                                  "uses_total": a.get("uses_total"),
                                  "uses_turn": a.get("uses_turn")}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        a1 = [x for x in v1["theater_assets"] if x["asset"] == a["asset"]][0]
        self.assertEqual(a1.get("to_use"), new)
        un = self.post("/api/undo", {"save_id": self.copy})
        self.assertTrue(un["ok"], un.get("errors"))
        v2 = self._view()
        a2 = [x for x in v2["theater_assets"] if x["asset"] == a["asset"]][0]
        self.assertEqual(a2.get("to_use"), a.get("to_use"))

    def test_theater_invariant_is_enforced(self):
        """当前可用 > 本场景剩余 ⇒ 必须拦（游戏每用一次就让剩余减 1）。"""
        v = self._view()
        for a in (v.get("theater_assets") or []):
            tot = a.get("uses_total")
            if isinstance(tot, int):
                cm = self.post("/api/commit", {
                    "save_id": self.copy,
                    "edits": [{"kind": "theater_asset",
                               "params": {"asset": a["asset"], "to_use": tot + 5,
                                          "uses_total": tot,
                                          "uses_turn": a.get("uses_turn")}}]})
                self.assertFalse(cm["ok"])
                self.assertTrue(cm["errors"])
                return
        self.skipTest("没有有限的 uses_total")

    def test_theater_uses_turn_zero_is_rejected(self):
        """每回合恢复 ≥ 1（游戏 schema 是 Range(min=1)）。"""
        v = self._view()
        a = (v.get("theater_assets") or [])[0]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "theater_asset",
                       "params": {"asset": a["asset"], "to_use": a.get("to_use"),
                                  "uses_total": a.get("uses_total"),
                                  "uses_turn": 0}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])

    # ------------------------------------------------ U45：全量候选

    def test_view_has_theater_universe(self):
        """视图要带**全量候选**（游戏那 7 种）与本次战斗的上下文。"""
        v = self._view()
        uni = v.get("theater_universe") or []
        self.assertEqual(len(uni), 7)
        for u in uni:
            for k in ("asset", "has_texture", "in_current", "in_other",
                      "scenario", "added"):
                self.assertIn(k, u)
        meta = v.get("theater_meta") or {}
        for k in ("editable", "reason", "phase", "phase_count", "groups"):
            self.assertIn(k, meta)

    def test_universe_assets_all_have_chinese_names(self):
        """7 种候选**都要有中文名**（locale `id_<asset>_view`）。"""
        v = self._view()
        cn = v.get("theater_cn") or {}
        for u in (v.get("theater_universe") or []):
            self.assertIn(u["asset"], cn)
            self.assertTrue(cn[u["asset"]])

    def test_add_asset_through_api(self):
        """API 加一项 ⇒ 存档里多一项，且 5 个字段写全。"""
        v = self._view()
        have = {a["asset"] for a in (v.get("theater_assets") or [])}
        from save_modifier_core.catalog import THEATER_ASSET_TYPES
        missing = [a for a in THEATER_ASSET_TYPES if a not in have]
        if not missing:
            self.skipTest("这场战斗已经有全部 7 种")
        target = missing[0]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "theater_asset_add",
                       "params": {"asset": target, "uses_total": 2,
                                  "uses_turn": 1}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        it = [x for x in v1["theater_assets"] if x["asset"] == target]
        self.assertTrue(it, "新加的资产没出现在视图里")
        self.assertEqual(it[0]["uses_total"], 2)

    def test_remove_asset_through_api(self):
        """API 删一项 ⇒ 存档里那一项整个没了。"""
        v = self._view()
        ta = v.get("theater_assets") or []
        if not ta:
            self.skipTest("这场战斗没有战区资产")
        target = ta[0]["asset"]
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "theater_asset_remove",
                       "params": {"asset": target}}]})
        self.assertTrue(cm["ok"], cm.get("errors"))
        v1 = self._view()
        self.assertNotIn(target, {a["asset"] for a in (v1.get("theater_assets") or [])})

    def test_add_out_of_seven_is_rejected(self):
        """`sabotage` 是卡牌的一次性能力 ⇒ API 也必须拒。"""
        cm = self.post("/api/commit", {
            "save_id": self.copy,
            "edits": [{"kind": "theater_asset_add",
                       "params": {"asset": "sabotage", "uses_total": 1,
                                  "uses_turn": 1}}]})
        self.assertFalse(cm["ok"])
        self.assertTrue(cm["errors"])


class TestWriteConfirmGate(WebGuiTestBase):
    """U40：写盘前的闸门 —— `/api/plan` 要能报出「改哪些文件 + 备份叫什么」。

    ⚠️ **plan 不碰磁盘**（规范 §6.3）—— 确认框就是靠它来预览的。
    """

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        self.tmp = Path(tempfile.mkdtemp(prefix="webplan_"))
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
        self.before = os.path.getmtime(self.copy)

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

    def test_plan_reports_files_backup_and_touches_nothing(self):
        """plan 要报：改动条目、备份文件名、存档名 —— 且**不碰磁盘**。"""
        r = self.post("/api/plan", {
            "save_id": self.copy,
            "edits": [{"kind": "progress",
                       "params": {"field": "prestige", "value": 12345}}]})
        self.assertTrue(r["ok"], r.get("errors"))
        self.assertTrue(r["changes"])
        self.assertIn("main.yml", [c["entry"] for c in r["changes"]])
        self.assertTrue(r.get("backup"), "没报备份文件名")
        self.assertTrue(r.get("save_name"), "没报存档名")
        # **plan 不碰磁盘**
        self.assertEqual(os.path.getmtime(self.copy), self.before)

    def test_plan_reports_errors_without_writing(self):
        """越界 ⇒ plan.ok False + errors（确认框的硬错误分支）。"""
        r = self.post("/api/plan", {
            "save_id": self.copy,
            "edits": [{"kind": "hq_field",
                       "params": {"hq_id": 1, "field": "cp", "value": 99}}]})
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"])
        self.assertEqual(os.path.getmtime(self.copy), self.before)


class TestFrontendGateExists(unittest.TestCase):
    """U40：前端**必须**先 plan 再写盘（闸门不能被绕过）。"""

    @classmethod
    def setUpClass(cls):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src", "save_modifier_web", "web", "index.html")
        cls.html = io.open(p, encoding="utf-8").read()

    def test_apply_goes_through_plan(self):
        self.assertIn("/api/plan", self.html)
        self.assertIn("openConfirm(", self.html)

    def test_three_confirm_variants_exist(self):
        """确认 / 硬错误 / 软警告 三个变体。"""
        self.assertIn('openConfirm("error"', self.html)
        self.assertIn('openConfirm("warn"', self.html)
        self.assertIn('openConfirm("ok"', self.html)

    def test_error_variant_disables_the_button(self):
        """硬错误 ⇒ 应用按钮禁用（原存档不会被写入）。"""
        self.assertIn("disabled>应用更改", self.html)

    def test_three_operation_modals_exist(self):
        """设计稿 §9②③④：加兵库条目 / 换牌 / 上架新商品。"""
        for fn in ("openHqPoolModal", "openCardPickerModal", "openStoreAddModal"):
            self.assertIn("function " + fn, self.html)


class TestCampaignDetailApi(WebGuiTestBase):
    """U41：战役页的三块（路线图 / 场景名册 / 会议商店）。"""

    def _save_id(self):
        from save_modifier_core import list_saves
        for info in list_saves():
            if info.is_primary and info.campaign_id:
                return info.save_id
        self.skipTest("本机没有战役存档")

    def test_campaign_detail_has_route_roster_store(self):
        sid = self._save_id()
        d = self.get_json("/api/campaign-detail?save_id=" + _quote(sid))
        self.assertNotIn("error", d, d.get("error"))
        self.assertTrue(d.get("route"), "没有路线图")
        for c in d["route"]:
            self.assertIn("id", c)
            self.assertIn("text", c)
            self.assertIn("done", c)
            self.assertIn("now", c)
        # 当前会议至多一个是 now
        self.assertLessEqual(len([c for c in d["route"] if c["now"]]), 1)

    def test_campaign_detail_route_marks_current_conference(self):
        """路线图里要有一个 now（= 存档所在的会议）。"""
        sid = self._save_id()
        d = self.get_json("/api/campaign-detail?save_id=" + _quote(sid))
        now = [c for c in d["route"] if c["now"]]
        if not now:
            self.skipTest("这个存档的会议不在索引里")
        self.assertTrue(now[0]["scenes"] or now[0]["id"])

    def test_undo_stack_endpoint(self):
        """撤销栈 + 备份列表。"""
        from save_modifier_core import list_saves
        sid = None
        for info in list_saves():
            if info.is_primary:
                sid = info.save_id
                break
        if sid is None:
            self.skipTest("本机没有存档")
        d = self.get_json("/api/undo-stack?save_id=" + _quote(sid))
        self.assertIn("stack", d)
        self.assertIn("backups", d)
        self.assertIsInstance(d["stack"], list)
        self.assertIsInstance(d["backups"], list)


class TestUiDetailsPresent(unittest.TestCase):
    """U43：界面细节必须在（前端源码存在性检查）。

    ⚠️ 这些是**表现层**的东西，Python 测不了行为 ⇒ 只锁「有没有」。
    """

    @classmethod
    def setUpClass(cls):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src", "save_modifier_web", "web", "index.html")
        cls.html = io.open(p, encoding="utf-8").read()

    def test_hover_tip_exists(self):
        """悬停浮层（设计稿 §1 的 .tip）。"""
        self.assertIn("function initTip()", self.html)
        self.assertIn("data-tip=", self.html)
        self.assertIn(".tip{", self.html)

    def test_full_pool_view_exists(self):
        """备选池「显示全部」+ 国籍分组 + 折叠。"""
        self.assertIn("function fullPoolHTML(", self.html)
        self.assertIn("grphead", self.html)
        self.assertIn("togglePoolGroup", self.html)

    def test_hq_tabs_exist(self):
        """总部的「升级矩阵 / 兵库」页签。"""
        self.assertIn("function pickHqTab(", self.html)
        self.assertIn("hqtabs", self.html)

    def test_splash_warning_exists(self):
        """启动页的「改存档前请先退出游戏」警示 + 历史存档分隔带。"""
        self.assertIn("改存档前请先退出游戏", self.html)
        self.assertIn("histband", self.html)

    def test_theater_linked_warnings_exist(self):
        """战区资产的两条联动警告（设计稿 §7）。"""
        self.assertIn("每回合恢复", self.html)
        self.assertIn("回合开始后的有效值", self.html)

    # ------------------------------------------------ U45：全量候选

    def test_theater_universe_is_rendered(self):
        """U45：战区资产页列**全量候选**，并区分「有/没有」。"""
        self.assertIn("theater_universe", self.html)
        self.assertIn("theater_meta", self.html)
        self.assertIn("添加这一项", self.html)
        self.assertIn("删除这一项", self.html)
        self.assertIn("场景自带", self.html)
        self.assertIn("场景没有", self.html)

    def test_theater_add_remove_edits_exist(self):
        """前端要能发出 `theater_asset_add` / `theater_asset_remove`。"""
        self.assertIn("theater_asset_add", self.html)
        self.assertIn("theater_asset_remove", self.html)
        self.assertIn("openTheaterAddModal", self.html)
        self.assertIn("theaterRemove", self.html)

    def test_theater_page_is_not_gated_on_having_assets(self):
        """⚠️ 守卫用「在不在战斗中」，不是「当前 phase 有没有资产」——
        战斗里一个资产都没有时也要能进去**添加**。"""
        self.assertIn("theaterEditable", self.html)
        self.assertNotIn("if(!(VIEW.theater_assets||[]).length){", self.html)


# =====================================================================
# U46：特种兵图标放大 + 名册冗余数字删除 + 详情卡图标去方框底
# =====================================================================


class TestSpecialistIconScale(unittest.TestCase):
    """**纯界面层**的规则 ⇒ 用「读前端源码」的方式锁死（app + 视觉稿一起查）。

    依据：游戏贴图 `specialist/<类型>/hq_action_icon.png` 是 **160×160 画布**，
    而图形只占 **60×69**（实测 378/378 个完全一致 ⇒ 只占边长的 40%）
    ⇒ 直接塞进方框里，图标只有方框的 40%，看着像一个小色块。
    办法：img 放大 **200%**，让方框裁掉透明边 ⇒ 图标占框 ~78%。
    """

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()
        cls.vis = io.open(os.path.join(root, "docs", "GUI视觉稿.html"),
                          encoding="utf-8").read()

    @staticmethod
    def _rule(css, selector):
        """取一条 CSS 规则的完整文本（含大括号）。"""
        i = css.find(selector + "{")
        if i < 0:
            return ""
        j = css.find("}", i)
        return css[i:j + 1]

    def test_specialist_icon_is_scaled_200_percent(self):
        """特种兵图标放大 200%（`.ubadge` / `.pcell` / `.slot .sq` 三个容器）。"""
        for css, tag in ((self.html, "app"), (self.vis, "视觉稿")):
            self.assertIn(".ubadge img,.pcell img,.slot .sq img{", css, tag)
            rule = self._rule(css, ".ubadge img,.pcell img,.slot .sq img")
            self.assertIn("width:200%", rule, tag)
            self.assertIn("height:200%", rule, tag)

    def test_specialist_imgs_carry_the_scale_class(self):
        """特种兵图标要带 `.spico`（混装图标的表格里只有特种兵能放大）。"""
        for css, tag in ((self.html, "app"), (self.vis, "视觉稿")):
            self.assertIn("spico", css, tag)
        # app：名册兵牌 / 详情卡已挂 / 备选池 三处都要带
        self.assertIn('imgTag(specTex(s.type), specCn(s.type), "spico")', self.html)
        self.assertIn('imgTag(specTex(t), specCn(t), "spico")', self.html)

    def test_detail_card_icon_has_no_box(self):
        """详情卡里**已挂特种兵**的图标不再套方框底（卡片本身就是一体）。"""
        for css, tag in ((self.html, "app"), (self.vis, "视觉稿")):
            rule = self._rule(css, ".slot .sq")
            self.assertTrue(rule, tag)
            self.assertNotIn("background:var(--stage)", rule, tag)
            self.assertNotIn("var(--stage-edge)", rule, tag)

    def test_roster_has_no_specialist_count(self):
        """名册右侧**不再显示「已挂 N 个」**（看一眼就知道，写数字是冗余的）。"""
        self.assertNotIn("ucount", self.html)
        self.assertNotIn("ucount", self.vis)
        self.assertNotIn("${cnt}", self.vis)
        self.assertNotIn("${badges}${cnt}", self.vis)

    def test_mixed_tables_only_scale_specialists(self):
        """兵种图标（`steps/step.png`，不是正方形）**不能**套 200% 规则。"""
        for css, tag in ((self.html, "app"), (self.vis, "视觉稿")):
            rule = self._rule(css, "table.spec-tbl .thumb img")
            self.assertIn("max-width:100%", rule, tag)
            self.assertIn("img.spico", css, tag)
