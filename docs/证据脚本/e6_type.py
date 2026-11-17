# -*- coding: utf-8 -*-
"""E6: type 从哪来 + document/units.yml 与根总表的关系 + 关键函数反汇编"""
import os, io, zipfile, yaml, marshal, dis, types

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e6_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

p = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(p) as zf:
    P("=" * 100)
    P("[A] document/units.yml（战役文档名册）")
    P("=" * 100)
    doc_u = zl(zf, "document/units.yml")
    P(f"    类型 {type(doc_u).__name__} 长度 {len(doc_u)}")
    P("    第 1 项: " + yaml.safe_dump(doc_u[0], allow_unicode=True, sort_keys=False).replace("\n", "\n      "))
    P(f"    键集种类: { {tuple(sorted(u.keys())) for u in doc_u} }")
    root_u = zl(zf, "units.yml")
    dids = {u["id"] for u in doc_u}; rids = {u["id"] for u in root_u}
    P(f"    document id 数 {len(dids)}  根总表 id 数 {len(rids)}")
    P(f"    根总表 ⊆ document ? {rids <= dids}   仅在根总表: {sorted(rids-dids)[:20]}   仅在 document: {sorted(dids-rids)[:20]}")
    dmap = {u["id"]: u for u in doc_u}
    same = sum(1 for i in (rids & dids) if dmap[i] == next((r for r in root_u if r["id"] == i), None))
    P(f"    交集 {len(rids & dids)} 个中，完全相同的: {same}")
    for i in sorted(rids & dids)[:3]:
        r = next(u for u in root_u if u["id"] == i)
        P(f"      id {i}  doc={dmap[i]}")
        P(f"           root={r}")

    P("")
    P("=" * 100)
    P("[B] document/hqs.yml 与根 hqs.yml")
    P("=" * 100)
    dh = zl(zf, "document/hqs.yml")
    rh = zl(zf, "hqs.yml")
    P(f"    document/hqs.yml 类型 {type(dh).__name__} 长度 {len(dh)}")
    P(f"    根 hqs.yml      类型 {type(rh).__name__} 长度 {len(rh)}")
    P("    document 第 1 项: " + yaml.safe_dump(dh[0] if isinstance(dh, list) else dh,
                                              allow_unicode=True, sort_keys=False).replace("\n", "\n      "))

# ------------------------------------------------------------------
P("")
P("=" * 100)
P("[C] 关键函数反汇编")
P("=" * 100)
LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def find(code, names):
    out = []
    def walk(c, path):
        for k in c.co_consts:
            if isinstance(k, types.CodeType):
                if k.co_name in names:
                    out.append((path + "/" + k.co_name, k))
                walk(k, path + "/" + k.co_name)
    walk(code, "")
    return out

def dump(label, code_obj, maxlines=200):
    P(f"  --- {label}")
    buf = io.StringIO()
    dis.dis(code_obj, file=buf, depth=0)
    for ln in buf.getvalue().split("\n")[:maxlines]:
        P("      " + ln)

c = load("uoc2\\state\\campaign\\campaign.pyc")
for path, fn in find(c, {"_load_campaign_objects", "_save_campaign_units", "_load_campaign_units"}):
    dump(path, fn, 140)

# 单位 type 的来源：UnitState.load / _to_dict
c2 = load("uoc2\\state\\entities\\unit.pyc")
for path, fn in find(c2, {"load", "_to_dict", "load_repair_specs"}):
    dump(path, fn, 120)

# scenario 侧加载
c3 = load("uoc2\\state\\scenario\\scenario.pyc")
names = set()
def walk(c, path):
    for k in c.co_consts:
        if isinstance(k, types.CodeType):
            names.add((path + "/" + k.co_name, k))
            walk(k, path + "/" + k.co_name)
walk(c3, "")
P("")
P("  --- scenario.pyc 全部函数名")
for path, fn in names:
    P(f"      {path}   args={fn.co_varnames[:fn.co_argcount]}")

OUT.close()
print("done")
