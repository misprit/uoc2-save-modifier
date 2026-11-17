"""C1: classify every save we can find into campaign-flow states."""
import os, yaml, zipfile, re, json, collections

GAME_SAVE = r"C:\Users\misprit\AppData\Local\.uoc2\save"

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

def probe(usg):
    """Extract every state marker we can find."""
    out = {"file": os.path.basename(usg)}
    with zipfile.ZipFile(usg) as zf:
        names = zf.namelist()
        m = zl(zf, "main.yml", {}) or {}
        out["root_exists"] = "main.yml" in names
        if not out["root_exists"]:
            return out
        out["standalone"] = m.get("standalone_scenario")
        out["level"] = m.get("level")
        out["prestige"] = m.get("prestige")
        out["score"] = m.get("score")
        out["card_store"] = len(m.get("card_store") or []) if m.get("card_store") is not None else None
        out["conf_start_state"] = m.get("conference_start_state")
        ins = m.get("in_state") or {}
        out["conference"] = ins.get("conference")
        out["front"] = ins.get("front")
        out["scenario"] = ins.get("scenario")
        out["variant"] = ins.get("variant")
        out["segment_finished"] = ins.get("segment_finished")
        out["completed"] = ins.get("completed")
        out["lost_scenario"] = ins.get("lost_scenario")
        for fr, fv in (ins.get("fronts") or {}).items():
            out[f"front_{fr}"] = (fv.get("segment"), fv.get("situation_idx"),
                                  fv.get("approved_plan"), fv.get("tmp_approved_plan"),
                                  len(fv.get("played_segments") or []))
        # checkpoints
        for cp in ("last_conference", "last_game"):
            cm = zl(zf, f"{cp}/main.yml", None)
            if cm is None:
                out[cp] = None
                continue
            ci = cm.get("in_state") or {}
            out[cp] = dict(prestige=cm.get("prestige"), score=cm.get("score"),
                           card_store=(len(cm.get("card_store") or [])
                                       if cm.get("card_store") is not None else None),
                           conf_start_state=cm.get("conference_start_state"),
                           conference=ci.get("conference"), front=ci.get("front"),
                           scenario=ci.get("scenario"), variant=ci.get("variant"),
                           seg_finished=ci.get("segment_finished"))
        # games
        games = {}
        for g in sorted({n.split("/")[1] for n in names if n.startswith("games/")}):
            gm = zl(zf, f"games/{g}/main.yml", None)
            if gm is None:
                games[g] = {"main": None}
                continue
            try:
                with zipfile.ZipFile.__new__(zipfile.ZipFile) if False else open(os.devnull, "rb"):
                    pass
            except Exception:
                pass
            games[g] = dict(
                completed=gm.get("completed"), turn=gm.get("turn"), phase=gm.get("phase"),
                deployment=gm.get("deployment"), outcome=gm.get("outcome_status"),
                victory=gm.get("victory_level"), start=gm.get("start"),
                has_archive="games/%s/archive" % g in names,
                start_prestige=(gm.get("start_data") or {}).get("prestige"),
                end_prestige=(gm.get("end_data") or {}).get("prestige"))
        out["games"] = games
        # archive snapshot count for the current scenario
        cur = out["scenario"]
        if cur and f"games/{cur}/archive" in names:
            with zipfile.ZipFile(usg) as _:
                pass
        try:
            with zipfile.ZipFile(os.path.join(usg)) as _:
                pass
        except Exception:
            pass
        out["cur_game_dir"] = f"games/{cur}" if cur else None
        out["cur_game_exists"] = bool(cur) and (f"games/{cur}/main.yml" in names)
    return out

def archive_snaps(usg, scen):
    try:
        with zipfile.ZipFile(usg) as zf:
            data = zf.read(f"games/{scen}/archive")
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as az:
            snaps = sorted({n.split("/")[0] for n in az.namelist()})
        return snaps
    except Exception:
        return []

# ---------- gather all saves ----------
all_saves = []
for dp, dn, fn in os.walk(GAME_SAVE):
    for f in fn:
        if f.endswith(".usg"):
            all_saves.append(os.path.join(dp, f))
all_saves.sort()
print(f"found {len(all_saves)} .usg files under {GAME_SAVE}")
for s in all_saves:
    print("   ", os.path.relpath(s, GAME_SAVE))

print()
print("=" * 110)
print("STATE TABLE")
print("=" * 110)
rows = []
for s in all_saves:
    try:
        p = probe(s)
    except Exception as e:
        print(f"!! {s}: {type(e).__name__}: {e}")
        continue
    p["path"] = os.path.relpath(s, GAME_SAVE)
    cur = p.get("scenario")
    p["cur_snaps"] = len(archive_snaps(s, cur)) if cur else 0
    rows.append(p)

hdr = ["file", "conference", "front", "scenario", "variant", "seg_fin", "card_store",
       "conf_start", "prestige", "score", "games", "cur_snap"]
print("  ".join(f"{h}" for h in hdr))
for p in rows:
    print(f"{p['file'][:26]:26s} {str(p.get('conference')):11s} {str(p.get('front')):7s} "
          f"{str(p.get('scenario')):15s} {str(p.get('variant')):22s} {str(p.get('segment_finished')):7s} "
          f"{str(p.get('card_store')):10s} {str(p.get('conf_start_state')):10s} "
          f"{str(p.get('prestige')):9s} {str(p.get('score')):7s} {len(p.get('games') or {}):5d} "
          f"{p.get('cur_snap')}")

print()
print("=" * 110)
print("DETAIL: games/<scenario> runtime state")
print("=" * 110)
for p in rows:
    if not p.get("games"):
        continue
    print(f"\n--- {p['file']}   (in_state.scenario={p.get('scenario')}) ---")
    for g, v in sorted(p["games"].items()):
        print(f"    {g:22s} {v}")
