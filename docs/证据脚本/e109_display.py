# -*- coding: utf-8 -*-
"""E109: 单位名显示走 get 还是 get_unformatted —— 决定明文是否会显示为空"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib")
OUT = io.open(r"D:\MiniMax\_analysis\e109_out.txt", "w", encoding="utf-8")
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
def dump(c, lim=120):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 100: a = a[:100] + "..."
        W("      %-24s %s" % (x.opname, a))

# ---- A. _MyDefaultDict.__init__ / get_dict 的默认行为
W("=" * 92)
W("[A] tools/localization.pyc :: _MyDefaultDict.__init__ / get_dict")
W("=" * 92)
r = load(os.path.join(LIB, "tools", "localization.pyc"))
funcs = dict(walk(r))
for nm in ("_MyDefaultDict.__init__", "_MyDefaultDict.get_dict"):
    c = funcs.get(nm)
    if c:
        W("")
        W("  === %s ===" % nm)
        dump(c, 80)

# ---- B. 谁在读 name_brief / name_full 并调 locale
W("")
W("=" * 92)
W("[B] 全 pyc：引用 name_brief 且同时引用 locale.get / get_unformatted 的函数")
W("=" * 92)
hits = {}
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"):
            continue
        p = os.path.join(dirpath, fn)
        try: rr = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(rr):
            ns = set(c.co_names)
            if "name_brief" in ns or "name_full" in ns:
                loc = [x for x in ("get", "get_unformatted", "locale", "localize") if x in ns]
                hits.setdefault(rel, []).append((n, sorted(loc)))

for rel in sorted(hits):
    W("  === %s ===" % rel)
    for n, loc in hits[rel][:14]:
        W("      %-52s %s" % (n, loc))

# ---- C. entities_view/unit.pyc 里 name_brief 的使用点
W("")
W("=" * 92)
W("[C] state/entities_view/unit.pyc :: 名字取用点")
W("=" * 92)
p = os.path.join(LIB, "uoc2", "state", "entities_view", "unit.pyc")
if os.path.exists(p):
    rr = load(p)
    for n, c in walk(rr):
        if "name_brief" in c.co_names:
            W("")
            W("  === %s ===" % n)
            ins = list(dis.get_instructions(c))
            for i, x in enumerate(ins):
                if "name_brief" in x.argrepr:
                    for j in range(max(0, i - 3), min(len(ins), i + 12)):
                        a = ins[j].argrepr
                        if len(a) > 95: a = a[:95] + "..."
                        W("        %-22s %s" % (ins[j].opname, a))
                    W("        ---")

# ---- D. 界面上单位名的渲染：搜 engine/ui 与 main_screen 里 locale.get 调用
W("")
W("=" * 92)
W("[D] 搜 'get_unformatted' 的全部调用点")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: rr = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(rr):
            if "get_unformatted" in c.co_names:
                W("  %-34s %s" % (rel, n))

OUT.close()
print("done")
