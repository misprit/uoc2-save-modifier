# -*- coding: utf-8 -*-
"""E25: Scenario._load / _set_unit_data —— 场景单位如何拿到 type"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e25_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=200):
    P(f"  --- {label}  (line={code_obj.co_firstlineno})")
    buf = io.StringIO(); dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)

c = load("uoc2\\state\\scenario\\scenario.pyc")
for path, fn, ln in walk_all(c):
    if fn.co_name in ("_set_unit_data", "_load", "_set_hq_data", "attach_unit_by_id"):
        dump(path, fn, 200)
        P("")

OUT.close()
print("done")
