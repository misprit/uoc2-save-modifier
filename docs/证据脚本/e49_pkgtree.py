import os, io, zipfile, yaml, hashlib
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
out = io.open(r"D:\MiniMax\_analysis\e49_pkgtree.txt","w",encoding="utf-8")
pkgs = {}
for dlc in os.listdir(os.path.join(GAME, "_packages")):
    cdir = os.path.join(GAME, "_packages", dlc, "data", "campaigns")
    if os.path.isdir(cdir):
        for u in os.listdir(cdir):
            p = os.path.join(cdir, u)
            if os.path.isdir(p): pkgs[u[:-4]] = p

def tree(root):
    d = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            fp = os.path.join(dp, f)
            rel = os.path.relpath(fp, root).replace("\\", "/")
            h = hashlib.sha256(open(fp,"rb").read()).hexdigest()
            d[rel] = h
    return d

for savename in ("campaigns/Stalingrad.usg", "campaigns/Stalingrad_BACKUP.usg"):
    target = os.path.join(G, savename.replace("/", os.sep))
    if not os.path.exists(target): continue
    with zipfile.ZipFile(target) as zf:
        m = yaml.safe_load(zf.read("main.yml"))
        doc = {nm[len("document/"):]: hashlib.sha256(zf.read(nm)).hexdigest()
               for nm in zf.namelist() if nm.startswith("document/") and not nm.endswith("/")}
        out.write("=== %s  campaign_id=%r  document/ 条目=%d ===\n" % (savename, m.get("campaign_id"), len(doc)))
        best = None
        for pk, p in sorted(pkgs.items()):
            t = tree(p)
            same = sum(1 for k,v in doc.items() if t.get(k)==v)
            diff = sum(1 for k,v in doc.items() if k in t and t[k]!=v)
            out.write("  vs %-12s 同名相同=%-4d 同名不同=%-4d (包内文件=%d)\n" % (pk, same, diff, len(t)))
        out.write("\n")
out.close(); print("ok")
