import os, zipfile, yaml, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        with zipfile.ZipFile(p) as zf:
            m = yaml.safe_load(zf.read("main.yml")) or {}
            if m.get("standalone_scenario"):
                continue
            ins = m.get("in_state") or {}
            fr = ins.get("fronts") or {}
            seg = any((v or {}).get("segment") for v in fr.values())
            if not seg:
                names = zf.namelist()
                ngames = len(set(n.split("/")[1] for n in names if n.startswith("games/") and n.count("/") >= 2))
                print("无 segment: %-56s games=%d conf=%s card_store=%s seg_finished=%s completed=%s" % (
                    os.path.relpath(p, G)[:56], ngames, ins.get("conference"),
                    bool(m.get("card_store")), ins.get("segment_finished"), ins.get("completed")))
