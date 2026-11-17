"""找出 sheet_R 的使用位置（对阵的另一方）。"""

from __future__ import annotations

import dis
import marshal
import types
from pathlib import Path

LIB = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")


def walk(code, path=""):
    yield path, code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from walk(const, f"{path}.{const.co_name}")


for rel in ("uoc2/common/sheets/combat_sheet.pyc", "uoc2/common/sheets/unit_sheet.pyc"):
    code = marshal.loads((LIB / rel).read_bytes()[16:])
    for path, c in walk(code):
        rows = dis.Bytecode(c).dis().splitlines()
        hits = [i for i, r in enumerate(rows) if "sheet_L" in r or "sheet_R" in r]
        if not hits:
            continue
        print(f"\n########## {rel} :: {path} ##########")
        for i in hits:
            lo, hi = max(0, i - 12), min(len(rows), i + 3)
            print("\n".join(rows[lo:hi]))
            print("-" * 70)
