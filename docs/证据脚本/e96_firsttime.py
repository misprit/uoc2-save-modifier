# -*- coding: utf-8 -*-
"""E96: MilestoneInfo.first_time / campaign_doc_dir_abs / 全局里程碑首次达成时间"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e96_out.txt", "w", encoding="utf-8")
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

# ---- 1. MilestoneInfo 完整
W("=" * 92)
W("[1] state/campaign/campaign_info.pyc :: MilestoneInfo 完整")
W("=" * 92)
root = load(os.path.join(LIB, "state", "campaign", "campaign_info.pyc"))
funcs = dict(walk(root))
c = funcs.get("MilestoneInfo")
for k in c.co_consts:
    if isinstance(k, tuple) and "campaign_img" in str(k):
        W("  __static_attributes__ = %r" % (k,))
W("")
W("  --- MilestoneInfo.__init__ ---")
ic = funcs.get("MilestoneInfo.__init__")
if ic:
    W("  常量: %s" % (consts(ic)[:30],))
    W("  局部: %s" % (ic.co_varnames,))
    dump(ic, 200)
W("")
W("  --- campaign_info.pyc 全部顶层类/函数 ---")
for n in funcs:
    W("      %s" % n)

# ---- 2. 全 pyc 搜 'first_time'
W("")
W("=" * 92)
W("[2] 全 pyc: 'first_time' 出现位置")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            ns = [s for s in c.co_names if "first_time" in s]
            ss = [s for s in c.co_consts if isinstance(s, str) and "first_time" in s]
            if ns or ss:
                W("  %-34s %-46s names=%s consts=%s" % (rel, n, ns[:5], ss[:5]))

# ---- 3. paths.pyc: campaign_doc_dir_abs 在哪
W("")
W("=" * 92)
W("[3] paths.pyc: 所有含 'campaign_doc' / 'milestone' / 'achievement' 的名字")
W("=" * 92)
r = load(os.path.join(LIB, "paths.pyc"))
allnames = set()
for n, c in walk(r):
    allnames |= set(c.co_names)
    for k in c.co_consts:
        if isinstance(k, str): allnames.add("STR:" + k)
for s in sorted(allnames):
    if any(k in s.lower() for k in ("campaign_doc", "milestone", "achievement", "first_time", "save")):
        W("      %s" % s)

# ---- 4. 找 campaign_doc_dir_abs 定义
W("")
W("=" * 92)
W("[4] 谁定义 campaign_doc_dir_abs")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            if "campaign_doc_dir_abs" in c.co_names:
                W("  %-34s %s" % (rel, n))
                W("      常量: %s" % (consts(c)[:20],))
                W("      局部: %s" % (c.co_varnames,))
                dump(c, 120)

# ---- 5. Campaign.has_achieved_milestones
W("")
W("=" * 92)
W("[5] state/campaign/campaign.pyc :: Campaign.has_achieved_milestones + _save_campaign_main_file")
W("=" * 92)
r = load(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
funcs = dict(walk(r))
for nm in ("Campaign.has_achieved_milestones", "Campaign._save_campaign_main_file",
           "Campaign.__init__", "Campaign.campaign_front_data"):
    c = funcs.get(nm)
    if not c:
        W("  !! MISSING %s" % nm); continue
    W("")
    W("  === %s ===" % nm)
    W("  常量: %s" % (consts(c)[:30],))
    W("  局部: %s" % (c.co_varnames,))
    dump(c, 200)

OUT.close()
print("done")
