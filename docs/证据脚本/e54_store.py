# -*- coding: utf-8 -*-
"""E54: campaign.pyc 商店数据流 —— 库存耗尽时是否移除条目"""
import os, io, marshal, dis, types, re

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e54_out.txt", "w", encoding="utf-8")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk(k, path + "/" + k.co_name)

for rel in ("uoc2/state/campaign/campaign.pyc", "uoc2/state/campaign/conferences.pyc"):
    c = load(rel)
    for path, code in walk(c):
        if re.search(r"store", path, re.I):
            OUT.write("\n=== %s :: %s (line=%d) ===\n" % (rel, path, code.co_firstlineno))
            OUT.write("  names : %s\n" % sorted(set(code.co_names)))
            OUT.write("  consts: %s\n" % [x for x in code.co_consts if isinstance(x, (str, int, float, tuple))][:24])
            buf = io.StringIO(); dis.dis(code, file=buf, depth=0)
            OUT.write(buf.getvalue()[:2600])
OUT.close()
print("ok")
