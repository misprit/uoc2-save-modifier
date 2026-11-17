# -*- coding: utf-8 -*-
"""E55: 存档能识别出哪些战役/场景？document/scenarios 是否自带全部场景？"""
import os, io, zipfile, yaml, collections, json

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e55_out.txt", "w", encoding="utf-8")

rows = []
scen_pkg = {}          # campaign_id -> 存档 document/scenarios 里的场景名
scen_pkgsrc = {}      # campaign_id -> 文档里的场景名集合
doc_top = collections.Counter()
store_src = collections.Counter()

for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, G)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            m = yaml.safe_load(zf.read("main.yml")) or {}
            ins = m.get("in_state") or {}
            sa = m.get("standalone_scenario")
            cid = m.get("campaign_id")
            scen = ins.get("scenario")
            front = ins.get("front")

            games = sorted(set("/".join(n.split("/")[:2]) for n in names
                               if n.startswith("games/") and n.count("/") >= 2))
            gamename = sorted(set(n.split("/")[1] for n in names
                                  if n.startswith("game/") and n.count("/") >= 2))
            docscen = sorted(set(n.split("/")[2] for n in names
                                 if n.startswith("document/scenarios/") and n.count("/") >= 3))

            # document/ 顶层条目
            for n in names:
                if n.startswith("document/"):
                    rest = n[len("document/"):]
                    doc_top[rest.split("/")[0] + ("/" if "/" in rest else "")] += 1

            # 场景商店定义在哪
            if "document/fallback_prices.yml" in names:
                store_src["document/fallback_prices.yml"] += 1
            confs = sorted(set(n.split("/")[2] for n in names
                               if n.startswith("document/conferences/") and n.count("/") >= 3))
            for c in confs:
                if "document/conferences/%s/store.yml" % c in names:
                    store_src["document/conferences/<会议>/store.yml"] += 1

            rows.append(dict(
                save=rel, campaign_id=cid, standalone=sa,
                in_scenario=scen, in_front=front,
                n_games=len(games), n_doc_scen=len(docscen),
                games=games[:3], standalone_game=gamename,
                doc_scen=docscen[:3],
                has_doc_store="store.yml" in names,
            ))
            scen_pkg.setdefault(cid or ("standalone:" + str(sa)), set()).update(docscen)

OUT.write("=== 存档数 = %d ===\n\n" % len(rows))
OUT.write("=== 每个存档的战役/场景识别字段 ===\n")
for r in rows[:80]:
    OUT.write("%-52s cid=%-12s standalone=%-22s in_scenario=%-22s front=%-10s games=%-2d doc_scen=%-2d\n"
              % (r["save"][:52], str(r["campaign_id"]), str(r["standalone"]),
                 str(r["in_scenario"]), str(r["in_front"]), r["n_games"], r["n_doc_scen"]))

OUT.write("\n=== campaign_id 分布 ===\n")
c = collections.Counter(str(r["campaign_id"]) for r in rows)
for k, v in c.most_common():
    OUT.write("  %-14s %d\n" % (k, v))

OUT.write("\n=== 独立场景存档（standalone_scenario 非空）===\n")
for r in rows:
    if r["standalone"]:
        OUT.write("  %-52s standalone=%-22s game/ 目录=%s  document/ 条目数=%d\n"
                  % (r["save"][:52], r["standalone"], r["standalone_game"], r["n_doc_scen"]))

OUT.write("\n=== document/ 顶层条目（按出现次数）===\n")
for k, v in doc_top.most_common(20):
    OUT.write("  %-30s %d\n" % (k, v))

OUT.write("\n=== 场景商店定义来源 ===\n")
for k, v in store_src.most_common():
    OUT.write("  %-40s %d\n" % (k, v))

OUT.write("\n=== 每个战役的 document/scenarios 场景数 ===\n")
for cid, s in sorted(scen_pkg.items(), key=lambda kv: -len(kv[1])):
    OUT.write("  %-16s %3d 个场景  例: %s\n" % (cid, len(s), sorted(s)[:5]))

OUT.close()
print("ok")
