# -*- coding: utf-8 -*-
"""E105: lib/tools/steam_api.pyc / steamworks.pyc 完整反汇编 —— 统计值的真实存储"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib")
OUT = io.open(r"D:\MiniMax\_analysis\e105_out.txt", "w", encoding="utf-8")
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
def dump(c, lim=260):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 100: a = a[:100] + "..."
        W("      %-24s %s" % (x.opname, a))
def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

for rel in ("tools/steam_api.pyc", "tools/steamworks.pyc"):
    p = os.path.join(LIB, rel.replace("/", os.sep))
    W("")
    W("=" * 92)
    W("FILE %s" % rel)
    W("=" * 92)
    if not os.path.exists(p):
        W("  不存在"); continue
    r = load(p)
    W("  module co_names: %s" % (sorted(set(r.co_names)),))
    funcs = dict(walk(r))
    W("")
    W("  --- 全部函数名 ---")
    for n in funcs:
        W("      %s" % n)
    W("")
    for n, c in funcs.items():
        W("")
        W("  === %s ===" % n)
        W("  常量: %s" % (consts(c)[:36],))
        W("  局部: %s" % (c.co_varnames,))
        dump(c, 200)

OUT.close()
print("done")
