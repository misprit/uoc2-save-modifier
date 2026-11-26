# -*- coding: utf-8 -*-
"""U126：护栏 —— `save_id` **不许越界**出存档目录（外部审阅报告 P1-2）。

**漏洞**

`save_id` 来自 HTTP 请求（query / body）⇒ **不能直接信**。
核心库的 `resolve_save_id` 明确**允许绝对路径** ⇒ 传
`C:\\Windows\\win.ini` 就会把**任意文件**当成存档打开；
`api_save_as` 还会把它**复制**到玩家选的位置 ⇒ 任意文件读取 + 外传。

**这些测试守着**

① 存档根**之内**的相对路径 ⇒ 照旧能用；
② 绝对路径（存档根外）⇒ **拒绝**；
③ `..` 越界 ⇒ **拒绝**；
④ 空 `save_id` ⇒ **拒绝**；
⑤ 服务端的接口（`api_view` 等）同样受这条约束。
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_web import server  # noqa: E402

from ._fixtures import make_save  # noqa: E402


class SaveIdBoundaryTest(unittest.TestCase):
    def setUp(self):
        scratch = Path(REPO) / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="u126_sid_", dir=scratch))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.appdata = self.tmp / ".uoc2"
        self.save_dir = self.appdata / "save" / "campaigns"
        self.save_dir.mkdir(parents=True)
        self.save_file = make_save(self.save_dir / "test.usg")
        # 存档根**外面**的一个文件
        self.outside = self.tmp / "secret.usg"
        make_save(self.outside)

        self._old = os.environ.get("UOC2_APPDATA")
        os.environ["UOC2_APPDATA"] = str(self.appdata)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._old is None:
            os.environ.pop("UOC2_APPDATA", None)
        else:
            os.environ["UOC2_APPDATA"] = self._old

    # -------------------------------------------------- ① 里面照旧能用
    def test_a_relative_id_inside_the_save_root_works(self):
        got = server._save_id_checked("campaigns/test.usg")
        self.assertEqual("campaigns/test.usg", got)

    def test_the_api_can_still_open_a_real_save(self):
        data = server.api_view("campaigns/test.usg")
        self.assertIn("_save_id", data)

    # -------------------------------------------------- ② 绝对路径被拒
    def test_an_absolute_path_outside_the_save_root_is_rejected(self):
        for bad in (str(self.outside), "C:/Windows/win.ini",
                    "C:\\Windows\\win.ini"):
            with self.assertRaises(ValueError, msg="不该放行：%r" % bad):
                server._save_id_checked(bad)

    def test_the_api_rejects_an_out_of_bounds_id(self):
        with self.assertRaises(ValueError):
            server.api_view(str(self.outside))

    # -------------------------------------------------- ③ `..` 越界
    def test_dotdot_is_rejected(self):
        """`..` 爬出**游戏数据目录** ⇒ 拒绝。"""
        for bad in ("campaigns/../../../secret.usg",
                    "../../secret.usg",
                    "../../../secret.usg"):
            with self.assertRaises(ValueError, msg="不该放行：%r" % bad):
                server._save_id_checked(bad)

    def test_the_import_folder_is_allowed(self):
        """⭐ 导入 .usg 生成的副本在 `<游戏数据目录>/modifier_imports/`
        —— **不在存档根里**，但它是合法流程 ⇒ 必须放行。"""
        imp = self.appdata / "modifier_imports"
        imp.mkdir(parents=True)
        copy = imp / "imported.usg"
        copy.write_bytes(b"PK")
        got = server._save_id_checked(str(copy))
        self.assertTrue(got.endswith("imported.usg"), got)

    def test_only_portable_imported_saves_are_allowed_outside_appdata(self):
        home = self.tmp / "portable"
        with patch("save_modifier_core.paths.modifier_home", return_value=home):
            imported = home / "data" / "imports" / "copy.usg"
            self.assertEqual(str(imported), server._save_id_checked(str(imported)))
            for other in (home / "data" / "copy.usg", home / "bak" / "copy.usg",
                          imported.with_suffix(".ini")):
                with self.assertRaises(ValueError):
                    server._save_id_checked(str(other))

    def test_profile_creation_failure_closes_service_without_launching_edge(self):
        from unittest.mock import MagicMock
        httpd = MagicMock(server_address=("127.0.0.1", 23))
        with (patch.object(server, "ThreadingHTTPServer", return_value=httpd),
              patch.object(server, "_log_startup"), patch.object(server, "find_edge", return_value="edge"),
              patch("save_modifier_core.paths.modifier_profile_dir", return_value=self.outside / "profile"),
              patch.object(server.subprocess, "Popen") as launch, patch("builtins.print") as output):
            self.assertEqual(1, server.run())
        self.assertIn(str(self.outside / "profile"), output.call_args.args[0])
        httpd.shutdown.assert_called_once()
        httpd.server_close.assert_called_once()
        launch.assert_not_called()

    def test_the_game_data_dir_is_the_sandbox(self):
        """边界 = **游戏数据目录**（`<本地应用数据>/.uoc2`）——
        目录**里面**的东西（游戏自己的设置、撤销栈…）不算越界。"""
        got = server._save_id_checked("../settings.yml")
        self.assertTrue(got.endswith("settings.yml"), got)

    def test_a_dotdot_that_stays_inside_the_root_is_fine(self):
        """`campaigns/../x.usg` 解析后**仍在存档根里** ⇒ 不是越界。"""
        got = server._save_id_checked("campaigns/../test.usg")
        self.assertEqual("test.usg", got)

    # -------------------------------------------------- ④ 空
    def test_an_empty_id_is_rejected(self):
        for bad in ("", "   ", None):
            with self.assertRaises(ValueError):
                server._save_id_checked(bad)

    def test_the_save_root_itself_is_rejected(self):
        with self.assertRaises(ValueError):
            server._save_id_checked(str(self.appdata / "save"))


if __name__ == "__main__":
    unittest.main()
