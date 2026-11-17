"""D4: last specifics -- lost_scenario, completed-campaign signature, set_conference callers."""
import marshal, types, os, dis, io, re, zipfile, yaml, collections

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\uoc2"
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"

def load_pyc(path):
    with open(path, "rb") as f:
        return marshal.loads(f.read()[16:])

def walk(code, out, depth=0):
    out.append(code)
    for c in code.co_consts:
        if isinstance(c, types.CodeType) and depth < 8:
            walk(c, out, depth + 1)
    return out

print("=" * 100)
print("A) set_conference call sites (with the save_revert_data argument)")
print("=" * 100)
code = load_pyc(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
for c in walk(code, []):
    txt = io.StringIO()
    dis.dis(c, file=txt)
    s = txt.getvalue()
    if "set_conference" in s and c.co_name != "set_conference":
        keeps = [l.strip() for l in s.splitlines()
                 if any(k in l for k in ("set_conference", "LOAD_CONST", "LOAD_FAST", "LOAD_ATTR",
                                         "STORE_FAST", "CALL"))]
        print(f"\n  fn {c.co_name}({', '.join(c.co_varnames[:c.co_argcount])})")
        for l in keeps[:40]:
            print("     ", l)

print()
print("=" * 100)
print("B) where is in_state.lost_scenario / completed set? (name-based search)")
print("=" * 100)
for rel in ["state/campaign/campaign.pyc", "state/campaign/conferences.pyc",
            "state/campaign/segments.pyc", "state/campaign/front.pyc",
            "state/campaign/tools.pyc", "state/campaign/conference_actions.pyc"]:
    p = os.path.join(LIB, rel.replace("/", os.sep))
    if not os.path.isfile(p):
        continue
    code = load_pyc(p)
    for c in walk(code, []):
        txt = io.StringIO()
        dis.dis(c, file=txt)
        s = txt.getvalue()
        if "lost_scenario" in s:
            print(f"\n  {rel} :: fn {c.co_name}")
            for l in s.splitlines():
                if "lost_scenario" in l or "STORE_ATTR" in l or "LOAD_ATTR" in l:
                    print("     ", l.strip())

print()
print("=" * 100)
print("C) the completed-campaign saves: full signature")
print("=" * 100)
def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d
paths = []
for dp, dn, fn in os.walk(G):
    for f in fn:
        if f.endswith(".usg"):
            paths.append(os.path.join(dp, f))
paths.sort()
for p in paths:
    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
        m = zl(zf, "main.yml", {}) or {}
        if not (m.get("in_state") or {}).get("completed"):
            continue
        ins = m["in_state"]
        lg = zl(zf, "last_game/main.yml", None)
        lc = zl(zf, "last_conference/main.yml", None)
        print(f"\n  {os.path.relpath(p, G)}")
        print(f"     card_store={None if m.get('card_store') is None else len(m['card_store'])} "
              f"cstart={m.get('conference_start_state')!r} "
              f"root_units={'units.yml' in names} "
              f"games={len({n.split('/')[1] for n in names if n.startswith('games/')})} "
              f"last_game={lg is not None} last_conf={lc is not None}")
        print(f"     in_state: scenario={ins.get('scenario')} front={ins.get('front')} "
              f"seg_finished={ins.get('segment_finished')} lost_scenario={ins.get('lost_scenario')} "
              f"conference={ins.get('conference')}")
        print(f"     reverted_games={m.get('reverted_games')}  tokens={len(m.get('tokens') or [])}")
        if lc:
            print(f"     last_conf.in_state: {lc.get('in_state')}")
