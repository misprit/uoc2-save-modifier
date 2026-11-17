import os, io, zipfile, yaml, collections, json
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e66_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

# 1. fallback_prices 覆盖
c = collections.Counter()
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        with zipfile.ZipFile(os.path.join(dp, f)) as zf:
            names = zf.namelist()
            m = yaml.safe_load(zf.read("main.yml")) or {}
            kind = "独立" if m.get("standalone_scenario") else "战役"
            c[(kind, "fallback_prices", "document/fallback_prices.yml" in names)] += 1
P("fallback_prices 覆盖:")
for k, v in sorted(c.items()):
    P("  %s %s" % (k, v))

# 2. 各战役包里 fronts/<战线>/conferences/<会议>.yml 是否带 store
P("")
P("各战役包 conference 文件的 store 情况:")
for dlc, camp in [("base", "west"), ("dlc1", "blitzkrieg"), ("dlc2", "barbarossa"),
                  ("dlc3", "moscow"), ("dlc4", "stalingrad")]:
    cd = os.path.join(PK, dlc, "data", "campaigns", camp + ".usc")
    if not os.path.isdir(cd):
        P("  %s 缺" % camp); continue
    fr = os.path.join(cd, "fronts")
    tot = withstore = 0
    sample = None
    for rt, _, fn in os.walk(fr):
        for x in fn:
            if not x.endswith(".yml"):
                continue
            tot += 1
            try:
                o = yaml.safe_load(open(os.path.join(rt, x), encoding="utf-8", errors="replace").read())
            except Exception:
                continue
            if isinstance(o, dict) and o.get("store"):
                withstore += 1
                if sample is None:
                    sample = (os.path.relpath(os.path.join(rt, x), cd).replace("\\", "/"), o)
    P("  %-12s fronts 下 yml %d 个, 其中带 store 的 %d 个" % (camp, tot, withstore))
    if sample:
        P("      样例 %s 顶层键=%s" % (sample[0], list(sample[1])))
        st = sample[1]["store"]
        P("      store 条目 %d 条, 首条=%s" % (len(st), json.dumps(st[0], ensure_ascii=False)))
        ks = collections.Counter()
        for e in st:
            ks[tuple(sorted(e))] += 1
        P("      条目键组合: %s" % dict(ks))

# 3. 存档根 store.yml 与包里会议默认清单的关系（stalingrad）
P("")
P("stalingrad 存档根 store.yml 的 front 键 vs 包里 fronts 目录:")
cd = os.path.join(PK, "dlc4/data/campaigns/stalingrad.usc")
P("  包 fronts/: %s" % sorted(os.listdir(os.path.join(cd, "fronts"))))
with zipfile.ZipFile(os.path.join(G, r"campaigns\Stalingrad.usg")) as zf:
    s = yaml.safe_load(zf.read("store.yml"))
    P("  存档根 store.yml 顶层键: %s" % list(s))
    for k, v in s.items():
        P("    %s: %d 条, elite_store=%s" % (k, len(v.get("store") or []), v.get("elite_store")))
    confs = sorted(set(n.split("/")[2] for n in zf.namelist() if n.startswith("document/conferences/") and n.count("/") >= 3))
    P("  存档 document/conferences/ 会议: %s" % confs)
    for c0 in confs[:4]:
        fp = os.path.join(cd, "fronts")
        for rt, _, fn in os.walk(fp):
            if c0 + ".yml" in fn:
                o = yaml.safe_load(open(os.path.join(rt, c0 + ".yml"), encoding="utf-8", errors="replace").read())
                P("    包里 %s 顶层键=%s store条数=%s" % (c0, list(o) if isinstance(o, dict) else type(o),
                  len(o.get("store") or []) if isinstance(o, dict) else "-"))
OUT.close()
print("done")
