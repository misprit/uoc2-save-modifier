"""实测两个系统 Python 能否真正创建 Tk 窗口（不是只 import）。"""

import sys

print("python:", sys.version.split()[0])
try:
    import tkinter as tk
    from tkinter import ttk

    print("  TkVersion const:", tk.TkVersion, "TclVersion const:", tk.TclVersion)
    root = tk.Tk()
    root.withdraw()
    print("  Tk() OK  patchlevel:", root.tk.call("info", "patchlevel"))
    print("  windowingsystem:", root.tk.call("tk", "windowingsystem"))
    style = ttk.Style(root)
    print("  themes:", style.theme_names())
    style.theme_use("clam")
    print("  clam OK")
    img = tk.PhotoImage(width=2, height=2)
    print("  PhotoImage OK")
    root.destroy()
except Exception as exc:
    import traceback

    print("  FAIL:", type(exc).__name__, exc)
    traceback.print_exc()
