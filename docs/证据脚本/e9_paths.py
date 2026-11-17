# -*- coding: utf-8 -*-
"""E9: Gamelike._load_entities / _save_gamelike / Campaign._save_campaign_files —— 最终确认读写路径"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e9_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=220):
    P(f"  --- {label}")
    buf = io.StringIO()
    dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)
    if len(txt) > maxlines:
        P(f"      ... (共 {len(txt)} 行)")

TARGETS = {
    "uoc2\\state\\gamelike\\gamelike.pyc": {"_load_entities", "_save_gamelike"},
    "uoc2\\state\\campaign\\campaign.pyc": {"_save_campaign_files", "_save_campaign_game_files", "_load", "save"},
}
for rel, names in TARGETS.items():
    P("=" * 100)
    P(rel)
    P("=" * 100)
    code = load(rel)
    for path, fn in walk_all(code):
        if fn.co_name in names:
            dump(f"{path}  args={fn.co_varnames[:fn.co_argcount]}", fn, 220)
            P("")

OUT.close()
print("done")
