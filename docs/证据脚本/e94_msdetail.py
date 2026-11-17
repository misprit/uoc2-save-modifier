# -*- coding: utf-8 -*-
"""E94: 全局里程碑 —— get_milestones / _cr_prepare_milestones_selectors / usg_campaign_info /
   Campaign.get_achieved_milestones / CampaignCtrl._append_milestones / GameWorldCtrl.slot_tooltip_victory"""
import os, io, marshal, types, dis

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e94_out.txt", "w", encoding="utf-8")
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

TARGETS = {
    "main_screen/ctrl.pyc": [
        "MainScreenCtrl.get_milestones",
        "MainScreenCtrl._cr_prepare_milestones_selectors",
        "MainScreenCtrl.__init__",
        "MainScreenCtrl._cr_prepare_achievements_selectors",
    ],
    "main_screen/setup.pyc": [
        "usg_campaign_info",
        "Setup.check",
    ],
    "state/campaign/campaign.pyc": [
        "Campaign.get_achieved_milestones",
        "Campaign.get_campaign_medal",
        "Campaign.can_get_victory_achivement",
    ],
    "main_screen/campaign_ctrl.pyc": [
        "CampaignCtrl._append_milestones",
        "CampaignCtrl.slot_tooltip_milestone",
    ],
    "game_world/ctrl.pyc": [
        "GameWorldCtrl.slot_tooltip_victory",
    ],
}

for rel, names in TARGETS.items():
    p = os.path.join(LIB, rel.replace("/", os.sep) + "")
    if not os.path.exists(p):
        p = os.path.join(LIB, rel.replace("/", os.sep))
    W("")
    W("=" * 92)
    W("FILE: %s" % rel)
    W("=" * 92)
    try:
        root = load(p)
    except Exception as e:
        W("  LOAD FAIL %s" % e); continue
    funcs = dict(walk(root))
    W("  -- 该文件含 'milestone'/'achiev' 的全部函数 --")
    for n, c in funcs.items():
        ns = [s for s in c.co_names if "milestone" in s.lower() or "achiev" in s.lower()]
        ss = [s for s in c.co_consts if isinstance(s, str) and ("milestone" in s.lower() or "achiev" in s.lower())]
        if ns or ss:
            W("      %s  names=%s consts=%s" % (n, ns[:6], ss[:6]))
    W("  -- 目标函数反汇编 --")
    for nm in names:
        c = funcs.get(nm)
        if not c:
            W("  !! MISSING %s" % nm); continue
        W("")
        W("  === %s ===" % nm)
        W("  常量: %s" % (consts(c)[:36],))
        W("  局部: %s" % (c.co_varnames,))
        dump(c, 320)

OUT.close()
print("done")
