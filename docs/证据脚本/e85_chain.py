# -*- coding: utf-8 -*-
"""E85: 存档 document/scenarios/ 的读取与写回链路（是否经由包优先级解析）"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e85_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")
def load(p):
    with open(p, "rb") as f:
        return marshal.loads(f.read()[16:])
def walk(code, prefix=""):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield prefix + c.co_name, c
            for n, cc in walk(c, prefix + c.co_name + "."):
                yield n, cc
def strconsts(code):
    o = []
    for c in code.co_consts:
        if isinstance(c, str):
            o.append(c)
        elif isinstance(c, types.CodeType):
            o.extend(strconsts(c))
    return o
def dump(c, lim=130):
    out = []
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            out.append("    ..."); break
        a = x.argrepr
        if len(a) > 70:
            a = a[:70] + "…"
        out.append("    %-26s %s" % (x.opname, a))
    return "\n".join(out)

root = load(os.path.join(LIB, "state", "campaign", "campaign_doc.pyc"))
for target in ["_load", "_save", "_save_main_files", "load_scenario_units", "_load_scenario_unit_and_hq_ids",
               "load_scenario_main_data_from_file", "scenario_serialization"]:
    for n, c in walk(root):
        if c.co_name == target:
            W("=" * 78)
            W("【%s】  字符串: %s" % (n, [s for s in strconsts(c)][:18]))
            W(dump(c))
            W("")
            break
OUT.close()
print("done")
