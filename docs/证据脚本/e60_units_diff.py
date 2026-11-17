# -*- coding: utf-8 -*-
"""E60: document/units.yml 的存档 vs 包 差异（集合关系）；是否随进度增长"""
import os, io, zipfile, yaml, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e60_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

pkgdir = {
    "barbarossa": os.path.join(PK, "dlc2/data/campaigns/barbarossa.usc"),
    "blitzkrieg": os.path.join(PK, "dlc1/data/campaigns/blitzkrieg.usc"),
    "moscow": os.path.join(PK, "dlc3/data/campaigns/moscow.usc"),
    "stalingrad": os.path.join(PK, "dlc4/data/campaigns/stalingrad.usc"),
    "west": os.path.join(PK, "base/data/campaigns/west.usc"),
}

def ids_of(data):
    o = yaml.safe_load(data)
    if isinstance(o, list):
        return [x.get("id") if isinstance(x, dict) else x for x in o]
    if isinstance(o, dict):
        return list(o.keys())
    return []

pkgids = {}
for c, d in pkgdir.items():
    pkgids[c] = ids_of(open(os.path.join(d, "units.yml"), encoding="utf-8").read())
    P("包 %-12s units.yml 条目数=%d  唯一 id=%d" % (c, len(pkgids[c]), len(set(pkgids[c]))))

P("")
P("=" * 74)
P("各存档 document/units.yml 与包的关系")
P("=" * 74)
rows = []
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        try:
            zf = zipfile.ZipFile(p)
            names = zf.namelist()
            if "document/units.yml" not in names or "main.yml" not in names:
                zf.close(); continue
            m = yaml.safe_load(zf.read("main.yml")) or {}
            cid = m.get("campaign_id")
            if cid not in pkgids:
                zf.close(); continue
            sids = ids_of(zf.read("document/units.yml"))
            ngames = len(set(n.split("/")[1] for n in names if n.startswith("games/") and n.count("/") >= 2))
            pids = set(pkgids[cid]); ss = set(sids)
            rel = os.path.relpath(p, G)
            rows.append((cid, ngames, len(sids), len(pkgids[cid]), len(ss - pids), len(pids - ss), rel))
            zf.close()
        except Exception as e:
            P("  ERR %s: %s" % (p, e))

rows.sort()
for cid, ng, ns, npk, extra, miss, rel in rows:
    flag = ""
    if extra or miss:
        flag = "  <== 与包不同"
    P("  %-12s games=%-3d save=%-5d pkg=%-5d 存档多=%-4d 存档缺=%-4d %s%s" % (cid, ng, ns, npk, extra, miss, rel[:52], flag))

P("")
P("  按战役统计 extra 分布:")
c2 = collections.Counter()
for cid, ng, ns, npk, extra, miss, rel in rows:
    c2[(cid, extra, miss)] += 1
for k, v in sorted(c2.items()):
    P("    %s -> %d 个存档" % (k, v))

P("")
P("=" * 74)
P("存包里多出来的单位 id 样例（stalingrad）")
P("=" * 74)
for cid, ng, ns, npk, extra, miss, rel in rows:
    if cid == "stalingrad" and extra:
        zf = zipfile.ZipFile(os.path.join(G, rel))
        sids = ids_of(zf.read("document/units.yml"))
        d = {x.get("id"): x for x in yaml.safe_load(zf.read("document/units.yml"))}
        pp = {x.get("id"): x for x in yaml.safe_load(open(os.path.join(pkgdir[cid], "units.yml"), encoding="utf-8").read())}
        ex = [i for i in sids if i not in set(pkgids[cid])]
        P("  %s (games=%d): 多 %d 个 id = %s" % (rel[:48], ng, len(ex), ex[:10]))
        for i in ex[:3]:
            P("      存档条目: %s" % yaml.safe_dump(d[i], allow_unicode=True, default_flow_style=False)[:400])
        miss = [i for i in pkgids[cid] if i not in set(sids)]
        P("      存档缺: %s" % (miss[:10] or "无"))
        zf.close()
        break

OUT.close()
print("done")
