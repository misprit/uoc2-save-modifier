import os, io, zipfile, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
out = io.open(r"D:\MiniMax\_analysis\e47_cu.txt","w",encoding="utf-8")
cnt = collections.Counter(); live_hits = []
for dp,_,fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        p=os.path.join(dp,f)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            for nm in names:
                parts = nm.split("/")
                if parts[0]=="games" and len(parts)==3 and parts[2] in ("campaign_units.yml","enroute_units.yml"):
                    cnt["games/<场景>/" + parts[2]] += 1
                    if len(live_hits) < 8: live_hits.append((os.path.relpath(p,G), nm))
out.write("=== 实时层 games/<场景>/ 直属 campaign_units.yml / enroute_units.yml 出现次数 ===\n")
for k,v in sorted(cnt.items()): out.write("  %-40s %d\n" % (k,v))
out.write("\n样例:\n")
for e in live_hits: out.write("  %s | %s\n" % e)
out.close(); print("ok")
