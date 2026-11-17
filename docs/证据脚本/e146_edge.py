"""边角数据：1 个缺 7 图的特种兵类型、1 个小写 sheet_l.png 的单位类型、战区资产名。"""

from __future__ import annotations

from pathlib import Path

SUR = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\assets\surfaces")

print("=== 特种兵：缺图的那个 ===")
for p in sorted(x for x in (SUR / "specialist").iterdir() if x.is_dir()):
    if not (p / "sheet_large.png").is_file():
        have = sorted(f.name for f in p.iterdir() if f.suffix.lower() == ".png")
        print(f"   {p.name}  现有: {have}")

print("\n=== 单位：sheet_L 大小写不一致的 ===")
for p in sorted(x for x in (SUR / "unit").iterdir() if x.is_dir()):
    names = {f.name for f in p.iterdir() if f.suffix.lower() == ".png"}
    if "sheet_L.png" not in names:
        print(f"   {p.name}  现有: {sorted(names)}")

print("\n=== theater 资产名（去变体后缀）===")
names = set()
for f in (SUR / "theater").glob("*.png"):
    stem = f.stem
    for suf in ("_neutral", "_hover", "_down", "_disabled"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    names.add(stem)
for n in sorted(names):
    print("   ", n)
