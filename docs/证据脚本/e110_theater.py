# -*- coding: utf-8 -*-
"""E110: theater_assets 的读写链路 —— 读档时是否用存档值？写盘时是否覆盖？"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e110_out.txt", "w", encoding="utf-8")
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
def dump(c, lim=200):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 100: a = a[:100] + "..."
        W("      %-24s %s" % (x.opname, a))
def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

def ctx(c, needle, before=4, after=14):
    ins = list(dis.get_instructions(c))
    for i, x in enumerate(ins):
        if needle in x.argrepr:
            W("        ---")
            for j in range(max(0, i - before), min(len(ins), i + after)):
                a = ins[j].argrepr
                if len(a) > 95: a = a[:95] + "..."
                W("        %-22s %s" % (ins[j].opname, a))
            return True
    return False

# ---- 1. game.pyc 里 theater_assets 的用法
W("=" * 92)
W("[1] state/game/game.pyc —— theater_assets 的读写点")
W("=" * 92)
r = load(os.path.join(LIB, "state", "game", "game.pyc"))
funcs = dict(walk(r))
for n, c in funcs.items():
    if "theater_assets" in c.co_names or any(
            isinstance(k, str) and "theater_assets" in k for k in c.co_consts):
        W("")
        W("  === %s ===" % n)
        W("  常量: %s" % (consts(c)[:24],))
        W("  局部: %s" % (c.co_varnames,))
        ctx(c, "theater_assets", 6, 20)

# ---- 2. Game._load 读哪些字段
W("")
W("=" * 92)
W("[2] state/game/game.pyc :: Game._load —— 载入来源")
W("=" * 92)
c = funcs.get("Game._load")
if c:
    W("  常量: %s" % (consts(c)[:36],))
    W("  局部: %s" % (c.co_varnames,))
    dump(c, 150)

# ---- 3. Game._save 写哪些字段
W("")
W("=" * 92)
W("[3] state/game/game.pyc :: Game._save —— 写盘内容")
W("=" * 92)
c = funcs.get("Game._save")
if c:
    W("  常量: %s" % (consts(c)[:36],))
    W("  局部: %s" % (c.co_varnames,))
    dump(c, 150)

# ---- 4. common/placement.pyc —— 战斗开始时 theater_assets 从哪来
W("")
W("=" * 92)
W("[4] common/placement.pyc —— theater_assets 初始化")
W("=" * 92)
p = os.path.join(LIB, "common", "placement.pyc")
if os.path.exists(p):
    r = load(p)
    funcs2 = dict(walk(r))
    for n, c in funcs2.items():
        if "theater_assets" in c.co_names or any(
                isinstance(k, str) and "theater_assets" in k for k in c.co_consts):
            W("")
            W("  === %s ===" % n)
            W("  常量: %s" % (consts(c)[:24],))
            ctx(c, "theater_assets", 8, 22)

# ---- 5. scenario/scenario.pyc —— 场景预设里的 theater_assets
W("")
W("=" * 92)
W("[5] state/scenario/scenario.pyc —— 场景侧的 theater_assets")
W("=" * 92)
p = os.path.join(LIB, "state", "scenario", "scenario.pyc")
if os.path.exists(p):
    r = load(p)
    funcs3 = dict(walk(r))
    for n, c in funcs3.items():
        if "theater_assets" in c.co_names or any(
                isinstance(k, str) and "theater_assets" in k for k in c.co_consts):
            W("")
            W("  === %s ===" % n)
            W("  常量: %s" % (consts(c)[:24],))
            ctx(c, "theater_assets", 8, 22)

OUT.close()
print("done")
