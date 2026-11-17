# -*- coding: utf-8 -*-
"""E99: steam_api 实现定位 —— inc_stat / get_stat_value / store_stats / 本地是否有镜像文件"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e99_out.txt", "w", encoding="utf-8")
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
        if len(a) > 90: a = a[:90] + "..."
        W("      %-24s %s" % (x.opname, a))

def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

# ---- A. 全库找 inc_stat / get_stat_value 的定义处
W("=" * 92)
W("[A] 定义 inc_stat / get_stat_value / store_stats 的函数")
W("=" * 92)
allfiles = []
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if fn.endswith(".pyc"):
            allfiles.append(os.path.join(dirpath, fn))

for p in allfiles:
    rel = os.path.relpath(p, LIB)
    try: r = load(p)
    except Exception: continue
    funcs = dict(walk(r))
    for n, c in funcs.items():
        if c.co_name in ("inc_stat", "get_stat_value", "store_stats", "set_stat_value"):
            W("")
            W("  === %s :: %s ===" % (rel, n))
            W("  常量: %s" % (consts(c)[:26],))
            W("  局部: %s" % (c.co_varnames,))
            dump(c, 140)

# ---- B. 库里所有非 uoc2 的顶层文件（可能有 steam 绑定）
W("")
W("=" * 92)
W("[B] lib 目录结构 + 非 uoc2 模块")
W("=" * 92)
base = os.path.dirname(LIB)
for dirpath, dirnames, filenames in os.walk(base):
    rel = os.path.relpath(dirpath, base)
    if rel.count(os.sep) > 2: 
        dirnames[:] = []
        continue
    py = [f for f in filenames if f.endswith(".py") or f.endswith(".pyc")]
    dll = [f for f in filenames if f.lower().endswith((".dll", ".pyd"))]
    if py or dll:
        W("  %-40s py=%s dll=%s" % (rel, py[:8], dll[:6]))

# ---- C. steam_api 对象绑定的类型（main.pyc / globals.pyc）
W("")
W("=" * 92)
W("[C] globals.pyc / main.pyc 的 steam_api 相关")
W("=" * 92)
for rel in ("globals.pyc", "main.pyc"):
    p = os.path.join(LIB, rel)
    if not os.path.exists(p): continue
    r = load(p)
    funcs = dict(walk(r))
    W("")
    W("  ### %s ###" % rel)
    for n, c in funcs.items():
        ins = list(dis.get_instructions(c))
        if any(x.opname == "STORE_ATTR" and "steam_api" in x.argrepr for x in ins):
            W("  === %s ===" % n)
            W("  常量: %s" % (consts(c)[:30],))
            W("  局部: %s" % (c.co_varnames,))
            dump(c, 180)
        elif "steam_api" in c.co_names and c.co_name == "main":
            W("  === %s (module main) ===" % n)
            W("  常量: %s" % (consts(c)[:30],))
            dump(c, 180)

OUT.close()
print("done")
