"""严格核对视觉稿引用的贴图（按 JS 数组解析，不误伤 PALETTE）。"""

from __future__ import annotations

import re
from pathlib import Path

HTML = Path(r"E:\Workspace\projects\统一指挥数据整理\uoc2-save-modifier\docs\GUI视觉稿.html")
SUR = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\assets\surfaces")

text = HTML.read_text(encoding="utf-8")
bad: list[str] = []


def check(rel: str, label: str) -> None:
    p = SUR / rel
    ok = p.is_file()
    if not ok:
        bad.append(rel)
    print(f"  {'OK  ' if ok else 'MISS'}  {label:<26} {rel}")


# UNITS 数组
print("=== UNITS（单位头像 sheet_L / sheet_l）===")
for t in re.findall(r'\{t:"([^"]+)"', text):
    d = SUR / "unit" / t
    hit = next((n for n in ("sheet_L.png", "sheet_l.png") if (d / n).is_file()), None)
    if hit is None:
        bad.append(f"unit/{t}")
        print(f"  MISS  {t}")
    else:
        print(f"  OK    {t:<26} {hit}")

# SPECIALISTS 数组
print("\n=== SPECIALISTS（hq_action_icon）===")
block = re.search(r"const SPECIALISTS = \[(.*?)\];", text, re.S).group(1)
for t in re.findall(r'\["([a-z0-9_]+)","', block):
    check(f"specialist/{t}/hq_action_icon.png", t)

# THEATER 数组
print("\n=== THEATER（四态）===")
block = re.search(r"const THEATER = \[(.*?)\];", text, re.S).group(1)
for t in re.findall(r'\["([a-z0-9_]+)","', block):
    for st in ("neutral", "hover", "down", "disabled"):
        check(f"theater/{t}_{st}.png", f"{t}/{st}")

# 字面量
print("\n=== 字面量引用 ===")
for r in sorted(set(re.findall(r'SUR\+"([^"+]+/[^"]+)"', text))):
    check(r, "literal")

print("\n缺失合计:", len(bad))
for b in bad:
    print("   MISSING:", b)
