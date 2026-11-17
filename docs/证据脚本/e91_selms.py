# -*- coding: utf-8 -*-
"""E91: _sel_milestones 从哪来？主菜单的「已获得里程碑」集合的来源"""
import os, io, marshal, types, dis, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e91_out.txt", "w", encoding="utf-8")
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
def dump(c, lim=220):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ..."); break
        a = x.argrepr
        if len(a) > 80:
            a = a[:80] + "…"
        W("      %-26s %s" % (x.opname, a))

W("=" * 88)
W("【1】所有提到 _sel_milestones 的地方")
W("=" * 88)
for rt, _, fn in os.walk(LIB):
    for f in fn:
        if not f.endswith(".pyc"):
            continue
        try:
            root = load(os.path.join(rt, f))
        except Exception:
            continue
        rel = os.path.relpath(os.path.join(rt, f), LIB).replace("\\", "/")
        for n, c in walk(root):
            if "_sel_milestones" in strconsts(c):
                W("  %-40s :: %s" % (rel, n))

W("")
W("=" * 88)
W("【2】MainScreenCtrl.on_enter__main_selector")
W("=" * 88)
root = load(os.path.join(LIB, "main_screen", "ctrl.pyc"))
for n, c in walk(root):
    if c.co_name == "on_enter__main_selector":
        W("  === %s ===" % n)
        dump(c, 300)

W("")
W("=" * 88)
W("【3】MainScreenCtrl._selector_add_item")
W("=" * 88)
for n, c in walk(root):
    if c.co_name == "_selector_add_item":
        W("  === %s ===" % n)
        dump(c, 260)

W("")
W("=" * 88)
W("【4】MainScreenCtrl._cr_prepare_achievements_selectors")
W("=" * 88)
for n, c in walk(root):
    if c.co_name == "_cr_prepare_achievements_selectors":
        W("  === %s ===" % n)
        dump(c, 200)
OUT.close()
print("done")
