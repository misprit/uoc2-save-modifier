"""C9: is root units.yml the live battle table? compare with archive snapshot."""
import os, yaml, zipfile, io, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"

def zl(zf, n):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return None

def cmp_units(a, b):
    """a,b: lists of unit dicts. Return (common, n_field_diffs, sample)."""
    am = {u["id"]: u for u in a}
    bm = {u["id"]: u for u in b}
    common = set(am) & set(bm)
    diffs = 0
    sample = []
    for i in sorted(common):
        dd = {k: (am[i].get(k), bm[i].get(k)) for k in set(am[i]) | set(bm[i])
              if am[i].get(k) != bm[i].get(k)}
        if dd:
            diffs += 1
            if len(sample) < 3:
                sample.append((i, dd))
    return common, diffs, sample, set(am) - set(bm), set(bm) - set(am)

CASES = [
    (r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "in-battle, ID manifest"),
    (r"campaigns\Stalingrad.usg", "in-battle, ID manifest"),
    (r"Old Saves\Victory in the West\经典难度\west-LastWar.usg", "just entered"),
]
for rel, note in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        print("MISS", rel); continue
    print("=" * 112)
    print(f"{os.path.basename(p)}  [{note}]")
    print("=" * 112)
    with zipfile.ZipFile(p) as zf:
        m = zl(zf, "main.yml") or {}
        scen = (m.get("in_state") or {}).get("scenario")
        root = zl(zf, "units.yml") or []
        manifest = zl(zf, f"games/{scen}/units.yml") or []
        man_ids = set(manifest) if manifest and isinstance(manifest[0], int) else None
        print(f"  root units.yml: {len(root)} objects")
        print(f"  games/{scen}/units.yml: {len(manifest)} "
              f"{'ID manifest' if man_ids is not None else 'objects'}")
        if man_ids is not None:
            root_ids = {u["id"] for u in root}
            print(f"    manifest ⊆ root? {man_ids <= root_ids}")
            # the battle's units are the manifest ids; find them in root
            battle_in_root = [u for u in root if u["id"] in man_ids]
            print(f"    battle units resolved from root units.yml: {len(battle_in_root)}")
            # compare with archive last snapshot
            az = io.BytesIO(zf.read(f"games/{scen}/archive"))
            with zipfile.ZipFile(az) as a:
                snaps = sorted({n.split("/")[0] for n in a.namelist()})
                last = snaps[-1]
                snap_u = zl(a, f"{last}/units.yml") or []
                common, nd, samp, only_a, only_b = cmp_units(battle_in_root, snap_u)
                print(f"    archive[{last}]/units.yml: {len(snap_u)} objects")
                print(f"    root(battle subset) vs archive last: 共同={len(common)} "
                      f"字段有差异的单位={nd}  root多={len(only_a)} archive多={len(only_b)}")
                for i, dd in samp:
                    print(f"        unit {i}: {dd}")
                # and compare root(battle subset) vs archive FIRST snapshot
                first = snaps[0]
                snap0 = zl(a, f"{first}/units.yml") or []
                c0, nd0, s0, _, _ = cmp_units(battle_in_root, snap0)
                print(f"    root(battle subset) vs archive[{first}]: 共同={len(c0)} 差异单位={nd0}")
                for i, dd in s0[:2]:
                    print(f"        unit {i}: {dd}")
        print()

# Also: does the ROOT roster contain units NOT in the current battle?
print("=" * 112)
print("ROOT roster vs current battle (how many campaign units are outside the battle?)")
print("=" * 112)
for rel, note in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        continue
    with zipfile.ZipFile(p) as zf:
        m = zl(zf, "main.yml") or {}
        scen = (m.get("in_state") or {}).get("scenario")
        root = zl(zf, "units.yml") or []
        man = zl(zf, f"games/{scen}/units.yml") or []
        if man and isinstance(man[0], int):
            ids = set(man)
            print(f"  {os.path.basename(p):34s} root={len(root):4d} battle={len(ids):4d} "
                  f"root中不在本战斗的={len(root)-len(ids & {u['id'] for u in root})}")
