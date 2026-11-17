"""B16: data-driven field dictionary + catalogs + prestige/score flow."""
import sys, numpy, yaml, os, collections, zipfile, json
sys.path.append(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")

OUT = r"D:\MiniMax\_analysis\extracted"
PKG = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages"
SERIES = r"C:\Users\misprit\AppData\Local\.uoc2\save\Old Saves\Victory in the West\困难难度-史实线"

def load(p):
    return yaml.safe_load(open(p, "r", encoding="utf-8").read())

# ---------- 1. observed field dictionary across BOTH saves ----------
print("=" * 80)
print("1) OBSERVED FIELD DICTIONARY (union over both sample saves)")
print("=" * 80)
agg = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
for tag in ["conf3", "ahist2"]:
    base = os.path.join(OUT, tag)
    for dirpath, dirnames, filenames in os.walk(base):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, base).replace("\\", "/")
            if rel.startswith("games/") and "/archive/" in rel:
                rel = "games/<x>/archive/<snap>/" + os.path.basename(rel)
            elif rel.startswith("games/"):
                rel = "games/<x>/" + os.path.basename(rel)
            elif rel.startswith("document/"):
                rel = "document/" + ("<sub>/" if "/" in rel[len("document/"):] else "") + os.path.basename(rel)
            elif rel.startswith("last_"):
                rel = rel.split("/")[0] + "/" + os.path.basename(rel)
            if fn.endswith(".yml"):
                try:
                    d = load(fp)
                except Exception:
                    continue
                if isinstance(d, list):
                    for item in d:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                agg[rel][k][type(v).__name__] += 1
                elif isinstance(d, dict):
                    for k, v in d.items():
                        agg[rel][k][type(v).__name__] += 1

for rel in sorted(agg):
    fields = agg[rel]
    print(f"\n  {rel}   ({len(fields)} top-level keys)")
    for k in sorted(fields):
        t = ",".join(f"{n}:{c}" for n, c in fields[k].most_common(3))
        print(f"     {k:26s} {t}")

# ---------- 2. catalogs ----------
print()
print("=" * 80)
print("2) CATALOGS from the game package (for GUI dropdowns)")
print("=" * 80)
def load_dir(sub):
    out = {}
    for pkg in ["base", "dlc1", "dlc2", "dlc3", "dlc4", "dlc5", "dlc6", "dlc7", "dlc8", "dlc9", "dlc10"]:
        d = os.path.join(PKG, pkg, "data", "entity_types", sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".yml"):
                continue
            try:
                raw = yaml.safe_load(open(os.path.join(d, f), encoding="utf-8").read())
            except Exception:
                continue
            if isinstance(raw, dict):
                out[f[:-4]] = raw
    return out

cards = load_dir("cards")
specs = load_dir("specialists")
units = load_dir("unit_types")
print(f"  cards={len(cards)} specialists={len(specs)} unit_types={len(units)}")
print("\n  CARD TABLE (type, cost, faction, has_unit, meta_type, recoup):")
for name, c in sorted(cards.items(), key=lambda x: (str(x[1].get('cost')), x[0])):
    print(f"    {name:32s} cost={str(c.get('cost')):>4s} fac={str(c.get('faction')):7s} "
          f"unit={str(c.get('has_unit')):5s} meta={str(c.get('meta_type')):22s} recoup={c.get('recoup')}")
print("\n  SPECIALIST TABLE (type, faction, nationality, att/dfe/armor/arty, flags) count=%d" % len(specs))
for name, s in list(sorted(specs.items()))[:12]:
    print(f"    {name:30s} fac={str(s.get('faction')):7s} nat={str(s.get('nationality')):14s} "
          f"att={s.get('att_idx')} dfe={s.get('dfe_idx')} arm={s.get('armor')} arty={s.get('artillery')} flags={s.get('flags')}")
print(f"    ... ({len(specs)} total)")
flags = collections.Counter()
for s in specs.values():
    for fl in (s.get("flags") or []):
        flags[fl] += 1
print("  specialist flag histogram:", dict(flags.most_common()))

# ---------- 3. prestige / score flow across the progression ----------
print()
print("=" * 80)
print("3) PRESTIGE / SCORE FLOW across the 16-save progression series")
print("=" * 80)
files = sorted(f for f in os.listdir(SERIES) if f.endswith(".usg"))
def srt(f):
    import re
    d = re.findall(r"\d+", f)
    return (int(d[0]) if d else 0, int(d[1]) if len(d) > 1 else 0)
files.sort(key=srt)
print(f"  {'file':26s} {'root.prestige':>13s} {'root.score':>11s} {'last_conf.prestige':>20s} "
      f"{'last_conf.score':>16s} {'battle.start':>12s} {'battle.end':>11s} {'delta':>7s}")
for f in files:
    p = os.path.join(SERIES, f)
    with zipfile.ZipFile(p) as zf:
        def zl(n, d=None):
            try:
                return yaml.safe_load(zf.read(n).decode("utf-8"))
            except KeyError:
                return d
        m = zl("main.yml", {}) or {}
        lc = zl("last_conference/main.yml", {}) or {}
        # find the battle dir = games/<x> with the latest archive
        games = sorted({n.split("/")[1] for n in zf.namelist() if n.startswith("games/")})
        bp = sp = ep = None
        for g in reversed(games):
            gm = zl(f"games/{g}/main.yml", None)
            if gm and gm.get("start_data"):
                bp = g
                sp = (gm.get("start_data") or {}).get("prestige")
                ep = (gm.get("end_data") or {}).get("prestige")
                break
        d = (ep - sp) if (sp is not None and ep is not None) else None
        print(f"  {f:26s} {str(m.get('prestige')):>13s} {str(m.get('score')):>11s} "
              f"{str(lc.get('prestige')):>20s} {str(lc.get('score')):>16s} "
              f"{str(sp):>12s} {str(ep):>11s} {str(d):>7s}   [{bp}]")
