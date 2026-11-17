# -*- coding: utf-8 -*-
"""E103: globals.pyc 全文 + app.paths 赋值来源 + _Paths 路径名列表"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e103_out.txt", "w", encoding="utf-8")
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
        if len(a) > 100: a = a[:100] + "..."
        W("      %-4d %-24s %s" % (i, x.opname, a))
def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

# ---- 1. globals.pyc 模块级反汇编
W("=" * 92)
W("[1] uoc2/globals.pyc 模块级")
W("=" * 92)
r = load(os.path.join(LIB, "globals.pyc"))
W("  co_names: %s" % (sorted(set(r.co_names)),))
W("  co_consts: %s" % ([c for c in r.co_consts if not isinstance(c, types.CodeType)],))
W("")
W("  --- 模块级指令 ---")
dump(r, 300)
W("")
for n, c in walk(r):
    W("  === %s ===" % n)
    W("      常量: %s" % (consts(c)[:24],))
    dump(c, 120)

# ---- 2. 全 pyc: STORE_ATTR paths
W("")
W("=" * 92)
W("[2] 全 pyc: 谁把 paths 挂到 app 上（STORE_ATTR paths）")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: rr = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(rr):
            for x in dis.get_instructions(c):
                if x.opname == "STORE_ATTR" and x.argrepr.strip("'") in ("paths", "app"):
                    W("  %-30s %-40s %s" % (rel, n, x.argrepr))
                    W("      常量: %s" % (consts(c)[:22],))
                    W("      局部: %s" % (c.co_varnames,))
                    dump(c, 160)
                    break

# ---- 3. _Paths.__init__ 中所有含 'dir' 的字符串常量
W("")
W("=" * 92)
W("[3] _Paths.__init__ 全部字符串常量（找 campaign_doc_dir）")
W("=" * 92)
r = load(os.path.join(LIB, "paths.pyc"))
fp = dict(walk(r))
c = fp["_Paths.__init__"]
for k in c.co_consts:
    if isinstance(k, str):
        W("   %r" % k)
W("")
W("  --- 模块级 paths.pyc 常量 ---")
for k in r.co_consts:
    if isinstance(k, (str, tuple, list)):
        W("   %r" % (k,))

OUT.close()
print("done")
