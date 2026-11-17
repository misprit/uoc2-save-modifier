"""枚举单位类型的 (movement, equipment, equipment_q, max_st, max_spec) 组合。

产出改写 e135 报告的 step 图标映射段。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

PK = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base")
UT = PK / "data" / "entity_types" / "unit_types"

combo = Counter()
maxst = Counter()
maxspec = Counter()
nationalities = Counter()
movements = Counter()
fields = Counter()

import re

for yml in UT.glob("*.yml"):
    text = yml.read_text(encoding="utf-8", errors="replace")
    data: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    for k in data:
        fields[k] += 1
    combo[(data.get("equipment", "??"), data.get("equipment_q", "??"))] += 1
    maxst[data.get("max_st", "??")] += 1
    maxspec[data.get("max_spec", "??")] += 1
    nationalities[data.get("nationality", "??")] += 1
    movements[data.get("movement", "??")] += 1

print(f"单位类型文件总数：{len(list(UT.glob('*.yml')))}")
print("\n字段出现次数：", dict(fields))
print("\n(equipment, equipment_q) 组合：")
for k, v in sorted(combo.items(), key=lambda kv: -kv[1]):
    print(f"   {k}: {v}")
print("\nmovement：", dict(movements))
print("\nmax_st 分布：", dict(sorted(maxst.items(), key=lambda kv: (len(kv[0]), kv[0]))))
print("\nmax_spec 分布：", dict(maxspec))
print(f"\nnationality 共 {len(nationalities)} 种")
