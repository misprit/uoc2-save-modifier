# -*- coding: utf-8 -*-
"""E93: 全局里程碑状态机制 —— campaign_setup / CampaignSetup.__init__ / paths.campaign_dir 全量反汇编"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e93_out.txt", "w", encoding="utf-8")
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
            W("      ...(truncated)")
            break
        a = x.argrepr
        if len(a) > 90:
            a = a[:90] + "..."
        W("      %-24s %s" % (x.opname, a))

def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

# ---------------------------------------------------------------- 1
W("=" * 90)
W("[1] main_screen/ctrl.pyc :: MainScreenCtrl.campaign_setup 全量反汇编")
W("=" * 90)
root = load(os.path.join(LIB, "main_screen", "ctrl.pyc"))
funcs = dict(walk(root))
c = funcs.get("campaign_setup")
if c:
    W("  常量: %s" % (consts(c)[:40],))
    W("  局部变量: %s" % (c.co_varnames,))
    dump(c, 500)
else:
    W("  !! 未找到 campaign_setup；候选: %s" % [k for k in funcs if "campaign" in k.lower()])

# ---------------------------------------------------------------- 2
W("")
W("=" * 90)
W("[2] main_screen/setup.pyc :: CampaignSetup.__init__ 全量反汇编")
W("=" * 90)
root2 = load(os.path.join(LIB, "main_screen", "setup.pyc"))
funcs2 = dict(walk(root2))
for nm in ("CampaignSetup.__init__", "__init__"):
    c = funcs2.get(nm)
    if c:
        W("  === %s ===" % nm)
        W("  常量: %s" % (consts(c)[:40],))
        W("  参数名: %s" % (c.co_varnames,))
        dump(c, 400)
        break

W("")
W("  --- setup.pyc 全部函数名 ---")
for n in funcs2:
    W("      %s" % n)

# ---------------------------------------------------------------- 3
W("")
W("=" * 90)
W("[3] paths.pyc :: campaign_dir / addable_dir / _build_package_list 反汇编")
W("=" * 90)
root3 = load(os.path.join(LIB, "paths.pyc"))
funcs3 = dict(walk(root3))
for nm in ("_Paths.campaign_dir", "campaign_dir", "_Paths.addable_dir", "addable_dir",
           "_Paths.get_yml", "get_yml", "_Paths.usg_campaign_info", "usg_campaign_info"):
    c = funcs3.get(nm)
    if c:
        W("")
        W("  === %s ===" % nm)
        W("  常量: %s" % (consts(c)[:30],))
        dump(c, 260)

# ---------------------------------------------------------------- 4
W("")
W("=" * 90)
W("[4] 全 pyc 扫描: 哪些模块引用 campaign_setup / usg_campaign_info / _sel_milestones")
W("=" * 90)
KEYS = ("campaign_setup", "usg_campaign_info", "_sel_milestones", "get_achieved_milestones",
        "campaign_dir", "addable_dir")
hits = {}
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in filenames:
        if not fn.endswith(".pyc"):
            continue
        p = os.path.join(dirpath, fn)
        try:
            r = load(p)
        except Exception:
            continue
        for n, c in walk(r):
            for k in c.co_names:
                if k in KEYS:
                    hits.setdefault(os.path.relpath(p, LIB), set()).add("%s -> %s" % (n, k))
            for k in c.co_consts:
                if isinstance(k, str) and k in KEYS:
                    hits.setdefault(os.path.relpath(p, LIB), set()).add("%s :: '%s'" % (n, k))
for f in sorted(hits):
    W("  === %s ===" % f)
    for h in sorted(hits[f]):
        W("      %s" % h)

# ---------------------------------------------------------------- 5
W("")
W("=" * 90)
W("[5] main_screen/ctrl.pyc 中所有含 'milestone' 的常量与函数")
W("=" * 90)
for n, c in funcs.items():
    ss = [s for s in c.co_consts if isinstance(s, str) and "milestone" in s.lower()]
    ns = [s for s in c.co_names if "milestone" in s.lower()]
    if ss or ns:
        W("  === %s ===" % n)
        if ss: W("      常量: %s" % ss[:12])
        if ns: W("      名字: %s" % ns[:12])

OUT.close()
print("done")
