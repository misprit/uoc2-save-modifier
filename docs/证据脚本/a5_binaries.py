"""Stage 5: open 'archive' as zip, inspect npz payloads, compare state layers."""
import os, yaml, numpy as np, zipfile, io, collections, binascii

OUT = r"D:\MiniMax\_analysis\extracted"

def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

base = os.path.join(OUT, "conf3")

print("=" * 78)
print("A) games/avalanche/archive as ZIP")
print("=" * 78)
ap = os.path.join(base, "games", "avalanche", "archive")
with zipfile.ZipFile(ap) as zf:
    for i in zf.infolist():
        head = zf.read(i.filename)[:48]
        print(f"  {i.filename:40s} size={i.file_size:>9d} head={binascii.hexlify(head).decode()}")

print()
print("=" * 78)
print("B) npz payloads (own / fow / weather)")
print("=" * 78)
for name in ["own.npz", "fow.npz", "weather.npz"]:
    p = os.path.join(base, "games", "avalanche", name)
    with np.load(p) as z:
        print(f"\n-- {name} -- keys={z.files}")
        for k in z.files:
            a = z[k]
            print(f"   {k:20s} shape={a.shape} dtype={a.dtype}")
            flat = a.ravel()
            print(f"      values[:12]={flat[:12]}")

print()
print("=" * 78)
print("C) state layers comparison (conf3)")
print("=" * 78)
layers = {
    "root": base,
    "last_conference": os.path.join(base, "last_conference"),
    "last_game": os.path.join(base, "last_game"),
    "document": os.path.join(base, "document"),
}
for fn in ["main.yml", "units.yml", "hqs.yml", "cards.yml", "store.yml"]:
    print(f"\n--- {fn} ---")
    for lname, ldir in layers.items():
        p = os.path.join(ldir, fn)
        if os.path.isfile(p):
            d = load(p)
            sz = os.path.getsize(p)
            print(f"   {lname:16s} {sz:>8d} B  type={type(d).__name__} len={len(d) if hasattr(d,'__len__') else '-'}")
        else:
            print(f"   {lname:16s} <missing>")

print()
print("=" * 78)
print("D) root main.yml vs last_conference/main.yml vs last_game/main.yml")
print("=" * 78)
for lname, ldir in layers.items():
    p = os.path.join(ldir, "main.yml")
    if os.path.isfile(p):
        print(f"\n### {lname}/main.yml")
        print(open(p, encoding="utf-8").read()[:2600])
