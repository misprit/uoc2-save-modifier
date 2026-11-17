# -*- coding: utf-8 -*-
"""E97: steam_api 实现 —— get_stat_value / set_stat_value / ms_ 里程碑统计写入点"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e97_out.txt", "w", encoding="utf-8")
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

def dump(c, lim=300):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 90: a = a[:90] + "..."
        W("      %-24s %s" % (x.opname, a))

def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

# ---- A. 全库扫描：谁引用 steam_api / get_stat_value / set_stat_value / ms_
W("=" * 92)
W("[A] 全 pyc: steam_api / stat_value / 'ms_' 引用")
W("=" * 92)
KEYS = ("steam_api", "get_stat_value", "set_stat_value", "get_achievement",
        "set_achievement", "get_achievement_names", "store_stats")
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            ns = [k for k in c.co_names if k in KEYS]
            ss = [k for k in c.co_consts if isinstance(k, str) and k in ("ms_", "steam_api")]
            if ns or ss:
                W("  %-34s %-44s names=%s consts=%s" % (rel, n, ns[:8], ss[:4]))

# ---- B. 找 steam_api 类/模块定义
W("")
W("=" * 92)
W("[B] steam_api 定义位置")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        names = set()
        for n, c in walk(r):
            names |= set(c.co_names)
        if "get_stat_value" in names and ("SteamApi" in " ".join(names) or "steam" in rel.lower() or True):
            if "get_stat_value" in names:
                W("  %s" % rel)

# ---- C. 对候选文件全量反汇编
W("")
W("=" * 92)
W("[C] 候选文件中的 stat 相关函数")
W("=" * 92)
for rel in ("steam.pyc", "steam_api.pyc", "steamworks.pyc", "app.pyc"):
    p = os.path.join(LIB, rel)
    if not os.path.exists(p):
        continue
    W("")
    W("  ### FILE %s ###" % rel)
    r = load(p)
    funcs = dict(walk(r))
    for n, c in funcs.items():
        if any(k in n.lower() for k in ("stat", "achievement", "steam")):
            W("")
            W("  === %s ===" % n)
            W("  常量: %s" % (consts(c)[:30],))
            W("  局部: %s" % (c.co_varnames,))
            dump(c, 160)

OUT.close()
print("done")
