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
        if not data["saves"]:
            # ⚠️ 这台机器上没有存档（外部测试者可能没玩过游戏）⇒ 跳过，
            # **不能失败**（接口结构本身已经验过了）。
            self.skipTest("这台机器上没有存档 ⇒ 无法验列表行的字段")
        row = data["saves"][0]
        for k in ("save_id", "name", "kind", "mtime", "size"):
            self.assertIn(k, row)

    def test_view_endpoint_returns_units_and_features(self):
        data = self.get_json("/api/saves")
        if not data["saves"]:
            self.skipTest("这台机器上没有存档 ⇒ 无法验 /api/view")
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

    def test_wheel_works_without_alt_key(self):
        """U54：**滚轮默认生效**，不再需要 Alt（用户实测「alt+滚轮简直反人类」）。

        ⚠️ 全局**唯一**保留 Alt 的是**血量条**（普通滚轮 = 调活跃、Alt+滚轮 = 调压制）。
        """
        self.assertIn("function wheelBind(el, fn)", self.html)
        self.assertNotIn("function altWheel(el, fn)", self.html)
        self.assertNotIn("if(!ev.altKey) return;", self.html)
        self.assertIn("if(ev.altKey){", self.html)

    def test_big_numbers_are_editable_inputs(self):
        """大数字（声望/分数）= 可直接编辑的输入框。"""
        self.assertIn('class="num"', self.html)
        self.assertIn('inputmode="numeric"', self.html)
        self.assertIn("el.value = base;", self.html)

    def test_hint_text_mentions_alt_wheel(self):
        self.assertIn("滚轮 ±1", self.html)
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


def _save_has_hand_cards(path):
    """存档里有没有**手牌数据**（顶层 `cards.yml`）。

    ⚠️ **新开的战役存档没有手牌**（还没打过一局）⇒ 挑"第一个存档"会挑到
    这种 ⇒ 写测试就会误报「没有手牌数据」。（用户 2026-11-20 新建的
    `west.usg` 就是这种 —— 它排在存档列表最前面。）
    """
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            return "cards.yml" in z.namelist()
    except Exception:
        return False


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
            if "BACKUP" in p or not p.endswith(".usg"):
                continue
            # ⚠️ **必须挑有手牌数据的存档**（新开的战役还没有 cards.yml）
            if not _save_has_hand_cards(p):
                continue
            src = p
            break
        if src is None:
            self.skipTest("本机没有带手牌数据的存档")
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
    """**纯界面层**的规则 ⇒ 用「读前端源码」的方式锁死（**只查 app**）。

    ⚠️ **2026-11-19 起**：GUI 视觉稿已冻结，**不再与实现比对**（§5.1kk）⇒
    这里原本「app + 视觉稿一起查」的断言改成**只查 app**。

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
        self.assertIn(".ubadge img,.pcell img,.slot .sq img{", self.html)
        rule = self._rule(self.html, ".ubadge img,.pcell img,.slot .sq img")
        self.assertIn("width:200%", rule)
        self.assertIn("height:200%", rule)

    def test_specialist_imgs_carry_the_scale_class(self):
        """特种兵图标要带 `.spico`（混装图标的表格里只有特种兵能放大）。"""
        self.assertIn("spico", self.html)
        # app：名册兵牌 / 详情卡已挂 / 备选池 三处都要带
        self.assertIn('imgTag(specTex(s.type), specCn(s.type), "spico")', self.html)
        self.assertIn('imgTag(specTex(t), specCn(t), "spico")', self.html)

    def test_detail_card_icon_has_no_box(self):
        """详情卡里**已挂特种兵**的图标不再套方框底（卡片本身就是一体）。"""
        rule = self._rule(self.html, ".slot .sq")
        self.assertTrue(rule)
        self.assertNotIn("background:var(--stage)", rule)
        self.assertNotIn("var(--stage-edge)", rule)

    def test_roster_has_no_specialist_count(self):
        """名册右侧**不再显示「已挂 N 个」**（看一眼就知道，写数字是冗余的）。"""
        self.assertNotIn("ucount", self.html)

    def test_mixed_tables_only_scale_specialists(self):
        """兵种图标（`steps/step.png`，不是正方形）**不能**套 200% 规则。"""
        rule = self._rule(self.html, "table.spec-tbl .thumb img")
        self.assertIn("max-width:100%", rule)
        self.assertIn("img.spico", self.html)


# =====================================================================
# U47：对话框形态 / 中文名 / 空态 / 目录加载态
# =====================================================================


class TestUiDialogsAndNames(unittest.TestCase):
    """U47 的界面规则 —— 用「读前端源码」的方式锁死。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()
        cls.srv = io.open(os.path.join(root, "src", "save_modifier_web",
                                       "server.py"), encoding="utf-8").read()

    def test_three_pickers_have_a_search_box(self):
        """三个操作模态框（兵库加条目 / 商店上架 / 卡牌换牌）都要有搜索框。"""
        self.assertEqual(self.html.count('id="spick_q"'), 3)
        self.assertIn("function bindSpickSearch(", self.html)
        self.assertIn("function spickMatch(", self.html)

    def test_picker_search_filters_by_chinese_flag(self):
        """搜索要能按**中文特性**匹配（`recon` → 侦察）。"""
        self.assertIn("(it.flags||[]).map(flagCn).join", self.html)

    def test_specialist_flags_use_chinese_names(self):
        """特种兵特性标签走 locale（`id_sheet_spec_flag_<flag>`）。"""
        self.assertIn("function flagCn(", self.html)
        self.assertIn("id_sheet_spec_flag_", self.srv)
        self.assertIn('"spec_flags": spec_flags', self.srv)

    def test_front_names_are_chinese(self):
        """战线要显示中文名，不是 id。"""
        self.assertIn('data["front_names"]', self.srv)
        self.assertIn('"front_names": front_names', self.srv)
        self.assertIn("front_names", self.html)

    def test_catalog_loading_state(self):
        """目录到位前不渲染半成品（否则先闪一遍 type id + 空图标）。"""
        self.assertIn("const NEEDS_CATALOG", self.html)
        self.assertIn("正在加载游戏目录", self.html)


# =====================================================================
# U55：待应用明细改到「应用更改」弹窗 + 主体锁定
# =====================================================================


