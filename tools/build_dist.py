"""打成品包：`dist/uoc2-save-modifier-v1.0.0.zip`。

**为什么要有这个脚本**：成品 zip 之前是一次性手工打的，
下次想重打只能靠回忆 —— 这个脚本把「打进去什么 / 不打什么」写死下来。

成品形态（开发规范 §0.1）：**解压即用** —— 解压后双击 `run.bat` 即可。
zip 里有一个顶层目录 `uoc2-save-modifier/`，**不是**散文件。

打进去的
--------
```
uoc2-save-modifier/
  python/            Python 3.14 运行时（含 PyYAML）
  src/               核心库 + 命令行外壳 + Web GUI
  tests/             自动化测试
  docs/              规范文档 + 证据脚本
  run.bat            双击启动（命令行外壳）
  run_web.bat        双击启动（★ 正式界面：本地 HTTP + 浏览器窗口）
  run_tests.bat      跑自检
  使用说明.txt
```

**不打进去的**
* `dist/` 自身、`__pycache__/`、`*.pyc` —— 构建产物与缓存；
* 仓库根的 `*.usg` 存档样本 —— **玩家的存档不进包**（`.gitignore` 也忽略）；
* `config/` `config.yml` `data/`（**仅仓库根层级**）—— 本机配置与运行时状态；
* `docs/证据脚本/v6_check.txt` —— 终检输出（生成物）。

⚠️ **`src/save_modifier_core/data/` 要进包** —— 那是**内置索引**
（`campaign_index.json`，U18 起，33.5 KB）⇒ 战役只读页的「会议→可选场景」靠它。
漏掉它 ⇒ 换台机器就降级成「没有会议→场景列表」。

跑法（仓库根目录）：
```
.\\python\\python.exe tools\\build_dist.py
```

⚠️ `.bat` 必须保持 **纯 ASCII + CRLF** —— 打包脚本只**复制**，不重写，
所以不会破坏它们的行尾（用 `write`/`edit` 改 `.bat` 时才要注意）。
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "dist"
PKG_NAME = "uoc2-save-modifier"
def _product_version():
    """成品版本号的**唯一来源** = `src/save_modifier_web/version.py`。

    ⚠️ **不是**核心库的 `__version__`（那是「库」的版本 0.1.0）。
    """
    src = io.open(REPO / "src" / "save_modifier_web" / "version.py",
                  encoding="utf-8").read()
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', src, re.M)
    return m.group(1) if m else "0.0.0"


VERSION = _product_version()
OUT = OUT_DIR / f"{PKG_NAME}-v{VERSION}.zip"

#: 整个目录打进去
#:
#: ⚠️ **不含 `lib/`**（U78）—— 那是 Tcl/Tk 8.6 的脚本库，只有 Tk 界面要；
#:    正式界面是 Web 版（本地 HTTP + Edge）⇒ 不带，**省 4.55 MB**。
INCLUDE_DIRS = ("python", "src", "tests", "docs")

#: 启动器 exe（U80）—— 编译产物，**放包根**（用户就点它）
LAUNCHER_NAME = "统一指挥2存档修改器.exe"
LAUNCHER_SRC = "build/" + LAUNCHER_NAME

#: 单个文件打进去
#:
#: ⚠️ **不含 `run_gui.bat`**（U78）—— 那是 Tk 备用简版的入口；
#:    「Windows 自带 Edge」⇒ 不带无浏览器兼容层（用户 2026-11-19 拍板）。
INCLUDE_FILES = ("run.bat", "run_web.bat", "run_tests.bat", "使用说明.txt")

#: 目录名黑名单（任意层级）
#:
#: ⚠️ **`data` 只在仓库根层级跳过** —— `src/save_modifier_core/data/`
#:    装的是**内置索引**（campaign_index.json，U18 起），
#:    漏掉它 ⇒ 战役只读页在别的机器上降级成「没有会议→场景列表」。
#: ⚠️ `_edge_profile` 是 **U26 Web GUI 的运行时 profile**（Edge 自己的
#:    独立用户目录）—— 它是**缓存**，不进包。
SKIP_DIRS = {"__pycache__", ".git", ".gitignore", "dist",
             ".pytest_cache", ".idea", ".vscode", "_edge_profile",
             # U170：临时产物目录（会话与工具的中间文件）—— 绝不进成品
             ".scratch",
             # U142：只读审阅通道的目录（.review/）与它的写权限探针（_probe*）
             # —— **绝不**进成品（`python/`、`src/`、`tests/`、`docs/` 都会被打包）。
             ".review"}

#: 只在**仓库根层级**跳过的目录名
SKIP_DIRS_ROOT = {"data"}

#: U78：**不打包**的 Tk 那套（Web 界面用不上）⇒ 省 8.5 MB
#:
#: * `lib/` 整个目录（Tcl/Tk 脚本库）；
#: * `python/` 里的 Tk 运行时（DLL + tkinter 包）；
#: * `src/save_modifier_gui/`（Tk 界面 —— **仓库里保留**，只是不打进包）；
#: * `tests/test_gui_smoke.py`（Tk 界面的冒烟测试）。
SKIP_PATHS = (
    "lib",
    # U79：**用不上的运行时**（实测省 8.79 MB）
    #   * `libcrypto-3.dll` 只有 `_hashlib.pyd` 用 ⇒ 砍了 hashlib 回退到内置
    #     `_sha256`（实测 sha256 仍对；撤销栈就靠它）
    #   * `libssl-3.dll` / `_ssl.pyd`：只起本地 HTTP，不用 TLS
    #   * `sqlite3.dll` / `_sqlite3.pyd`：不用 sqlite
    #   * `python.cat`：调试符号目录；`_zstd.pyd`：我们的 zip 用 zlib
    "python/libcrypto-3.dll",
    "python/libssl-3.dll",
    "python/_ssl.pyd",
    "python/sqlite3.dll",
    "python/_sqlite3.pyd",
    "python/python.cat",
    "python/_zstd.pyd",
    "python/_remote_debugging.pyd",
    "python/_wmi.pyd",
    "python/_multiprocessing.pyd",
    "python/_queue.pyd",
    "python/_tkinter.pyd",
    "python/tcl86t.dll",
    "python/tk86t.dll",
    "python/zlib1.dll",
    "python/Lib/site-packages/tkinter",
    "src/save_modifier_gui",
    "tests/test_gui_smoke.py",
)


def _skipped(rel: Path) -> bool:
    """rel（相对仓库根）是否命中「不打包」清单。"""
    s = rel.as_posix()
    for p in SKIP_PATHS:
        if s == p or s.startswith(p + "/"):
            return True
    return False

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
    # U142：审阅通道的写权限探针（`_probe.py` 之类）—— 不是产品的一部分
    if rel.name.startswith("_probe"):
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
            if _skipped(rel):
                continue
            # 根层级的 data/（运行时状态）不进包；包内的 src/*/data/ 要进
            if rel.parts and rel.parts[0] in SKIP_DIRS_ROOT:
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
    # 启动器（放**包根** ⇒ 用户一眼看到）
    lp = REPO / LAUNCHER_SRC
    if lp.is_file():
        out.append((lp, f"{PKG_NAME}/{LAUNCHER_NAME}"))
    else:
        print(f"  ! 没有启动器 exe（先跑 tools/build_launcher.py）：{LAUNCHER_SRC}")
    return out


def main() -> int:
    # 启动器：没有就现编一个（用系统自带的 csc.exe，零第三方工具链）
    if not (REPO / LAUNCHER_SRC).is_file():
        import subprocess
        r = subprocess.run([str(REPO / "python" / "python.exe"),
                            str(REPO / "tools" / "build_launcher.py")],
                           cwd=REPO, capture_output=True)
        msg = (r.stdout.decode("utf-8", "replace")
               + r.stderr.decode("utf-8", "replace")).strip()
        if msg:
            print(msg)
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
        f"{PKG_NAME}/run_web.bat",                           # U26 Web GUI 入口
        f"{PKG_NAME}/src/save_modifier_web/__init__.py",
        f"{PKG_NAME}/src/save_modifier_web/server.py",
        f"{PKG_NAME}/src/save_modifier_web/web/index.html",  # U26 界面层（HTML/CSS）
        f"{PKG_NAME}/src/save_modifier_core/__init__.py",
        f"{PKG_NAME}/src/save_modifier_core/locale.py",
        f"{PKG_NAME}/src/save_modifier_core/campaigns.py",            # U18 战役只读
        f"{PKG_NAME}/src/save_modifier_core/data/campaign_index.json",  # U18 内置索引（33.5 KB）
        f"{PKG_NAME}/src/save_modifier_web/server.py",
        f"{PKG_NAME}/src/save_modifier_web/web/index.html",
        f"{PKG_NAME}/python/python314.zip",          # 标准库
        f"{PKG_NAME}/python/Lib/site-packages/yaml/__init__.py",
        f"{PKG_NAME}/python/Lib/site-packages/yaml/_yaml.cp314-win_amd64.pyd",
        f"{PKG_NAME}/tests/test_api_contract.py",
        # U74/U75 新增的（之前漏了 ⇒ 打出来的包可能缺东西却照样「自检 OK」）
        f"{PKG_NAME}/run_web.bat",
        f"{PKG_NAME}/run_tests.bat",
        f"{PKG_NAME}/使用说明.txt",
        f"{PKG_NAME}/src/save_modifier_web/web/i18n.json",
        f"{PKG_NAME}/src/save_modifier_web/version.py",
        f"{PKG_NAME}/{LAUNCHER_NAME}",
    ]
    missing = [m for m in must if m not in names]
    if missing:
        print("!! 缺少必需条目：")
        for m in missing:
            print("   ", m)
        return 1
    print("自检 OK：启动器 exe / run.bat / run_web.bat / 核心库 / Web GUI / locale / "
          "战役索引 / i18n 词表 / PyYAML / 使用说明 都在包里")
    return 0


if __name__ == "__main__":
    sys.exit(main())
