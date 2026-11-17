# -*- coding: utf-8 -*-
"""E23: units_schema(gamelike, from_scenario_data) —— 场景单位如何拿到 type"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e23_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=160):
    P(f"  --- {label}  (line={code_obj.co_firstlineno})")
    buf = io.StringIO(); dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)

c = load("uoc2\\state\\entities\\data_validation\\unit.pyc")
P("=" * 100); P("[A] data_validation/unit.pyc 函数清单"); P("=" * 100)
for path, fn, ln in walk_all(c):
    P(f"  {path} line={ln} args={fn.co_varnames[:fn.co_argcount]}")
    strs = [s for s in fn.co_consts if isinstance(s, str)]
    if strs:
        P(f"      strings: {[s for s in strs if len(s)<70]}")

P(""); P("=" * 100); P("[B] units_schema / campaign_units_schema 反汇编"); P("=" * 100)
for path, fn, ln in walk_all(c):
    if fn.co_name in ("units_schema", "campaign_units_schema", "unit_schema", "campaign_unit_schema"):
        dump(path, fn, 170)
        P("")

OUT.close()
print("done")