class TestU55PendingModalAndLayoutLock(unittest.TestCase):
    """U55 —— 底栏删掉（不再跳变 / 不再挤变形），明细改到弹窗里。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_bottom_drawer_is_gone(self):
        """底部那个会跳变的待应用抽屉**删掉了**。"""
        self.assertNotIn('id="drawer"', self.html)
        self.assertNotIn('id="pendList"', self.html)
        self.assertNotIn('id="pendCount"', self.html)
        self.assertNotIn(".drawer", self.html)

    def test_pending_detail_lives_in_the_confirm_modal(self):
        """待应用**明细**在「应用更改」的确认弹窗里逐条列出。"""
        self.assertIn("待应用明细（", self.html)
        self.assertIn("dropPendingFromModal(", self.html)
        self.assertIn('class="plist"', self.html)

    def test_body_is_layout_locked(self):
        """主体锁定：`.body` 高度恒定（内部各自滚动）。"""
        self.assertIn(".body{flex:1;display:flex;min-height:0;overflow:hidden}", self.html)
        self.assertIn(".status{display:flex", self.html)
        self.assertIn("flex:none;white-space:nowrap;overflow:hidden", self.html)

    def test_apply_result_shown_in_modal(self):
        """写入结果 / 失败原因改成弹窗（原来写在抽屉里的 errBox / warnBox）。"""
        self.assertNotIn('getElementById("errBox")', self.html)
        self.assertNotIn('getElementById("warnBox")', self.html)
        self.assertNotIn('id="errBox"', self.html)
        self.assertNotIn('id="warnBox"', self.html)
        self.assertIn("✓ 已应用", self.html)
        self.assertIn("✕ 应用失败", self.html)


# =====================================================================
# U54：血量条单一入口 / 全局移除 Alt+滚轮 / 活跃+压制 >= 1
# =====================================================================


class TestU54BloodBarAndWheel(unittest.TestCase):
    """U54 —— 数字区删掉；滚轮默认生效（血量条除外）；活跃+压制 >= 1。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_no_alt_wheel_outside_the_blood_bar(self):
        """**除血量条外**没有 Alt 依赖了。"""
        self.assertNotIn("altWheel(", self.html)
        self.assertNotIn("function altWheel", self.html)
        self.assertEqual(self.html.count("if(ev.altKey){"), 1)

    def test_prestige_and_score_have_no_wheel(self):
        """概览的声望 / 分数**只允许直接输入**（不再有滚轮）。"""
        self.assertIn("战役进度（可直接输入）", self.html)
        self.assertNotIn("可直接输入 · 滚轮", self.html)

    def test_blood_bar_keeps_total_at_least_one(self):
        """**活跃 + 压制 >= 1**（避免游戏内 bug）。"""
        self.assertIn("if(a+s<1) a = Math.max(0, 1-s);", self.html)

    def test_blood_bar_shows_the_unit_type_max(self):
        """上限按**单位类型**取（不是常数 7）—— 来自 `Catalog.max_st(type)`。"""
        self.assertIn("const max = u.max_st || ut.max_st || 0;", self.html)

    def test_active_wheel_drops_suppressed_when_over_max(self):
        """普通滚轮把活跃推过上限时，**消减压制**补上。"""
        self.assertIn("const over = a+s-max;", self.html)
        self.assertIn("if(over>0) s = Math.max(0, s-over);", self.html)


# =====================================================================
# U53：单位页工具条横跨整页 + 「仅当前场景激活」筛选 + 列表列加宽
# =====================================================================


class TestU53ToolbarAndBattleFilter(unittest.TestCase):
    """U53 —— 筛选栏回到同一行 + 补上「当前场景激活单位」筛选 + 列表宽度回复。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()
        cls.srv = io.open(os.path.join(root, "src", "save_modifier_web",
                                      "server.py"), encoding="utf-8").read()
        cls.core = io.open(os.path.join(root, "src", "save_modifier_core",
                                       "container.py"), encoding="utf-8").read()

    @staticmethod
    def _rule(css, selector):
        import re
        want = ",".join(x.strip() for x in selector.split(","))
        for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
            sel = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
            got = ",".join(x.strip() for x in sel.split(","))
            if got == want:
                return m.group(0)
        return ""

    def test_toolbar_spans_the_whole_page(self):
        """工具条**横跨整页**（放在两栏之上）⇒ 搜索 + 总部 + 激活筛选**一行**。"""
        self.assertIn('class="toolbar toolbar-top"', self.html)
        self.assertIn('class="cols cols-units cols-fill"', self.html)

    def test_battle_only_filter_exists(self):
        """「仅当前场景激活」筛选；**不在战斗里置灰**（按能力位 in_battle）。"""
        self.assertIn('id="ubattle"', self.html)
        self.assertIn("仅当前场景激活", self.html)
        self.assertIn("UONLY", self.html)
        self.assertIn("VIEW.battle_unit_ids", self.html)
        self.assertIn("VIEW.in_battle", self.html)
        # U74：整段模板被包成 L2() ⇒ 表达式本身还在，只是没有 ${} 了
        self.assertIn('inBattle?"":"disabled"', self.html)

    def test_units_columns_are_wider_without_the_gap(self):
        """列表列加宽（0.6fr → 0.64fr）。

        ⚠️ **U58 改了栏间隔**：U53 当初是 `gap:0`（为了「列表别被挤」），
        U58 按用户口径「栏间隔 = 面板到边缘的间隔」改回 14px ——
        面板 margin 归零后列表反而比原来还宽一点，视觉也统一了。"""
        rule = self._rule(self.html, ".cols-units")
        self.assertIn("0.64fr", rule)
        self.assertIn("gap:14px", rule)
        self.assertIn("margin:14px", rule)

    def test_data_tip_quotes_are_escaped(self):
        """`data-tip` 的值里**不能直接带双引号**（`class="tn"` 会把属性提前闭合
        ⇒ 提示文字被当成正文渲染出来，U53 实测踩到）。"""
        self.assertIn('.replace(/"/g, "&quot;")', self.html)

    def test_server_exposes_battle_unit_ids(self):
        """服务端把战斗名单与 in_battle 一起给前端。"""
        self.assertIn('data["battle_unit_ids"]', self.srv)
        self.assertIn('data["in_battle"]', self.srv)
        self.assertIn("def battle_unit_ids(", self.core)


# =====================================================================
# U52：字号整体放大 + 滚轮区显著放大 + 注释小字保持原样
# =====================================================================


class TestU52TypographyScale(unittest.TestCase):
    """U52 —— 界面整体放大，但「注释用的小字」保持原样。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    @staticmethod
    def _rule(css, selector):
        """按「**选择器列表完全相等**」取一条 CSS 规则（含大括号）。

        ⚠️ 不能用 `css.find(sel + "{")` —— 组合规则会抢先命中
        （`.stat .v .spin,.stat .v .numin{` 里也有 `.numin{`），
        前置断言也挡不住（第二项前面是**空格**不是逗号）。
        ⇒ 直接扫规则、比较归一化后的选择器列表。
        """
        import re
        want = ",".join(x.strip() for x in selector.split(","))
        for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
            sel = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
            got = ",".join(x.strip() for x in sel.split(","))
            if got == want:
                return m.group(0)
        return ""

    def test_base_font_is_bigger(self):
        """正文 12.5px → 14px。"""
        self.assertIn("font:14px/1.55", self.html)

    def test_rail_is_wider_and_bigger(self):
        """左侧功能列整列放大（用户：「空间冗余很多，可以多放大点」）。"""
        self.assertIn("width:200px", self._rule(self.html, ".rail"))
        self.assertIn("font-size:15px", self._rule(self.html, ".rail .nav"))

    def test_wheel_controls_are_much_bigger(self):
        """★ 滚轮区（可改的地方）：控件和数字都要大。"""
        self.assertIn("font-size:22px", self._rule(self.html, ".spin"))
        self.assertIn("min-width:60px", self._rule(self.html, ".spin"))
        self.assertIn("font-size:22px", self._rule(self.html, ".numin"))
        self.assertIn("font-size:22px", self._rule(self.html, ".tun .num"))
        self.assertIn("width:19px", self._rule(self.html, ".blood .bar .pip"))
        self.assertIn("height:34px", self._rule(self.html, ".stat .v .spin,.stat .v .numin"))

    def test_auxiliary_small_text_kept(self):
        """注释用的小字**保持原大小**（单位行副信息 11.5px、技能名 9.5px）。"""
        self.assertIn("font-size:11.5px", self._rule(self.html, ".umeta"))
        self.assertIn("font-size:9.5px", self._rule(self.html, ".sk .nm"))

    def test_wheel_control_has_hint(self):
        """滚轮控件悬停给提示（「第一反应就是这里可以改」）。"""
        self.assertIn("滚轮 ±1（也可按住上下拖）", self.html)


