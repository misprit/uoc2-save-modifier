# -*- coding: utf-8 -*-
"""E112: HQ 侧重组/继承机制 —— force_pool / branch_levels 在 HQ 延续时是否保留"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e112_out.txt", "w", encoding="utf-8")
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

# ---- 1. 全库找 hq 重组/继承相关函数
W("=" * 92)
W("[1] 全 pyc：名字含 hq 的重组/继承/持久 相关函数")
W("=" * 92)
KEY = ("adjust_hq", "hq_between", "inherit", "persistent_hq", "rename_hq", "_rename_hqs",
       "replace_hq", "hq_continu", "hq_replace")
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            low = n.lower()
            if any(k in low for k in KEY):
                W("  %-32s %s" % (rel, n))

# ---- 2. game_adjust_data.pyc 全部函数
W("")
W("=" * 92)
W("[2] state/game/game_adjust_data.pyc 全部函数")
W("=" * 92)
p = os.path.join(LIB, "state", "game", "game_adjust_data.pyc")
r = load(p)
f = dict(walk(r))
for n in f:
    W("   %s" % n)

# ---- 3. campaign.pyc 里跟 HQ 延续/更名有关的函数
W("")
W("=" * 92)
W("[3] state/campaign/campaign.pyc 里含 hq 的函数 + 常量")
W("=" * 92)
p = os.path.join(LIB, "state", "campaign", "campaign.pyc")
r = load(p)
f2 = dict(walk(r))
for n, c in f2.items():
    if "hq" in n.lower():
        W("")
        W("  === %s ===" % n)
        W("  常量: %s" % (consts(c)[:30],))
        W("  局部: %s" % (c.co_varnames,))

OUT.close()
print("done")
