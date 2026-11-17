# -*- coding: utf-8 -*-
"""E14: 复核当前版本 game_adjust_data.pyc 的重组机制"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e14_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=300):
    P(f"  --- {label}   (firstlineno={code_obj.co_firstlineno})")
    buf = io.StringIO()
    dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)
    if len(txt) > maxlines:
        P(f"      ... (共 {len(txt)} 行)")

code = load("uoc2\\state\\game\\game_adjust_data.pyc")
P("=" * 100)
P("game_adjust_data.pyc 全部函数（含源行号）")
P("=" * 100)
for path, fn, ln in walk_all(code):
    P(f"  {path}   firstlineno={ln}  args={fn.co_varnames[:fn.co_argcount]}")
    strs = [s for s in fn.co_consts if isinstance(s, str)]
    if strs:
        P(f"      strings: {[s for s in strs if len(s) < 70]}")

P("")
P("=" * 100)
P("关键函数完整反汇编")
P("=" * 100)
for path, fn, ln in walk_all(code):
    if fn.co_name in ("adjust_units_between_situations", "campaign_agree_on_unit",
                      "_take_force_for_lci", "take_spec_for_recovery"):
        dump(path, fn, 320)
        P("")

OUT.close()
print("done")
