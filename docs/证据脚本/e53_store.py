# -*- coding: utf-8 -*-
"""E53: game.pyc 的 store_deployable_to_unit / conference_store —— quantity==0 是否被过滤"""
import os, io, marshal, dis, types, re

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e53_out.txt", "w", encoding="utf-8")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk(k, path + "/" + k.co_name)

c = load("uoc2/state/game/game.pyc")
for path, code in walk(c):
    if re.search(r"store_deployable|conference_store$|_store_data|deploy_store", path):
        OUT.write("\n=== %s (line=%d) ===\n" % (path, code.co_firstlineno))
        OUT.write("  names : %s\n" % sorted(set(code.co_names)))
        OUT.write("  consts: %s\n" % [x for x in code.co_consts if isinstance(x, (str, int, float, tuple))][:30])
        buf = io.StringIO(); dis.dis(code, file=buf, depth=0)
        OUT.write(buf.getvalue()[:3500])
OUT.close()
print("ok")
