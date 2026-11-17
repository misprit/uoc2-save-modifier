# -*- coding: utf-8 -*-
"""E59: 会议/商店默认值在游戏包里的位置；存档 vs 包的语义等价性"""
import os, io, zipfile, yaml, collections, json

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e59_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

WEST = os.path.join(PK, "base", "data", "campaigns", "west.usc")

P("=" * 74)
P("【1】west.usc/fronts/ 完整结构（深度 4）")
P("=" * 74)
for rt, dn, fn in os.walk(os.path.join(WEST, "fronts")):
    rel = os.path.relpath(rt, WEST).replace("\\", "/")
    depth = rel.count("/")
    if depth <= 3:
        P("  %s%s/  (%d 文件)" % ("  " * depth, rel, len(fn)))
    if depth <= 2:
        for x in sorted(fn)[:6]:
            P("      %s (%d bytes)" % (x, os.path.getsize(os.path.join(rt, x))))

P("")
P("=" * 74)
P("【2】会议定义文件内容样例")
P("=" * 74)
for rel in ["conferences/c_43_04.yml", "conferences/c_44_05.yml",
            "fronts/france/conferences"]:
    fp = os.path.join(WEST, rel.replace("/", os.sep))
    if os.path.isdir(fp):
        P("  --- %s/ ---" % rel)
        for x in sorted(os.listdir(fp))[:8]:
            P("      %s (%d bytes)" % (x, os.path.getsize(os.path.join(fp, x))))
        continue
    if os.path.isfile(fp):
        P("  --- %s ---" % rel)
        P(open(fp, encoding="utf-8").read()[:1200])
        P("")

P("")
P("=" * 74)
P("【3】全游戏包里含 store/quantity 关键词的文件（战役包 + base）")
P("=" * 74)
hits = []
for dlc in sorted(os.listdir(PK)):
    base = os.path.join(PK, dlc, "data")
    if not os.path.isdir(base):
        continue
    for rt, _, fn in os.walk(base):
        for x in fn:
            if not x.endswith((".yml", ".yaml")):
                continue
            fp = os.path.join(rt, x)
            try:
                t = open(fp, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            if "quantity" in t:
                hits.append(os.path.relpath(fp, GAME).replace("\\", "/"))
P("  含 'quantity' 的 yml 共 %d 个:" % len(hits))
for h in hits[:40]:
    P("     %s" % h)

P("")
P("  --- 逐个看前 3 个的内容 ---")
for h in hits[:3]:
    fp = os.path.join(GAME, h.replace("/", os.sep))
    P("  === %s ===" % h)
    P(open(fp, encoding="utf-8", errors="replace").read()[:1500])
    P("")

P("")
P("=" * 74)
P("【4】存档 vs 游戏包 units.yml 语义等价性（yaml.safe_load 后逐项比较）")
P("=" * 74)
def sem(path_zip, member, path_plain):
    with zipfile.ZipFile(path_zip) as zf:
        a = yaml.safe_load(zf.read(member))
    b = yaml.safe_load(open(path_plain, encoding="utf-8").read())
    if a == b:
        return "语义完全相同"
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return "长度不同 %d vs %d" % (len(a), len(b))
        d = [i for i in range(len(a)) if a[i] != b[i]]
        if not d:
            return "语义完全相同（格式差异）"
        i = d[0]
        return "前 %d 项不同, 例 idx=%d\n      存档=%s\n      包  =%s" % (len(d), i, json.dumps(a[i], ensure_ascii=False, default=str)[:300], json.dumps(b[i], ensure_ascii=False, default=str)[:300])
    if isinstance(a, dict) and isinstance(b, dict):
        d = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
        return "语义不同, 键 %s" % d[:8]
    return "类型不同 %s vs %s" % (type(a), type(b))

cases = [
    (r"campaigns\Stalingrad.usg", "document/units.yml", os.path.join(PK, "dlc4/data/campaigns/stalingrad.usc/units.yml")),
    (r"Old Saves\Moscow1941\Moscow-f.usg", "document/units.yml", os.path.join(PK, "dlc3/data/campaigns/moscow.usc/units.yml")),
    (r"games\west_unthinkable.usg", "document/units.yml", os.path.join(WEST, "units.yml")),
    (r"games\west_unthinkable.usg", "document/main.yml", os.path.join(WEST, "main.yml")),
    (r"games\west_unthinkable.usg", "document/locale.yml", os.path.join(WEST, "locale.yml")),
    (r"games\west_unthinkable.usg", "document/hqs.yml", os.path.join(WEST, "hqs.yml")),
    (r"games\west_unthinkable.usg", "document/fallback_prices.yml", os.path.join(WEST, "fallback_prices.yml")),
]
for sav, mem, plain in cases:
    zp = os.path.join(G, sav)
    if not os.path.isfile(zp):
        P("  %s 缺失" % sav); continue
    P("  --- %s :: %s" % (sav, mem))
    P("      %s" % sem(zp, mem, plain))

P("")
P("=" * 74)
P("【5】独立场景存档 game/units.yml 是 ID 清单还是完整对象？（对照文档 §3.4.3）")
P("=" * 74)
with zipfile.ZipFile(os.path.join(G, r"games\west_unthinkable.usg")) as zf:
    u = yaml.safe_load(zf.read("game/units.yml"))
    P("  game/units.yml 类型=%s 长度=%d" % (type(u), len(u)))
    P("  前 5 项: %s" % json.dumps(u[:5], ensure_ascii=False, default=str))
    h = yaml.safe_load(zf.read("game/hqs.yml"))
    P("  game/hqs.yml 类型=%s 长度=%d 内容=%s" % (type(h), len(h), json.dumps(h, ensure_ascii=False, default=str)[:200]))

P("")
P("=" * 74)
P("【6】根 units.yml（存档根，L1）与 game/units.yml 的关系")
P("=" * 74)
with zipfile.ZipFile(os.path.join(G, r"games\west_unthinkable.usg")) as zf:
    P("  根 units.yml: %d bytes, 前 300 字符:" % len(zf.read("units.yml")))
    P("  %s" % zf.read("units.yml").decode("utf-8", "replace")[:300])
    P("  根 hqs.yml: %d bytes" % len(zf.read("hqs.yml")))

OUT.close()
print("done")
