# -*- coding: utf-8 -*-
"""U141：护栏 —— 审阅挂着的两条 P2。

**P2-1**：战区资产弹窗里「场景定义：每回合恢复 X、本场景剩余 Y」的参照值
         可能取自**另一个阶段**（`theater_assets` 是**按阶段分组**的，
         同名资产在不同阶段次数不同 ⇒ 拍平会「后一组覆盖前一组」）。
**P2-2**：打不开的坏 ZIP 把 `BadZipFile` 原样抛穿 ⇒ HTTP 500 +
         「BadZipFile: File is not a zip file」⇒ 玩家看不懂、也不知道
         可以用 `bak` 里的备份恢复。

**这些测试守着**

① 场景设计值按**当前阶段**取（阶段 0 / 阶段 1 各取各的）；
② 不给阶段时保持旧行为（拍平）；
③ 坏存档 ⇒ `SaveUnreadable` + 一句**提到 `bak` 备份**的人话；
④ HTTP 层把它当 **400（用户的文件坏了）**，不是 500；
⑤ 前端 `api()` 把错误正文里的 JSON 拆出来 ⇒ 界面上是**人话**不是花括号。
"""

import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import quote
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import Catalog, CorePaths, SaveUnreadable, open_save  # noqa: E402
from save_modifier_core.container import (theater_assets_by_phase,  # noqa: E402
                                          theater_assets_flat)
from save_modifier_web import server  # noqa: E402

from ._fixtures import make_save  # noqa: E402

WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")

#: 场景定义：同名资产在**两个阶段**次数不同（这才是问题现场）
SCEN_DEF = {
    "theater_assets": [
        [{"asset": "air_attack", "uses_total": 3, "uses_turn": 1}],
        [{"asset": "air_attack", "uses_total": 5, "uses_turn": 2}],
    ],
}


class PhaseGroupsHelperTest(unittest.TestCase):
    """两个助手本身。"""

    def test_by_phase_keeps_the_groups(self):
        groups = theater_assets_by_phase(SCEN_DEF["theater_assets"])
        self.assertEqual(2, len(groups))
        self.assertEqual(3, groups[0]["air_attack"]["uses_total"])
        self.assertEqual(5, groups[1]["air_attack"]["uses_total"])

    def test_flat_takes_the_last_group(self):
        """拍平 = 旧行为（后一组覆盖前一组）⇒ 保持兼容。"""
        flat = theater_assets_flat(theater_assets_by_phase(
            SCEN_DEF["theater_assets"]))
        self.assertEqual(5, flat["air_attack"]["uses_total"])

    def test_broken_input_is_tolerated(self):
        self.assertEqual([], theater_assets_by_phase(None))
        self.assertEqual([], theater_assets_by_phase("x"))
        self.assertEqual({}, theater_assets_flat([]))