# =====================================================================
# U50：工具条横向溢出 + 兵力卡恢复「数字调血量 / 条上调压制」
# =====================================================================


class TestU50ToolbarAndStrength(unittest.TestCase):
    """U50 —— 两处：① 单位页工具条不许横向溢出；② 兵力卡恢复 §6.1b 两层滚轮。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    @staticmethod
    def _rule(css, selector):
        i = css.find(selector + "{")
        if i < 0:
            return ""
        j = css.find("}", i)
        return css[i:j + 1]

    def test_toolbar_wraps_instead_of_overflowing(self):
        """总部下拉框的宽度由**最长总部名**决定 ⇒ 窄窗口必须换行，不能横向溢出。"""
        self.assertIn(".toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;",
                      self.html)
        self.assertIn("max-width:100%", self._rule(self.html, ".sel"))

    def test_strength_card_has_only_the_blood_bar(self):
        """U54：兵力卡**只有血量条**（数字区删掉）。"""
        # U74：模板被包成 L2() ⇒ id 变成占位符 `id="sp_blood_{8}"`
        self.assertIn('id="sp_blood_', self.html)
        self.assertNotIn('id="sp_tot_${u.id}"', self.html)
        self.assertNotIn('id="sp_act_${u.id}"', self.html)
        self.assertNotIn('id="sp_sup_${u.id}"', self.html)

    def test_blood_bar_wheel_has_two_modes(self):
        """U54：血量条 = **普通滚轮调活跃** + **Alt+滚轮调压制**（全局唯一保留 Alt 的控件）。"""
        self.assertIn('if(ev.altKey){', self.html)
        self.assertIn('field:"act_st"', self.html)
        self.assertIn('field:"sup_st"', self.html)
        # Alt 分支：两者之和不变。U82：**方向跟活跃一致**
        # （向上滚 = 活跃 +1 / 压制 −1；向下滚 = 活跃 −1 / 压制 +1）
        self.assertIn("if(d<0){ if(a<1) return; s+=1; a-=1; }", self.html)
        self.assertIn("else    { if(s<1) return; s-=1; a+=1; }", self.html)

    def test_blood_bar_clamps_to_game_max(self):
        """血量条夹取：活跃 + 压制 ≤ **上限**（上限按单位类型取，不是常数 7）。"""
        self.assertIn("if(a>max) a=max;", self.html)
        self.assertIn("const over = a+s-max;", self.html)
        self.assertIn("if(over>0) s = Math.max(0, s-over);", self.html)

    def test_pending_list_shows_player_facing_numbers(self):
        """待应用清单显示玩家看到的量，写盘仍是 `act_st` / `sup_st`。"""
        # U74：文案进了 i18n 词表（键里用 {0} 占位）
        self.assertIn('L2("单位 {0} 活跃兵力"', self.html)
        self.assertIn('L2("单位 {0} 被压制兵力"', self.html)


# =====================================================================
# U49：兵力卡精简 / 备选池固定尺寸 + 默认折叠 / 挂载合法性方向
# =====================================================================


class TestU49LayoutAndLegality(unittest.TestCase):
    """U49 的三个改动 —— 用「读前端源码」的方式锁死。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    @staticmethod
    def _rule(css, selector):
        """取一条 CSS 规则的完整文本（含大括号）。"""
        i = css.find(selector + "{")
        if i < 0:
            return ""
        j = css.find("}", i)
        return css[i:j + 1]

    def test_detail_card_has_no_legend_row(self):
        """单位详情兵力卡**不再有那条常驻图例行**（未压 / 压制 / 差 的文字说明）。

        ⚠️ **U50 改判了一部分**：段格条（血量条）是**控件不是装饰** ——
        它是「在条上滚轮调被压制量」的入口（规范 §6.1b），
        U49 把它当冗余展示删掉时**连这个交互一起删没了** ⇒ U50 把血量条恢复了。
        真正被删掉并**保留删除**的只有那条**图例行**（`.legend`）；
        血量条的颜色含义改由**悬停浮层**说明。
        """
        self.assertNotIn('class="legend"', self.html)
        self.assertNotIn(".legend{", self.html)

    def test_strength_and_xp_cards_line_up(self):
        """兵力卡与经验卡都是「标签 / 数值 / 第三行」三行，数值控件一样高。

        U50：兵力卡的第三行是**血量条**（U49 之前是提示行），
        经验卡的第三行仍是提示行 ⇒ 两张卡的行数与基线仍然对齐。

        U85：单位详情多了三张卡（**工事等级 / 移动力 / 行动力**）⇒
        详情里一共 5 张卡、5 行 hintline（每张卡都还是「标签 / 内容 / 提示」三行）。
        """
        # U54：兵力卡**删掉数值区**，改成一条血量条 + 一行颜色含义说明
        # ⇒ 两张卡都是「标签 / 内容 / 提示」三行
        # U85：+3 张卡（工事等级 / 移动力 / 行动力）⇒ 2 → 5；U89：+1 张（作战标记）⇒ 6
        self.assertEqual(self.html.count('class="hintline"'), 6)
        # U74：class 变成占位符 `class="blood{7}"`
        self.assertIn('class="blood{', self.html)
        self.assertNotIn('id="sp_tot_${u.id}"', self.html)
        self.assertIn(".stat .v .spin,.stat .v .numin{height:34px", self.html)
        self.assertIn("min-height:34px", self.html)

    def test_specialist_pool_window_has_fixed_height(self):
        """备选池窗口**固定高度** —— 勾「显示全部」不许变大小。"""
        self.assertIn("height:240px", self._rule(self.html, ".specsplit"))
        self.assertIn("overflow:auto", self._rule(self.html, ".specslots"))
        self.assertNotIn("max-height:340px", self._rule(self.html, ".specpool"))

    def test_full_pool_groups_start_collapsed(self):
        """375 种全量视图的各国分组**默认折叠**。"""
        self.assertIn("function poolGroupOpen(", self.html)
        self.assertIn("SEL.poolOpen", self.html)
        self.assertNotIn("SEL.poolClosed", self.html)
        self.assertIn("const open = poolGroupOpen(n);", self.html)

    def test_attach_check_uses_unit_parent_nationality(self):
        """挂载判定方向：**单位国籍的 parent == 特种兵国籍**（单向）。"""
        self.assertIn("const nat = (cat.nationalities||{})[ut.nationality]||{};",
                      self.html)
        self.assertIn('if(nat.parent === sp.nationality) return {ok:true, why:""};',
                      self.html)
        self.assertNotIn("(cat.nationalities||{})[sp.nationality]", self.html)

    def test_add_spec_is_guarded_in_frontend(self):
        """前端点挂载时也拦一道非法挂载（核心库还有一道硬拦）。"""
        self.assertIn("function addSpec(", self.html)
        self.assertIn("const chk = specAttachCheck(specType, u.type);", self.html)


