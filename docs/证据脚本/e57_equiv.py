# -*- coding: utf-8 -*-
"""E57: 存档 document/ 与游戏包 .usc 的等价性；场景预设/商店定义的确切位置"""
import os, io, zipfile, yaml, collections, hashlib

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e57_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]

def pkg_campaign_dir(cid):
    """campaign_id -> 游戏包里的 .usc 目录"""
    hits = []
    for dlc in sorted(os.listdir(PK)):
        cd = os.path.join(PK, dlc, "data", "campaigns")
        if not os.path.isdir(cd):
            continue
        for camp in sorted(os.listdir(cd)):
            if camp.rsplit(".", 1)[0] == cid:
                hits.append(os.path.join(cd, camp))
    return hits

P("=" * 74)
P("【1】campaign_id -> 游戏包 .usc 目录 映射表（唯一性检查）")
P("=" * 74)
allcids = set()
for dp, _, fs in os.walk(G):
    for f in fs:
        if f.lower().endswith(".usg"):
            try:
                with zipfile.ZipFile(os.path.join(dp, f)) as zf:
                    if "main.yml" in zf.namelist():
                        allcids.add((yaml.safe_load(zf.read("main.yml")) or {}).get("campaign_id"))
            except Exception:
                pass
cidmap = {}
for c in sorted(x for x in allcids if x):
    hits = pkg_campaign_dir(c)
    cidmap[c] = hits
    P("  %-14s -> %s" % (c, hits if hits else "!! 游戏包里没有 !!"))

P("")
P("=" * 74)
P("【2】战役存档 document/ vs 游戏包 .usc：逐文件 SHA256 比对（全部战役存档）")
P("=" * 74)
summary = collections.Counter()
per_cam = {}
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        try:
            zf = zipfile.ZipFile(p)
        except Exception:
            continue
        names = zf.namelist()
        if "main.yml" not in names:
            zf.close(); continue
        cid = (yaml.safe_load(zf.read("main.yml")) or {}).get("campaign_id")
        sa = (yaml.safe_load(zf.read("main.yml")) or {}).get("standalone_scenario")
        doc = [n for n in names if n.startswith("document/")]
        if not doc:
            zf.close(); continue
        hits = cidmap.get(cid) or []
        if not hits:
            summary["no_pkg"] += 1
            zf.close(); continue
        # 取第一个匹配的包（多包时选文件数多的）
        best = None
        for h in hits:
            pfiles = []
            for rt, _, ff in os.walk(h):
                for x in ff:
                    pfiles.append(os.path.relpath(os.path.join(rt, x), h).replace("\\", "/"))
            if best is None or len(pfiles) > best[1]:
                best = (h, len(pfiles))
        pkgdir, npkg = best
        pkgfiles = set()
        for rt, _, ff in os.walk(pkgdir):
            for x in ff:
                pkgfiles.add(os.path.relpath(os.path.join(rt, x), pkgdir).replace("\\", "/"))
        docfiles = set(n[len("document/"):] for n in doc)
        same = diff = onlydoc = onlypkg = 0
        difflist = []
        for n in sorted(docfiles):
            b = zf.read("document/" + n)
            fp = os.path.join(pkgdir, n.replace("/", os.sep))
            if os.path.isfile(fp):
                if sha(b) == sha(open(fp, "rb").read()):
                    same += 1
                else:
                    diff += 1; difflist.append(n)
            else:
                onlydoc += 1; difflist.append("ONLYDOC:" + n)
        for n in sorted(pkgfiles - docfiles):
            onlypkg += 1
        key = "%s/%s" % (cid, sa if sa else "campaign")
        if key not in per_cam:
            per_cam[key] = (same, diff, onlydoc, onlypkg, len(docfiles), len(pkgfiles), difflist[:5])
        zf.close()
for k, v in sorted(per_cam.items()):
    P("  %-24s same=%-5d diff=%-4d onlydoc=%-4d onlypkg=%-4d  doc=%d pkg=%d" % (k, v[0], v[1], v[2], v[3], v[4], v[5]))
    if v[6]:
        P("      例外: %s" % v[6])

