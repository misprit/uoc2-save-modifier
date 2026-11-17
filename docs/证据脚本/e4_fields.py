# -*- coding: utf-8 -*-
"""E4: 字段结构级别 —— 各层文件的条目到底有哪些键；游戏字节码如何加载战斗单位"""
import os, io, zipfile, yaml, marshal, re, dis

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e4_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

p = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(p) as zf:
    names = zf.namelist()

    P("=" * 100)
    P("[A] document/scenarios/road_to_stalingrad/units.yml  条目键集")
    P("=" * 100)
    v = zl(zf, "document/scenarios/road_to_stalingrad/units.yml")
    P(f"    容器类型 {type(v).__name__}  长度 {len(v)}")
    P(f"    第 1 项完整内容:")
    P("      " + yaml.safe_dump(v[0], allow_unicode=True, sort_keys=False).replace("\n", "\n      "))
    keysets = {tuple(sorted(u.keys())) for u in v}
    P(f"    全部条目的键集种类数 = {len(keysets)}")
    for ks in list(keysets)[:3]:
        P(f"      {ks}")

    P("")
    P("=" * 100)
    P("[B] document/scenarios/road_to_stalingrad/enroute_units.yml  条目键集")
    P("=" * 100)
    v = zl(zf, "document/scenarios/road_to_stalingrad/enroute_units.yml")
    P(f"    长度 {len(v)}")
    P("    第 1 项完整内容:")
    P("      " + yaml.safe_dump(v[0], allow_unicode=True, sort_keys=False).replace("\n", "\n      "))
    P(f"    顶层键集种类: { {tuple(sorted(e.keys())) for e in v} }")
    P(f"    unit 子字典键集: { {tuple(sorted(e['unit'].keys())) for e in v} }")

    P("")
    P("=" * 100)
    P("[C] games/road_to_stalingrad/main.yml 全文")
    P("=" * 100)
    m = zl(zf, "games/road_to_stalingrad/main.yml")
    P("      " + yaml.safe_dump(m, allow_unicode=True, sort_keys=False).replace("\n", "\n      "))

    P("")
    P("=" * 100)
    P("[D] games/road_to_stalingrad/ 目录全部条目")
    P("=" * 100)
    for n in sorted(x for x in names if x.startswith("games/road_to_stalingrad/")):
        P(f"    {n}")

    P("")
    P("=" * 100)
    P("[E] archive 快照 campaign_units.yml 条目结构")
    P("=" * 100)
    with zipfile.ZipFile(os.path.join(G, r"Old Saves\Victory in the West\经典难度\west-Husky.usg")) as z2:
        az = zipfile.ZipFile(__import__("io").BytesIO(z2.read("games/husky/archive")))
        cu = zl(az, "turn_01_phase_00_allies/campaign_units.yml")
        P(f"    长度 {len(cu)}")
        P("    第 1 项完整内容:")
        P("      " + yaml.safe_dump(cu[0], allow_unicode=True, sort_keys=False).replace("\n", "\n      "))
        P(f"    键集种类: { {tuple(sorted(u.keys())) for u in cu} }")

    # ------------------------------------------------------------------
    P("")
    P("=" * 100)
    P("[F] 字节码：游戏如何加载战斗单位（搜 units.yml / campaign_units / enroute）")
    P("=" * 100)
    LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
    pats = ["units.yml", "campaign_units", "enroute", "archive"]
    hits = {}
    for dirpath, _, files in os.walk(LIB):
        for f in files:
            if not f.endswith(".pyc"):
                continue
            fp = os.path.join(dirpath, f)
            try:
                code = marshal.loads(open(fp, "rb").read()[16:])
            except Exception:
                continue
            strs = set()
            def walk(c):
                for k in c.co_consts:
                    if isinstance(k, str):
                        strs.add(k)
                    elif hasattr(k, "co_consts"):
                        walk(k)
            walk(code)
            found = [p for p in pats if any(p in s for s in strs)]
            if found:
                rel = os.path.relpath(fp, LIB)
                hits[rel] = (found, strs)
    for rel, (found, strs) in sorted(hits.items()):
        P(f"    {rel}   命中 {found}")
        for s in sorted(strs):
            if any(p in s for p in pats) and len(s) < 90:
                P(f"        {s!r}")

OUT.close()
print("done")