# =====================================================================
# U48：同一种特种兵可以挂多个（前端不许把已挂过的种灰掉）
# =====================================================================


class TestSameSpecialistMounting(unittest.TestCase):
    """U48 —— 游戏规则允许同一种挂多个，前端必须照办。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_pool_does_not_gray_out_mounted_specialists(self):
        """候选池里已挂的种**不能**再按 type 判灰。"""
        self.assertNotIn("const has = specs.some(s=>s.type===t);", self.html)
        self.assertNotIn("const has = selected.some(s=>s.type===t);", self.html)
        self.assertIn('${n?`<span class="dup">${n}</span>`:""}', self.html)

    def test_pool_shows_how_many_more_can_be_mounted(self):
        """tooltip 要写清「已挂 N 个 / 还能再挂 M 个 / 槽位已满」。"""
        self.assertIn('L("已挂 ")+n+L(" 个，还能再挂 ")+(cap-used)+L(" 个")', self.html)
        self.assertIn("特种兵槽已满", self.html)

    def test_pending_add_uses_a_unique_key(self):
        """待应用的 key 必须带序号，否则同种第二次会**覆盖**第一条。"""
        self.assertIn("let SPECSEQ = 0;", self.html)
        self.assertIn("unit_spec_add:${unitId}:${specType}:${seq}", self.html)

    def test_remove_spec_targets_the_right_slot(self):
        """卸载按 idx 定位（点哪张卸哪张）。"""
        self.assertIn("function removeSpec(unitId, specType, idx)", self.html)
        self.assertIn("unit_spec_remove:${unitId}:${specType}:${s.idx}", self.html)
        self.assertTrue('L("点击卸下这个特种兵（第 ")+nth+"/"+same.length+L(" 个 · 槽位 ")' in self.html)


# =====================================================================
# U56：概览页排版统一 + 修「内容被截断、且滚不动」
# =====================================================================


class TestU56OverviewLayout(unittest.TestCase):
    """U56 —— `.work` 子项锁死不缩（超出就滚，不再把面板压扁）；概览页两栏 + 定死列数。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_work_children_cannot_shrink(self):
        """`.work` 是 column flex ⇒ 子项默认能压缩 ⇒ 面板被压扁 + overflow:hidden 裁掉
        ⇒ 底部截断且没有滚动条。必须锁死 `flex:none`。"""
        self.assertIn(".work > *{flex:none}", self.html)
        self.assertIn(".work{flex:1;min-width:0;display:flex;flex-direction:column;overflow:auto",
                      self.html)

    def test_overview_uses_two_column_layout(self):
        """概览页改成两栏面板（宽度有上限、位置固定）。"""
        self.assertIn(".ovwrap{display:grid", self.html)
        self.assertIn(".ovcol{display:flex;flex-direction:column", self.html)
        self.assertIn('<div class="ovwrap">', self.html)
        self.assertIn('<div class="ovcol">', self.html)

    def test_capgrid_columns_are_fixed_not_autofill(self):
        """能力位卡片列数**按断点定死** —— 不许再用 `auto-fill`
        （auto-fill ⇒ 窗口一放大列数说变就变、卡片被拉得极宽 ⇒ 位移随意）。"""
        rule = self.html.split(".capgrid{")[1].split("}")[0]
        self.assertNotIn("auto-fill", rule)
        self.assertIn("repeat(3,minmax(0,1fr))", rule)
        self.assertIn("@media (max-width:1240px)", self.html)
        self.assertIn("repeat(2,minmax(0,1fr))", self.html)

    def test_last_capcard_spans_full_row(self):
        """7 张卡：3 列 / 2 列时最后一张独占一行 ⇒ 不留孤零零的一张。"""
        self.assertIn(".capgrid > .capcard:last-child:nth-child(3n+1){grid-column:1/-1}",
                      self.html)
        self.assertIn(".capgrid > .capcard:last-child:nth-child(2n+1){grid-column:1/-1}",
                      self.html)

    def test_value_cards_share_the_capcard_style(self):
        """战役进度也做成「卡片」，外观和能力位卡统一。"""
        self.assertIn(".tungrid{display:grid", self.html)
        self.assertIn(".tun{display:flex;flex-direction:column", self.html)
        self.assertIn("border:1px solid var(--border);border-radius:7px;background:var(--surface)",
                      self.html)
        self.assertIn('<div class="tungrid">', self.html)
        self.assertNotIn(".tun:last-child{border-bottom:none}", self.html)

    def test_backup_rows_are_unified_three_columns(self):
        """备份/撤销行统一成三栏：标签 | 主内容（省略号截断）| 右侧小字。
        原来大小被 `margin-left:auto` 甩到面板最右边，和名字隔了一整屏。"""
        self.assertIn(".bkrow{display:grid;grid-template-columns:56px minmax(0,1fr) auto",
                      self.html)
        self.assertNotIn(".bkrow .n{margin-left:auto", self.html)
        self.assertIn('<span class="bt">备份</span>', self.html)
        self.assertIn('<span class="bn" title=', self.html)
        self.assertIn('<span class="bm">', self.html)