P("")
P("=" * 74)
P("【3】独立场景存档 game/ vs 游戏包 scenarios/<name>/：逐文件比对")
P("=" * 74)
for sp in [r"games\west_unthinkable.usg", r"games\west_normandy_breakout.usg", r"games\west_unthinkable_hotseat.usg"]:
    fp = os.path.join(G, sp)
    if not os.path.isfile(fp):
        P("  缺失: %s" % sp); continue
    with zipfile.ZipFile(fp) as zf:
        names = zf.namelist()
        m = yaml.safe_load(zf.read("main.yml"))
        sa = m.get("standalone_scenario"); cid = m.get("campaign_id")
        gm = [n for n in names if n.startswith("game/")]
        P("  --- %s  (cid=%s, standalone=%s)" % (sp, cid, sa))
        cands = []
        for h in pkg_campaign_dir(cid):
            sd = os.path.join(h, "scenarios", sa)
            if os.path.isdir(sd):
                cands.append(sd)
        for sd in cands:
            P("      包: %s" % os.path.relpath(sd, GAME).replace("\\", "/"))
            for n in sorted(gm):
                rel = n[len("game/"):]
                if rel == "archive":
                    continue
                fp2 = os.path.join(sd, rel.replace("/", os.sep))
                if os.path.isfile(fp2):
                    ok = sha(zf.read(n)) == sha(open(fp2, "rb").read())
                    P("        %-26s %s" % (rel, "SHA256一致" if ok else "!! 不同 !!"))
                else:
                    P("        %-26s 包里没有（存档独有）" % rel)
            extra = []
            for rt, _, ff in os.walk(sd):
                for x in ff:
                    rel = os.path.relpath(os.path.join(rt, x), sd).replace("\\", "/")
                    if rel not in [n[len("game/"):] for n in gm]:
                        extra.append(rel)
            P("        包里存档没有的: %s" % (sorted(extra) or "无"))

P("")
P("=" * 74)
P("【4】商店定义的确切位置与结构")
P("=" * 74)
SP = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(SP) as zf:
    names = zf.namelist()
    stores = [n for n in names if n.endswith("store.yml")]
    P("  Stalingrad.usg 里 store.yml 共 %d 个:" % len(stores))
    for s in sorted(stores)[:6]:
        P("    %s (%d bytes)" % (s, len(zf.read(s))))
    if "store.yml" in names:
        P("  --- 根 store.yml ---")
        P(zf.read("store.yml").decode("utf-8")[:1500])
    c0 = sorted(set(n.split("/")[2] for n in names if n.startswith("document/conferences/") and n.count("/") >= 3))
    P("  --- document/conferences/ 会议列表 (%d) ---" % len(c0))
    P("      %s" % c0[:12])
    cs = "document/conferences/%s/store.yml" % (c0[0] if c0 else "__none__")
    if c0 and cs in names:
        P("  --- %s ---" % cs)
        P(zf.read(cs).decode("utf-8")[:1800])
    P("  --- document/ 顶层目录清单 ---")
    dtree = collections.Counter()
    for n in names:
        if n.startswith("document/"):
            r = n[len("document/"):]
            dtree[r.split("/")[0] + ("/" if "/" in r else "")] += 1
    for k, v in dtree.most_common():
        P("      %-30s %d" % (k, v))
    P("  --- document/scenarios/<id>/ 的示例（取一个场景，列出其下全部文件）---")
    sid0 = sorted(set(n.split("/")[2] for n in names if n.startswith("document/scenarios/") and n.count("/") >= 3))
    if sid0:
        sub = sorted(n for n in names if n.startswith("document/scenarios/%s/" % sid0[0]))
        P("      场景 %s 下 %d 个条目:" % (sid0[0], len(sub)))
        for s in sub:
            P("        %s (%d bytes)" % (s, zf.getinfo(s).file_size))
        main_s = "document/scenarios/%s/main.yml" % sid0[0]
        if main_s in names:
            P("      --- %s (前 2500 字符) ---" % main_s)
            P(zf.read(main_s).decode("utf-8")[:2500])
    P("  --- 场景目录下有哪些文件（document/scenarios/<id>/ 前缀统计）---")
    pref = collections.Counter()
    for n in names:
        if n.startswith("document/scenarios/"):
            rest = n[len("document/scenarios/"):]
            sid, fn = rest.split("/", 1) if "/" in rest else (rest, "")
            pref[fn.split("/")[0] + ("/" if "/" in fn else "")] += 1
    for k, v in pref.most_common(30):
        P("      %-28s %d" % (k, v))

P("")
P("  --- document/fallback_prices.yml 内容 ---")
with zipfile.ZipFile(SP) as zf:
    if "document/fallback_prices.yml" in zf.namelist():
        P(zf.read("document/fallback_prices.yml").decode("utf-8")[:1200])
    else:
        P("    (Stalingrad 存档没有此文件)")
with zipfile.ZipFile(os.path.join(G, r"Old Saves\Victory in the West\经典难度\west-Husky.usg")) as zf:
    if "document/fallback_prices.yml" in zf.namelist():
        P("  --- west-Husky.usg 的 fallback_prices.yml ---")
        P(zf.read("document/fallback_prices.yml").decode("utf-8")[:1200])

OUT.close()
print("done")
