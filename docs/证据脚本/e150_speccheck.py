"""用 Python 复查特种兵目录内容（PowerShell 那次返回空，可疑）。"""

from __future__ import annotations

from pathlib import Path

S = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\assets\surfaces\specialist")

dirs = sorted(p for p in S.iterdir() if p.is_dir())
print(f"目录数: {len(dirs)}")

target = "bul_s_towed_at_dlc9"
for p in dirs:
    if p.name == target:
        files = sorted(f.name for f in p.iterdir())
        print(f"{target}: {len(files)} 个文件 -> {files}")

# 全量统计
import collections

missing = collections.Counter()
empty = []
for p in dirs:
    names = {f.name for f in p.iterdir() if f.suffix.lower() == ".png"}
    if not names:
        empty.append(p.name)
    for f in ("sheet_act.png", "sheet_sup.png", "status_act.png", "status_sup.png",
              "sheet_large.png", "hq_action_icon.png", "hq_menu_icon.png"):
        if f not in names:
            missing[f] += 1
print("空目录:", empty)
print("各文件缺失数:", dict(missing))

# 目录名里有没有不可见字符
weird = [p.name for p in dirs if p.name != p.name.strip() or any(ord(c) > 127 for c in p.name)]
print("目录名含不可见/非 ASCII:", weird[:10])
