# -*- coding: utf-8 -*-
"""E62: 改名/单位名 从名册还是根表读；campaign 存档的加载-保存流程"""
import os, io, marshal, dis, sys, types, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e62_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(pyc):
    with open(pyc, "rb") as f:
        return marshal.loads(f.read()[16:])

def walk(code, prefix=""):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield prefix + c.co_name, c
            for n, cc in walk(c, prefix + c.co_name + "."):
                yield n, cc

def find(root, *names):
    for c in root.co_consts:
        if isinstance(c, types.CodeType):
            if c.co_name in names:
                yield c
            for cc in walk(c):
                if cc.co_name in names:
                    yield cc

def show(code, maxline=400):
    lines = []
    try:
        ins = list(dis.get_instructions(code))
    except Exception:
        return ""
    for i, x in enumerate(ins):
        if i > 400:
            lines.append("    ...(截断)")
            break
        arg = x.argrepr
        lines.append("    %-28s %s" % (x.opname, arg))
    return "\n".join(lines)

def strconsts(code):
    out = []
    for c in code.co_consts:
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, types.CodeType):
            out.extend(strconsts(c))
    return out

P("=" * 74)
P("【1】campaign_doc.pyc 里的 _save_units_file / add_campaign_unit")
P("=" * 74)
p = os.path.join(LIB, "state", "campaign", "campaign_doc.pyc")
root = load(p)
names = {}
for n, c in walk(root):
    names.setdefault(c.co_name, []).append(n)
for target in ["_save_units_file", "add_campaign_unit", "_load_units_file", "save", "load"]:
    hits = [n for n, c in walk(root) if c.co_name == target]
    if not hits:
        continue
    P("  %s -> %s" % (target, hits))
    for n, c in walk(root):
        if c.co_name == target:
            P("  --- %s ---" % n)
            ss = [s for s in strconsts(c) if any(k in s for k in ("units", "yml", "document", "name"))]
            P("      字符串常量: %s" % ss[:20])
            P(show(c, 120))
            P("")

P("")
P("=" * 74)
P("【2】campaign.pyc 里的 rename 相关")
P("=" * 74)
p2 = os.path.join(LIB, "state", "campaign", "campaign.pyc")
root2 = load(p2)
allnames = sorted(set(c.co_name for n, c in walk(root2)))
P("  campaign.pyc 所有函数名:")
P("    %s" % ", ".join(allnames))
P("")
for n, c in walk(root2):
    ss = strconsts(c)
    if any("rename" in s.lower() for s in ss) or "rename" in c.co_name.lower():
        P("  命中 %s :: 字符串 %s" % (n, [s for s in ss if "rename" in s.lower()][:8]))

P("")
P("  --- rename_units / _rename 之类 ---")
for n, c in walk(root2):
    if "rename" in c.co_name.lower():
        P("  === %s ===" % n)
        P(show(c, 150))
        P("")

P("")
P("=" * 74)
P("【3】campaign_doc.pyc 全部函数名 + 含 name_brief 的字符串")
P("=" * 74)
P("  %s" % ", ".join(sorted(set(c.co_name for n, c in walk(root)))))
P("")
for n, c in walk(root):
    ss = [s for s in strconsts(c) if "name_brief" in s or "name_full" in s]
    if ss:
        P("  %s -> %s" % (n, ss[:6]))

OUT.close()
print("done")
