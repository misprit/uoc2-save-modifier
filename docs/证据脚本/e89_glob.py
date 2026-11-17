# -*- coding: utf-8 -*-
"""E89: 全局里程碑激活状态：settings.yml 尾部 + achievements/ 路径 + _sel_milestones"""
import os, io, marshal, types, dis, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
UD = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e89_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

W("=" * 84)
W("【1】settings.yml 全文（含尾部）")
W("=" * 84)
W(open(os.path.join(UD, "settings.yml"), encoding="utf-8", errors="replace").read())

W("")
W("=" * 84)
W("【2】steam_autocloud.vdf 全文")
W("=" * 84)
v = os.path.join(UD, "save", "steam_autocloud.vdf")
if os.path.isfile(v):
    W(open(v, encoding="utf-8", errors="replace").read())

W("")
W("=" * 84)
W("【3】debug/ 目录")
W("=" * 84)
dbg = os.path.join(UD, "debug")
if os.path.isdir(dbg):
    for rt, dn, fn in os.walk(dbg):
        for f in sorted(fn):
            fp = os.path.join(rt, f)
            W("  %-50s %d bytes" % (os.path.relpath(fp, UD).replace("\\", "/"), os.path.getsize(fp)))

W("")
W("=" * 84)
W("【4】游戏包里有没有 achievements/ 目录")
W("=" * 84)
PK = os.path.join(GAME, "_packages")
for rt, dn, fn in os.walk(PK):
    for d in dn:
        if "achiev" in d.lower() or "medal" in d.lower() or "milestone" in d.lower():
            W("  %s" % os.path.relpath(os.path.join(rt, d), GAME).replace("\\", "/"))

W("")
W("=" * 84)
W("【5】main_screen/ctrl.pyc 里 achievements/ 与 _sel_milestones 的用法")
W("=" * 84)
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

root = load(os.path.join(LIB, "main_screen", "ctrl.pyc"))
for n, c in walk(root):
    ss = strconsts(c)
    if any("achiev" in s.lower() or "milestone" in s.lower() or "_sel_milestones" in s for s in ss):
        W("")
        W("  === %s ===" % n)
        W("      字符串: %s" % [s for s in ss if "achiev" in s.lower() or "milestone" in s.lower() or "save" in s.lower()][:20])
        for i, x in enumerate(dis.get_instructions(c)):
            if i > 150:
                W("      ..."); break
            a = x.argrepr
            if len(a) > 75:
                a = a[:75] + "…"
            W("      %-26s %s" % (x.opname, a))
OUT.close()
print("done")
