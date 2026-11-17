"""C8: exact format of games/<x>/units.yml & hqs.yml -- full objects vs ID manifest."""
import os, yaml, zipfile, collections, io

GAME_SAVE = r"C:\Users\misprit\AppData\Local\.uoc2\save"

def shape_of(raw):
    try:
        d = yaml.safe_load(raw.decode("utf-8"))
    except Exception as e:
        return f"parse-error:{e}", None
    if d is None:
        return "null", None
    if isinstance(d, list):
        if not d:
            return "list[]", d
        kinds = collections.Counter(type(x).__name__ for x in d)
        if set(kinds) == {"int"}:
            return "list[int]  << ID MANIFEST", d
        if set(kinds) == {"dict"}:
            return "list[dict]  << FULL OBJECTS", d
        return f"list[{dict(kinds)}]", d
    if isinstance(d, dict):
        return "dict", d
    return type(d).__name__, d

paths = []
for dp, dn, fn in os.walk(GAME_SAVE):
    for f in fn:
        if f.endswith(".usg"):
            paths.append(os.path.join(dp, f))
paths.sort()

cnt = collections.Counter()
ex = {}
manifest_files = []
for p in paths:
    base = os.path.basename(p)
    with zipfile.ZipFile(p) as zf:
        for n in zf.namelist():
            if not n.endswith(".yml"):
                continue
            parts = n.split("/")
            if parts[0] == "games" and len(parts) > 2:
                t = "games/<x>/" + parts[-1]
            elif parts[0] == "game":
                t = "game/" + parts[-1]
            elif parts[0] in ("last_conference", "last_game"):
                t = parts[0] + "/" + parts[-1]
            else:
                t = n
            if not (t.endswith("units.yml") or t.endswith("hqs.yml")):
                continue
            if t.startswith("document/"):
                continue
            sh, d = shape_of(zf.read(n))
            cnt[(t, sh)] += 1
            ex.setdefault((t, sh), (base, n))
            if "MANIFEST" in sh:
                manifest_files.append((base, n, len(d) if d else 0, (d or [])[:8]))

print("=" * 112)
print("UNIT / HQ TABLE FORMATS")
print("=" * 112)
for (t, sh), c in sorted(cnt.items()):
    print(f"  {t:28s} {sh:30s} x{c}   eg {ex[(t,sh)][0]} :: {ex[(t,sh)][1]}")

print()
print("=" * 112)
print(f"ALL ID-MANIFEST OCCURRENCES ({len(manifest_files)})")
print("=" * 112)
for b, n, ln, sample in manifest_files:
    print(f"  {b:34s} {n:44s} n={ln:4d}  {sample}")
