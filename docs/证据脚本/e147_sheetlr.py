"""sheet_L / sheet_R 语义：哪个阵营用哪张？（全量扫 pyc 字符串 + 反汇编命中处）"""

from __future__ import annotations

import dis
import marshal
import types
from pathlib import Path

LIB = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")
NEEDLES = (b"sheet_L", b"sheet_R", b"sheet_l", b"/sheet_")

for pyc in sorted(LIB.rglob("*.pyc")):
    data = pyc.read_bytes()
    if not any(n in data for n in NEEDLES):
        continue
    rel = pyc.relative_to(LIB).as_posix()
    print(f"\n########## {rel} ##########")

    def walk(code, path=""):
        yield path, code
        for const in code.co_consts:
            if isinstance(const, types.CodeType):
                yield from walk(const, f"{path}.{const.co_name}")

    try:
        code = marshal.loads(data[16:])
    except Exception as exc:
        print("   解析失败", exc)
        continue
    for path, c in walk(code):
        blob = " ".join(
            [str(x) for x in c.co_consts if isinstance(x, str)]
            + [str(x) for x in c.co_names]
            + list(c.co_varnames)
        )
        if not any(n.decode() in blob for n in NEEDLES):
            continue
        print(f"--- {path} args={c.co_varnames[:c.co_argcount]}")
        print("   consts:", [x for x in c.co_consts if isinstance(x, (str, int, float))][:20])
        print("   names:", c.co_names[:20])
