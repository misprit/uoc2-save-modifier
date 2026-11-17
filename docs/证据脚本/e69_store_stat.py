import os, io, zipfile, yaml, json, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e69_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

pkgroot = {}
for dlc, camp in [("base", "west"), ("dlc1", "blitzkrieg"), ("dlc2", "barbarossa"),
                  ("dlc3", "moscow"), ("dlc4", "stalingrad")]:
    pkgroot[camp] = os.path.join(PK, dlc, "data", "campaigns", camp + ".usc")

def key(e):
    return (e.get("nationality"), e.get("equipment"), e.get("spec"))

stat = collections.Counter()
samples = []
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, G)
        try:
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
                if "store.yml" not in names or "main.yml" not in names:
                    continue
                m = yaml.safe_load(zf.read("main.yml")) or {}
                cid = m.get("campaign_id"); conf = (m.get("in_state") or {}).get("conference")
                if cid not in pkgroot or not conf:
                    stat["跳过(无会议/无包)"] += 1
                    continue
                root = yaml.safe_load(zf.read("store.yml")) or {}
                pkgf = os.path.join(pkgroot[cid], "fronts")
                hit = None
                for rt, _, fn in os.walk(pkgf):
                    if conf + ".yml" in fn:
                        hit = os.path.join(rt, conf + ".yml")
                if not hit:
                    stat["跳过(包里无该会议)"] += 1
                    continue
                po = yaml.safe_load(open(hit, encoding="utf-8", errors="replace").read()) or {}
                pk = {key(e): e for e in (po.get("store") or [])}
                for front, v in root.items():
                    cur = {key(e): e for e in ((v or {}).get("store") or [])}
                    for k, e in cur.items():
                        if k not in pk:
                            stat["存档有但包里没有"] += 1
                            continue
                        if e.get("quantity") == pk[k].get("quantity") and e.get("price") == pk[k].get("price"):
                            stat["与包默认完全相同"] += 1
                        elif e.get("quantity", 0) < pk[k].get("quantity", 0):
                            stat["quantity 少于默认(已购买递减)"] += 1
                            if len(samples) < 8:
                                samples.append(("递减", rel, front, conf, pk[k], e))
                        else:
                            stat["quantity 多于默认/价格不同"] += 1
                            if len(samples) < 8:
                                samples.append(("其它", rel, front, conf, pk[k], e))
                    for k in pk:
                        if k not in cur:
                            stat["包里默认有、存档已移除(售罄)"] += 1
                            if len(samples) < 16:
                                samples.append(("移除", rel, front, conf, pk[k], None))
        except Exception as e:
            stat["ERR"] += 1

P("统计（存档根 store.yml vs 包里当前会议默认清单）:")
for k, v in stat.most_common():
    P("  %-34s %d" % (k, v))
P("")
P("样例:")
for s in samples:
    P("  [%s] %s | %s | %s" % (s[0], s[1][:48], s[2], s[3]))
    P("      包=%s" % json.dumps(s[4], ensure_ascii=False))
    P("      存=%s" % (json.dumps(s[5], ensure_ascii=False) if s[5] else "(条目不存在)"))
OUT.close()
print("done")
