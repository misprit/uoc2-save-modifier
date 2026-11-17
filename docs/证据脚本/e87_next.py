# -*- coding: utf-8 -*-
"""E87: 战役地图阶段（战斗外），「下一场要打的场景」的单位是否已经在根表里？"""
import os, io, zipfile, yaml, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e87_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")
def ids(o):
    if isinstance(o, list):
        return set(e.get("id") for e in o if isinstance(e, dict) and e.get("id") is not None)
    return set()

rows = []
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, G)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            if "main.yml" not in names or "units.yml" not in names:
                continue
            m = yaml.safe_load(zf.read("main.yml")) or {}
            if m.get("standalone_scenario"):
                continue
            ins = m.get("in_state") or {}
            if ins.get("scenario"):
                continue            # 只看战斗外
            root = yaml.safe_load(zf.read("units.yml")) or []
            rids = ids(root)
            fronts = ins.get("fronts") or {}
            # 当前段 -> 场景列表
            for fname, fv in fronts.items():
                seg = (fv or {}).get("segment")
                if not seg:
                    continue
                segyml = "document/fronts/%s/segments/%s/data.yml" % (fname, seg)
                if segyml not in names:
                    continue
                sd = yaml.safe_load(zf.read(segyml)) or {}
                situations = sd.get("situations") or []
                flat = []
                for s in situations:
                    if isinstance(s, list):
                        flat.extend(s)
                    else:
                        flat.append(s)
                for sc in flat:
                    uy = "document/scenarios/%s/units.yml" % sc
                    if uy not in names:
                        continue
                    sids = ids(yaml.safe_load(zf.read(uy)))
                    if not sids:
                        continue
                    rows.append(dict(rel=rel, front=fname, seg=seg, scen=sc,
                                     nscen=len(sids), in_root=len(sids & rids),
                                     nroot=len(rids),
                                     pct=100.0 * len(sids & rids) / len(sids)))

W("=" * 108)
W("【1】战斗外存档：当前段的场景单位，有多少已经在根表里？")
W("=" * 108)
W("  %-44s %-9s %-22s %8s %8s %8s" % ("存档", "战线", "场景", "场景单位", "已在根表", "占比%"))
agg = collections.Counter()
for r in sorted(rows, key=lambda x: (x["rel"], x["scen"])):
    W("  %-44s %-9s %-22s %8d %8d %8.1f" % (r["rel"][:44], r["front"], r["scen"], r["nscen"], r["in_root"], r["pct"]))
    agg["全在根表" if r["in_root"] == r["nscen"] else ("部分" if r["in_root"] else "全不在")] += 1
W("")
W("  汇总: %s" % dict(agg))

W("")
W("=" * 108)
W("【2】★ 关键判断：战斗外能不能改「下一场要打的场景的单位」？")
W("=" * 108)
part = [r for r in rows if 0 < r["in_root"] < r["nscen"]]
none = [r for r in rows if r["in_root"] == 0]
allin = [r for r in rows if r["in_root"] == r["nscen"]]
W("  当前段场景单位【全部已在根表】: %d 例" % len(allin))
W("  当前段场景单位【部分在根表】  : %d 例" % len(part))
W("  当前段场景单位【完全不在根表】: %d 例" % len(none))
if part:
    W("")
    W("  部分在根表的样例:")
    for r in part[:12]:
        W("    %-42s %-20s 场景单位 %3d, 在根表 %3d" % (r["rel"][:42], r["scen"], r["nscen"], r["in_root"]))
if none:
    W("")
    W("  完全不在根表的样例:")
    for r in none[:12]:
        W("    %-42s %-20s 场景单位 %3d" % (r["rel"][:42], r["scen"], r["nscen"]))
OUT.close()
print("done")
