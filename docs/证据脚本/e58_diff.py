# -*- coding: utf-8 -*-
"""E58: 差异定性 + 会议/商店默认值的真实位置"""
import os, io, zipfile, yaml, collections, difflib, hashlib

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e58_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

WEST = os.path.join(PK, "base", "data", "campaigns", "west.usc")

P("=" * 74)
P("【1】游戏包 west.usc 顶层结构")
P("=" * 74)
for n in sorted(os.listdir(WEST)):
    full = os.path.join(WEST, n)
    if os.path.isdir(full):
        P("  %-16s <dir>  %d 个" % (n, len(os.listdir(full))))
    else:
        P("  %-16s %d bytes" % (n, os.path.getsize(full)))

P("")
P("=" * 74)
P("【2】west.usc/conferences/ 结构（会议级默认值来源）")
P("=" * 74)
cf = os.path.join(WEST, "conferences")
if os.path.isdir(cf):
    for c in sorted(os.listdir(cf))[:6]:
        d = os.path.join(cf, c)
        if os.path.isdir(d):
            P("  会议 %s:" % c)
            for rt, _, ff in os.walk(d):
                for x in sorted(ff):
                    P("     %s (%d bytes)" % (os.path.relpath(os.path.join(rt, x), d).replace("\\", "/"), os.path.getsize(os.path.join(rt, x))))
        else:
            P("  %s (%d bytes)" % (c, os.path.getsize(d)))
    P("  会议总数: %d" % len(os.listdir(cf)))

P("")
P("=" * 74)
P("【3】west.usc/fronts/ 结构（战线级默认值来源）")
P("=" * 74)
fr = os.path.join(WEST, "fronts")
if os.path.isdir(fr):
    for c in sorted(os.listdir(fr)):
        d = os.path.join(fr, c)
        if os.path.isdir(d):
            P("  front %s: %d 个文件 -> %s" % (c, len(os.listdir(d)), sorted(os.listdir(d))[:14]))
        else:
            P("  %s (%d bytes)" % (c, os.path.getsize(d)))

P("")
P("=" * 74)
P("【4】独立场景存档 document/ 6 文件 vs 游戏包同名文件 —— 差异性质")
P("=" * 74)
SA = os.path.join(G, r"games\west_unthinkable.usg")
with zipfile.ZipFile(SA) as zf:
    for n in ["fallback_prices.yml", "hqs.yml", "locale.yml", "main.yml", "medals.yml", "units.yml"]:
        b = zf.read("document/" + n)
        fp = os.path.join(WEST, n.replace("/", os.sep))
        if not os.path.isfile(fp):
            P("  %-22s 包里没有" % n); continue
        pb = open(fp, "rb").read()
        P("  %-22s 存档=%-7d 包=%-7d %s" % (n, len(b), len(pb), "字节相同" if b == pb else "不同"))
        if b != pb and n in ("main.yml", "units.yml", "locale.yml", "medals.yml"):
            try:
                ya = yaml.safe_load(b.decode("utf-8"))
                yb = yaml.safe_load(pb.decode("utf-8"))
                if isinstance(ya, dict) and isinstance(yb, dict):
                    ka, kb = set(ya), set(yb)
                    P("       顶层键: 存档=%d 包=%d  仅存档有=%s  仅包有=%s" % (len(ka), len(kb), sorted(ka - kb)[:8], sorted(kb - ka)[:8]))
                    diffk = [k for k in sorted(ka & kb) if ya[k] != yb[k]]
                    P("       同键但值不同的: %d 个 -> %s" % (len(diffk), diffk[:8]))
                    for k in diffk[:2]:
                        P("         [%s] 存档=%s" % (k, str(ya[k])[:220]))
                        P("         [%s] 包  =%s" % (k, str(yb[k])[:220]))
                else:
                    P("       类型: 存档=%s 包=%s" % (type(ya), type(yb)))
            except Exception as e:
                P("       YAML 解析失败: %s" % e)

P("")
P("=" * 74)
P("【5】独立场景存档 game/ vs 包 scenarios/unthinkable/ —— 差异性质（逐文件）")
P("=" * 74)
SCD = os.path.join(WEST, "scenarios", "unthinkable")
with zipfile.ZipFile(SA) as zf:
    for n in sorted(x for x in zf.namelist() if x.startswith("game/") and x != "game/archive"):
        rel = n[len("game/"):]
        fp = os.path.join(SCD, rel.replace("/", os.sep))
        if not os.path.isfile(fp):
            P("  %-26s 包里没有" % rel); continue
        b = zf.read(n); pb = open(fp, "rb").read()
        same = b == pb
        P("  %-26s 存档=%-7d 包=%-7d %s" % (rel, len(b), len(pb), "字节相同" if same else "不同"))
        if not same and rel.endswith(".yml"):
            try:
                ya = yaml.safe_load(b.decode("utf-8")); yb = yaml.safe_load(pb.decode("utf-8"))
                if isinstance(ya, dict) and isinstance(yb, dict):
                    ka, kb = set(ya), set(yb)
                    diffk = [k for k in sorted(ka & kb) if ya[k] != yb[k]]
                    P("       顶层键 存档=%d 包=%d | 仅存档:%s | 仅包:%s | 值不同:%s" %
                      (len(ka), len(kb), sorted(ka - kb)[:6], sorted(kb - ka)[:6], diffk[:6]))
                    for k in diffk[:3]:
                        P("         [%s] 存档=%s" % (k, str(ya[k])[:200]))
                        P("         [%s] 包  =%s" % (k, str(yb[k])[:200]))
                else:
                    P("       顶层: 存档=%s 包=%s" % (str(ya)[:150], str(yb)[:150]))
            except Exception as e:
                P("       YAML 解析失败: %s" % e)

P("")
P("=" * 74)
P("【6】moscow / stalingrad 战役存档里唯一不同的 document/units.yml")
P("=" * 74)
for sav, camp in [(r"Old Saves\Moscow1941\Moscow-f.usg", "dlc3/data/campaigns/moscow.usc"),
                  (r"campaigns\Stalingrad.usg", "dlc4/data/campaigns/stalingrad.usc")]:
    with zipfile.ZipFile(os.path.join(G, sav)) as zf:
        b = zf.read("document/units.yml")
    pb = open(os.path.join(PK, camp.replace("/", os.sep), "units.yml"), "rb").read()
    P("  --- %s" % sav)
    P("      存档=%d 包=%d 字节相同=%s" % (len(b), len(pb), b == pb))
    ya = yaml.safe_load(b.decode("utf-8")); yb = yaml.safe_load(pb.decode("utf-8"))
    ka = set(ya) if isinstance(ya, dict) else set()
    kb = set(yb) if isinstance(yb, dict) else set()
    P("      顶层键 存档=%d 包=%d | 仅存档=%s | 仅包=%s" % (len(ka), len(kb), sorted(ka - kb)[:6], sorted(kb - ka)[:6]))
    if ka & kb:
        diffk = [k for k in sorted(ka & kb) if ya[k] != yb[k]]
        P("      值不同: %s" % diffk[:6])
        for k in diffk[:2]:
            P("         [%s] 存档=%s" % (k, str(ya[k])[:200]))
            P("         [%s] 包  =%s" % (k, str(yb[k])[:200]))
    else:
        P("      存档类型=%s 包类型=%s" % (type(ya), type(yb)))
        P("      存档前 400 字符: %s" % b.decode("utf-8", "replace")[:400])
        P("      包   前 400 字符: %s" % pb.decode("utf-8", "replace")[:400])

OUT.close()
print("done")
