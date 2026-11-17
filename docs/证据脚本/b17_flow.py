"""B17: prestige/score flow + card & specialist catalogs (compact)."""
import os, yaml, zipfile, re, collections, sys

PKG = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages"
SERIES = r"C:\Users\misprit\AppData\Local\.uoc2\save\Old Saves\Victory in the West\困难难度-史实线"

print("=" * 92)
print("PRESTIGE / SCORE FLOW across the 16-save progression series")
print("=" * 92)
files = sorted(f for f in os.listdir(SERIES) if f.endswith(".usg"))
def srt(f):
    d = re.findall(r"\d+", f)
    return (int(d[0]) if d else 0, int(d[1]) if len(d) > 1 else 0)
files.sort(key=srt)
print(f"  {'save file':26s} {'root.prest':>10s} {'root.score':>10s} | {'lastConf.prest':>14s} "
      f"{'lastConf.score':>14s} | {'btl.start':>9s} {'btl.end':>8s} {'delta':>6s} | battle")
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
        lg = zl("last_game/main.yml", {}) or {}
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
        print(f"  {f:26s} {str(m.get('prestige')):>10s} {str(m.get('score')):>10s} | "
              f"{str(lc.get('prestige')):>14s} {str(lc.get('score')):>14s} | "
              f"{str(sp):>9s} {str(ep):>8s} {str(d):>6s} | {bp}")
        print(f"       last_game: prestige={lg.get('prestige')} score={lg.get('score')} "
              f"scenario={((lg.get('in_state') or {}).get('scenario'))} "
              f"variant={((lg.get('in_state') or {}).get('variant'))} "
              f"seg_finished={((lg.get('in_state') or {}).get('segment_finished'))} "
              f"cards={len(lg.get('card_store') or [])}")

print()
print("=" * 92)
print("CARD CATALOG (base+dlc)")
print("=" * 92)
def load_dir(sub):
    out = {}
    for pkg in ["base", "dlc1", "dlc2", "dlc3", "dlc4", "dlc5", "dlc6", "dlc7", "dlc8", "dlc9", "dlc10"]:
        d = os.path.join(PKG, pkg, "data", "entity_types", sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".yml"):
                continue
            try:
                raw = yaml.safe_load(open(os.path.join(d, fn), encoding="utf-8").read())
            except Exception:
                continue
            if isinstance(raw, dict):
                out[fn[:-4]] = raw
    return out
cards = load_dir("cards")
specs = load_dir("specialists")
units = load_dir("unit_types")
print(f"  {len(cards)} card types")
for name, c in sorted(cards.items(), key=lambda x: (str(x[1].get('cost')), x[0])):
    print(f"    {name:34s} cost={str(c.get('cost')):>4s} fac={str(c.get('faction')):7s} "
          f"has_unit={str(c.get('has_unit')):5s} meta={str(c.get('meta_type')):20s} "
          f"recoup={c.get('recoup')} persistent={c.get('persistent')}")
print(f"\n  {len(specs)} specialist types; flags histogram:")
fh = collections.Counter()
for s in specs.values():
    for fl in (s.get("flags") or []):
        fh[fl] += 1
print("   ", dict(fh.most_common()))
print(f"\n  unit_type max_st histogram: ", end="")
ms = collections.Counter(v.get("max_st") for v in units.values())
print(dict(sorted(ms.items(), key=lambda x: (x[0] is None, x[0]))))
print(f"  unit_type max_spec histogram:", end=" ")
mx = collections.Counter(v.get("max_spec") for v in units.values())
print(dict(sorted(mx.items(), key=lambda x: (x[0] is None, x[0]))))
print("\n  units whose type has max_st/max_spec (sample):")
for n in ["us_inf_42", "ger_inf_39", "uk_inf_42", "us_armx_42", "ger_pz_pz4_42"]:
    v = units.get(n)
    print(f"    {n:16s} {({k: v.get(k) for k in ('faction','nationality','movement','attack','defense','armor','max_st','max_spec','equipment','equipment_q','name_brief')} if v else 'MISSING')}")
