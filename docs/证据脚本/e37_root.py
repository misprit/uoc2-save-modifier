import zipfile, os, collections, io
save = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "save")
roots = collections.Counter()
rootfiles = collections.Counter()
n = 0
for dirpath, _, files in os.walk(save):
    for f in files:
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dirpath, f)
        try:
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
        except Exception as e:
            continue
        n += 1
        tops = set()
        for nm in names:
            if "/" in nm:
                tops.add(nm.split("/")[0] + "/")
            else:
                tops.add(nm)
                rootfiles[nm] += 1
        roots[tuple(sorted(tops))] += 1
out = io.open(r"D:\MiniMax\_analysis\e37_root.txt", "w", encoding="utf-8")
out.write("存档总数 = %d\n" % n)
out.write("\n根级文件出现次数:\n")
for k, v in rootfiles.most_common():
    out.write("  %-24s %d\n" % (k, v))
out.write("\n顶层条目组合:\n")
for k, v in roots.most_common(12):
    out.write("  x%-4d %s\n" % (v, list(k)))
out.close()
print("ok", n)
