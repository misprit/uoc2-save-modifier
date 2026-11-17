"""E2: campaign_units.yml 的确切语义 + 参战单位的来源"""
import os, yaml, zipfile, io

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

def arch(usg, scen):
    try:
        with zipfile.ZipFile(usg) as zf:
            return zipfile.ZipFile(io.BytesIO(zf.read(f"games/{scen}/archive")))
    except Exception:
        return None

CASES = [
    (r"campaigns\Stalingrad.usg", "road_to_stalingrad"),
    (r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "husky"),
    (r"Old Saves\Victory in the West\经典难度\west-LastWar.usg", "unthinkable"),
    (r"Old Saves\Victory in the West\经典难度\west-MonteCassino.usg", "monte_cassino"),
]

for rel, scen in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        print("MISS", rel); continue
    print("=" * 118)
    print(f"{os.path.basename(p)}   scenario={scen}")
    print("=" * 118)
    with zipfile.ZipFile(p) as zf:
        root = zl(zf, "units.yml") or []
        root_ids = {u["id"] for u in root}
        manifest = set(zl(zf, f"games/{scen}/units.yml") or [])
        # scenario 预设单位
        scen_units = zl(zf, f"document/scenarios/{scen}/units.yml", []) or []
        scen_ids = {u["id"] for u in scen_units}
        # 场景变体可能覆盖
        scen_variants = [n for n in zf.namelist()
                         if n.startswith(f"document/scenarios/{scen}/variants/")]
        az = arch(p, scen)
        snaps = sorted({n.split("/")[0] for n in az.namelist()})
        first = snaps[0]
        cu = zl(az, f"{first}/campaign_units.yml", []) or []
        cu_ids = {u["id"] for u in cu}

        print(f"  根总表 id 数           : {len(root_ids)}")
        print(f"  参战清单 id 数         : {len(manifest)}")
        print(f"  场景预设 id 数         : {len(scen_ids)}   (document/scenarios/{scen}/units.yml)")
        print(f"  场景预设 ⊆ 参战清单 ?  : {scen_ids <= manifest}   "
              f"预设∩清单={len(scen_ids & manifest)}  预设∩总表={len(scen_ids & root_ids)}")
        print(f"  campaign_units id 数   : {len(cu_ids)}  {sorted(cu_ids)}")
        print(f"    campaign_units ⊆ 参战清单 ? {cu_ids <= manifest}")
        print(f"    campaign_units ∩ 场景预设  = {sorted(cu_ids & scen_ids)}")
        print(f"    campaign_units ∩ (清单-预设) = {sorted(cu_ids & (manifest - scen_ids))}")
        print(f"    (清单-预设) 即『非场景预设的参战单位』: {len(manifest - scen_ids)} 个 "
              f"{sorted(manifest - scen_ids)[:12]}")
        print(f"  场景变体目录: {scen_variants[:4]}")
        print(f"  参战清单中不在场景预设里的单位（= 战役带入/上局幸存）: "
              f"{sorted(manifest - scen_ids)}")
        # 这些单位在根表里的 xp vs 场景预设的类型
        for i in sorted(manifest - scen_ids)[:6]:
            u = next((x for x in root if x["id"] == i), None)
            if u:
                print(f"      总表 unit {i}: type={u.get('type')} xp={u.get('xp')} "
                      f"act_st={u.get('act_st')} name={u.get('name_brief')}")
    print()
