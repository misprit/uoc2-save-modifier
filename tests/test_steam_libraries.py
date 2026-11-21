# -*- coding: utf-8 -*-
"""U122：护栏 —— Steam 库清单文件是 **`libraryfolders.vdf`**（外部审阅报告 P1-6）。

**漏洞**

`paths.py::steam_libraries()` 原来读的是 `libraryfolders.vcf` ——
**这个文件根本不存在**（Steam 写的是 `.vdf`；本机实测也只有 `.vdf`）
⇒ 「装在别的盘上的库」**一个都发现不了** ⇒ 找不到游戏本体。

**这些测试守着**

① 造的 `libraryfolders.vdf` 里列出来的库 ⇒ **必须**被 `steam_libraries()` 找到；
② `steamapps/` 与 `config/` 两处都读；
③ 源码里**不许**再出现 `libraryfolders.vcf`（别改回去）。
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

from save_modifier_core import paths as core_paths  # noqa: E402
from save_modifier_core.paths import steam_libraries  # noqa: E402


def _vdf(lib_path: Path) -> str:
    """仿 Valve 的 VDF：路径里的反斜杠是**转义**过的（`\\\\`）。"""
    return (
        '"libraryfolders"\n'
        '{\n'
        '\t"0"\n'
        '\t{\n'
        '\t\t"path"\t\t"%s"\n'
        '\t\t"label"\t\t""\n'
        '\t\t"contentid"\t\t"123"\n'
        '\t\t"apps"\n'
        '\t\t{\n'
        '\t\t\t"228980"\t\t"2344520"\n'
        '\t\t}\n'
        '\t}\n'
        '}\n' % str(lib_path).replace("\\", "\\\\")
    )


class SteamLibraryFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u122_steam_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "Steam"
        self.lib = self.tmp / "SteamLibrary"
        (self.root / "steamapps").mkdir(parents=True)
        self.lib.mkdir(parents=True)

        self._old_root = core_paths._steam_root
        core_paths._steam_root = lambda: self.root
        self.addCleanup(self._restore)

    def _restore(self):
        core_paths._steam_root = self._old_root

    def test_the_library_from_the_vdf_is_found(self):
        """⭐ `steamapps/libraryfolders.vdf` 里列出来的库必须被找到。"""
        (self.root / "steamapps" / "libraryfolders.vdf").write_text(
            _vdf(self.lib), encoding="utf-8")
        libs = steam_libraries()
        self.assertIn(self.lib.resolve(), [p.resolve() for p in libs],
                      "装在别的盘上的 Steam 库没被发现（.vdf 读不到）")

    def test_the_config_copy_is_read_too(self):
        """有些安装在 `config/libraryfolders.vdf` 里也有一份 ⇒ 两处都读。"""
        (self.root / "config").mkdir(parents=True)
        (self.root / "config" / "libraryfolders.vdf").write_text(
            _vdf(self.lib), encoding="utf-8")
        libs = steam_libraries()
        self.assertIn(self.lib.resolve(), [p.resolve() for p in libs])

    def test_a_missing_file_does_not_break_anything(self):
        """没有这个文件 ⇒ 不报错（只是没有额外库）。"""
        libs = steam_libraries()
        self.assertIn(self.root.resolve(), [p.resolve() for p in libs])

    def test_the_source_no_longer_says_vcf(self):
        """别把文件名改回去。"""
        p = os.path.join(REPO_SRC, "save_modifier_core", "paths.py")
        with io.open(p, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("libraryfolders.vcf", src)
        self.assertIn("libraryfolders.vdf", src)


if __name__ == "__main__":
    unittest.main()