# =====================================================================
# U57：总部页排版微调
# =====================================================================


class TestU57HqPageTweaks(unittest.TestCase):
    """U57 —— 栏间隔 = 到边缘的间隔；详情首行对齐；数值框统一；清单撑满高度。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_column_gap_equals_edge_margin(self):
        """**栏间隔 = 面板到边缘的间隔**（都 14px）。
        原来 `.cols{gap:14px}` + `.panel{margin:14px}` ⇒ 栏间隔 42px、边缘 14px。"""
        self.assertIn(".cols > .panel{margin:0}", self.html)
        self.assertIn(".cols{margin:14px}", self.html)

    def test_hq_list_fills_the_available_height(self):
        """总部清单**撑满可用高度**（原来写死 max-height:430px ⇒ 下面空一大片）。"""
        self.assertIn(".work > .cols-fill{flex:1 1 auto;min-height:0}", self.html)
        self.assertIn(".cols-fill .hqlist{max-height:none;height:100%;overflow:auto}", self.html)
        self.assertNotIn(".hqlist{padding:4px 0;max-height:430px", self.html)
        self.assertIn('<div class="cols cols-fill">', self.html)

    def test_hq_head_blocks_align(self):
        """名称/将领、经验卡、CP 卡三块对齐；名称与将领不再隔 ~96px。"""
        blk = self.html.split(".hqhead .idblk{")[1].split("}")[0]
        self.assertIn("justify-content:flex-start", blk)
        self.assertNotIn("space-between", blk)
        self.assertIn("gap:3px", blk)
        self.assertIn(".hqhead .stat{width:214px;min-width:214px}", self.html)

    def test_hq_value_boxes_have_one_size(self):
        """总部的数值框统一尺寸（主值 72×34 / 次值 56×26），数字在框里居中。"""
        self.assertIn(".hqhead .stat .v .numin,.hqhead .stat .v .spin{width:72px;height:34px",
                      self.html)
        self.assertIn(".hqhead .cphint .numin,.hqhead .cphint .spin{display:inline-block;width:56px",
                      self.html)
        # 目标输入框不能再用内联尺寸（会盖掉 CSS 里的统一尺寸）
        self.assertNotIn('autocomplete="off" value="${xt}" style=', self.html)


# =====================================================================
# U58：单位页排版微调
# =====================================================================


class TestU58UnitsPageTweaks(unittest.TestCase):
    """U58 —— 栏间隔统一、搜索栏留上边距、两栏撑满高度、详情标题不挤成竖排。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_units_column_gap_equals_edge_margin(self):
        """单位页两栏：栏间隔 = 到边缘的间隔（14px）。"""
        self.assertIn(".cols-units > .panel{margin:0}", self.html)
        rule = self.html.split(".cols-units{")[1].split("}")[0]
        self.assertIn("gap:14px", rule)
        self.assertIn("margin:14px", rule)
        self.assertNotIn("gap:0", rule)

    def test_toolbar_has_top_margin(self):
        """顶部工具条**上边距也要 14px**（原来 `margin:0 14px 12px` ⇒ 顶到边缘）。"""
        self.assertIn(".toolbar-top{margin:14px 14px 12px}", self.html)
        self.assertNotIn(".toolbar-top{margin:0 14px 12px}", self.html)

    def test_units_panels_fill_the_height(self):
        """两栏撑满可用高度 ⇒ 列表在卡内滚（能显示更多单位）。"""
        self.assertIn('<div class="cols cols-units cols-fill">', self.html)
        self.assertIn(".cols-fill .rows{max-height:none;height:100%;overflow:auto}", self.html)
        self.assertNotIn(".rows{max-height:430px", self.html)

    def test_specialist_area_grows_with_the_panel(self):
        """详情卡里的特种兵区**跟着面板长高**（原来写死 240px ⇒ 下面空一大片）。"""
        self.assertIn(".cols-fill #udetail{display:flex;flex-direction:column}", self.html)
        self.assertIn(".cols-fill #udetail .specsplit{height:auto;flex:1;min-height:240px}",
                      self.html)

    def test_detail_title_is_not_squeezed_vertically(self):
        """窄栏时详情标题不许被挤成竖排（「第21步兵师」一字一行）
        ⇒ 数字卡整块换到第二行（容器查询按**栏宽**判，不按窗口宽）。"""
        self.assertIn("container-type:inline-size", self.html)
        head = self.html.split("\n.dhead{")[1].split("}")[0]
        self.assertIn("flex-wrap:wrap", head)
        self.assertIn("@container (max-width:760px)", self.html)
        self.assertIn(".dhead .stats{flex:1 1 100%;width:auto}", self.html)


