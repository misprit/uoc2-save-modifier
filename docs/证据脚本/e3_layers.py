# -*- coding: utf-8 -*-
"""E3: 战斗中单位数据的分层机制 —— 一次查清
问题：战斗中保存时，游戏把每个单位的信息存在哪？改哪里？
"""
import os, sys, io, zipfile, yaml, json

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e3_out.txt", "w", encoding="utf-8")
def P(*a):
    s = " ".join(str(x) for x in a)
    OUT.write(s + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

def arch(usg, scen):
    try:
        with zipfile.ZipFile(usg) as zf:
            data = zf.read(f"games/{scen}/archive")
        return zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None

CASES = [
    (r"campaigns\Stalingrad.usg", "road_to_stalingrad"),
    (r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "husky"),
    (r"Old Saves\Victory in the West\经典难度\west-LastWar.usg", "unthinkable"),
    (r"Old Saves\Victory in the West\经典难度\west-MonteCassino.usg", "monte_cassino"),
]

P("=" * 100)
P("E3 战斗中单位数据分层机制")
P("=" * 100)

for rel, scen in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        P("MISS", rel); continue
    P("")
    P("#" * 100)
    P(f"# {os.path.basename(p)}   scenario={scen}")
    P("#" * 100)
    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
        root = zl(zf, "units.yml") or []
        rootmap = {u["id"]: u for u in root}
        man = zl(zf, f"games/{scen}/units.yml") or []
        man_ids = set(man) if man and isinstance(man[0], int) else {u["id"] for u in man}
        is_list = bool(man and isinstance(man[0], int))

        P(f"[1] 根 units.yml  : {len(root)} 个单位对象")
        P(f"    games/{scen}/units.yml : {len(man)} 项  格式={'ID清单(list[int])' if is_list else '对象(list[dict])'}")
        P(f"    清单 ⊆ 总表 ? {man_ids <= set(rootmap)}   总表中不在本场的 = {len(set(rootmap)-man_ids)} 个")

        # 根级 enroute_units.yml ?
        root_en = zl(zf, "enroute_units.yml", None)
        P(f"[2] 根级 enroute_units.yml 存在 ? {root_en is not None}"
          + (f"  ({len(root_en)} 项)" if isinstance(root_en, list) else ""))

        # document/scenarios/<scen>/ 下的 enroute / campaign
        for cand in [f"document/scenarios/{scen}/enroute_units.yml",
                     f"document/scenarios/{scen}/campaign_units.yml",
                     f"document/scenarios/{scen}/units.yml",
                     f"document/scenarios/{scen}/hqs.yml"]:
            v = zl(zf, cand, None)
            if v is not None:
                P(f"    {cand}  -> {len(v)} 项")
            else:
                P(f"    {cand}  -> 不存在")

        # variants 下的 enroute
        ven = [n for n in names if n.startswith(f"document/scenarios/{scen}/variants/") and n.endswith("enroute_units.yml")]
        for n in ven:
            v = zl(zf, n)
            P(f"    [variant] {n} -> {len(v) if isinstance(v,list) else type(v)}")

        az = arch(p, scen)
        if az:
            snaps = sorted({n.split("/")[0] for n in az.namelist()})
            P(f"[3] archive 快照 {len(snaps)} 个: {snaps[:3]} ... {snaps[-1:]}")
            # 找出所有含 enroute_units.yml / campaign_units.yml 的条目
            P(f"    archive 内含 enroute_units.yml 的条目: "
              f"{[n for n in az.namelist() if n.endswith('enroute_units.yml')][:6]}")
            P(f"    archive 内含 campaign_units.yml 的条目: "
              f"{[n for n in az.namelist() if n.endswith('campaign_units.yml')][:6]}")
            for s in snaps:
                cu = zl(az, f"{s}/campaign_units.yml", None)
                eu = zl(az, f"{s}/enroute_units.yml", None)
                if cu is None and eu is None:
                    continue
                P(f"    --- {s}")
                if cu is not None:
                    P(f"        campaign_units.yml: {len(cu)} 项 ids={[x['id'] for x in cu]}")
                if eu is not None:
                    P(f"        enroute_units.yml : {len(eu)} 项")
                    for e in (eu if isinstance(eu, list) else [])[:4]:
                        u = e.get("unit", {})
                        P(f"           on_turn={e.get('on_turn')} unit id={u.get('id')} type={u.get('type')} "
                          f"xp={u.get('xp')} uv={u.get('uv')} supply={u.get('supply')} act_st={u.get('act_st')}")
                        if u.get("id") in rootmap:
                            r = rootmap[u["id"]]
                            P(f"           └ 同 id 在【根总表】: type={r.get('type')} xp={r.get('xp')} "
                              f"uv={r.get('uv')} supply={r.get('supply')} ap={r.get('ap')} mp={r.get('mp')}")
                            same = {k: (u.get(k), r.get(k)) for k in set(u) | set(r)
                                    if u.get(k) != r.get(k) and k != "id"}
                            P(f"           └ 字段差异: {same if same else '无'}")

# ---------------------------------------------------------------
# id 空间复用检查：不同场景的预设文件是否用同一 id 空间
# ---------------------------------------------------------------
P("")
P("=" * 100)
P("[4] document/scenarios/*/units.yml 的 id 空间是否复用（同名同 id 不同场景）")
P("=" * 100)
p = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(p) as zf:
    scen_files = sorted(n for n in zf.namelist()
                        if n.startswith("document/scenarios/") and n.endswith("/units.yml"))
    P(f"    场景预设单位文件 {len(scen_files)} 个")
    byid = {}
    for n in scen_files:
        v = zl(zf, n, []) or []
        scen_name = n.split("/")[2]
        for u in v:
            byid.setdefault(u["id"], []).append((scen_name, u.get("type"), u.get("xp")))
    shared = {i: v for i, v in byid.items() if len(v) > 1}
    P(f"    出现在多个场景预设中的 id 数: {len(shared)} / 总 id 数 {len(byid)}")
    for i in sorted(shared)[:6]:
        P(f"      id {i}: {shared[i]}")

OUT.close()
print("done")
