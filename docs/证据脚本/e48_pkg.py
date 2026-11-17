import os, io, zipfile, yaml, hashlib, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
out = io.open(r"D:\MiniMax\_analysis\e48_pkg.txt","w",encoding="utf-8")
pkgs = {}
for dlc in os.listdir(os.path.join(GAME, "_packages")):
    cdir = os.path.join(GAME, "_packages", dlc, "data", "campaigns")
    if os.path.isdir(cdir):
        for u in os.listdir(cdir):
            if u.endswith(".usc"): pkgs[u[:-4]] = os.path.join(cdir, u)

target = os.path.join(G, "campaigns", "Stalingrad.usg")
with zipfile.ZipFile(target) as zf:
    m = yaml.safe_load(zf.read("main.yml"))
    out.write("Stalingrad.usg  campaign_id = %r\n" % m.get("campaign_id"))
    doc = {nm[len("document/"):]: hashlib.sha256(zf.read(nm)).hexdigest()
           for nm in zf.namelist() if nm.startswith("document/") and not nm.endswith("/")}
    out.write("document/ 条目数 = %d\n\n" % len(doc))
    for pk, p in sorted(pkgs.items()):
        try:
            pz = zipfile.ZipFile(p)
        except Exception as e:
            out.write("  vs %-12s 打开失败(%s)\n" % (pk, type(e).__name__)); continue
        same = diff = only = 0; total = 0
        for nm in pz.namelist():
            if nm.endswith("/"): continue
            total += 1
            if nm in doc:
                if hashlib.sha256(pz.read(nm)).hexdigest() == doc[nm]: same += 1
                else: diff += 1
            else: only += 1
        out.write("  vs %-12s 同名相同=%-4d 同名不同=%-4d 包独有=%-4d (包内条目=%d)\n" % (pk, same, diff, only, total))
        pz.close()

out.write("\n=== 商店 price/quantity 普查（全部存档）===\n")
c = collections.Counter(); ex = []
for dp,_,fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        p = os.path.join(dp,f)
        with zipfile.ZipFile(p) as zf:
            if "store.yml" not in zf.namelist(): continue
            v = yaml.safe_load(zf.read("store.yml"))
            if not isinstance(v, dict): continue
            for front, body in v.items():
                for e in (body or {}).get("store") or []:
                    c["quantity==0" if e.get("quantity")==0 else "quantity>0"] += 1
                    c["price==0" if e.get("price")==0 else "price>0"] += 1
                    if e.get("price")==0 and len(ex)<5: ex.append((os.path.relpath(p,G), front, e))
out.write("  " + " | ".join("%s=%d" % (k,v) for k,v in sorted(c.items())) + "\n")
for e in ex: out.write("    %s | %s | %s\n" % e)
out.close(); print("ok")