# =====================================================================
# U59：卡牌页恢复横排
# =====================================================================


class TestU59CardsHorizontal(unittest.TestCase):
    """U59 —— 卡牌容器 `.hand` 之前**根本没有 CSS** ⇒ 卡按 block 逐个换行 = 竖排。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_card_container_is_a_wrapping_row(self):
        """卡牌容器：横排 + 放不下自动换行。"""
        self.assertIn(".hand{display:flex;flex-wrap:wrap;gap:9px", self.html)
        self.assertIn('class="hand"', self.html)

    def test_cards_are_not_squashed(self):
        """卡与空槽位都不许被 flex 压扁（压扁就会变形）。"""
        self.assertIn(".hcard{width:104px;flex:none}", self.html)
        self.assertIn(".slotempty{width:104px;height:124px;flex:none", self.html)


# =====================================================================
# U61：战区资产「无限」的语义提示
# =====================================================================


class TestU61TheaterInfiniteHint(unittest.TestCase):
    """U61 —— 「无限」不是「无限次可用」，是「每回合恢复到 N 次」；UI 要说清楚。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_infinite_semantics_are_explained(self):
        """「无限」= 每回合恢复 N 次、**只恢复到 N 次**、上一回合没用完的**不累积**。"""
        self.assertIn("「无限」= 每回合恢复", self.html)
        self.assertIn("不会累积", self.html)

    def test_the_hint_only_shows_for_infinite_assets(self):
        """提示只给「无限」的那些项显示（有限的不用显示）。"""
        self.assertIn('<div class=\"talt\">「无限」= 每回合恢复', self.html)


# =====================================================================
# U62：导航栏图标 —— 自绘的「两字母徽标」
# =====================================================================


class TestU62NavBadges(unittest.TestCase):
    """U62 —— 占位字符（▤▥▦▧▨▩▪◈）换成自绘的两字母徽标。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_all_seven_pages_have_a_letter_badge(self):
        """7 个功能页各一个徽标：OV / UN / HQ / CD / ST / TA / CP。"""
        for tag in ("OV", "UN", "HQ", "CD", "ST", "TA", "CP"):
            self.assertIn('class="ic">%s<' % tag, self.html)

    def test_placeholder_glyphs_are_gone(self):
        """视觉稿的占位字符不许再留着。"""
        for ch in ("\u2592", "\u25a4", "\u25a6", "\u25a7", "\u25a8",
                   "\u25a9", "\u25c8"):
            self.assertNotIn('class="ic">%s<' % ch, self.html)

    def test_badge_is_drawn_in_css(self):
        """徽标是 CSS 画的（圆角方块 + 字母），不依赖素材。"""
        self.assertIn(".rail .nav .ic{width:22px;height:22px", self.html)
        self.assertIn("font:700 10.5px/20px var(--mono)", self.html)


# =====================================================================
# U63：单位头像按画面内容居中
# =====================================================================


class TestU63AvatarCentering(unittest.TestCase):
    """U63 —— 大图是横幅、主体偏右偏下 ⇒ 用 alpha 内容框把内容摆到方框正中。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_avatar_box_is_a_positioning_context(self):
        """头像框要能当定位参照。"""
        self.assertIn("overflow:hidden;position:relative}", self.html)

    def test_bbox_is_measured_and_cached(self):
        """运行时量 alpha 内容框，按类型缓存（每个类型只量一次）。"""
        self.assertIn("const AVA_BBOX = {};", self.html)
        self.assertIn("function avaBBox(img)", self.html)
        self.assertIn("function avaFit(img)", self.html)
        self.assertIn("AVA_BBOX[type] = bb;", self.html)

    def test_both_avatar_places_use_the_fitting_helper(self):
        """列表行与详情抬头都用 `avaImg`（而不是普通 imgTag）。"""
        self.assertIn("function avaImg(type, alt, box)", self.html)
        # U65 起两处头像框尺寸不同（列表 58 / 详情 84），分别断言
        # U74：整行模板被包成 L2() ⇒ 外层 div 变成占位符，改按 avaImg 调用计数
        self.assertEqual(self.html.count(
            "avaImg(u.type, unitCn(u.type), AVA_BOX_LIST)"), 1)
        self.assertEqual(self.html.count(
            "avaImg(u.type, unitCn(u.type), AVA_BOX_DETAIL)"), 1)


# =====================================================================
# U64：概览页「难度」
# =====================================================================


