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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_web import server  # noqa: E402

from ._fixtures import make_save  # noqa: E402


class SaveIdBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u126_sid_"))
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
        for bad in ("../secret.usg", "campaigns/../../secret.usg",
                    "campaigns/../../../secret.usg"):
            with self.assertRaises(ValueError, msg="不该放行：%r" % bad):
                server._save_id_checked(bad)

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
