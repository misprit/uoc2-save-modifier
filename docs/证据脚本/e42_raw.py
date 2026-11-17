import zipfile, io, os, collections, yaml, hashlib
save = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "save")
out = io.open(r"D:\MiniMax\_analysis\e42_raw.txt", "w", encoding="utf-8")
def fmt(v):
    if isinstance(v, list):
        if not v: return "list[]"
        if isinstance(v[0], int): return "list[int]"
        if isinstance(v[0], dict): return "list[dict]"
    return "None" if v is None else type(v).__name__
agg = collections.Counter(); mixed = []
for dp, _, fs in os.walk(save):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        p = os.path.join(dp, f); rel = os.path.relpath(p, save)
        with zipfile.ZipFile(p) as zf:
            for nm in zf.namelist():
                parts = nm.split("/")
                if parts[0]=="document": continue
                if parts[0]=="games" and len(parts)==3 and parts[2] in ("units.yml","hqs.yml"): kind="games"
                elif parts[0]=="game" and len(parts)==2 and parts[1] in ("units.yml","hqs.yml"): kind="game"
                else: continue
                try: v = yaml.safe_load(zf.read(nm))
                except Exception: v="ERR"
                agg["%s/%s -> %s" % (kind, parts[-1], fmt(v))] += 1
                if parts[-1]=="units.yml" and kind=="games":
                    scen = parts[1]
                    mixed.append((scen, fmt(v), rel))
out.write("=== 未去重(70 个 .usg) ===\n")
tot=0
for k,v in sorted(agg.items()): out.write("  %-42s %d\n"%(k,v)); tot+=v
out.write("  合计 = %d\n" % tot)
out.write("\n  ID 清单(list[int])总数 = %d\n" % sum(v for k,v in agg.items() if "list[int]" in k))
out.write("  完整对象(list[dict])总数 = %d\n" % sum(v for k,v in agg.items() if "list[dict]" in k))
sc = collections.defaultdict(set)
for scen, f, rel in mixed: sc[scen].add(f)
out.write("\n=== 同一场景在不同存档里格式不同的情况 ===\n")
for scen, fs in sorted(sc.items()):
    if len(fs)>1: out.write("  %-24s %s\n" % (scen, sorted(fs)))
out.close(); print("ok")