class ScenarioValueByPhaseTest(unittest.TestCase):
    """P2-1：场景设计值要按**当前阶段**取。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u141_phase_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def _universe(self, phase):
        save_path = make_save(
            self.tmp / ("s%s.usg" % phase),
            battle_overrides={"phase": phase},
            extra_entries={"document/scenarios/avalanche/main.yml":
                           yaml.safe_dump(SCEN_DEF, allow_unicode=True).encode("utf-8")})
        with open_save(str(save_path), self.paths) as save:
            universe, _meta = server._theater_universe_of(save, self.catalog)
        return {u["asset"]: u for u in universe}

    def test_phase_zero_uses_the_first_group(self):
        u = self._universe(0)["air_attack"]
        self.assertEqual(3, u["scenario_uses_total"],
                         "阶段 0 的设计次数被写成了别的阶段的值")
        self.assertEqual(1, u["scenario_uses_turn"])

    def test_phase_one_uses_the_second_group(self):
        u = self._universe(1)["air_attack"]
        self.assertEqual(5, u["scenario_uses_total"])
        self.assertEqual(2, u["scenario_uses_turn"])

    def test_the_two_phases_really_differ(self):
        """护栏本身要有效（两个阶段的取值必须不同）。"""
        a = self._universe(0)["air_attack"]["scenario_uses_total"]
        b = self._universe(1)["air_attack"]["scenario_uses_total"]
        self.assertNotEqual(a, b)


class BrokenSaveTest(unittest.TestCase):
    """P2-2：坏存档 ⇒ 人话 + 400。"""

    def setUp(self):
        # ⚠️ 目录名**故意带中文** —— 守住「路径里有非 ASCII 时也能跑」
        #    （中文用户名 / 中文 TEMP 的机器上以前直接 UnicodeEncodeError）。
        self.tmp = Path(tempfile.mkdtemp(prefix="u141_坏档_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.corrupt = self.tmp / "broken.usg"
        self.corrupt.write_bytes(b"this is definitely not a zip file")
        self._old_app = os.environ.get("UOC2_APPDATA")
        os.environ["UOC2_APPDATA"] = str(self.tmp)
        self.addCleanup(self._restore_app)

    def _restore_app(self):
        if self._old_app is None:
            os.environ.pop("UOC2_APPDATA", None)
        else:
            os.environ["UOC2_APPDATA"] = self._old_app

    def test_the_api_raises_a_readable_error(self):
        with self.assertRaises(SaveUnreadable) as cm:
            server.api_view(str(self.corrupt))
        msg = str(cm.exception)
        self.assertNotIn("BadZipFile", msg, "别把内部异常甩给玩家")
        self.assertIn("bak", msg, "要告诉玩家可以用 bak 里的备份恢复")

    def test_the_http_layer_answers_400_not_500(self):
        """用户的文件坏了 ⇒ 不是服务器出错 ⇒ 400。"""
        server._Handler.token = "u141-token"
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server._Handler)
        port = httpd.server_address[1]
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        try:
            # ⚠️ 路径里有中文 ⇒ 必须百分号编码
            #    （http.client 只按 ASCII 编码 ⇒ 不编码直接 UnicodeEncodeError；
            #     服务端 do_GET 里有 unquote(u.path) ⇒ 编码后照样还原）。
            sid = quote(str(self.corrupt).replace("\\", "/"), safe="/")
            req = urllib.request.Request(
                "http://127.0.0.1:%d/api/view/%s" % (port, sid),
                headers={"X-Token": "u141-token"})
            try:
                urllib.request.urlopen(req, timeout=30)
                self.fail("坏存档居然返回了 200")
            except urllib.error.HTTPError as exc:
                self.assertEqual(400, exc.code, "坏存档应�� 400，不是 500")
                body = exc.read().decode("utf-8")
                self.assertIn("bak", body)
        finally:
            httpd.shutdown()


class FrontendErrorTextTest(unittest.TestCase):
    """前端：错误正文是 JSON ⇒ 要拆出来显示人话。"""

    @classmethod
    def setUpClass(cls):
        with io.open(os.path.join(WEB, "index.html"),
                     encoding="utf-8", newline="") as f:
            cls.html = f.read()

    def test_api_parses_the_error_body(self):
        i = self.html.index("async function api(path)")
        body = self.html[i:i + 900]
        self.assertIn("JSON.parse", body,
                      "api() 没解析错误正文 ⇒ 界面上会显示一串花括号")
        self.assertIn("j.error", body)

    def test_the_broken_save_message_tells_the_user_about_bak(self):
        """那句人话在**核心库**里（服务端返回它，前端原样显示）。"""
        with io.open(os.path.join(REPO_SRC, "save_modifier_core",
                                  "container.py"),
                     encoding="utf-8", newline="") as f:
            core = f.read()
        self.assertIn("bak 文件夹", core,
                      "坏存档的提示里要提到 bak 备份")
        self.assertIn("SaveUnreadable", core)


if __name__ == "__main__":
    unittest.main()
