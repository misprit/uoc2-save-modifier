import zipfile, io, os, collections
save = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "save")
out = io.open(r"D:\MiniMax\_analysis\e38_arlist.txt", "w", encoding="utf-8")

def snapshots_of(zf, scen_dir):
    """返回 [(快照名, 文件名集合)]"""
    inner = zf.read(scen_dir + "/archive")
    with zipfile.ZipFile(io.BytesIO(inner)) as iz:
        d = collections.defaultdict(set)
        for nm in iz.namelist():
            if "/" in nm:
                sd, fn = nm.split("/", 1)
                d[sd].add(fn)
        return d

tot_dirs = 0; tot_with = 0
last_dirs = 0; last_with = 0
allnames = collections.Counter()
per_save = []
for dp, _, fs in os.walk(save):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, save)
        try:
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
                games = sorted(set(n.split("/")[0] + "/" + n.split("/")[1]
                                   for n in names if n.startswith("games/") and n.count("/") >= 2))
                sw = lw = swt = lwt = 0
                for g in games:
                    try: d = snapshots_of(zf, g)
                    except Exception: continue
                    if not d: continue
                    ordered = sorted(d.keys())
                    for sd in ordered:
                        allnames.update(d[sd])
                        tot_dirs += 1
                        if "ar_list.yml" in d[sd]: tot_with += 1
                    last = ordered[-1]
                    last_dirs += 1
                    if "ar_list.yml" in d[last]: last_with += 1
                per_save.append((rel, sw, swt, lw, lwt))
        except Exception as e:
            out.write("ERR %s %s\n" % (rel, e))

out.write("全部快照目录 = %d, 含 ar_list.yml = %d (%.1f%%)\n" % (tot_dirs, tot_with, 100.0*tot_with/max(tot_dirs,1)))
out.write("每存档的【最后快照】= %d, 含 ar_list.yml = %d\n\n" % (last_dirs, last_with))
out.write("快照内文件名出现次数:\n")
for k, v in allnames.most_common():
    out.write("  %-28s %d\n" % (k, v))

# 点名核对文档引用过的两个存档
for target in ("west-Husky.usg", "west-MonteCassino.usg"):
    for dp, _, fs in os.walk(save):
        for f in fs:
            if f == target:
                p = os.path.join(dp, f)
                out.write("\n===== %s =====\n" % os.path.relpath(p, save))
                with zipfile.ZipFile(p) as zf:
                    names = zf.namelist()
                    games = sorted(set("/".join(n.split("/")[:2]) for n in names if n.startswith("games/") and n.count("/") >= 2))
                    for g in games:
                        d = snapshots_of(zf, g)
                        for sd in sorted(d):
                            has = "ar_list.yml" in d[sd]
                            out.write("  %-46s %2d 个文件  ar_list:%s\n" % (sd, len(d[sd]), "YES" if has else "-- NO --"))
out.close()
print("ok")
