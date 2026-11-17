# -*- coding: utf-8 -*-
"""E90: 主菜单如何决定「里程碑已激活」—— 是读某个全局文件，还是汇总所有存档？"""
import os, io, marshal, types, dis, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e90_out.txt", "w", encoding="utf-8")
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

# 1) 哪些模块提到 milestones / achievements
W("=" * 88)
W("【1】main_screen 与 campaign 相关模块里含 milestone/achievement 的函数")
W("=" * 88)
TARGETS = []
for rel in ["main_screen/ctrl.pyc", "main_screen/campaign_ctrl.pyc", "main_screen/campaign_view.pyc",
            "main_screen/campaign_renderer.pyc", "main_screen/campaign_widget.pyc", "main_screen/setup.pyc"]:
    p = os.path.join(LIB, rel.replace("/", os.sep))
    if not os.path.isfile(p):
        continue
    root = load(p)
    for n, c in walk(root):
        ss = strconsts(c)
        if any("milestone" in s.lower() or "achievement" in s.lower() for s in ss):
            TARGETS.append((rel, n, c, ss))

for rel, n, c, ss in TARGETS:
    W("")
    W("  === %s :: %s ===" % (rel, n))
    W("      字符串: %s" % [s for s in ss if len(s) < 60][:24])

W("")
W("=" * 88)
W("【2】关键函数完整反汇编：谁在收集「已获得的里程碑」")
W("=" * 88)
INTEREST = ["_prepare_achievements_selectors", "slot_tooltip_milestone", "_append_milestones",
            "setup_main_medal", "clear_main_medal", "_show_campaign_sidebar_strategic",
            "slot_tooltip_victory"]
for rel, n, c, ss in TARGETS:
    if c.co_name not in INTEREST:
        continue
    W("")
    W("  === %s :: %s ===" % (rel, n))
    for i, x in enumerate(dis.get_instructions(c)):
        if i > 200:
            W("      ..."); break
        a = x.argrepr
        if len(a) > 78:
            a = a[:78] + "…"
        W("      %-26s %s" % (x.opname, a))

W("")
W("=" * 88)
W("【3】搜索：有没有「读所有存档 / 汇总」的痕迹（save_dir / list_saves / 遍历 usg）")
W("=" * 88)
KEY = ["save_dir", "listdir", ".usg", "get_saves", "all_saves", "load_campaign", "read_save",
       "save_files", "get_save", "campaign_info", "medals"]
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
            ss = strconsts(c)
            hit = [s for s in ss if any(k.lower() in s.lower() for k in KEY)]
            if hit:
                W("  %-40s :: %-34s %s" % (rel, n, hit[:8]))
OUT.close()
print("done")
