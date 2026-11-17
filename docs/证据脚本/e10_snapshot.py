# -*- coding: utf-8 -*-
"""E10: archive 快照的完整文件清单 + games/<场景>/main.yml 与最后快照的对比"""
import os, io, zipfile, yaml

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e10_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

CASES = [
    (r"campaigns\Stalingrad.usg", "road_to_stalingrad"),
    (r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "husky"),
    (r"Old Saves\Victory in the West\经典难度\west-MonteCassino.usg", "monte_cassino"),
]

for rel, scen in CASES:
    p = os.path.join(G, rel)
    P("=" * 100)
    P(f"{os.path.basename(p)}   scenario={scen}")
    P("=" * 100)
    with zipfile.ZipFile(p) as zf:
        az = zipfile.ZipFile(io.BytesIO(zf.read(f"games/{scen}/archive")))
        snaps = sorted({n.split("/")[0] for n in az.namelist()})
        last = snaps[-1]
        P(f"  archive 快照 {len(snaps)} 个，最后一个 = {last}")
        P(f"  最后快照的文件清单:")
        for n in sorted(x for x in az.namelist() if x.startswith(last + "/")):
            P(f"      {n[len(last)+1:]}")

        gm = zl(zf, f"games/{scen}/main.yml")
        sm = zl(az, f"{last}/main.yml")
        P(f"  games/{scen}/main.yml  键: {sorted(gm.keys()) if isinstance(gm, dict) else type(gm)}")
        P(f"  snapshot/main.yml      键: {sorted(sm.keys()) if isinstance(sm, dict) else type(sm)}")
        if isinstance(gm, dict) and isinstance(sm, dict):
            diff = {k: (gm.get(k), sm.get(k)) for k in set(gm) | set(sm) if gm.get(k) != sm.get(k)}
            P(f"  main.yml 差异字段: {diff if diff else '无（完全一致）'}")
            P(f"    games turn/phase/ar_ord = {gm.get('turn')}/{gm.get('phase')}/{gm.get('ar_ord')}")
            P(f"    snap  turn/phase/ar_ord = {sm.get('turn')}/{sm.get('phase')}/{sm.get('ar_ord')}")

        ga = zl(zf, f"games/{scen}/ar_list.yml")
        sa = zl(az, f"{last}/ar_list.yml")
        P(f"  games ar_list.yml: {type(ga).__name__} 长度 {len(ga) if ga is not None else None}")
        P(f"  snap  ar_list.yml: {type(sa).__name__} 长度 {len(sa) if sa is not None else None}")
        if isinstance(ga, list) and isinstance(sa, list):
            P(f"    是否相同: {ga == sa}")
            P(f"    games 最后 2 条: {ga[-2:]}")
            P(f"    snap  最后 2 条: {sa[-2:]}")

        # hqs
        gh = zl(zf, f"games/{scen}/hqs.yml")
        sh = zl(az, f"{last}/hqs.yml")
        P(f"  games/{scen}/hqs.yml: {type(gh).__name__} 长度 {len(gh) if gh is not None else None}  内容 {gh}")
        P(f"  snapshot/hqs.yml    : {type(sh).__name__} 长度 {len(sh) if sh is not None else None}")
        P("")

OUT.close()
print("done")
