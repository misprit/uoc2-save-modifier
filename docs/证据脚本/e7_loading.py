# -*- coding: utf-8 -*-
"""E7: 战斗存档的加载路径 —— 参战单位从哪来；campaign_units.yml 谁写谁读"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e7_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=160):
    P(f"  --- {label}")
    buf = io.StringIO()
    dis.dis(code_obj, file=buf, depth=0)
    for ln in buf.getvalue().split("\n")[:maxlines]:
        P("      " + ln)

# 1) 谁调用 _save_campaign_units / _load_campaign_units
P("=" * 100)
P("[A] campaign.pyc 中 _save_campaign_units / _load_campaign_units 的调用者")
P("=" * 100)
cc = load("uoc2\\state\\campaign\\campaign.pyc")
for path, fn in walk_all(cc):
    if "_save_campaign_units" in fn.co_names or "_load_campaign_units" in fn.co_names:
        P(f"    {path}   args={fn.co_varnames[:fn.co_argcount]}")
        P(f"       co_names: {[n for n in fn.co_names if 'campaign' in n or 'unit' in n]}")

# 2) _load_campaign_game_files
P("")
P("=" * 100)
P("[B] Campaign/_load_campaign_game_files")
P("=" * 100)
for path, fn in walk_all(cc):
    if fn.co_name == "_load_campaign_game_files":
        dump(path, fn, 200)

# 3) game.pyc 中与 units 相关的函数
P("")
P("=" * 100)
P("[C] game.pyc 中引用 units / campaign_units 的函数")
P("=" * 100)
gc = load("uoc2\\state\\game\\game.pyc")
for path, fn in walk_all(gc):
    names = [n for n in fn.co_names if "unit" in n.lower()]
    strs = [s for s in fn.co_consts if isinstance(s, str) and ("unit" in s.lower() or "yml" in s.lower())]
    if names or strs:
        P(f"    {path}  args={fn.co_varnames[:fn.co_argcount]}")
        if names:
            P(f"        names: {names[:20]}")
        if strs:
            P(f"        strs : {[s for s in strs if len(s)<60][:14]}")

OUT.close()
print("done")
