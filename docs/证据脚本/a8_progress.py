"""Stage 8: document/ vs package west.usc, and progression diff across west series."""
import os, yaml, zipfile, collections

PKG = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages"
BASE = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\data\campaigns\west.usc"
DOC = r"D:\MiniMax\_analysis\extracted\conf3\document"
SERIES = r"C:\Users\misprit\AppData\Local\.uoc2\save\Old Saves\Victory in the West\困难难度-史实线"

def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

print("=" * 78)
print("A) document/  vs  base/data/campaigns/west.usc/")
print("=" * 78)
def relset(root):
    s = set()
    for dp, dn, fn in os.walk(root):
        for f in fn:
            s.add(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    return s
ds, bs = relset(DOC), relset(BASE)
print(f"document/={len(ds)} files, west.usc/={len(bs)} files")
print(f"only in document : {sorted(ds-bs)}")
print(f"only in west.usc : {sorted(bs-ds)}")
same = diff = 0; diffs = []
for r in sorted(ds & bs):
    a = open(os.path.join(DOC, r.replace("/", os.sep)), "rb").read()
    b = open(os.path.join(BASE, r.replace("/", os.sep)), "rb").read()
    if a == b: same += 1
    else:
        diff += 1; diffs.append(r)
print(f"content identical: {same}, differing: {diff}")
print(f"differing: {diffs}")
# show one diff
if diffs:
    r = diffs[0]
    print(f"\n--- diff example: {r} ---")
    da, db = load(os.path.join(DOC, r.replace("/", os.sep))), load(os.path.join(BASE, r.replace("/", os.sep)))
    print("document keys:", sorted(da) if isinstance(da, dict) else type(da))
    print("package  keys:", sorted(db) if isinstance(db, dict) else type(db))

print()
print("=" * 78)
print("B) progression diff: Victory in the West, hard/historical series")
print("=" * 78)
files = sorted(os.listdir(SERIES))
files = [f for f in files if f.endswith(".usg")]
order = []
for f in files:
    stem = f[:-4]
    order.append(f)
# sort by conference number then suffix
def key(s):
    import re
    body = s.split("-", 1)[1]
    m = re.search(r"(\d+)", body)
    digits = re.findall(r"\d+", body)
    return (int(digits[0]) if digits else 0,
            int(digits[1]) if len(digits) > 1 else 0)
order.sort(key=key)

rows = []
def zl(zf, name, default):
    try:
        return yaml.safe_load(zf.read(name).decode("utf-8"))
    except KeyError:
        return default
for stem in order:
    p = os.path.join(SERIES, stem)
    stem = stem[:-4]
    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
        m = zl(zf, "main.yml", {}) or {}
        u = zl(zf, "units.yml", []) or []
        h = zl(zf, "hqs.yml", []) or []
        c = zl(zf, "cards.yml", []) or []
        games = sorted({n.split("/")[1] for n in names if n.startswith("games/")})
        ins = m.get("in_state", {}) or {}
        fronts = ins.get("fronts", {}) or {}
        rows.append(dict(
            stem=stem, size=os.path.getsize(p), entries=len(names),
            conf=ins.get("conference"), front=ins.get("front"),
            scenario=ins.get("scenario"), seg_fin=ins.get("segment_finished"),
            prestige=m.get("prestige"), score=m.get("score"),
            milestones=len(m.get("milestones") or []),
            units=len(u), hqs=len(h), cards=len(c),
            games=len(games), tokens=len(m.get("tokens") or []),
            played=sum(len((f.get("played_segments") or [])) for f in fronts.values()),
            level=m.get("level"),
        ))
hdr = ["stem","size","entries","conf","front","scenario","seg_fin","prestige","score","milestones","units","hqs","cards","games","tokens","played","level"]
w = [max(len(str(r[h])) for r in rows + [{h: h}]) for h in hdr]
print("  ".join(str(h).ljust(w[i]) for i, h in enumerate(hdr)))
for r in rows:
    print("  ".join(str(r[h]).ljust(w[i]) for i, h in enumerate(hdr)))

print()
print("=" * 78)
print("C) what files change between two consecutive saves?")
print("=" * 78)
for a, b in [(order[0], order[1]), (order[len(order)//2], order[len(order)//2+1]), (order[-2], order[-1])]:
    pa, pb = os.path.join(SERIES, a), os.path.join(SERIES, b)
    with zipfile.ZipFile(pa) as za, zipfile.ZipFile(pb) as zb:
        na, nb = set(za.namelist()), set(zb.namelist())
        changed = []
        for n in sorted(na & nb):
            if za.read(n) != zb.read(n):
                changed.append(n)
        # group changed by top dir
        grp = collections.Counter()
        for n in changed:
            parts = n.split("/")
            grp["/".join(parts[:2]) if len(parts) > 1 else n] += 1
        print(f"\n{a} -> {b}:  +{len(nb-na)} new, -{len(na-nb)} removed, {len(changed)} changed")
        print(f"   new sample: {sorted(nb-na)[:6]}")
        print(f"   removed sample: {sorted(na-nb)[:6]}")
        print(f"   changed by group: {dict(grp.most_common(12))}")
