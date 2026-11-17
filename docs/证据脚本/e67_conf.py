import os, io, zipfile, yaml, json, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e67_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

with zipfile.ZipFile(os.path.join(G, r"campaigns\Stalingrad.usg")) as zf:
    names = zf.namelist()
    P("document/conferences/ 下的条目:")
    for n in sorted(names):
        if n.startswith("document/conferences/"):
            P("  %s (%d bytes)" % (n, zf.getinfo(n).file_size))
    P("")
    P("--- document/conferences/*.yml 内容 ---")
    for n in sorted(names):
        if n.startswith("document/conferences/") and n.endswith(".yml"):
            P("  === %s ===" % n)
            P(open(os.path.join(G, r"campaigns\Stalingrad.usg"), "rb") and zf.read(n).decode("utf-8")[:700])
    P("")
    m = yaml.safe_load(zf.read("main.yml"))
    P("当前会议 in_state.conference = %s" % m["in_state"]["conference"])
    s = yaml.safe_load(zf.read("store.yml"))
    P("根 store.yml:")
    for k, v in s.items():
        P("  %s: %d 条" % (k, len(v.get("store") or [])))
        for e in (v.get("store") or [])[:3]:
            P("     %s" % json.dumps(e, ensure_ascii=False))
    P("")
    P("--- last_conference/store.yml vs 根 store.yml ---")
    if "last_conference/store.yml" in names:
        lc = yaml.safe_load(zf.read("last_conference/store.yml"))
        for k, v in lc.items():
            P("  last_conf %s: %d 条" % (k, len(v.get("store") or [])))
        P("  与根 store.yml 完全相同? %s" % (lc == s))

P("")
P("=" * 70)
P("包里 stalingrad fronts 下每个会议的 store 条数 vs 存档根 store.yml")
P("=" * 70)
cd = os.path.join(PK, "dlc4/data/campaigns/stalingrad.usc")
for front in sorted(os.listdir(os.path.join(cd, "fronts"))):
    cdir = os.path.join(cd, "fronts", front, "conferences")
    if not os.path.isdir(cdir):
        continue
    for f in sorted(os.listdir(cdir)):
        o = yaml.safe_load(open(os.path.join(cdir, f), encoding="utf-8", errors="replace").read())
        P("  %-10s %-12s store=%d 条  elite_store=%s" % (front, f, len(o.get("store") or []), o.get("elite_store")))
OUT.close()
print("done")
