# -*- coding: utf-8 -*-
"""U69 —— 游戏本体目录可配置（换电脑 / 非 Steam 安装能用）。

**为什么要有**：修改器大量数据来自**游戏包**（特种兵 / 单位类型 / 卡牌贴图 /
战役名册 / 商店默认值）⇒ 找不到游戏目录就等于「半个修改器」。
而旧实现只认「Steam 注册表 + 4 个写死路径 + 环境变量」，
**非 Steam 安装**（GOG / 解压版 / 别的盘）一律探测不到，也没有地方能改。

字节码依据（游戏自己的规矩）：
* `paths.pyc::all_package_dirs` ⇒ 包目录 = mod 包 + 用户包 + 游戏包；
* 游戏本体目录由**安装位置**决定（`_Paths.__init__`）；
* 目录结构：`_packages/`（base + dlc1..dlc10）或 `lib/uoc2`。
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import paths as core_paths   # noqa: E402

from .test_web_gui import WebGuiTestBase             # noqa: E402


class _TempAppdata(unittest.TestCase):
    """把「游戏数据目录」指到临时目录 ⇒ 测试**不碰**用户真目录。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gamedir_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        old = os.environ.get("UOC2_APPDATA")
        os.environ["UOC2_APPDATA"] = str(self.tmp / "appdata")

        def restore():
            if old is None:
                os.environ.pop("UOC2_APPDATA", None)
            else:
                os.environ["UOC2_APPDATA"] = old
        self.addCleanup(restore)

    def fake_game_dir(self, name="FakeGame") -> Path:
        """造一个「像游戏本体」的目录。"""
        p = self.tmp / name
        (p / "_packages" / "base").mkdir(parents=True)
        return p


class TestGameDirConfig(_TempAppdata):
    """核心库：设置文件 + 探测顺序。"""

    def test_config_file_lives_in_the_appdata_dir(self):
        """设置文件放在**游戏数据目录**下（不进存档目录）。"""
        p = core_paths.config_path()
        self.assertEqual(p.name, "modifier_config.json")
        self.assertEqual(p.parent, self.tmp / "appdata")
        self.assertNotIn("save", p.parts)

    def test_config_roundtrip(self):
        self.assertEqual(core_paths.read_config(), {})
        core_paths.write_config({"game_dir": "D:/x"})
        self.assertEqual(core_paths.read_config().get("game_dir"), "D:/x")

    def test_broken_config_is_treated_as_empty(self):
        p = core_paths.config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ 这不是 json", encoding="utf-8")
        self.assertEqual(core_paths.read_config(), {})

    def test_set_game_dir_rejects_a_non_game_dir(self):
        """目录里没有 `_packages` / `lib/uoc2` ⇒ 拒绝（别把用户指到错地方）。"""
        with self.assertRaises(ValueError):
            core_paths.set_game_dir(self.tmp)

    def test_set_game_dir_accepts_a_game_dir(self):
        fake = self.fake_game_dir()
        core_paths.set_game_dir(fake)
        self.assertEqual(core_paths.read_config().get("game_dir"), str(fake.resolve()))
        self.assertEqual(core_paths.detect_game_dir(), fake.resolve())

    def test_detect_game_dir_ignores_a_stale_setting(self):
        """设置文件里指的目录没了（游戏被移动）⇒ 自动忽略，继续往下找。"""
        stale = self.tmp / "gone"
        core_paths.write_config({"game_dir": str(stale)})
        found = core_paths.detect_game_dir()
        self.assertNotEqual(found, stale.resolve(),
                            "失效的设置不能被当成结果")

    def test_candidates_include_the_configured_entry(self):
        fake = self.fake_game_dir()
        core_paths.set_game_dir(fake)
        labels = [c["label"] for c in core_paths.game_dir_candidates()]
        self.assertIn("设置文件里指定的", labels)

    def test_library_scan_finds_game_dirs(self):
        """扫 Steam 库的 `steamapps/common/*`（不靠 appmanifest 的 installdir）。"""
        from unittest import mock
        lib = self.tmp / "SteamLibrary"
        game = lib / "steamapps" / "common" / "Unity of Command 2"
        (game / "_packages" / "base").mkdir(parents=True)
        with mock.patch.object(core_paths, "steam_libraries", return_value=[lib]):
            found = [p.resolve() for _label, p in core_paths.library_game_dirs()]
        self.assertIn(game.resolve(), found)


