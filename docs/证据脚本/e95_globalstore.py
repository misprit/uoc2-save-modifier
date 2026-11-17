# -*- coding: utf-8 -*-
"""E95: 全局里程碑存储定位 —— CampaignDoc.get_milestones / MilestoneInfo 定义 /
   paths.campaign_doc_dir_abs / 全局存档枚举 / 任何写全局里程碑的代码"""
import os, io, marshal, types, dis, re

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e95_out.txt", "w", encoding="utf-8")
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

def show(path, names, tag=""):
    W("")
    W("=" * 92)
    W("FILE: %s %s" % (path, tag))
    W("=" * 92)
    p = os.path.join(LIB, path.replace("/", os.sep))
    try:
        root = load(p)
    except Exception as e:
        W("  LOAD FAIL %s" % e); return {}
    funcs = dict(walk(root))
    for nm in names:
        c = funcs.get(nm)
        if not c:
            W("  !! MISSING %s" % nm); continue
        W("")
        W("  === %s ===" % nm)
        W("  常量: %s" % (consts(c)[:40],))
        W("  局部: %s" % (c.co_varnames,))
        dump(c, 260)
    return funcs

# ---- 1. CampaignDoc.get_milestones / _load milestones
f = show("state/campaign/campaign_doc.pyc",
         ["CampaignDoc.get_milestones", "get_milestones", "CampaignDoc.locale_data",
          "CampaignDoc.milestones", "CampaignDoc._load", "CampaignDoc._save"])
W("")
W("  -- campaign_doc.pyc 含 milestone 的全部函数 --")
for n, c in f.items():
    ns = [s for s in c.co_names if "milestone" in s.lower() or "medal" in s.lower()]
    ss = [s for s in c.co_consts if isinstance(s, str) and ("milestone" in s.lower() or "medal" in s.lower())]
    if ns or ss:
        W("      %s  names=%s consts=%s" % (n, ns[:8], ss[:8]))

# ---- 2. MilestoneInfo 类定义在哪
W("")
W("=" * 92)
W("MilestoneInfo / MedalInfo 类定义位置")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in filenames:
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        for n, c in walk(r):
            if c.co_name in ("MilestoneInfo", "MedalInfo"):
                W("  %s :: %s" % (os.path.relpath(p, LIB), n))
                W("      常量: %s" % (consts(c)[:24],))
                W("      局部: %s" % (c.co_varnames,))
                dump(c, 120)

# ---- 3. paths.campaign_doc_dir_abs / campaign_dir
show("paths.pyc", ["_Paths.campaign_doc_dir_abs", "campaign_doc_dir_abs",
                   "_Paths.campaign_dir", "_Paths.save_dir", "_Paths.saves_dir",
                   "_Paths.list_saves", "_Paths.game_saves"])

# ---- 4. 全局：谁在枚举存档目录 / 谁会写全局文件
W("")
W("=" * 92)
W("全 pyc: 含 'save_dir'/'saves'/'usg' 遍历 与 'milestone' 写回 的函数")
W("=" * 92)
KEYS = ("campaign_doc_dir_abs", "save_dir", "saves_dir", "list_saves", "usg_dir",
        "milestones", "has_achieved_milestones")
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            hits = [k for k in c.co_names if k in KEYS]
            if hits:
                W("  %-34s %-48s %s" % (rel, n, hits))

OUT.close()
print("done")
