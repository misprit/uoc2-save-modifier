# -*- coding: utf-8 -*-
"""E52: 商店 UI 与 store_schema —— quantity==0 是否被过滤；price=0 的语义"""
import os, io, marshal, dis, types, re

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e52_out.txt", "w", encoding="utf-8")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk(k, path + "/" + k.co_name)

for rel, pat in (("uoc2/state/campaign/campaign.pyc", r"store_schema"),
                 ("uoc2/game_world/hq_ctrl.pyc", r"_menu_store")):
    c = load(rel)
    for path, code in walk(c):
        if not re.search(pat, path, re.I):
            continue
        OUT.write("\n=== %s :: %s (line=%d) ===\n" % (rel, path, code.co_firstlineno))
        OUT.write("  names : %s\n" % sorted(set(code.co_names)))
        OUT.write("  consts: %s\n" % [x for x in code.co_consts if isinstance(x, (str, int, float, tuple))][:30])
        buf = io.StringIO(); dis.dis(code, file=buf, depth=0)
        OUT.write(buf.getvalue()[:4500])

OUT.close()
print("ok")
