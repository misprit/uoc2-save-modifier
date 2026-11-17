# -*- coding: utf-8 -*-
"""E12: enroute_units 与 campaign_units 的 id 集合关系"""
import zipfile, io, yaml, os

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
out = io.open(r"D:\MiniMax\_analysis\e12_out.txt", "w", encoding="utf-8")

for rel, scen in [(r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "husky"),
                  (r"Old Saves\Victory in the West\经典难度\west-MonteCassino.usg", "monte_cassino"),
                  (r"campaigns\Stalingrad.usg", "road_to_stalingrad")]:
    p = os.path.join(G, rel)
    zf = zipfile.ZipFile(p)
    az = zipfile.ZipFile(io.BytesIO(zf.read("games/%s/archive" % scen)))
    out.write("=" * 90 + "\n")
    out.write("%s  scenario=%s\n" % (os.path.basename(p), scen))
    root = yaml.safe_load(zf.read("units.yml").decode("utf-8")) or []
    root_ids = {u["id"] for u in root}
    out.write("根总表 id 数 = %d\n" % len(root_ids))
    for s in sorted({n.split("/")[0] for n in az.namelist()}):
        try:
            eu = yaml.safe_load(az.read(s + "/enroute_units.yml").decode("utf-8")) or []
        except KeyError:
            eu = None
        try:
            cu = yaml.safe_load(az.read(s + "/campaign_units.yml").decode("utf-8")) or []
        except KeyError:
            cu = None
        eids = [e["unit"]["id"] for e in eu] if eu is not None else None
        cids = [u["id"] for u in cu] if cu is not None else None
        out.write("  %-30s enroute=%s\n" % (s, eids))
        out.write("  %-30s campaign_units=%s\n" % ("", cids))
        if eids is not None and cids is not None:
            out.write("  %-30s enroute∩campaign=%s  campaign⊆根表=%s  enroute⊆根表=%s\n"
                      % ("", sorted(set(eids) & set(cids)), set(cids) <= root_ids, set(eids) <= root_ids))
out.close()
print("ok")
