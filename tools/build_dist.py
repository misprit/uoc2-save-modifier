"""打成品包：`dist/uoc2-save-modifier-v1.0.0.zip`。

**为什么要有这个脚本**：成品 zip 之前是一次性手工打的，
下次想重打只能靠回忆 —— 这个脚本把「打进去什么 / 不打什么」写死下来。

成品形态（开发规范 §0.1）：**解压即用** —— 解压后双击 `run.bat` 即可。
zip 里有一个顶层目录 `uoc2-save-modifier/`，**不是**散文件。

打进去的
--------
```
uoc2-save-modifier/
  python/            Python 3.14 运行时（含 PyYAML + tkinter）
  lib/{tcl8.6,tk8.6} Tcl/Tk 脚本库（Tcl 的 <prefix> 是包根 ⇒ 必须在 lib/）
  src/               核心库 + 命令行外壳 + GUI
  tests/             自动化测试
  docs/              规范文档 + 证据脚本
  run.bat            双击启动（命令行外壳）
  run_gui.bat        双击启动（图形界面）
  run_tests.bat      跑自检
  使用说明.txt
```

**不打进去的**
* `dist/` 自身、`__pycache__/`、`*.pyc` —— 构建产物与缓存；
* 仓库根的 `*.usg` 存档样本 —— **玩家的存档不进包**（`.gitignore` 也忽略）；
* `config/` `config.yml` `data/` —— 本机配置与运行时状态；
* `docs/证据脚本/v6_check.txt` —— 终检输出（生成物）。

跑法（仓库根目录）：
```
.\\python\\python.exe tools\\build_dist.py
```

⚠️ `.bat` 必须保持 **纯 ASCII + CRLF** —— 打包脚本只**复制**，不重写，
所以不会破坏它们的行尾（用 `write`/`edit` 改 `.bat` 时才要注意）。
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "dist"
PKG_NAME = "uoc2-save-modifier"
VERSION = "1.0.0"
OUT = OUT_DIR / f"{PKG_NAME}-v{VERSION}.zip"

#: 整个目录打进去
INCLUDE_DIRS = ("python", "lib", "src", "tests", "docs")

#: 单个文件打进去
INCLUDE_FILES = ("run.bat", "run_gui.bat", "run_tests.bat", "使用说明.txt")

#: 目录名黑名单（任意层级）
SKIP_DIRS = {"__pycache__", ".git", ".gitignore", "dist", "data",
             ".pytest_cache", ".idea", ".vscode"}

#: 文件名 / 后缀黑名单
#:
#: ⚠️ **不要排除 `.pyd`** —— `yaml/_yaml.cp314-win_amd64.pyd` 与 `_tkinter.pyd`
#: 是必需的 C 扩展（开发规范 §0.1 第 51 条）。
#: ⚠️ **也不要排除 `.zip`** —— `python/python314.zip` 是整个标准库。
SKIP_SUFFIXES = (".pyc", ".pyo", ".usg")
SKIP_NAMES = {"v6_check.txt", "Thumbs.db", "desktop.ini", ".DS_Store"}


def _skip_file(rel: Path) -> bool:
    if rel.name in SKIP_NAMES:
        return True
    if rel.suffix.lower() in SKIP_SUFFIXES:
        return True
    # 玩家的存档 / 撤销栈不该进包
    if rel.name.endswith(".undo.json"):
        return True
    return False


def collect() -> list[tuple[Path, str]]:
    """返回 [(磁盘路径, zip 内条目名)]。"""
    out: list[tuple[Path, str]] = []
    for d in INCLUDE_DIRS:
        base = REPO / d
        if not base.is_dir():
            print(f"  ! 跳过不存在的目录：{d}")
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(REPO)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if _skip_file(rel):
                continue
            out.append((p, f"{PKG_NAME}/{rel.as_posix()}"))
    for f in INCLUDE_FILES:
        p = REPO / f
        if p.is_file():
            out.append((p, f"{PKG_NAME}/{f}"))
        else:
            print(f"  ! 跳过不存在的文件：{f}")
    return out


def main() -> int:
    items = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 用固定时间戳 ⇒ 同样的输入打出同样的包（可复现）
    stamp = (2026, 11, 18, 0, 0, 0)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src, arc in items:
            zi = zipfile.ZipInfo(arc, date_time=stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zi.create_system = 0
            zf.writestr(zi, src.read_bytes())

    size = OUT.stat().st_size
    print(f"已打包 {len(items)} 个文件 → {OUT}")
    print(f"大小 {size / 1024 / 1024:.1f} MB")

    # 自检：能不能打开、核心库在不在、run.bat 在不在
    with zipfile.ZipFile(OUT) as zf:
        bad = zf.testzip()
        if bad:
            print(f"!! ZIP 损坏：{bad}")
            return 1
        names = set(zf.namelist())
    must = [
        f"{PKG_NAME}/run.bat",
        f"{PKG_NAME}/run_gui.bat",
        f"{PKG_NAME}/src/save_modifier_core/__init__.py",
        f"{PKG_NAME}/src/save_modifier_core/locale.py",
        f"{PKG_NAME}/src/save_modifier_gui/__init__.py",
        f"{PKG_NAME}/src/save_modifier_gui/main.py",
        f"{PKG_NAME}/src/save_modifier_gui/app.py",
        f"{PKG_NAME}/src/save_modifier_gui/theme.py",
        f"{PKG_NAME}/src/save_modifier_gui/names.py",
        f"{PKG_NAME}/src/save_modifier_gui/splash.py",
        f"{PKG_NAME}/src/save_modifier_gui/pages/__init__.py",
        f"{PKG_NAME}/lib/tcl8.6/init.tcl",
        f"{PKG_NAME}/lib/tk8.6/ttk/ttk.tcl",
        f"{PKG_NAME}/python/python314.zip",          # 标准库
        f"{PKG_NAME}/python/_tkinter.pyd",          # Tk 的 C 扩展
        f"{PKG_NAME}/python/tcl86t.dll",
        f"{PKG_NAME}/python/Lib/site-packages/yaml/__init__.py",
        f"{PKG_NAME}/python/Lib/site-packages/yaml/_yaml.cp314-win_amd64.pyd",
        f"{PKG_NAME}/python/Lib/site-packages/tkinter/__init__.py",
        f"{PKG_NAME}/tests/test_api_contract.py",
    ]
    missing = [m for m in must if m not in names]
    if missing:
        print("!! 缺少必需条目：")
        for m in missing:
            print("   ", m)
        return 1
    print("自检 OK：run.bat / run_gui.bat / 核心库 / GUI / locale / Tcl-Tk / PyYAML / tkinter 都在包里")
    return 0


if __name__ == "__main__":
    sys.exit(main())
