# -*- coding: utf-8 -*-
"""E16: deploy_calc_new_xp / take_steps_for_recovery / _take_force_for_kia 的确切语义"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e16_out.txt", "w", encoding="utf-8")
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

uc = load("uoc2\\state\\entities\\unit.pyc")
P("=" * 100); P("[A] deploy_calc_new_xp（XP 是绝对赋值还是累加？）"); P("=" * 100)
for path, fn, ln in walk_all(uc):
    if fn.co_name in ("deploy_calc_new_xp", "deploy_calc_xp", "tot_st"):
        dump(path, fn, 90)
        P("")

ac = load("uoc2\\state\\game\\game_adjust_data.pyc")
P("=" * 100); P("[B] take_steps_for_recovery / _take_force_for_kia"); P("=" * 100)
for path, fn, ln in walk_all(ac):
    if fn.co_name in ("take_steps_for_recovery", "_take_force_for_kia"):
        dump(path, fn, 110)
        P("")

P("=" * 100); P("[C] take_spec_for_recovery/<lambda> line=79（供给单位排序键）"); P("=" * 100)
for path, fn, ln in walk_all(ac):
    if fn.co_name == "<lambda>" and ln == 79:
        dump(path, fn, 60)
P("=" * 100); P("[D] take_spec_for_recovery/<genexpr> line=76（类型匹配）"); P("=" * 100)
for path, fn, ln in walk_all(ac):
    if fn.co_name == "<genexpr>" and ln == 76:
        dump(path, fn, 60)

OUT.close()
print("done")
