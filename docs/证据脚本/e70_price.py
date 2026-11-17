import os, io, zipfile, yaml, json, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e70_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def key(e):
    return (e.get("nationality"), e.get("equipment"), e.get("spec"))

rows = []
for dp, _, fs in os.walk(os.path.join(G, r"Old Saves\Stalingrad")):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            if "store.yml" not in names:
                continue
            m = yaml.safe_load(zf.read("main.yml")) or {}
            s = yaml.safe_load(zf.read("store.yml")) or {}
            ca = (s.get("caucasus") or {}).get("store") or []
            rows.append((f, m.get("level"), m.get("prestige"), m.get("score"),
                         (m.get("in_state") or {}).get("conference"), len(ca),
                         {key(e): e.get("price") for e in ca}))

P("Stalingrad 存档的 caucasus 商店价格（看是否随难度/进度变化）:")
ref = None
for f, lv, pr, sc, conf, n, prices in rows:
    P("  %-28s level=%-8s prestige=%-5s score=%-6s conf=%-9s 条数=%d" % (f[:28], lv, pr, sc, conf, n))
    if ref is None:
        ref = prices
    else:
        d = [(k, ref.get(k), v) for k, v in prices.items() if ref.get(k) != v]
        P("        与参考存档价格不同: %d 条 %s" % (len(d), d[:6]))
P("")
P("每条的 (spec/equipment, nationality) -> 各存档价格:")
allk = sorted(set(k for r in rows for k in r[6]), key=str)
P("  %-42s %s" % ("条目", "  ".join(r[0][:14] for r in rows)))
for k in allk:
    P("  %-42s %s" % (str(k), "  ".join(str(r[6].get(k)) for r in rows)))
OUT.close()
print("done")
