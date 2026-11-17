import os, io, yaml, json, collections
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
cd = os.path.join(PK, "dlc4/data/campaigns/stalingrad.usc")
OUT = io.open(r"D:\MiniMax\_analysis\e71_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def key(e):
    return (e.get("nationality"), e.get("equipment"), e.get("spec"))

SAVE = {  # Stalingrad-Conference3-2.usg 根 store.yml caucasus
    ('german', 'infantry', None): 10, ('german', 'armor', None): 10,
    ('german', None, 'ger_towed_arty_42'): 40, ('german', None, 'ger_towed_at_dlc3'): 25,
    ('german', None, 'ger_towed_at_dlc4_opt'): 35, ('german', None, 'ger_eng_dlc4'): 50,
    ('german', None, 'ger_asg_dlc4'): 50, ('german', None, 'ger_asg_dlc4_opt'): 60,
    ('german', None, 'ger_recon_41'): 40, ('german', None, 'ger_at_dlc4'): 35,
    ('romanian', 'infantry', None): 5, ('italian', 'infantry', None): 5,
    ('hungarian', 'infantry', None): 5, ('slovak', 'infantry', None): 5,
    ('hungarian', None, 'hun_towed_arty_41'): 40, ('italian', None, 'ita_recon_dlc4'): 35,
    ('italian', None, 'ita_arty_towed_41'): 40, ('italian', None, 'ita_eng_39'): 35,
    ('italian', None, 'ita_towed_at_41'): 35,
}

for front in ["caucasus", "south"]:
    P("=== front %s ===" % front)
    cdir = os.path.join(cd, "fronts", front, "conferences")
    for f in sorted(os.listdir(cdir)):
        o = yaml.safe_load(open(os.path.join(cdir, f), encoding="utf-8", errors="replace").read()) or {}
        st = o.get("store") or []
        pm = {key(e): e.get("price") for e in st}
        qm = {key(e): e.get("quantity") for e in st}
        same_p = sum(1 for k, v in SAVE.items() if pm.get(k) == v)
        same_q = sum(1 for t in [('german','infantry',None,20),('german','armor',None,10),('romanian','infantry',None,10),('italian','infantry',None,5),('hungarian','infantry',None,5),('slovak','infantry',None,5)] if qm.get(t[0:3]) == t[3])
        P("  %-12s 条数=%-3d 价格与存档相同 %2d/19  6个通用装备quantity与存档(20/10/10/5/5/5)相同 %d/6  顶层键=%s"
          % (f, len(st), same_p, same_q, list(o)))
P("")
P("存档 caucasus 的价格向量 vs 各包文件价格向量:")
for front in ["caucasus", "south"]:
    cdir = os.path.join(cd, "fronts", front, "conferences")
    for f in sorted(os.listdir(cdir)):
        o = yaml.safe_load(open(os.path.join(cdir, f), encoding="utf-8", errors="replace").read()) or {}
        st = o.get("store") or []
        pm = {key(e): e.get("price") for e in st}
        diff = [(k, pm.get(k), SAVE.get(k)) for k in pm if pm.get(k) != SAVE.get(k)]
        P("  %s/%-12s 与存档价不同的条目 %d 个: %s" % (front, f, len(diff), diff[:8]))
OUT.close()
print("done")