class TestU64LevelPicker(unittest.TestCase):
    """U64 —— 概览页能改难度；手牌超过新上限的难度**置灰**（核心库也会硬拦）。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_level_panel_exists(self):
        self.assertIn("<h3>难度</h3>", self.html)
        self.assertIn("function levelPickerHTML()", self.html)
        self.assertIn("function setLevel(lv)", self.html)
        self.assertIn("function curLevel()", self.html)

    def test_level_buttons_show_the_hand_limit(self):
        """每个难度按钮上标着它的**手牌上限**。"""
        # U74：模板被包成 L2() ⇒ 变成 `<span class="lvlim">{5} 张</span>`
        self.assertIn('<span class=\"lvlim\">{5} 张</span>', self.html)

    def test_over_limit_levels_are_disabled(self):
        """手里牌数超过某难度的上限 ⇒ 那个按钮置灰并说明原因。"""
        self.assertIn("const dis = nHand > l.deck_limit;", self.html)
        self.assertIn("请先删手牌", self.html)

    def test_level_edit_uses_the_level_kind(self):
        """写盘用核心库新加的 `level` 编辑类型。"""
        self.assertIn('queueEdit("level", "level", {value:lv}', self.html)

# =====================================================================
# U65：调血量 —— 只更新血量条，不整页重绘
# =====================================================================


class TestU65UnitBloodPartialRefresh(unittest.TestCase):
    """U65 —— 调血量时**不再整页重绘**。

    旧实现：滚轮调血量最后调 `show("units")` ⇒ 整页 `innerHTML` 重写
    ⇒ 几百个头像 `<img>` 全部重建 ⇒ ① 每个头像「先 hidden、onload 后再定位」
    ⇒ 闪一下；② 重建 + 重解码 ⇒ 明显卡。
    新实现：**局部更新**（详情卡血量条 + 列表该行段格条），头像**不再重建**。
    """

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def _wheel_block(self):
        """滚轮处理函数体（`barEl.addEventListener("wheel"` 到 `{passive:false}`）。"""
        i = self.html.index('barEl.addEventListener("wheel"')
        j = self.html.index("{passive:false}", i)
        return self.html[i:j]

    def test_wheel_does_not_repaint_the_whole_page(self):
        """调血量后**不得**再 `show("units")`（整页重绘 = 闪 + 卡）。"""
        self.assertNotIn('show("units")', self._wheel_block())

    def test_wheel_calls_the_partial_refresh(self):
        """滚轮处理改为调 `refreshUnitBlood`（局部更新）。"""
        self.assertIn("refreshUnitBlood(u, a, s);", self._wheel_block())

    def test_refresh_updates_detail_bar_and_row_pips_only(self):
        """局部刷新只动两处：详情卡 `.bar` 和列表该行 `.pips`。"""
        self.assertIn("function refreshUnitBlood(u, a, s)", self.html)
        self.assertIn('const bar = document.getElementById("sp_blood_"+u.id);', self.html)
        self.assertIn('bar.querySelector(".bar")', self.html)
        self.assertIn('document.querySelector(`.urow[data-uid="${u.id}"] .pips`)', self.html)
        self.assertIn("paintPending();", self.html)

    def test_row_carries_uid(self):
        """列表行带 `data-uid` ⇒ 局部刷新能精确定位到那一行。"""
        # U74：模板被包成 L2() ⇒ 变成 `class="urow {0}" data-uid="{1}"`
        self.assertIn('class=\"urow {0}\" data-uid=\"{1}\"', self.html)

    def test_pips_helper_is_shared(self):
        """列表行与详情卡共用同一份段格条逻辑。"""
        self.assertIn("function bloodPipsHTML(act, sup, max)", self.html)
        self.assertEqual(self.html.count("bloodPipsHTML(act, sup, max)"), 3)

    def test_avatar_position_is_inlined_at_build_time(self):
        """头像定位**在生成时就写进 style**（内容框已知 ⇒ 首帧就位 ⇒ 重绘不闪不跳）。"""
        self.assertIn("function avaStyle(type, box)", self.html)
        self.assertIn("const AVA_BOX_LIST = 58, AVA_BOX_DETAIL = 84;", self.html)
        self.assertIn("transform:translate(${tx}px,${ty}px) scale(${k})", self.html)

    def test_bbox_cache_carries_image_size(self):
        """内容框缓存里补上原图宽高（内联定位需要）。"""
        self.assertIn("return {x0:x0, y0:y0, x1:x1, y1:y1, w:W, h:H};", self.html)
# U67 / U68：切换存档 · 另存为 · 内置文件浏览器 · 拖拽导入
# =====================================================================


class _SaveCopyBase(WebGuiTestBase):
    """给服务端写操作测试用：准备一个存档**副本**（绝不碰用户的真存档）。"""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from save_modifier_core import list_saves

        self.tmp = Path(tempfile.mkdtemp(prefix="webcopy_"))
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

    def use_temp_appdata(self):
        """把「游戏数据目录」指到临时目录 ⇒ 导入的副本不会落进用户真目录。"""
        old = os.environ.get("UOC2_APPDATA")
        d = self.tmp / "appdata"
        d.mkdir(parents=True, exist_ok=True)
        os.environ["UOC2_APPDATA"] = str(d)

        def restore():
            if old is None:
                os.environ.pop("UOC2_APPDATA", None)
            else:
                os.environ["UOC2_APPDATA"] = old
        self.addCleanup(restore)


class TestU67SwitchAndSaveAs(_SaveCopyBase):
    """U67 —— 切换存档（不用退出）· 另存为 · 内置文件浏览器。

    用户原话：「目前选了一个存档后，除非退出，不然没法重新选择存档。
    我看现在存档编辑界面顶端有显示当前存档的名称，要不给那个变成一个按钮，
    按了出个菜单，允许更换编辑对象或存档另存为。」
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()          # ⚠️ 基类要起 HTTP 服务（别覆盖掉）
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    # ---- 前端 ----

    def test_current_save_is_a_button_that_opens_a_menu(self):
        self.assertIn("function openSaveMenu()", self.html)
        self.assertIn("onclick=\"openSaveMenu()\"", self.html)

    def test_menu_offers_switch_and_save_as(self):
        for t in ("切换到其他存档", "另存为", "导出当前副本", "放弃改动并重新读取"):
            self.assertIn(t, self.html)

    def test_switch_asks_before_dropping_pending_edits(self):
        self.assertIn("function doSwitchSave()", self.html)
        self.assertIn("function doSwitchSaveForce()", self.html)
        self.assertIn("放弃改动并切换", self.html)

    def test_file_picker_exists_and_is_responsive(self):
        self.assertIn("function openFilePicker(opts)", self.html)
        self.assertIn("function fbGo(", self.html)
        self.assertIn("function fbPick()", self.html)
        # 窄视口（内置浏览器侧栏 ~720 px）下按钮不能被挤出屏幕
        self.assertIn("width:min(880px,94vw)", self.html)

    # ---- 服务端 ----

    def test_fs_list_lists_dirs_and_usg_files(self):
        import urllib.parse
        d = self.get_json("/api/fs/list?dir=" + urllib.parse.quote(str(self.tmp)))
        self.assertTrue(d["ok"], d)
        self.assertIn("dirs", d)
        self.assertIn("files", d)
        self.assertIn("roots", d)
        self.assertTrue(any(f["name"] == "copy.usg" for f in d["files"]), d["files"])

    def test_fs_list_rejects_a_non_directory(self):
        import urllib.parse
        d = self.get_json("/api/fs/list?dir=" +
                          urllib.parse.quote(str(self.tmp / "copy.usg")))
        self.assertFalse(d["ok"])
        self.assertTrue(d.get("error"))

    def test_save_as_writes_a_copy_and_leaves_the_original_alone(self):
        before = io.open(self.copy, "rb").read()
        dest = str(self.tmp / "copy_out.usg")
        r = self.post("/api/save-as", {"save_id": self.copy, "dest": dest, "edits": []})
        self.assertTrue(r["ok"], r.get("errors"))
        self.assertTrue(os.path.isfile(dest))
        self.assertEqual(io.open(self.copy, "rb").read(), before, "原存档不能被动")

    def test_save_as_never_overwrites_an_existing_file(self):
        dest = str(self.tmp / "copy_out.usg")
        with io.open(dest, "wb") as fh:
            fh.write(b"KEEP")
        r = self.post("/api/save-as", {"save_id": self.copy, "dest": dest, "edits": []})
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"])
        self.assertEqual(io.open(dest, "rb").read(), b"KEEP", "已存在的文件不能被覆盖")

    def test_save_as_with_edits_only_touches_the_copy(self):
        dest = str(self.tmp / "copy_edit.usg")
        v = self.get_json("/api/view/" + urllib.request.quote(self.copy))
        old = v.get("prestige") or 0
        r = self.post("/api/save-as", {
            "save_id": self.copy, "dest": dest,
            "edits": [{"kind": "progress",
                       "params": {"field": "prestige", "value": old + 3}}]})
        self.assertTrue(r["ok"], r.get("errors"))
        v2 = self.get_json("/api/view/" + urllib.request.quote(dest))
        self.assertEqual(v2.get("prestige"), old + 3, "新文件要带上改动")
        v3 = self.get_json("/api/view/" + urllib.request.quote(self.copy))
        self.assertEqual(v3.get("prestige"), old, "原存档不能被动")

    def test_save_as_with_a_bad_edit_writes_nothing(self):
        dest = str(self.tmp / "copy_bad.usg")
        r = self.post("/api/save-as", {
            "save_id": self.copy, "dest": dest,
            "edits": [{"kind": "no_such_kind", "params": {}}]})
        self.assertFalse(r["ok"])
        self.assertFalse(os.path.exists(dest), "出错的另存为不能留下半成品")
