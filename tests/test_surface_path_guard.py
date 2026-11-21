# -*- coding: utf-8 -*-
r"""U120：护栏 —— `/surfaces/` **不许路径穿越**（外部审阅报告 P0-1）。

**漏洞**

`server.py::find_surface` 原来只挡了 `..`：

```python
rel = (rel or "").replace("\\\\", "/").lstrip("/")
if not rel or ".." in rel.split("/"):
    return None
cand = Path(pkg) / "assets" / "surfaces" / rel
```

⚠️ `rel` 来自 HTTP 请求路径，而 `do_GET` 里有 `unquote(u.path)`
⇒ `%2e%2e%2f` 会先变成 `../` 再进来（`..` 那道闸因此是**真的**在挡，
但只挡了 `..` 这一种）。

真正的洞是**盘符**：`Path("C:/Windows/win.ini")` 在 Windows 上是
**绝对路径** ⇒ `Path(pkg) / "assets" / "surfaces" / rel` 会把前半段
**整个替换掉** ⇒ 拿到的是 `C:\Windows\win.ini` ⇒ **任意文件读取**。

**这些测试守着**

① 正常的贴图路径**照旧**能找得到（别把功能改坏了）；
② `..` / `.` / 空段 / 盘符 / 绝对路径 —— 一律**找不到**；
③ 解析后**必须仍在 `assets/surfaces/` 里面**（含符号链接 / `..` 组合）。
"""

import io
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

from save_modifier_core import CorePaths  # noqa: E402
from save_modifier_web.server import find_surface  # noqa: E402


class _FakePaths:
    """只提供 `find_surface` 用到的那一个方法。"""

    def __init__(self, packages):
        self._packages = list(packages)

    def packages(self):
        return list(self._packages)


class SurfacePathGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u120_surf_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.pkg = self.tmp / "base"
        surfaces = self.pkg / "assets" / "surfaces"
        (surfaces / "unit").mkdir(parents=True)
        self.png = surfaces / "unit" / "sheet.png"
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n")
        # 包里的秘密文件（在 surfaces 之外）
        self.secret_in_pkg = self.pkg / "secret.txt"
        self.secret_in_pkg.write_text("top secret", encoding="utf-8")
        # 包外的秘密文件
        self.secret_outside = self.tmp / "outside.txt"
        self.secret_outside.write_text("top secret", encoding="utf-8")

        self._old_discover = CorePaths.discover
        CorePaths.discover = staticmethod(lambda *a, **k: _FakePaths([self.pkg]))
        self.addCleanup(self._restore)

    def _restore(self):
        CorePaths.discover = self._old_discover

    # -------------------------------------------------- ① 正常路径照旧
    def test_a_normal_surface_is_still_found(self):
        got = find_surface("unit/sheet.png")
        self.assertIsNotNone(got, "正常贴图必须还能找得到（别把功能改坏了）")
        self.assertEqual(self.png.resolve(), got)

    def test_backslash_separators_still_work(self):
        self.assertIsNotNone(find_surface("unit\\sheet.png"))

    # -------------------------------------------------- ② 各种穿越都挡住
    def test_dotdot_is_rejected(self):
        for bad in ("../secret.txt", "unit/../../secret.txt",
                    "..", "unit/.."):
            self.assertIsNone(find_surface(bad), "不该放行：%r" % bad)

    def test_dot_segments_are_rejected(self):
        for bad in (".", "./unit/sheet.png", "unit/./sheet.png"):
            self.assertIsNone(find_surface(bad), "不该放行：%r" % bad)

    def test_absolute_path_is_rejected(self):
        """⭐ `Path("C:/Windows/win.ini")` 是绝对路径 ⇒ 会顶掉整个前缀。"""
        for bad in ("C:/Windows/win.ini", "c:\\Windows\\win.ini",
                    "C:/" + str(self.secret_outside).lstrip("/")):
            self.assertIsNone(find_surface(bad), "不该放行：%r" % bad)

    def test_a_real_absolute_path_outside_the_game_is_rejected(self):
        bad = str(self.secret_outside).replace("\\", "/")
        self.assertIsNone(find_surface(bad))

    def test_empty_and_slash_only_are_rejected(self):
        for bad in ("", "/", "//", "/unit/sheet.png"):
            self.assertIsNone(find_surface(bad), "不该放行：%r" % bad)

    # -------------------------------------------------- ③ 结果一定在 surfaces 里
    def test_the_result_is_always_inside_the_surfaces_dir(self):
        """就算以后有人改了白名单，最后一道闸（解析后仍在 surfaces 里）也得在。"""
        for probe in ("unit/sheet.png", "../secret.txt",
                      str(self.secret_outside).replace("\\", "/"),
                      "unit/../../secret.txt"):
            got = find_surface(probe)
            if got is None:
                continue
            base = (self.pkg / "assets" / "surfaces").resolve()
            self.assertIn(base, got.resolve().parents,
                          "返回的文件跑到 surfaces 外面去了：%r" % probe)


if __name__ == "__main__":
    unittest.main()
