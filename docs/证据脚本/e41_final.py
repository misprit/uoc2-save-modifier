import zipfile, io, os, collections, yaml, hashlib
save = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "save")
out = io.open(r"D:\MiniMax\_analysis\e41_final.txt", "w", encoding="utf-8")

def fmt(v):
    if isinstance(v, list):
        if not v: return "list[]"
        if isinstance(v[0], int): return "list[int]"
        if isinstance(v[0], dict): return "list[dict]"
        return "list[" + type(v[0]).__name__ + "]"
    return "None" if v is None else type(v).__name__

agg = collections.Counter()
hashes = {}
for dp, _, fs in os.walk(save):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        p = os.path.join(dp, f)
        h = hashlib.sha256(open(p,"rb").read()).hexdigest()
        hashes.setdefault(h, []).append(os.path.relpath(p, save))

out.write("=== 存档去重 ===\n")
out.write("  .usg 文件 = %d, 唯一内容 = %d\n" % (sum(len(v) for v in hashes.values()), len(hashes)))
dup = {h:v for h,v in hashes.items() if len(v)>1}
for h, v in list(dup.items())[:8]:
    out.write("  重复 x%d: %s\n" % (len(v), " | ".join(v)))

seen = set()
for h, paths in hashes.items():
    p = os.path.join(save, paths[0])
    with zipfile.ZipFile(p) as zf:
        for nm in zf.namelist():
            parts = nm.split("/")
            if parts[0] == "document": continue
            if parts[0]=="games" and len(parts)==3 and parts[2] in ("units.yml","hqs.yml"):
                kind = "games"
            elif parts[0]=="game" and len(parts)==2 and parts[1] in ("units.yml","hqs.yml"):
                kind = "game(独立)"
            else: continue
            try: v = yaml.safe_load(zf.read(nm))
            except Exception: v = "ERR"
            agg["%s / %s -> %s" % (kind, parts[-1], fmt(v))] += 1

out.write("\n=== 去重后(唯一存档) games/ 与 game/ 下直属 YAML 格式 ===\n")
tot = 0
for k, v in sorted(agg.items()):
    out.write("  %-46s %d\n" % (k, v)); tot += v
out.write("  合计 = %d\n" % tot)
out.close(); print("ok")
