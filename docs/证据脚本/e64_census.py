# -*- coding: utf-8 -*-
"""E64: 根级文件存在性普查 + 战役包定位表（最终确认）"""
import os, io, zipfile, yaml, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e64_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

ROOTF = ["main.yml", "units.yml", "hqs.yml", "cards.yml", "store.yml"]
cnt = collections.Counter()
combos = collections.Counter()
missing_cards = []
missing_store = []
n=0
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f); rel = os.path.relpath(p, G); n+=1
        with zipfile.ZipFile(p) as zf:
            names = set(zf.namelist())
            m = yaml.safe_load(zf.read("main.yml")) or {}
            sa = m.get("standalone_scenario")
            kind = "独立场景" if sa else "战役"
            present = tuple(x for x in ROOTF if x in names)
            for x in ROOTF:
                cnt[(kind, x, x in names)] += 1
            combos[(kind, present)] += 1
            if "cards.yml" not in names:
                missing_cards.append((kind, rel, sorted(x for x in ["last_game/cards.yml","last_conference/cards.yml","game/cards.yml"] if x in names)))
            if "store.yml" not in names:
                missing_store.append((kind, rel, sorted(x for x in ["last_game/store.yml","last_conference/store.yml","game/store.yml"] if x in names)))
P("存档总数 = %d" % n)
P("")
P("根级文件存在性（按类型）:")
for kind in ["战役", "独立场景"]:
    tot = sum(v for (k, x, ok), v in cnt.items() if k == kind)
    P("  %s 共 %d 个:" % (kind, tot))
    for x in ROOTF:
        y = cnt[(kind, x, True)]
        P("    %-12s 存在 %-3d  缺失 %-3d" % (x, y, tot - y))
P("")
P("根级文件组合分布:")
for (kind, present), v in combos.most_common():
    P("  %-6s %-42s %d" % (kind, list(present), v))
P("")
P("无根 cards.yml 的存档 (%d):" % len(missing_cards))
for k, r, alt in missing_cards:
    P("  %-6s %-58s 其他来源=%s" % (k, r[:58], alt))
P("")
P("无根 store.yml 的存档 (%d):" % len(missing_store))
for k, r, alt in missing_store:
    P("  %-6s %-58s 其他来源=%s" % (k, r[:58], alt))
OUT.close()
print("done")
