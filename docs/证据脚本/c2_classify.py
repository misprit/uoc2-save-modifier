"""C2: definitive state classifier + decision-tree validation over all 70 saves."""
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

def classify(usg):
    R = {"file": os.path.basename(usg)}
    with zipfile.ZipFile(usg) as zf:
        names = zf.namelist()
        m = zl(zf, "main.yml", {}) or {}
        if m.get("standalone_scenario"):
            R["kind"] = "standalone"
            R["state"] = "S5_STANDALONE"
            gm = zl(zf, "game/main.yml", None)
            R["battle"] = {"turn": (gm or {}).get("turn"), "phase": (gm or {}).get("phase"),
                           "deployment": (gm or {}).get("deployment"),
                           "completed": (gm or {}).get("completed")}
            R["snaps"] = len(snaps_of(usg, "")) if False else 0
            try:
                with zipfile.ZipFile(usg) as z2:
                    R["snaps"] = len(sorted({n.split("/")[0] for n in z2.namelist()
                                             if n.startswith("game/archive/")}))
            except Exception:
                pass
            return R
        R["kind"] = "campaign"
        ins = m.get("in_state") or {}
        scen = ins.get("scenario")
        R["conference"] = ins.get("conference")
        R["front"] = ins.get("front")
        R["scenario"] = scen
        R["variant"] = ins.get("variant")
        R["segment_finished"] = ins.get("segment_finished")
        R["card_store"] = m.get("card_store")
        R["conf_start"] = m.get("conference_start_state")
        R["prestige"] = m.get("prestige")
        R["score"] = m.get("score")
        games = sorted({n.split("/")[1] for n in names if n.startswith("games/")})
        R["games"] = games
        R["game_main"] = {}
        for g in games:
            gm = zl(zf, f"games/{g}/main.yml", {}) or {}
            R["game_main"][g] = {"completed": gm.get("completed"), "turn": gm.get("turn"),
                                 "phase": gm.get("phase"), "deployment": gm.get("deployment")}
        # checkpoints
        for cp in ("last_conference", "last_game"):
            cm = zl(zf, f"{cp}/main.yml", None)
            if cm:
                ci = cm.get("in_state") or {}
                R[cp] = {"prestige": cm.get("prestige"), "score": cm.get("score"),
                         "card_store": cm.get("card_store"),
                         "conf_start": cm.get("conference_start_state"),
                         "scenario": ci.get("scenario"), "front": ci.get("front"),
                         "seg_finished": ci.get("segment_finished")}
        # front detail
        R["fronts"] = {fr: {"segment": fv.get("segment"), "situation_idx": fv.get("situation_idx"),
                            "played": fv.get("played_segments"),
                            "approved": fv.get("approved_plan"), "tmp": fv.get("tmp_approved_plan")}
                       for fr, fv in (ins.get("fronts") or {}).items()}
        # current battle snapshot state
        if scen:
            R["cur_snaps"] = snaps_of(usg, scen)
            R["cur_exists"] = f"games/{scen}/main.yml" in names
        else:
            R["cur_snaps"] = []
            R["cur_exists"] = False

    # ---------- decision tree ----------
    cs = R.get("card_store")
    if R["kind"] == "standalone":
        R["state"] = "S5_STANDALONE"
        R["reason"] = "standalone_scenario 非空"
    elif R["scenario"]:
        # inside / entering a battle
        gm = R["game_main"].get(R["scenario"], {})
        turn = gm.get("turn")
        sn = R["cur_snaps"]
        turn_snaps = [x for x in sn if x.startswith("turn_")]
        if turn_snaps or (turn or 0) > 0:
            R["state"] = "S1_IN_BATTLE"
            R["reason"] = (f"in_state.scenario={R['scenario']} 且战斗已推进 "
                           f"(turn={turn}, 快照 {len(sn)} 个)")
        else:
            R["state"] = "S3_DEPLOYMENT"
            R["reason"] = (f"in_state.scenario={R['scenario']} 但战斗未开始 "
                           f"(turn={turn}, 快照仅 {sn})")
    elif cs is not None:
        R["state"] = "S4_CONFERENCE"
        R["reason"] = (f"card_store 有 {len(cs)} 张牌 (会议已发牌), "
                       f"conference_start_state={R['conf_start']!r}")
    elif R.get("segment_finished"):
        R["state"] = "S2_SCENARIO_DONE"
        R["reason"] = ("scenario=null 且 segment_finished=true, card_store=null "
                       "(本场已打完, 下一场未激活)")
    else:
        R["state"] = "S0_UNKNOWN"
        R["reason"] = "scenario=null, card_store=null, segment_finished=false"
    return R

rows = []
for dp, dn, fn in os.walk(GAME_SAVE):
    for f in fn:
        if f.endswith(".usg"):
            p = os.path.join(dp, f)
            try:
                r = classify(p)
            except Exception as e:
                print(f"!! {p}: {type(e).__name__}: {e}")
                continue
            r["rel"] = os.path.relpath(p, GAME_SAVE)
            rows.append(r)

rows.sort(key=lambda r: (r.get("rel") or ""))
print("=" * 118)
print(f"CLASSIFICATION OF {len(rows)} SAVES")
print("=" * 118)
print(f"  {'file':30s} {'state':18s} {'conf':10s} {'front':7s} {'scenario':20s} "
      f"{'variant':22s} {'segfin':7s} {'cardStore':10s} {'games':6s} {'turn':5s}")
for r in rows:
    gm = (r.get("game_main") or {}).get(r.get("scenario") or "", {})
    print(f"  {r['file'][:30]:30s} {r['state']:18s} {str(r.get('conference')):10s} "
          f"{str(r.get('front')):7s} {str(r.get('scenario')):20s} {str(r.get('variant')):22s} "
          f"{str(r.get('segment_finished')):7s} {str(len(r['card_store']) if r.get('card_store') is not None else None):10s} "
          f"{len(r.get('games') or []):<6d} {str(gm.get('turn')):5s}")

print()
print("=" * 118)
print("STATE HISTOGRAM")
print("=" * 118)
h = collections.Counter(r["state"] for r in rows)
for k, v in sorted(h.items()):
    print(f"  {k:20s} {v}")

print()
print("=" * 118)
print("ONE EXAMPLE PER STATE (full detail)")
print("=" * 118)
seen = set()
for r in rows:
    if r["state"] in seen:
        continue
    seen.add(r["state"])
    print(f"\n### {r['state']}  --  {r['rel']}")
    for k in ["conference", "front", "scenario", "variant", "segment_finished", "card_store",
              "conf_start", "prestige", "score", "cur_exists", "cur_snaps", "reason"]:
        if k in r:
            print(f"    {k:18s} = {r[k]!r}")
    print(f"    fronts            = {r.get('fronts')}")
    print(f"    last_conference   = {r.get('last_conference')}")
    print(f"    last_game         = {r.get('last_game')}")
    print(f"    games             = {r.get('games')}")
