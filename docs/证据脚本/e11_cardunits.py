# -*- coding: utf-8 -*-
"""E11: _get_unit_ids_that_can_be_used / _game_data_snapshot 的精确实现"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e11_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=140):
    P(f"  --- {label}")
    buf = io.StringIO()
    dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)

gc = load("uoc2\\state\\game\\game.pyc")
for path, fn in walk_all(gc):
    if "_get_unit_ids_that_can_be_used" in fn.co_name or fn.co_name == "_game_data_snapshot":
        dump(f"{path}  args={fn.co_varnames[:fn.co_argcount]}", fn, 130)
        P("")

# 也看 Campaign.get_card_type_unit_id / get_used_card_unit_ids
cc = load("uoc2\\state\\campaign\\campaign.pyc")
for path, fn in walk_all(cc):
    if fn.co_name in ("get_card_type_unit_id", "get_used_card_unit_ids", "_find_unit_appearances"):
        dump(f"{path}  args={fn.co_varnames[:fn.co_argcount]}", fn, 90)
        P("")

OUT.close()
print("done")
