"""D1: combinatorial coverage analysis of the save state space."""
import os, yaml, zipfile, io, collections, itertools, json

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

def snaps(usg, scen):
    try:
        with zipfile.ZipFile(usg) as zf:
            data = zf.read(f"games/{scen}/archive")
        with zipfile.ZipFile(io.BytesIO(data)) as az:
            return sorted({n.split("/")[0] for n in az.namelist()})
    except Exception:
        return []

def sig(usg):
    """Full discriminating signature of a save."""
    with zipfile.ZipFile(usg) as zf:
        names = zf.namelist()
        m = zl(zf, "main.yml", {}) or {}
        ins = m.get("in_state") or {}
        scen = ins.get("scenario")
        has_root_units = "units.yml" in names
        cs = m.get("card_store")
        cstart = m.get("conference_start_state")
        sn = snaps(usg, scen) if scen else []
        has_turn = any(x.startswith("turn_") for x in sn)
        has_dep = any(x.startswith("deployment_phase") for x in sn)
        lg = zl(zf, "last_game/main.yml", None)
        lc = zl(zf, "last_conference/main.yml", None)
        fronts = ins.get("fronts") or {}
        return dict(
            standalone=bool(m.get("standalone_scenario")),
            scenario=bool(scen), variant=bool(ins.get("variant")),
            card_store=(None if cs is None else len(cs)),
            cstart=("None" if cstart is None else ("{}" if cstart == {} else "other")),
            seg_finished=ins.get("segment_finished"),
            completed=ins.get("completed"),
            lost=bool(ins.get("lost_scenario")),
            reverted_games=len(m.get("reverted_games") or []),
            has_root_units=has_root_units,
            n_games=len({n.split("/")[1] for n in names if n.startswith("games/")}),
            last_game=lg is not None,
            last_conf=lc is not None,
            has_turn=has_turn, has_dep=has_dep,
            front_seg=bool((fronts.get("france") or {}).get("segment")
                           or (fronts.get("italy") or {}).get("segment")
                           or any((v or {}).get("segment") for v in fronts.values())),
            any_played=any(len((v or {}).get("played_segments") or []) for v in fronts.values()),
            approved=any((v or {}).get("approved_plan") for v in fronts.values()),
            n_milestones=len(m.get("milestones") or []),
        )

paths = []
for dp, dn, fn in os.walk(G):
    for f in fn:
        if f.endswith(".usg"):
            paths.append(os.path.join(dp, f))
paths.sort()

recs = []
for p in paths:
    s = sig(p)
    s["file"] = os.path.basename(p)
    s["rel"] = os.path.relpath(p, G)
    recs.append(s)

# ---------- state labels ----------
def label(s):
    if s["standalone"]:
        return "S5_独立场景"
    if s["scenario"]:
        if s["has_turn"]:
            return "S1_战斗进行中"
        if s["has_dep"]:
            return "S2_部署阶段"
        return "S2x_已激活但无归档"
    if s["card_store"] is not None:
        return ("S0a_战役开局会议界面" if not s["has_root_units"]
                else "S0b_会议界面(已有单位)")
    if s["seg_finished"]:
        return "S4_本段打完待会议"
    return "S3_场景打完未激活下一个"

print("=" * 118)
print("A) 状态分布（按综合判据）")
print("=" * 118)
h = collections.Counter(label(s) for s in recs)
for k, v in sorted(h.items()):
    ex = [s["file"] for s in recs if label(s) == k][:3]
    print(f"  {k:28s} {v:3d}   eg {ex}")

print()
print("=" * 118)
print("B) 判别字段的取值空间 vs 实际出现情况")
print("=" * 118)
FIELDS = ["standalone", "scenario", "variant", "card_store", "cstart", "seg_finished",
          "completed", "lost", "reverted_games", "has_root_units", "last_game",
          "last_conf", "has_turn", "has_dep", "front_seg", "any_played", "approved"]
for f in FIELDS:
    c = collections.Counter(s[f] for s in recs)
    print(f"  {f:18s} {dict(sorted(c.items(), key=lambda x: str(x[0])))}")

print()
print("=" * 118)
print("C) 未被覆盖的组合（把独立字段做笛卡尔积，只列出有业务含义的）")
print("=" * 118)

# meaningful combinations
DIMS = {
    "standalone": [False, True],
    "scenario":   [False, True],
    "card_store": [None, ">0"],
    "has_root_units": [False, True],
    "last_game":  [False, True],
    "last_conf":  [False, True],
    "seg_finished": [False, True],
    "has_turn":   [False, True],
}

def norm(s):
    d = dict(s)
    d["card_store"] = None if s["card_store"] is None else ">0"
    return tuple(d[k] for k in DIMS)

covered = collections.Counter(norm(s) for s in recs)

def plausible(c):
    (standalone, scenario, cs, has_units, lg, lc, segfin, has_turn) = c
    if standalone:
        # 独立场景: 没有战役层
        return not (cs is not None or lg or lc or segfin or has_units)
    if scenario:
        # 战斗中: card_store 应为 None; 一定有 last_game(战斗检查点); 不看 seg_finished
        return cs is None and lg and not has_turn and not lc
    # 非战斗中
    if cs is not None:
        # 会议界面
        return has_units and not has_turn
    # 非会议、非战斗
    return has_units and lg and lc

rows = []
for c in itertools.product(*[DIMS[k] for k in DIMS]):
    if not plausible(c):
        continue
    n = covered.get(c, 0)
    rows.append((n, c))
rows.sort(key=lambda x: (x[0], str(x[1])))

print(f"  {'覆盖数':>6s}  {'standalone':>10s} {'scenario':>9s} {'cardStore':>10s} {'rootUnits':>10s} "
      f"{'last_game':>10s} {'last_conf':>10s} {'segFin':>7s} {'turn?':>6s}")
for n, c in rows:
    (standalone, scenario, cs, has_units, lg, lc, segfin, has_turn) = c
    mark = "  <== 未覆盖" if n == 0 else ""
    print(f"  {n:>6d}  {str(standalone):>10s} {str(scenario):>9s} {str(cs):>10s} "
          f"{str(has_units):>10s} {str(lg):>10s} {str(lc):>10s} {str(segfin):>7s} "
          f"{str(has_turn):>6s}{mark}")

print()
print("=" * 118)
print("D) 关键空白点的具体样例（S0b 等）")
print("=" * 118)
for s in recs:
    if s["card_store"] is not None:
        print(f"  card_store 非空: {s['file']:32s} root_units={s['has_root_units']} "
              f"n_games={s['n_games']} last_game={s['last_game']} last_conf={s['last_conf']} "
              f"milestones={s['n_milestones']} segfin={s['seg_finished']}")
