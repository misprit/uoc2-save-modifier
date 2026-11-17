"""D3: reachable-state enumeration from the game's own API + UI controller."""
import marshal, types, os, dis, io, re, collections

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\uoc2"

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
print("A) 'lost_scenario' / 'completed' / 'reverted_games' references")
print("=" * 100)
for dp, dn, fn in os.walk(LIB):
    for f in sorted(fn):
        if not f.endswith(".pyc"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, LIB).replace("\\", "/")
        try:
            code = load_pyc(p)
        except Exception:
            continue
        for c in walk(code, []):
            strs = {x for x in c.co_consts if isinstance(x, str)}
            if strs & {"lost_scenario", "reverted_games"}:
                print(f"  {rel} :: fn {c.co_name}  -> {sorted(strs & {'lost_scenario','reverted_games','completed'})}")

print()
print("=" * 100)
print("B) the campaign UI controller: what does 'continue' do?")
print("=" * 100)
for rel in ["main_screen/campaign_ctrl.pyc", "main_screen/campaign_widget.pyc",
            "main_screen/campaign_view.pyc"]:
    p = os.path.join(LIB, rel.replace("/", os.sep))
    if not os.path.isfile(p):
        print(f"  !! {rel}"); continue
    code = load_pyc(p)
    print(f"\n--- {rel} ---")
    for c in walk(code, []):
        strs = sorted({x for x in c.co_consts if isinstance(x, str)
                       and re.search(r"continue|conference|segment|scenario|battle|end_|start_|milestone|card|plan",
                                     x, re.I)})
        if not strs:
            continue
        print(f"   fn {c.co_name}({', '.join(c.co_varnames[:c.co_argcount])})")
        for s in strs[:26]:
            print(f"       {s!r}")

print()
print("=" * 100)
print("C) 'revert' / 'continue' / 'end_conference' implementations (campaign.pyc)")
print("=" * 100)
code = load_pyc(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
codes = {c.co_name: c for c in walk(code, [])}
for name in ["end_conference", "_remove_revert_campaign_data", "save_revert_campaign_data",
             "_load_revert_campaign_data", "revert_last_conference", "revert_last_game",
             "revert_last_game_to_deployment", "can_end_segment",
             "can_revert_to_last_conference", "get_last_game_scenario_name"]:
    c = codes.get(name)
    if c is None:
        print(f"  !! {name}"); continue
    print(f"\n--- fn {name}({', '.join(c.co_varnames[:c.co_argcount])}) ---")
    buf = io.StringIO()
    dis.dis(c, file=buf)
    keep = [s.strip() for s in buf.getvalue().splitlines()
            if any(k in s for k in ("LOAD_CONST", "LOAD_ATTR", "CALL", "STORE_ATTR",
                                    "STORE_FAST", "RETURN_VALUE", "POP_JUMP"))]
    for s in keep[:55]:
        print("   ", s)
    if len(keep) > 55:
        print(f"    ... (+{len(keep)-55})")
