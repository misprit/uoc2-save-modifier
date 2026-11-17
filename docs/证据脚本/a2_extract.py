"""Stage 2: extract both saves, dump key YAML roots."""
import zipfile, os, shutil, sys

OUT = r"D:\MiniMax\_analysis\extracted"
SAVES = [
    ("conf3", r"D:\MiniMax\uoc2-save-modifier\west-Conference3-1.usg"),
    ("ahist2", r"D:\MiniMax\uoc2-save-modifier\west-ahistorical-2.usg"),
]
for tag, p in SAVES:
    d = os.path.join(OUT, tag)
    if os.path.isdir(d):
        shutil.rmtree(d)
    with zipfile.ZipFile(p) as zf:
        zf.extractall(d)
    print("extracted", tag, "->", d)

def show(path, limit=200):
    print("#" * 70)
    print("### ", path)
    print("#" * 70)
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    lines = txt.splitlines()
    print(f"--- {len(lines)} lines / {len(txt)} chars ---")
    for l in lines[:limit]:
        print(l)
    if len(lines) > limit:
        print(f"... (+{len(lines)-limit} more lines)")
    print()

for tag, _ in SAVES:
    base = os.path.join(OUT, tag)
    for rel in ["main.yml", "cards.yml", "store.yml"]:
        show(os.path.join(base, rel))