class TestU68ImportWhenNoSave(_SaveCopyBase):
    """U68 —— 没识别到存档时：打开其他位置的存档 / 拖拽导入。

    用户原话：「另外在存档读取界面，如果没有识别到存档，是否应该允许玩家
    自己拖拽存档进来或者打开一个选区存档位置的窗口。」
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()          # ⚠️ 基类要起 HTTP 服务（别覆盖掉）
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_empty_state_offers_both_entrances(self):
        self.assertIn("没有识别到存档", self.html)
        self.assertIn("打开其他位置的存档", self.html)
        self.assertIn("id=\"nosave\"", self.html)

    def test_drop_zone_is_wired(self):
        self.assertIn("function bindDropZone()", self.html)
        self.assertIn("function importSaveFile(f)", self.html)
        self.assertIn("bindDropZone();", self.html)

    def test_import_writes_a_byte_identical_copy(self):
        import base64
        self.use_temp_appdata()
        raw = io.open(self.copy, "rb").read()
        r = self.post("/api/import-save", {
            "name": "拖进来的.usg",
            "data": base64.b64encode(raw).decode("ascii")})
        self.assertTrue(r["ok"], r.get("errors"))
        p = r["path"]
        self.assertTrue(os.path.isfile(p))
        self.assertEqual(io.open(p, "rb").read(), raw)
        self.assertIn("modifier_imports", p)

    def test_import_never_overwrites(self):
        import base64
        self.use_temp_appdata()
        raw = io.open(self.copy, "rb").read()
        b64 = base64.b64encode(raw).decode("ascii")
        r1 = self.post("/api/import-save", {"name": "同名.usg", "data": b64})
        r2 = self.post("/api/import-save", {"name": "同名.usg", "data": b64})
        self.assertTrue(r1["ok"] and r2["ok"])
        self.assertNotEqual(r1["path"], r2["path"], "同名导入不许覆盖")

    def test_import_rejects_a_non_zip_payload(self):
        import base64
        self.use_temp_appdata()
        r = self.post("/api/import-save", {
            "name": "假的.usg",
            "data": base64.b64encode(b"not a zip").decode("ascii")})
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"])

    def test_imported_copy_can_be_opened_by_path(self):
        import base64
        self.use_temp_appdata()
        raw = io.open(self.copy, "rb").read()
        r = self.post("/api/import-save", {
            "name": "打开用.usg",
            "data": base64.b64encode(raw).decode("ascii")})
        v = self.get_json("/api/view/" + urllib.request.quote(r["save_id"]))
        self.assertIn("units", v)
        self.assertIn("hqs", v)


# =====================================================================
# U72：表述修正（归档区不叫「Old Saves」· 血量条注释简化）
# =====================================================================


class TestU72Wording(unittest.TestCase):
    """U72 —— 表述修正。

    用户原话：「游戏本来只能识别 save 路径下 campaigns 和 games 两个文件夹的存档，
    old saves 这个文件夹是我自己加的。我觉得你能识别整个根目录存档的功能是实用的，
    但是其表述就别加 old saves 这种我自己创造的内容了……
    顺便你也修另一个表述小毛病，单位详情页修改兵力那里，有注释
    『实 = 活跃 · 淡 = 被压制 · 空 = 还差』，其实保留『实 = 活跃 · 淡 = 被压制』大家都能看懂了」
    """

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_no_claim_that_old_saves_is_a_game_feature(self):
        """界面里**不得**再把「Old Saves」说成游戏的功能。"""
        self.assertNotIn("Old Saves", self.html)
        self.assertNotIn("游戏自己的「Old Saves」", self.html)
        self.assertNotIn("历史存档（游戏自己的", self.html)

    def test_archive_band_uses_the_new_wording(self):
        self.assertIn("其他位置的存档（你自己归档的旧存档）", self.html)

    def test_archive_split_uses_the_archived_flag(self):
        """分组改用 `archived` 标记 ⇒ **不按目录名挑**。"""
        self.assertIn("const isOld = s => !!s.archived;", self.html)

    def test_blood_hint_drops_the_redundant_part(self):
        """血量条注释：「实 = 活跃 · 淡 = 被压制」（去掉「空 = 还差」）。"""
        self.assertIn("实 = 活跃 · 淡 = 被压制", self.html)
        self.assertNotIn("实 = 活跃 · 淡 = 被压制 · 空 = 还差", self.html)
        # 悬停浮层与行内提示两处
        self.assertEqual(self.html.count("实 = 活跃 · 淡 = 被压制"), 2)
