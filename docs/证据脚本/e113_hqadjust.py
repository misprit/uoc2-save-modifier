# -*- coding: utf-8 -*-
"""E113: HQ 重组/继承 —— force_pool / branch_levels 是否被重算"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e113_out.txt", "w", encoding="utf-8")
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
def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]
def dump(c, lim=240):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 100: a = a[:100] + "..."
        W("      %-24s %s" % (x.opname, a))

def loadmod(rel):
    r = load(os.path.join(LIB, rel.replace("/", os.sep)))
    return r, dict(walk(r))

# ---- Game._adjust_hqs_between_situations
W("=" * 92)
W("[1] state/game/game.pyc :: Game._adjust_hqs_between_situations")
W("=" * 92)
r, f = loadmod("state/game/game.pyc")
c = f.get("Game._adjust_hqs_between_situations")
if c:
    W("  常量: %s" % (consts(c)[:30],))
    W("  局部: %s" % (c.co_varnames,))
    dump(c, 240)

# ---- Campaign._rename_hqs
W("")
W("=" * 92)
W("[2] state/campaign/campaign.pyc :: Campaign._rename_hqs")
W("=" * 92)
r, f = loadmod("state/campaign/campaign.pyc")
c = f.get("Campaign._rename_hqs")
if c:
    W("  常量: %s" % (consts(c)[:30],))
    W("  局部: %s" % (c.co_varnames,))
    dump(c, 240)

# ---- Campaign._create_new_hqs
W("")
W("=" * 92)
W("[3] state/campaign/campaign.pyc :: Campaign._create_new_hqs —— 新 HQ 的 force_pool 来源")
W("=" * 92)
c = f.get("Campaign._create_new_hqs")
if c:
    W("  常量: %s" % (consts(c)[:30],))
    W("  局部: %s" % (c.co_varnames,))
    dump(c, 240)

# ---- 谁调用 _adjust_hqs_between_situations
W("")
W("=" * 92)
W("[4] _adjust_hqs_between_situations 的调用点")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: rr = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, cc in walk(rr):
            if "_adjust_hqs_between_situations" in cc.co_names:
                W("  %-32s %s" % (rel, n))
                for x in dis.get_instructions(cc):
                    if "_adjust_hqs_between_situations" in x.argrepr:
                        W("      -> %s %s" % (x.opname, x.argrepr))

OUT.close()
print("done")
