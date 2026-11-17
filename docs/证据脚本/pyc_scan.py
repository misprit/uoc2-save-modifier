"""Scan all game .pyc modules for save-format related string constants."""
import marshal, types, os, re, collections

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\uoc2"
MARKERS = re.compile(
    r"(\.usg|archive|deploy|\bturn_|phase_|campaign_units|enroute|prepositioned|"
    r"playable|\.npz|fow|own|weather|store\.yml|cards\.yml|units\.yml|hqs\.yml|"
    r"last_conference|last_game|document|scenarios|objectives\.yml|bridges|"
    r"locale\.yml|ar_list|ai_hints|supply_hubs|supply_sources|cities\.yml|"
    r"main\.yml|save_dir|savegame|saved)", re.I)

def load_pyc(path):
    with open(path, "rb") as f:
        return marshal.loads(f.read()[16:])

def walk(code, consts, depth=0, maxdepth=6):
    for c in code.co_consts:
        if isinstance(c, str):
            consts.append(c)
        elif isinstance(c, types.CodeType) and depth < maxdepth:
            walk(c, consts, depth + 1, maxdepth)
    return consts

hits = collections.defaultdict(set)
allfiles = []
for dp, dn, fn in os.walk(LIB):
    for f in fn:
        if f.endswith(".pyc"):
            allfiles.append(os.path.join(dp, f))

for p in allfiles:
    rel = os.path.relpath(p, LIB).replace("\\", "/")
    try:
        code = load_pyc(p)
    except Exception:
        continue
    consts = walk(code, [])
    for c in consts:
        if MARKERS.search(c) and len(c) < 90:
            hits[rel].add(c)

for rel in sorted(hits, key=lambda r: -len(hits[r])):
    print("=" * 70)
    print(rel)
    print("=" * 70)
    for c in sorted(hits[rel]):
        print("   ", repr(c))
