"""GUI 的命令行入口 —— `python -m save_modifier_gui.main`。

用法：
```
python -m save_modifier_gui.main          # 启动 GUI
python -m save_modifier_gui.main --check  # 只自检（不弹窗），给 CI / 排障用
```

⚠️ `--check` 会**建一个窗口再立刻关掉** —— 用来验证 Tcl/Tk 在当前机器上
能不能起来（随包 runtime、缺 zlib1.dll、缺 tcl 脚本库…… 都会在这里暴露）。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[1]
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))


def _check() -> int:
    """自检：Tk 能不能起来 + 核心库能不能 import + 存档能不能列。"""
    ok = True
    try:
        import tkinter as tk
        from tkinter import ttk  # noqa: F401  —— ttk 缺失是常见坑
        print(f"[OK ] tkinter {tk.TkVersion} + ttk")
    except Exception as exc:
        print(f"[NG ] tkinter/ttk 不可用：{exc}")
        return 1
    try:
        root = tk.Tk()
        root.withdraw()
        print(f"[OK ] Tk() 起来了（屏幕 {root.winfo_screenwidth()}x"
              f"{root.winfo_screenheight()}）")
        root.destroy()
    except Exception as exc:
        print(f"[NG ] Tk() 起不来：{exc}")
        ok = False
    try:
        from save_modifier_core import list_saves
        n = len(list_saves())
        print(f"[OK ] 核心库可用，列到 {n} 个存档")
    except Exception as exc:
        print(f"[NG ] 核心库不可用：{exc}")
        ok = False
    try:
        from save_modifier_gui.theme import apply_theme
        from save_modifier_gui.app import Application
        print("[OK ] GUI 模块可导入")
    except Exception as exc:
        print(f"[NG ] GUI 模块不可用：{exc}")
        ok = False
    print("自检" + ("通过" if ok else "失败"))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return _check()
    from save_modifier_gui.app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
