# -*- coding: utf-8 -*-
"""E86: 根 units.yml 到底装了什么？（战役开始就写入全部单位？只装已激活的？）"""
import os, io, zipfile, yaml, collections, json

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e86_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

def ids(o):
    if isinstance(o, list):
        return [e.get("id") for e in o if isinstance(e, dict)]
    return []

rows = []
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, G)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            if "main.yml" not in names:
                continue
            m = yaml.safe_load(zf.read("main.yml")) or {}
            kind = "独立" if m.get("standalone_scenario") else "战役"
            if kind == "独立":
                continue
            cid = m.get("campaign_id")
            docu = yaml.safe_load(zf.read("document/units.yml")) if "document/units.yml" in names else []
            roster = set(ids(docu))
            root = yaml.safe_load(zf.read("units.yml")) if "units.yml" in names else []
            rl = root if isinstance(root, list) else []
            rids = set(ids(rl))
            deployed = [e for e in rl if isinstance(e, dict) and e.get("uv") is not None]
            nouv = [e for e in rl if isinstance(e, dict) and e.get("uv") is None]
            # 参战场景集合
            scen_played = sorted(set(n.split("/")[1] for n in names if n.startswith("games/") and n.count("/") >= 2))
            # 名册里出现过的场景（document/scenarios/）
            allscen = sorted(set(n.split("/")[2] for n in names if n.startswith("document/scenarios/") and n.count("/") >= 3))
            # 该战役所有场景里的单位 id
            scen_ids = set()
            for n in names:
                if n.startswith("document/scenarios/") and n.endswith("/units.yml") and n.count("/") == 3:
                    try:
                        o = yaml.safe_load(zf.read(n))
                    except Exception:
                        continue
                    if isinstance(o, list):
                        for e in o:
                            if isinstance(e, dict) and e.get("id") is not None:
                                scen_ids.add(e["id"])
            rows.append(dict(rel=rel, cid=cid, nroot=len(rl), nroster=len(roster),
                             ndeploy=len(deployed), nouv=len(nouv),
                             games=len(scen_played), nscen=len(allscen),
                             nscenids=len(scen_ids),
                             root_in_scen=len(rids & scen_ids),
                             roster_not_in_root=len(roster - rids),
                             root_not_in_roster=len(rids - roster),
                             scen_not_in_root=len(scen_ids - rids),
                             played=scen_played))

W("=" * 110)
W("【1】战役存档：根表 vs 名册 vs 场景预设里的单位")
W("=" * 110)
W("  %-44s %6s %7s %7s %6s %7s %8s %9s %9s" % (
    "存档", "场景数", "名册", "根表", "已部署", "未部署", "根∩场景id", "名册-根表", "场景-根表"))
rows.sort(key=lambda r: (r["cid"], r["games"]))
for r in rows:
    W("  %-44s %6d %7d %7d %6d %7d %8d %9d %9d" % (
        r["rel"][:44], r["nscen"], r["nroster"], r["nroot"], r["ndeploy"], r["nouv"],
        r["root_in_scen"], r["roster_not_in_root"], r["scen_not_in_root"]))

W("")
W("  按战役分组，看 根表/名册 随进度(已打场景数)的变化:")
for cid in sorted(set(r["cid"] for r in rows)):
    sub = sorted([r for r in rows if r["cid"] == cid], key=lambda r: r["games"])
    W("    %s:" % cid)
    for r in sub:
        W("      已打 %2d 场 | 根表 %4d | 名册 %4d | 已部署 %4d | 未部署 %4d | 名册多出 %4d" % (
            r["games"], r["nroot"], r["nroster"], r["ndeploy"], r["nouv"], r["roster_not_in_root"]))

W("")
W("=" * 110)
W("【2】★ 根表里的单位有没有敌方阵营？（用户说『我方和己方』）")
W("=" * 110)
p = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(p) as zf:
    root = yaml.safe_load(zf.read("units.yml"))
    docu = yaml.safe_load(zf.read("document/units.yml"))
    rl = root if isinstance(root, list) else []
    W("  Stalingrad.usg 根表 %d 条，键集: %s" % (len(rl), sorted(rl[0].keys())))
    W("  根表里没有 faction 字段？ %s" % ("faction" not in rl[0]))
    fac = collections.Counter()
    for e in rl:
        fac[e.get("faction")] += 1
    W("  faction 分布: %s" % dict(fac))
    # 通过 type 反查 faction（名册没有 faction，用 entity_types）
    W("")
    W("  根表单位按 id 是否都在名册里: %s" % (set(ids(rl)) <= set(ids(docu))))
    W("  根表里有 uv 的（已部署）id 数: %d" % len([e for e in rl if e.get("uv") is not None]))
    W("  根表里 uv 为 null 的 id 数: %d" % len([e for e in rl if e.get("uv") is None]))
    ex = [e for e in rl if e.get("uv") is None][:3]
    for e in ex:
        W("     未部署样例: id=%s type=%s name=%s" % (e.get("id"), e.get("type"), e.get("name_brief")))
    ex2 = [e for e in rl if e.get("uv") is not None][:3]
    for e in ex2:
        W("     已部署样例: id=%s type=%s name=%s uv=%s" % (e.get("id"), e.get("type"), e.get("name_brief"), e.get("uv")))

W("")
W("=" * 110)
W("【3】★ 『战役开始就写入全部单位』—— 战役开局存档(C0)的根表 vs 名册")
W("=" * 110)
for r in rows:
    if r["games"] == 0:
        W("  %-46s 根表 %4d / 名册 %4d / 已部署 %4d" % (r["rel"][:46], r["nroot"], r["nroster"], r["ndeploy"]))
OUT.close()
print("done")
