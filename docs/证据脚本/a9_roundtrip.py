"""Stage 9: ZIP round-trip fidelity test (the critical risk for a save editor)."""
import zipfile, os, shutil, hashlib, io, sys

SRC = r"D:\MiniMax\uoc2-save-modifier\west-Conference3-1.usg"
WORK = r"D:\MiniMax\_analysis\rt"

def digest_tree(root):
    h = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            h[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return h

if os.path.isdir(WORK):
    shutil.rmtree(WORK)
os.makedirs(WORK)

# 1. extract
with zipfile.ZipFile(SRC) as zf:
    zf.extractall(WORK)
orig = digest_tree(WORK)
print(f"extracted {len(orig)} files")

# 2. repack exactly the way the friend's savefile.pack_directory does
out = os.path.join(WORK, "..", "repacked.usg")
out = os.path.abspath(out)
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for dp, dn, fn in os.walk(WORK):
        for f in sorted(fn):
            p = os.path.join(dp, f)
            zf.write(p, os.path.relpath(p, WORK).replace("\\", "/"))

print(f"repacked -> {out}  ({os.path.getsize(out)} bytes vs original {os.path.getsize(SRC)})")

# 3. verify content identity
with zipfile.ZipFile(out) as zf:
    new = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
print(f"entry count: orig={len(orig)} new={len(new)}  identical_content={orig == new}")
if orig != new:
    only_a = set(orig) - set(new); only_b = set(new) - set(orig)
    ch = [k for k in set(orig) & set(new) if orig[k] != new[k]]
    print("  only_orig:", sorted(only_a)[:5], " only_new:", sorted(only_b)[:5], " changed:", ch[:5])

# 4. can the game-relevant reader parse it? simulate .NET-ish read
with zipfile.ZipFile(out) as zf:
    bad = zf.testzip()
    print("zip integrity testzip():", bad or "OK")

# 5. compare zip metadata conventions
for tag, p in [("original", SRC), ("repacked", out)]:
    with zipfile.ZipFile(p) as zf:
        i = zf.infolist()[0]
        import collections
        dts = collections.Counter(x.date_time for x in zf.infolist())
        print(f"  {tag:9s} create_system={i.create_system} external_attr={i.external_attr} "
              f"distinct_dates={len(dts)} dirs={any(x.is_dir() for x in zf.infolist())}")