class TestSettingsApi(WebGuiTestBase, _TempAppdata):
    """服务端：读设置 / 改设置。"""

    def post(self, path, body):
        req = urllib.request.Request(
            self.url(path),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "X-Token": server_token()},
            method="POST")
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    def test_settings_reports_the_game_dir_and_candidates(self):
        d = self.get_json("/api/settings")
        for k in ("game_dir", "found", "packages", "candidates", "config_path"):
            self.assertIn(k, d)

    def test_setting_a_bad_dir_is_rejected(self):
        r = self.post("/api/settings", {"game_dir": str(self.tmp)})
        self.assertFalse(r["ok"])
        self.assertTrue(r["errors"])

    def test_setting_a_good_dir_is_saved(self):
        fake = self.fake_game_dir()
        r = self.post("/api/settings", {"game_dir": str(fake)})
        self.assertTrue(r["ok"], r.get("errors"))
        d = self.get_json("/api/settings")
        self.assertTrue(d["found"])
        self.assertEqual(d["game_dir"], str(fake.resolve()))
        self.assertEqual(core_paths.read_config().get("game_dir"), str(fake.resolve()))


def server_token() -> str:
    from save_modifier_web import server
    return server._Handler.token


class TestNoDuplicateApiDefs(unittest.TestCase):
    """⚠️ **同名 def 会覆盖前面那份** —— U69 的服务端补丁被跑了两遍，
    `api_settings` 就有了两份，后一份把前一份的字段吃掉了
    （U70 加的 `disabled_packages` 直接消失）。这里钉死。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.srv = io.open(os.path.join(root, "src", "save_modifier_web", "server.py"),
                          encoding="utf-8").read()

    def test_no_duplicate_top_level_defs(self):
        import re
        from collections import Counter
        defs = re.findall(r"^def (\w+)", self.srv, re.M)
        dups = {k: v for k, v in Counter(defs).items() if v > 1}
        self.assertEqual(dups, {}, "服务端出现重复的顶层函数定义：%s" % dups)

    def test_settings_api_is_declared_once(self):
        self.assertEqual(self.srv.count("def api_settings("), 1)
        self.assertEqual(self.srv.count("def api_settings_set("), 1)

    def test_settings_route_is_declared_once_each(self):
        self.assertEqual(self.srv.count('elif path == "/api/settings":'), 2,
                         "应当只有一条 GET 与一条 POST")


class TestU69Frontend(unittest.TestCase):
    """前端：游戏目录状态条 + 手动指定入口。"""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html = io.open(os.path.join(root, "src", "save_modifier_web", "web",
                                       "index.html"), encoding="utf-8").read()

    def test_splash_shows_the_game_dir_status(self):
        self.assertIn('id="gameDir"', self.html)
        self.assertIn("async function loadSettings()", self.html)
        self.assertIn("手动指定游戏目录", self.html)

    def test_file_picker_has_a_directory_mode(self):
        self.assertIn('FS.mode==="dir"', self.html)
        self.assertIn("用这个目录", self.html)

    def test_menu_has_the_game_dir_entry(self):
        self.assertIn('id="menuGameDir"', self.html)
        self.assertIn("游戏本体目录：", self.html)

    def test_picking_a_dir_writes_the_setting_and_reloads(self):
        self.assertIn("async function pickGameDir()", self.html)
        self.assertIn('post("/api/settings", {game_dir: dir})', self.html)
        self.assertIn("CATALOG = null;", self.html)


if __name__ == "__main__":
    unittest.main()
