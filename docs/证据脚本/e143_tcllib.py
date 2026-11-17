"""问 Tk 自己的 Tcl 解释器：脚本库和 DLL 到底从哪加载的。"""

import os
import sys

import tkinter as tk

print("python:", sys.version.split()[0], sys.executable)
for var in ("TCL_LIBRARY", "TK_LIBRARY", "PATH"):
    val = os.environ.get(var, "")
    if var == "PATH":
        val = "..." + val[-120:]
    print(f"  env {var} = {val}")

root = tk.Tk()
root.withdraw()
print("  info library      :", root.tk.eval("info library"))
print("  auto_path         :", root.tk.eval("set auto_path"))
print("  tcl_libraryPath  :", root.tk.eval("set tcl_libraryPath"))
print("  pkg require Tcl   :", root.tk.eval("info patchlevel"))
root.destroy()
