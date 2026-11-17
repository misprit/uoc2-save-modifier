# -*- coding: utf-8 -*-
"""E36: 存档 document/units.yml 与游戏包 west.usc/units.yml 的精确关系"""
import os, io, zipfile, yaml

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
PKG = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\data\campaigns\west.usc"
OUT = io.open(r"D:\MiniMax\_analysis\e36_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

# 游戏包
pkg_files = sorted(os.listdir(PKG))
P(f"游戏包 west.usc 顶层: {pkg_files}")
pkg_units = yaml.safe_load(open(os.path.join(PKG, "units.yml"), encoding="utf-8")) or []
pkgmap = {u["id"]: u for u in pkg_units}
P(f"包 units.yml: {len(pkg_units)} 条, id {min(pkgmap)}..{max(pkgmap)}")
P(f"  前 5 条: {pkg_units[:5]}")

CASES = [
    r"campaigns\west-Conference1-1.usg",
    r"campaigns\Stalingrad.usg",
    r"Old Saves\Victory in the West\经典难度\west-Husky.usg",
]
for rel in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        P(f"\nMISS {rel}"); continue
    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
        if "document/units.yml" not in names:
            P(f"\n{rel}: 无 document/units.yml"); continue
        su = zl(zf, "document/units.yml") or []
        smap = {u["id"]: u for u in su}
        doc_files = [n for n in names if n.startswith("document/")]
        P("")
        P("=" * 90)
        P(f"{rel}")
        P(f"  document/ 条目数 = {len(doc_files)}")
        P(f"  document/units.yml: {len(su)} 条, id {min(smap)}..{max(smap)}")
        onlysave = sorted(set(smap) - set(pkgmap))
        onlypkg = sorted(set(pkgmap) - set(smap))
        P(f"  仅在存档里的 id: {onlysave[:20]}  (共 {len(onlysave)})")
        P(f"  仅在包里的 id  : {onlypkg[:20]}  (共 {len(onlypkg)})")
        typediff = [(i, pkgmap[i].get("type"), smap[i].get("type"))
                    for i in sorted(set(pkgmap) & set(smap))
                    if pkgmap[i].get("type") != smap[i].get("type")]
        P(f"  交集 {len(set(pkgmap) & set(smap))} 个中 type 不同: {len(typediff)}")
        P(f"    样例: {typediff[:6]}")
        P(f"  存档前 3 条: {su[:3]}")
        # 存档 document/ 与包的其它文件是否一致
        diffs = []
        for n in doc_files:
            rel2 = n[len("document/"):]
            pp = os.path.join(PKG, rel2.replace("/", os.sep))
            if not os.path.isfile(pp):
                diffs.append((rel2, "包中无")); continue
            if open(pp, "rb").read() != zf.read(n):
                diffs.append((rel2, "内容不同"))
        P(f"  document/ 与包内容不同的文件: {len(diffs)} -> {diffs[:10]}")

OUT.close()
print("done")
