"""全量扫游戏 .pyc，找 force_pool / fp / step 阶梯的定义方。"""

from __future__ import annotations

from pathlib import Path

LIB = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")
NEEDLES = [b"force_pool", b"item_type", b"img_ident", b"steps/step", b"n_steps", b"equipment_q"]


hits: dict[str, list[str]] = {n.decode(): [] for n in NEEDLES}
for pyc in LIB.rglob("*.pyc"):
    data = pyc.read_bytes()
    for n in NEEDLES:
        if n in data:
            hits[n.decode()].append(pyc.relative_to(LIB).as_posix())

for needle, files in hits.items():
    print(f"=== {needle} ({len(files)}) ===")
    for f in files[:25]:
        print("   ", f)
    print()
