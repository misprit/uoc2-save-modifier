# -*- coding: utf-8 -*-
"""E8: Game._load / Game._save / Campaign._save_campaign_files —— 到底读写哪张表"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e8_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=260):
    P(f"  --- {label}")
    buf = io.StringIO()
    dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)
    if len(txt) > maxlines:
        P(f"      ... (共 {len(txt)} 行，截断)")

gc = load("uoc2\\state\\game\\game.pyc")
for path, fn in walk_all(gc):
    if fn.co_name in ("_load", "_save"):
        P("=" * 100)
        dump(f"Game/{fn.co_name}  args={fn.co_varnames[:fn.co_argcount]}", fn, 300)
        P("")

cc = load("uoc2\\state\\campaign\\campaign.pyc")
for path, fn in walk_all(cc):
    if fn.co_name in ("_save_campaign_files", "_save_campaign_game_files", "_save_campaign_main_file"):
        P("=" * 100)
        dump(f"Campaign/{fn.co_name}  args={fn.co_varnames[:fn.co_argcount]}", fn, 200)
        P("")

# gamelike
gl = load("uoc2\\state\\gamelike\\gamelike.pyc")
P("=" * 100)
P("gamelike.pyc 函数名")
for path, fn in walk_all(gl):
    P(f"    {path}  args={fn.co_varnames[:fn.co_argcount]}")

OUT.close()
print("done")
