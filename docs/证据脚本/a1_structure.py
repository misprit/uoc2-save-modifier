"""Stage 1: top-level structure of the two .usg saves."""
import zipfile, collections, os, sys

SAVES = [
    r"D:\MiniMax\uoc2-save-modifier\west-Conference3-1.usg",
    r"D:\MiniMax\uoc2-save-modifier\west-ahistorical-2.usg",
]

for p in SAVES:
    print("=" * 70)
    print(os.path.basename(p), os.path.getsize(p), "bytes")
    print("=" * 70)
    with zipfile.ZipFile(p) as zf:
        infos = zf.infolist()
        print(f"entries={len(infos)}")
        # compression types
        comp = collections.Counter(i.compress_type for i in infos)
        print("compress_type counts:", dict(comp))
        # top-level dir histogram
        top = collections.Counter()
        for i in infos:
            first = i.filename.split("/")[0]
            top[first] += 1
        print("top-level buckets:")
        for k, v in sorted(top.items(), key=lambda x: -x[1]):
            print(f"   {k:30s} {v}")
        # second level
        print("second-level (under games/):")
        g = collections.Counter()
        for i in infos:
            parts = i.filename.split("/")
            if parts[0] == "games" and len(parts) > 1:
                g[parts[1]] += 1
        for k, v in sorted(g.items()):
            print(f"   games/{k:28s} {v}")
        # file extension histogram
        ext = collections.Counter(os.path.splitext(i.filename)[1] or "<none>" for i in infos)
        print("extensions:", dict(ext))
        # root-level files
        print("root files:")
        for i in sorted(infos, key=lambda x: x.filename):
            if "/" not in i.filename:
                print(f"   {i.filename:30s} size={i.file_size:>10d} comp={i.compress_size:>9d} type={i.compress_type}")
    print()
