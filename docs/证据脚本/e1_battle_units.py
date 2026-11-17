"""E1: 战斗中存档的单位数据到底存在哪？（严格验证）"""
import os, yaml, zipfile, io, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"

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
    (r"campaigns\Stalingrad.usg", "战斗进行中(第1回合)"),
    (r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "战斗进行中(第5回合)"),
    (r"Old Saves\Victory in the West\经典难度\west-LastWar.usg", "刚进部署阶段"),
    (r"Old Saves\Victory in the West\经典难度\west-MonteCassino.usg", "战斗进行中(第6回合)"),
]

for rel, note in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        print("MISS", rel); continue
    print("=" * 118)
    print(f"{os.path.basename(p)}   [{note}]")
    print("=" * 118)
    with zipfile.ZipFile(p) as zf:
        m = zl(zf, "main.yml") or {}
        ins = m.get("in_state") or {}
        scen = ins.get("scenario")
        root = zl(zf, "units.yml") or []
        rootmap = {u["id"]: u for u in root}
        manifest = zl(zf, f"games/{scen}/units.yml") or []
        man_ids = set(manifest)
        root_ids = set(rootmap)
        print(f"  in_state.scenario = {scen}")
        print(f"  ① 根 units.yml（总表）        : {len(root)} 个单位对象")
        print(f"  ② games/{scen}/units.yml      : {len(manifest)} 个 "
              f"{'int → ID 清单' if manifest and isinstance(manifest[0], int) else '对象'}")
        print(f"     清单 ⊆ 总表 ? {man_ids <= root_ids}    "
              f"总表里不在本场的单位数 = {len(root_ids - man_ids)}")

        az = arch(p, scen)
        if az:
            snaps = sorted({n.split("/")[0] for n in az.namelist()})
            last = snaps[-1]
            snap_u = zl(az, f"{last}/units.yml") or []
            snap_ids = {u["id"] for u in snap_u}
            print(f"  ③ archive/{last}/units.yml   : {len(snap_u)} 个单位对象")
            print(f"     清单 ∩ 快照 = {len(man_ids & snap_ids)}   "
                  f"只在清单 = {sorted(man_ids - snap_ids)}   只在快照 = {sorted(snap_ids - man_ids)}")
            # root(清单子集) vs 快照
            cmp = {}
            for i in sorted(man_ids & snap_ids):
                a, b = rootmap[i], next(u for u in snap_u if u["id"] == i)
                dd = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
                if dd:
                    cmp[i] = dd
            print(f"     总表内该单位 vs 快照：{len(man_ids & snap_ids)} 个可比，"
                  f"{len(cmp)} 个有字段差异")
            for i, dd in list(cmp.items())[:3]:
                print(f"        unit {i}: {dd}")

            print(f"\n  ④ campaign_units.yml（每个快照）")
            print(f"     {'快照':32s} {'units.yml':>10s} {'campaign_units':>16s}  说明")
            for s in snaps:
                uu = zl(az, f"{s}/units.yml", []) or []
                cu = zl(az, f"{s}/campaign_units.yml", None)
                if cu is None:
                    note2 = "（无此文件）"
                    n = "-"
                else:
                    n = len(cu)
                    note2 = f"ids={[x['id'] for x in cu][:8]}"
                print(f"     {s:32s} {len(uu):>10d} {str(n):>16s}  {note2}")

    print()
