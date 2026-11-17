# -*- coding: utf-8 -*-
"""E88: 全局里程碑 / 成就激活状态到底存在哪里？"""
import os, io, marshal, types, dis, collections, json

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
UD = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e88_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

W("=" * 84)
W("【1】%LOCALAPPDATA%\\.uoc2 的完整内容")
W("=" * 84)
for rt, dn, fn in os.walk(UD):
    rel = os.path.relpath(rt, UD).replace("\\", "/")
    depth = rel.count("/") if rel != "." else 0
    if depth <= 1:
        for f in sorted(fn):
            fp = os.path.join(rt, f)
            W("  %-46s %10d bytes" % (os.path.join(rel, f).replace("\\", "/"), os.path.getsize(fp)))
W("")
W("  顶层目录:")
for d in sorted(os.listdir(UD)):
    p = os.path.join(UD, d)
    W("    %-30s %s" % (d, "<dir>" if os.path.isdir(p) else "%d bytes" % os.path.getsize(p)))

W("")
W("=" * 84)
W("【2】settings.yml（游戏自己解析出来的 settings_file）")
W("=" * 84)
sp = os.path.join(UD, "settings.yml")
if os.path.isfile(sp):
    W(open(sp, encoding="utf-8", errors="replace").read()[:3000])
else:
    W("  不存在")

W("")
W("=" * 84)
W("【3】全部 .pyc 里与 achievement / milestone 相关的字符串")
W("=" * 84)
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

KEYS = ["achieve", "achievment", "milestone", "medal", "SetAchievement", "steam_api", "stats", "profile"]
hits = collections.defaultdict(set)
for rt, _, fn in os.walk(LIB):
    for f in fn:
        if not f.endswith(".pyc"):
            continue
        try:
            root = load(os.path.join(rt, f))
        except Exception:
            continue
        rel = os.path.relpath(os.path.join(rt, f), LIB).replace("\\", "/")
        for n, c in walk(root):
            for s in strconsts(c):
                sl = s.lower()
                for k in KEYS:
                    if k.lower() in sl:
                        hits[k].add((rel, n, s))
for k in KEYS:
    v = sorted(hits[k])
    W("  【%s】 %d 处" % (k, len(v)))
    for rel, n, s in v[:14]:
        W("      %-40s :: %-28s %r" % (rel, n, s[:70]))

W("")
W("=" * 84)
W("【4】campaign.pyc: get_achieved_milestones / can_get_victory_achivement")
W("=" * 84)
root = load(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
for n, c in walk(root):
    if c.co_name in ("get_achieved_milestones", "can_get_victory_achivement", "get_campaign_medal"):
        W("")
        W("  === %s ===" % n)
        W("      字符串: %s" % [s for s in strconsts(c)][:20])
        for i, x in enumerate(dis.get_instructions(c)):
            if i > 110:
                W("      ..."); break
            W("      %-26s %s" % (x.opname, x.argrepr))
OUT.close()
print("done")
