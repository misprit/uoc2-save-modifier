import os, io, zipfile, yaml, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e73_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

pkgroot = {"west": "base", "blitzkrieg": "dlc1", "barbarossa": "dlc2",
           "moscow": "dlc3", "stalingrad": "dlc4"}
seen = {}
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            if "store.yml" not in names or "main.yml" not in names:
                continue
            m = yaml.safe_load(zf.read("main.yml")) or {}
            cid = m.get("campaign_id")
            if cid not in pkgroot:
                continue
            s = yaml.safe_load(zf.read("store.yml")) or {}
            seen.setdefault(cid, set()).add(tuple(sorted(s.keys())))

for cid, variants in sorted(seen.items()):
    pdir = os.path.join(PK, pkgroot[cid], "data", "campaigns", cid + ".usc", "fronts")
    pkgfronts = sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []
    P("%-12s 包 fronts/=%s" % (cid, pkgfronts))
    for v in sorted(variants):
        P("    存档 store.yml 顶层键=%s   一致=%s" % (list(v), list(v) == pkgfronts))
OUT.close()
print(open(r"D:\MiniMax\_analysis\e73_out.txt", encoding="utf-8").read())
