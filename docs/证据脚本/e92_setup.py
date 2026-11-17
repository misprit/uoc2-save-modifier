# -*- coding: utf-8 -*-
"""E92: main_screen/setup.pyc —— campaign_setup 怎么构造里程碑状态"""
import os, io, marshal, types, dis, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e92_out.txt", "w", encoding="utf-8")
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
def dump(c, lim=250):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ..."); break
        a = x.argrepr
        if len(a) > 82:
            a = a[:82] + "…"
        W("      %-26s %s" % (x.opname, a))

root = load(os.path.join(LIB, "main_screen", "setup.pyc"))

W("=" * 88)
W("【1】setup.pyc 全部函数名 + 字符串常量里的 milestone/save 相关")
W("=" * 88)
for n, c in walk(root):
    ss = [s for s in strconsts(c) if len(s) < 70]
    W("")
    W("  === %s ===" % n)
    W("      字符串: %s" % ss[:22])
    if c.co_name in ("campaign_setup", "_load_campaign", "usg_name", "usg_save_name",
                     "get_milestones", "milestones", "setup_milestones", "load_milestones",
                     "__init__", "setup", "load"):
        dump(c, 260)
OUT.close()
print("done")
