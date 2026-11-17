# -*- coding: utf-8 -*-
"""E77: 包内 data/ 子目录约定（campaigns vs scenarios vs entity_types），mod 是否同构"""
import os, io, marshal, types, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e77_out.txt", "w", encoding="utf-8")
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

W("=" * 76)
W("【1】所有 .pyc 里出现的 data 子目录名（campaigns / scenarios / entity_types ...）")
W("=" * 76)
hits = collections.defaultdict(set)
for rt, _, fn in os.walk(LIB):
    for f in fn:
        if not f.endswith(".pyc"):
            continue
        try:
            root = load(os.path.join(rt, f))
        except Exception:
            continue
        for n, c in walk(root):
            for s in strconsts(c):
                if s in ("campaigns", "scenarios", "entity_types", "localization", "campaign"):
                    hits[s].add(os.path.relpath(os.path.join(rt, f), LIB).replace("\\", "/"))
for k in sorted(hits):
    v = sorted(hits[k])
    W("  %-14s 出现在 %d 个模块: %s" % (k, len(v), v[:8]))

W("")
W("=" * 76)
W("【2】哪些模块负责枚举包内 data 子目录（找 'scenarios' 的用法）")
W("=" * 76)
for rel in [r"paths.pyc", r"state\campaign\campaign_ctrl.pyc", r"state\campaign\campaign_doc.pyc"]:
    p = os.path.join(LIB, rel)
    if not os.path.isfile(p):
        continue
    root = load(p)
    for n, c in walk(root):
        ss = strconsts(c)
        if "scenarios" in ss or "campaigns" in ss:
            W("  %s :: %s -> %s" % (rel, n, [s for s in ss if s in ("scenarios", "campaigns", "entity_types", "campaign")]))

W("")
W("=" * 76)
W("【3】各包目录下 data/ 的实际子目录（游戏包 vs 用户 mod 包）")
W("=" * 76)
PK = os.path.join(GAME, "_packages")
for dlc in sorted(os.listdir(PK)):
    d = os.path.join(PK, dlc, "data")
    if not os.path.isdir(d):
        continue
    W("  游戏包 %-8s data/: %s" % (dlc, sorted(os.listdir(d))))
UP = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "_packages")
for mod in sorted(os.listdir(UP)):
    d = os.path.join(UP, mod, "data")
    if not os.path.isdir(d):
        continue
    W("  用户包 %-8s data/: %s" % (mod, sorted(os.listdir(d))))
    for sub in sorted(os.listdir(d)):
        sd = os.path.join(d, sub)
        if os.path.isdir(sd):
            W("       %s/ -> %s" % (sub, sorted(os.listdir(sd))[:12]))
OUT.close()
print("done")
