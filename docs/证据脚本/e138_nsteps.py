"""解 force_pool / unit 里的 n_steps 语义（扩大检索：names/varnames/consts 全查）。"""

from __future__ import annotations

import marshal
import types
from pathlib import Path

LIB = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")
TARGETS = [
    ("uoc2/state/entities/force_pool.pyc", ["n_steps", "img_ident", "item_type"]),
    ("uoc2/state/entities/unit.pyc", ["n_steps"]),
]


def walk(code, path=""):
    yield path, code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from walk(const, f"{path}.{const.co_name}")


for rel, needles in TARGETS:
    pyc = LIB / rel
    code = marshal.loads(pyc.read_bytes()[16:])
    print("#" * 70)
    print("#", rel)
    for path, c in walk(code):
        blob = " | ".join(
            [
                " ".join(c.co_names),
                " ".join(c.co_varnames),
                " ".join(str(x) for x in c.co_consts if isinstance(x, (str, int, float))),
            ]
        )
        hit = [n for n in needles if n in blob]
        if not hit:
            continue
        print(f"\n--- {path}  命中={hit}")
        print("   args:", c.co_varnames[:c.co_argcount])
        print("   names:", c.co_names[:30])
        print("   varnames:", c.co_varnames[:30])
        print("   consts:", [x for x in c.co_consts if isinstance(x, (str, int, float))][:30])
