import os, io, zipfile, yaml, json
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e68_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def key(e):
    return (e.get("nationality"), e.get("equipment"), e.get("spec"))

with zipfile.ZipFile(os.path.join(G, r"campaigns\Stalingrad.usg")) as zf:
    root = yaml.safe_load(zf.read("store.yml"))
    lastc = yaml.safe_load(zf.read("last_conference/store.yml"))
    m = yaml.safe_load(zf.read("main.yml"))

P("当前会议 = %s" % m["in_state"]["conference"])
for front in sorted(root):
    a = root[front].get("store") or []
    b = lastc[front].get("store") or []
    ka = {key(e): e for e in a}
    kb = {key(e): e for e in b}
    P("")
    P("--- %s: 根 %d 条 / last_conference %d 条 ---" % (front, len(a), len(b)))
    only_b = [k for k in kb if k not in ka]
    P("  last_conf 有、根没有（= 已售罄/已买走）: %d 条" % len(only_b))
    for k in only_b:
        P("     %s" % json.dumps(kb[k], ensure_ascii=False))
    common = [k for k in ka if k in kb]
    diffq = [(k, kb[k], ka[k]) for k in common if kb[k] != ka[k]]
    P("  两边都有但内容不同: %d 条" % len(diffq))
    for k, x, y in diffq[:8]:
        P("     last_conf=%s" % json.dumps(x, ensure_ascii=False))
        P("     root    =%s" % json.dumps(y, ensure_ascii=False))

P("")
P("=" * 70)
P("对照：包里 fronts/south/conferences/c_42_07.yml 的 store 条目")
P("=" * 70)
cd = os.path.join(PK, "dlc4/data/campaigns/stalingrad.usc")
o = yaml.safe_load(open(os.path.join(cd, "fronts", "south", "conferences", "c_42_07.yml"), encoding="utf-8").read())
pkg = o.get("store") or []
P("  包 c_42_07 south: %d 条" % len(pkg))
for e in pkg:
    P("     %s" % json.dumps(e, ensure_ascii=False))
P("")
P("  与根 store.yml south 的 13 条对比:")
rootS = {key(e): e for e in (root["south"].get("store") or [])}
for e in pkg:
    k = key(e)
    if k in rootS:
        P("     [在] %s  包=%s 根=%s" % (json.dumps(k, ensure_ascii=False), json.dumps(e, ensure_ascii=False), json.dumps(rootS[k], ensure_ascii=False)))
    else:
        P("     [无] %s  包=%s" % (json.dumps(k, ensure_ascii=False), json.dumps(e, ensure_ascii=False)))
OUT.close()
print("done")
