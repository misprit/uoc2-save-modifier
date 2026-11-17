"""精确定位「战力阶梯」算法：use_from_deploy / get_num_nationality_steps / get_unit_equipment_steps。"""

from __future__ import annotations

import dis
import marshal
import types
from pathlib import Path

LIB = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")
WANT = {
    "use_from_deploy",
    "get_num_nationality_steps",
    "get_unit_equipment_steps",
    "get_num_steps",
    "n_steps",
}


def walk(code, path=""):
    yield path, code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from walk(const, f"{path}.{const.co_name}")


def dump(pyc: Path, label: str):
    code = marshal.loads(pyc.read_bytes()[16:])
    for path, c in walk(code):
        if c.co_name not in WANT:
            continue
        print(f"\n===== {label} :: {path} =====")
        print("args:", c.co_varnames[: c.co_argcount])
        print("names:", c.co_names)
        print("consts:", [x for x in c.co_consts if isinstance(x, (str, int, float, tuple))][:40])
        print("-" * 70)
        dis.dis(c)
        print("-" * 70)


# 先找定义位置
found: dict[str, list[str]] = {}
for pyc in LIB.rglob("*.pyc"):
    data = pyc.read_bytes()
    for needle in (b"get_num_nationality_steps", b"get_unit_equipment_steps", b"def use_from_deploy"):
        if needle in data:
            found.setdefault(needle.decode(), []).append(pyc.relative_to(LIB).as_posix())

for k, v in found.items():
    print(k, "->", v)

for rel in sorted({f for files in found.values() for f in files}):
    dump(LIB / rel, rel)
