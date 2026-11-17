"""`_fp_helper` 全量反汇编：搞清 step 阶梯到底怎么画。"""

from __future__ import annotations

import dis
import marshal
import types
from pathlib import Path

ROOT = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")


def walk(code, path=""):
    yield path, code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from walk(const, f"{path}.{const.co_name}")


for pyc in ROOT.rglob("hq_ctrl.pyc"):
    code = marshal.loads(pyc.read_bytes()[16:])
    for path, c in walk(code):
        if c.co_name != "_fp_helper":
            continue
        print(f"===== {pyc.name} :: {path} =====")
        print("args:", c.co_varnames[:c.co_argcount])
        print("consts:", [x for x in c.co_consts if isinstance(x, (str, int, float, tuple))])
        print("names:", c.co_names)
        print("-" * 60)
        dis.dis(c)
    break
