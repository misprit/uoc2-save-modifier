# -*- coding: utf-8 -*-
"""编译启动器 exe（**零第三方工具链** —— 用系统自带的 csc.exe）。

```
.\\python\\python.exe tools\\build_launcher.py
```

产物：`build\\统一指挥2存档修改器.exe`（约 20–40 KB），由 `tools/build_dist.py` 打进包根。

⚠️ 为什么不用 PyInstaller：
* 它每次启动都要把 20 MB 的运行时解包到 `%TEMP%`（慢 1–3 秒）；
* 未签名的 onefile exe 更容易被杀软启发式盯上；
* 而本启动器只是「起服务 + 开窗口」，**不需要带 Python**（Python 在包里）。
⇒ 用 .NET Framework 4.x 自带的 `csc.exe` 编译一个几十 KB 的壳，最省最稳。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "tools" / "launcher" / "Launcher.cs"
OUT_DIR = REPO / "build"
NAME = "统一指挥2存档修改器.exe"
OUT = OUT_DIR / NAME

#: .NET Framework 自带的 csc.exe（本机 Windows 10/11 都有）
CSC_CANDIDATES = (
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
)


def find_csc() -> str | None:
    for p in CSC_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def main() -> int:
    if not SRC.is_file():
        print("!! 找不到 %s" % SRC)
        return 1
    csc = find_csc()
    if not csc:
        print("!! 找不到系统自带的 csc.exe（.NET Framework 4.x）—— "
              "换台装了 .NET Framework 的 Windows 再试。")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        csc, "/nologo", "/target:winexe", "/optimize+", "/platform:anycpu",
        "/reference:System.dll", "/reference:System.Windows.Forms.dll",
        "/out:%s" % OUT, str(SRC),
    ]
    r = subprocess.run(cmd, capture_output=True)
    txt = (r.stdout.decode("utf-8", "replace")
           + r.stderr.decode("utf-8", "replace")).strip()
    if r.returncode != 0 or not OUT.is_file():
        print("!! 编译失败（rc=%d）：\n%s" % (r.returncode, txt))
        return 1
    size = OUT.stat().st_size
    print("启动器编译 OK：%s（%.1f KB）" % (OUT.name, size / 1024.0))
    if txt:
        print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
