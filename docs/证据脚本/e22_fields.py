# -*- coding: utf-8 -*-
"""E22: 字段覆盖实证 —— type/uv/hq_id 到底被谁覆盖"""
import os, io, zipfile, yaml

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e22_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

CASES = [
    (r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "husky"),
    (r"Old Saves\Victory in the West\经典难度\west-MonteCassino.usg", "monte_cassino"),
    (r"campaigns\Stalingrad.usg", "road_to_stalingrad"),
]

for rel, scen in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        continue
    P("=" * 100)
    P(f"{os.path.basename(p)}   scenario={scen}")
    P("=" * 100)
    with zipfile.ZipFile(p) as zf:
        root = {u["id"]: u for u in (zl(zf, "units.yml") or [])}
        doc = {u["id"]: u for u in (zl(zf, "document/units.yml") or [])}
        scen_u = zl(zf, f"document/scenarios/{scen}/units.yml") or []
        ppa = zl(zf, f"document/scenarios/{scen}/prepositioned_assets.yml") or []
        enr = zl(zf, f"document/scenarios/{scen}/enroute_units.yml") or []
        scen_ids = {u["id"] for u in scen_u}
        ppa_ids = {(a.get("unit") or {}).get("id") for a in ppa if a.get("type") != "bb"}
        enr_ids = {(e.get("unit") or {}).get("id") for e in enr}

        P(f"  场景初始单位 {len(scen_u)}  资产承载单位 {len(ppa_ids)}  增援 {len(enr_ids)}")
        P(f"  资产承载 id ∩ 场景初始 id = {sorted(ppa_ids & scen_ids)}")
        P(f"  增援 id     ∩ 场景初始 id = {sorted(enr_ids & scen_ids)}")

        # 玩家单位判定：用 doc 名册的 type 查 faction
        P("")
        P(f"  {'id':>5} {'来源':>10} {'根表type':>16} {'名册type':>16} {'一致':>5} "
          f"{'根表uv':>14} {'场景uv':>14} {'uv一致':>7} {'根表hq':>7} {'场景hq':>7} {'hq一致':>7}")
        for u in scen_u[:10]:
            i = u["id"]
            r = root.get(i)
            if not r:
                continue
            dt = (doc.get(i) or {}).get("type")
            same_type = (r.get("type") == dt)
            same_uv = (r.get("uv") == u.get("uv"))
            same_hq = (r.get("hq_id") == u.get("hq_id"))
            P(f"  {i:>5} {'场景初始':>10} {str(r.get('type')):>16} {str(dt):>16} {str(same_type):>5} "
              f"{str(r.get('uv')):>14} {str(u.get('uv')):>14} {str(same_uv):>7} "
              f"{str(r.get('hq_id')):>7} {str(u.get('hq_id')):>7} {str(same_hq):>7}")
        for i in sorted(ppa_ids):
            r = root.get(i)
            if not r:
                continue
            dt = (doc.get(i) or {}).get("type")
            P(f"  {i:>5} {'资产承载':>10} {str(r.get('type')):>16} {str(dt):>16} "
              f"{str(r.get('type')==dt):>5} {str(r.get('uv')):>14} {'-':>14} {'-':>7} "
              f"{str(r.get('hq_id')):>7} {'-':>7} {'-':>7}")
        for i in sorted(enr_ids):
            r = root.get(i)
            if not r:
                continue
            dt = (doc.get(i) or {}).get("type")
            e = next((x for x in enr if (x.get("unit") or {}).get("id") == i), None)
            eu = e.get("unit") if e else {}
            P(f"  {i:>5} {'增援':>10} {str(r.get('type')):>16} {str(dt):>16} "
              f"{str(r.get('type')==dt):>5} {str(r.get('uv')):>14} {str(eu.get('uv')):>14} "
              f"{str(r.get('uv')==eu.get('uv')):>7} {str(r.get('hq_id')):>7} {str(eu.get('hq_id')):>7} "
              f"{str(r.get('hq_id')==eu.get('hq_id')):>7}  on_turn={e.get('on_turn') if e else '?'}")
    P("")

OUT.close()
print("done")
