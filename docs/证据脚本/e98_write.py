# -*- coding: utf-8 -*-
"""E98: 里程碑统计写入点 —— Campaign.game_finished / app.steam_api 绑定 / stat API 实现"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e98_out.txt", "w", encoding="utf-8")
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

def dump(c, lim=400):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 90: a = a[:90] + "..."
        W("      %-24s %s" % (x.opname, a))

def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

def allcode(rel):
    p = os.path.join(LIB, rel.replace("/", os.sep))
    r = load(p)
    return r, dict(walk(r))

# ---- 1. Campaign.game_finished
W("=" * 92)
W("[1] state/campaign/campaign.pyc :: Campaign.game_finished")
W("=" * 92)
root, funcs = allcode("state/campaign/campaign.pyc")
c = funcs["Campaign.game_finished"]
W("  常量: %s" % (consts(c)[:40],))
W("  局部: %s" % (c.co_varnames,))
dump(c, 400)

# ---- 2. 谁把 steam_api 绑到 app 上
W("")
W("=" * 92)
W("[2] 全 pyc: STORE_ATTR steam_api 的位置 + steam_api 所属类型")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            ins = list(dis.get_instructions(c))
            for i, x in enumerate(ins):
                if x.opname == "STORE_ATTR" and "steam_api" in x.argrepr:
                    W("  %-30s %-44s" % (rel, n))
                    W("      常量: %s" % (consts(c)[:24],))
                    dump(c, 160)
                    break

# ---- 3. main.pyc / settings.pyc 里 steam_api 上下文
W("")
W("=" * 92)
W("[3] main.pyc / settings.pyc 的 steam_api 上下文")
W("=" * 92)
for rel in ("main.pyc", "settings.pyc"):
    p = os.path.join(LIB, rel)
    if not os.path.exists(p): continue
    r = load(p)
    funcs = dict(walk(r))
    for n, c in funcs.items():
        if "steam_api" in c.co_names:
            W("")
            W("  === %s :: %s ===" % (rel, n))
            W("  常量: %s" % (consts(c)[:26],))
            W("  局部: %s" % (c.co_varnames,))
            dump(c, 140)

# ---- 4. 找 steam_api 类的实现：含 get_stat_value 的 code object
W("")
W("=" * 92)
W("[4] 含 'get_stat_value' / 'set_stat_value' / 'store_stats' 定义的函数")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            if c.co_name in ("get_stat_value", "set_stat_value", "store_stats",
                             "get_achievement", "set_achievement", "get_achievement_names"):
                W("")
                W("  === %s :: %s ===" % (rel, n))
                W("  常量: %s" % (consts(c)[:26],))
                W("  局部: %s" % (c.co_varnames,))
                dump(c, 140)

OUT.close()
print("done")
