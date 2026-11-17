# -*- coding: utf-8 -*-
"""E35: campaign_units_schema / _id_unit_schema 的结构"""
import os, io, marshal, dis, types

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib")
OUT = io.open(r"D:\MiniMax\_analysis\e35_out.txt", "w", encoding="utf-8")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk(k, path + "/" + k.co_name)

c = load("uoc2/state/campaign/campaign_data_validation.pyc")
for p, f in walk(c):
    if f.co_name in ("campaign_units_schema", "_id_unit_schema", "doc_units_schema",
                     "campaign_hqs_schema", "doc_hqs_schema"):
        OUT.write("  --- " + p + " line=" + str(f.co_firstlineno) + "\n")
        b = io.StringIO(); dis.dis(f, file=b, depth=0)
        for l in b.getvalue().split("\n")[:70]:
            OUT.write("      " + l + "\n")
        OUT.write("\n")

OUT.close()
print("ok")
