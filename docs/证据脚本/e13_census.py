# -*- coding: utf-8 -*-
"""E13: 70 个存档里，各关键路径的存在性普查"""
import os, io, zipfile, yaml, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
out = io.open(r"D:\MiniMax\_analysis\e13_out.txt", "w", encoding="utf-8")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

saves = []
for dirpath, _, files in os.walk(G):
    for f in files:
        if f.lower().endswith(".usg"):
            saves.append(os.path.join(dirpath, f))
saves.sort()

stat = collections.Counter()
detail = []
for p in saves:
    rel = os.path.relpath(p, G)
    try:
        zf = zipfile.ZipFile(p)
    except Exception as e:
        out.write("ERR %s %s\n" % (rel, e)); continue
    names = zf.namelist()
    has_root_units = "units.yml" in names
    has_root_hqs = "hqs.yml" in names
    m = zl(zf, "main.yml") or {}
    ins = m.get("in_state") or {}
    scen = ins.get("scenario")
    standalone = m.get("standalone_scenario")
    key = []
    # 当前场景目录
    cur = None
    if scen:
        cur = "games/%s" % scen
    elif standalone:
        cur = "game"
    cur_units = cur + "/units.yml" if cur else None
    cur_campaign = cur + "/campaign_units.yml" if cur else None
    cur_enroute = cur + "/enroute_units.yml" if cur else None
    is_list = None
    if cur_units and cur_units in names:
        v = zl(zf, cur_units) or []
        is_list = bool(v) and isinstance(v[0], int)
    in_cur_campaign = (cur_campaign in names) if cur_campaign else False
    in_cur_enroute = (cur_enroute in names) if cur_enroute else False
    # 最后一个快照
    last = None
    if cur and (cur + "/archive") in names:
        az = zipfile.ZipFile(__import__("io").BytesIO(zf.read(cur + "/archive")))
        snaps = sorted({n.split("/")[0] for n in az.namelist()})
        last = snaps[-1] if snaps else None
        snap_has = {k: (last + "/" + k) in az.namelist()
                    for k in ("units.yml", "campaign_units.yml", "enroute_units.yml", "ar_list.yml")}
    else:
        snap_has = None
    stat["有根units"] += has_root_units
    stat["有根hqs"] += has_root_hqs
    if cur:
        stat["有当前场景目录"] += 1
        stat["当前units是ID清单"] += bool(is_list)
        stat["当前units是对象"] += (is_list is False)
        stat["当前场景有campaign_units.yml"] += in_cur_campaign
        stat["当前场景有enroute_units.yml"] += in_cur_enroute
    if snap_has:
        stat["有archive快照"] += 1
        for k, v in snap_has.items():
            stat["快照有" + k] += v
    detail.append((rel, scen, standalone, has_root_units, is_list, in_cur_campaign,
                   in_cur_enroute, snap_has))
    zf.close()

out.write("存档总数 = %d\n" % len(saves))
out.write("\n=== 普查统计 ===\n")
for k, v in sorted(stat.items()):
    out.write("  %-32s %d\n" % (k, v))
out.write("\n=== 当前场景目录里存在 campaign_units.yml 的存档 ===\n")
for d in detail:
    if d[5]:
        out.write("  %s\n" % d[0])
out.write("\n=== 当前场景目录里存在 enroute_units.yml 的存档 ===\n")
for d in detail:
    if d[6]:
        out.write("  %s  (enroute=%s)\n" % (d[0], d[1]))
out.close()
print("ok")
