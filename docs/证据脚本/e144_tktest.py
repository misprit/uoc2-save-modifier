"""在 scratch 里给随包 runtime 补 tcl/tk，并端到端验证 Tk 能否开窗。

材料全部来自本机已有文件，不联网：
* _tkinter.pyd / tcl86t.dll / tk86t.dll  ←  Unity of Command 2\\lib
* tkinter/ (纯 Python)                   ←  Unity of Command 2\\lib
* tcl8.6/ tk8.6/ (Tcl 脚本库)            ←  Unity of Command 2\\share
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

GAME = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2")
SRC = Path(r"E:\Workspace\projects\统一指挥数据整理\uoc2-save-modifier\python")
DST = Path(r"D:\MiniMax\_analysis\pytk3\python")

if DST.exists():
    shutil.rmtree(DST)
DST.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(SRC, DST)
print(f"复制基线 runtime -> {DST}")

pairs = [
    (GAME / "lib" / "_tkinter.pyd", DST / "_tkinter.pyd"),
    (GAME / "lib" / "tcl86t.dll", DST / "tcl86t.dll"),
    (GAME / "lib" / "tk86t.dll", DST / "tk86t.dll"),
    (GAME / "lib" / "zlib1.dll", DST / "zlib1.dll"),  # tcl86t.dll 的依赖
]
for src, dst in pairs:
    shutil.copy2(src, dst)
    print(f"  + {dst.name} ({dst.stat().st_size})")

sys_tkinter = Path(r"C:\Users\misprit\AppData\Local\Python\pythoncore-3.14-64\Lib\tkinter")
shutil.copytree(sys_tkinter, DST / "Lib" / "site-packages" / "tkinter")
shutil.copytree(GAME / "share" / "tcl8.6", DST / "tcl8.6")
shutil.copytree(GAME / "share" / "tk8.6", DST / "tk8.6")
print("  + tkinter/ (纯 Python，取自系统 3.14.7 源码包)")
print("  + tcl8.6/ tk8.6/ (脚本库)")

total = sum(f.stat().st_size for f in DST.rglob("*") if f.is_file())
print(f"补齐后体积：{total/1024/1024:.1f} MB")

env = {
    "TCL_LIBRARY": str(DST / "tcl8.6"),
    "TK_LIBRARY": str(DST / "tk8.6"),
    "PATH": r"C:\Windows\System32;C:\Windows",
    "SystemRoot": r"C:\Windows",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
}
print("\n=== 建窗实测 ===")
proc = subprocess.run(
    [str(DST / "python.exe"), r"D:\MiniMax\_analysis\e142_tkreal.py"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env=env,
    timeout=90,
)
print(proc.stdout)
if proc.stderr and proc.stderr.strip():
    print("STDERR:", proc.stderr[-2000:])
print("exit:", proc.returncode)
