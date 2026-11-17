"""C3: fingerprint analysis -- what distinguishes each state, exactly."""
import os, yaml, zipfile, io, collections, json

GAME_SAVE = r"C:\Users\misprit\AppData\Local\.uoc2\save"

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

def snaps_of(usg, scen):
    try:
        with zipfile.ZipFile(usg) as zf:
            data = zf.read(f"games/{scen}/archive")
        with zipfile.ZipFile(io.BytesIO(data)) as az:
            return sorted({n.split("/")[0] for n in az.namelist()})
    except Exception:
        return []

ALL = []
for dp, dn, fn in os.walk(GAME_SAVE):
    for f in fn:
        if f.endswith(".usg"):
            ALL.append(os.path.join(dp, f))
ALL.sort()

recs = []
for p in ALL:
    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
        m = zl(zf, "main.yml", {}) or {}
        if m.get("standalone_scenario"):
            continue
        ins = m.get("in_state") or {}
        scen = ins.get("scenario")
        gm = zl(zf, f"games/{scen}/main.yml", {}) if scen else {}
        recs.append(dict(
            f=os.path.basename(p), rel=os.path.relpath(p, GAME_SAVE),
            cs=m.get("card_store"), cstart=m.get("conference_start_state"),
            conf=ins.get("conference"), front=ins.get("front"), scen=scen,
            var=ins.get("variant"), segfin=ins.get("segment_finished"),
            completed=ins.get("completed"), games=len([n for n in names if n.startswith("games/")]),
            turn=(gm or {}).get("turn"), phase=(gm or {}).get("phase"),
            deploy=(gm or {}).get("deployment"), gcompleted=(gm or {}).get("completed"),
            snaps=snaps_of(p, scen) if scen else [],
            lc=zl(zf, "last_conference/main.yml", None),
            lg=zl(zf, "last_game/main.yml", None),
            fronts={fr: {"seg": fv.get("segment"), "sit": fv.get("situation_idx"),
                         "played": len(fv.get("played_segments") or []),
                         "appr": fv.get("approved_plan")}
                    for fr, fv in (ins.get("fronts") or {}).items()},
        ))

print("=" * 120)
print("A) in_state.front  vs  in_state.scenario  -- are they equivalent?")
print("=" * 120)
a = collections.Counter((bool(r["front"]), bool(r["scen"])) for r in recs)
for k, v in sorted(a.items()):
    print(f"   front={str(k[0]):5s} scenario={str(k[1]):5s} -> {v} saves")

print()
print("=" * 120)
print("B) card_store / conference_start_state / segment_finished crosstab")
print("=" * 120)
b = collections.Counter((
    "cards" if r["cs"] is not None else "no-cards",
    "cstart{}" if r["cstart"] == {} else ("cstart-null" if r["cstart"] is None else "cstart-other"),
    "segfin-T" if r["segfin"] else "segfin-F",
) for r in recs)
for k, v in sorted(b.items()):
    print(f"   {k} -> {v} saves")

print()
print("=" * 120)
print("C) every save WITH in_state.scenario set  (battle entered)")
print("=" * 120)
print(f"  {'file':30s} {'scenario':22s} {'variant':22s} {'turn':5s} {'phase':6s} {'deployment':18s} {'gcompleted':11s} snapshots")
for r in sorted(recs, key=lambda x: (x["rel"] or "")):
    if not r["scen"]:
        continue
    print(f"  {r['f'][:30]:30s} {str(r['scen'])[:22]:22s} {str(r['var'])[:22]:22s} {str(r['turn']):5s} "
          f"{str(r['phase']):6s} {str(r['deploy']):18s} {str(r['gcompleted']):11s} {r['snaps']}")

print()
print("=" * 120)
print("D) ALL games/<x>/main.yml across all saves: turn==0 ? deployment values ?")
print("=" * 120)
gdirs = collections.Counter()
turn0 = []
for p in ALL:
    with zipfile.ZipFile(p) as zf:
        for g in sorted({n.split("/")[1] for n in zf.namelist() if n.startswith("games/")}):
            gm = zl(zf, f"games/{g}/main.yml", {}) or {}
            gdirs[(gm.get("turn"), gm.get("phase"), str(gm.get("deployment")),
                   gm.get("completed"), gm.get("outcome_status"))] += 1
            if gm.get("turn") == 0:
                turn0.append((os.path.basename(p), g, gm.get("deployment"), gm.get("completed")))
print("   (turn, phase, deployment, completed, outcome) histogram:")
for k, v in sorted(gdirs.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
    print(f"      turn={str(k[0]):5s} phase={str(k[1]):5s} deploy={k[2]:18s} completed={str(k[3]):5s} outcome={str(k[4]):5s} -> {v}")
print(f"\n   games with turn==0: {len(turn0)}")
for t in turn0[:15]:
    print("      ", t)

print()
print("=" * 120)
print("E) does last_game mirror the current battle?")
print("=" * 120)
for r in sorted(recs, key=lambda x: (x["rel"] or "")):
    if not r["scen"] or not r["lg"]:
        continue
    lgi = r["lg"].get("in_state") or {}
    same = (lgi.get("scenario") == r["scen"])
    print(f"  {r['f'][:30]:30s} current.scenario={str(r['scen'])[:22]:22s} "
          f"last_game.scenario={str(lgi.get('scenario'))[:22]:22s} match={same} "
          f"last_game.front={lgi.get('front')}")

print()
print("=" * 120)
print("F) fronts detail for the 6 sample west saves (the 4 user states)")
print("=" * 120)
for want in ["west-Conference1-1.usg", "west-Conference1-2.usg", "west-Conference2-1.usg",
             "west-Conference2-2.usg", "west-MonteCassino.usg", "west-Husky.usg",
             "Moscow-Conference1.usg", "Moscow-Conference1-2.usg"]:
    r = next((x for x in recs if x["f"] == want), None)
    if not r:
        continue
    print(f"\n  {want}")
    print(f"     card_store={'(null)' if r['cs'] is None else str(len(r['cs']))+' cards'} "
          f"conf_start={r['cstart']!r} seg_finished={r['segfin']}")
    print(f"     fronts={r['fronts']}")
    print(f"     last_conference present={r['lc'] is not None}  last_game present={r['lg'] is not None}")
