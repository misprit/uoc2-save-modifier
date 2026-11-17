# -*- coding: utf-8 -*-
"""E63: 单位名读写方向（字节码）+ 各状态下场景名的可获取路径"""
import os, io, marshal, dis, sys, types, zipfile, yaml, json, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e63_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(pyc):
    with open(pyc, "rb") as f:
        return marshal.loads(f.read()[16:])

def walk(code, prefix=""):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield prefix + c.co_name, c
            for n, cc in walk(c, prefix + c.co_name + "."):
                yield n, cc

def show(code, lim=200):
    out = []
    for i, x in enumerate(dis.get_instructions(code)):
        if i > lim:
            out.append("    ...(截断)"); break
        out.append("    %-28s %s" % (x.opname, x.argrepr))
    return "\n".join(out)

def strconsts(code):
    o = []
    for c in code.co_consts:
        if isinstance(c, str):
            o.append(c)
        elif isinstance(c, types.CodeType):
            o.extend(strconsts(c))
    return o

P("=" * 74)
P("【1】Campaign._save_campaign_units / _load_campaign_units")
P("=" * 74)
root = load(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
for target in ["_save_campaign_units", "_load_campaign_units", "_save_campaign_files", "_load_campaign_objects"]:
    for n, c in walk(root):
        if c.co_name == target:
            P("  === %s ===" % n)
            P("      字符串: %s" % [s for s in strconsts(c)][:14])
            P(show(c, 90))
            P("")

P("")
P("=" * 74)
P("【2】各状态下场景名 / 会议名 的可获取路径（实测）")
P("=" * 74)
rows = []
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, G)
        try:
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
                m = yaml.safe_load(zf.read("main.yml")) or {}
                ins = m.get("in_state") or {}
                gnames = sorted(set(n.split("/")[1] for n in names if n.startswith("games/") and n.count("/") >= 2))
                # games/<x>/main.yml 里有没有场景名字段
                gm = None
                if gnames:
                    k = "games/%s/main.yml" % gnames[-1]
                    if k in names:
                        try:
                            gm = yaml.safe_load(zf.read(k))
                        except Exception:
                            gm = "PARSE_FAIL"
                lg = None
                if "last_game/main.yml" in names:
                    try:
                        lg = yaml.safe_load(zf.read("last_game/main.yml"))
                    except Exception:
                        lg = "PARSE_FAIL"
                lc = None
                if "last_conference/main.yml" in names:
                    try:
                        lc = yaml.safe_load(zf.read("last_conference/main.yml"))
                    except Exception:
                        lc = "PARSE_FAIL"
                rows.append((rel, m.get("campaign_id"), m.get("standalone_scenario"),
                             ins.get("scenario"), ins.get("front"), ins.get("conference"),
                             gnames[-3:], gm, lg, lc))
        except Exception as e:
            rows.append((rel, "ERR", str(e), None, None, None, None, None, None, None))

def brief(x, n=9):
    if isinstance(x, dict):
        return {k: x[k] for k in list(x)[:n]}
    return x

for r in rows[:6]:
    P("  --- %s" % r[0][:60])
    P("      cid=%s standalone=%s in.scenario=%s in.front=%s in.conference=%s" % r[1:6])
    P("      games 目录(后3)=%s" % r[6])
    P("      games/<x>/main.yml 键: %s" % (list(r[7])[:12] if isinstance(r[7], dict) else r[7]))
    if isinstance(r[7], dict):
        P("        scenario=%s variant=%s" % (r[7].get("scenario"), r[7].get("variant")))
    P("      last_game/main.yml 键: %s" % (list(r[8])[:12] if isinstance(r[8], dict) else r[8]))
    if isinstance(r[8], dict):
        P("        scenario=%s variant=%s" % (r[8].get("scenario"), r[8].get("variant")))
    P("      last_conference/main.yml 键: %s" % (list(r[9])[:12] if isinstance(r[9], dict) else r[9]))

P("")
P("  --- 全样本：games/<x>/main.yml 是否都含 scenario 字段 ---")
c = collections.Counter()
for r in rows:
    if isinstance(r[7], dict):
        c["games.main 键=" + str("scenario" in r[7])] += 1
    if isinstance(r[8], dict):
        c["last_game.main 键=" + str("scenario" in r[8])] += 1
    if isinstance(r[9], dict):
        c["last_conf.main 键=" + str("scenario" in r[9])] += 1
for k, v in c.most_common():
    P("      %s -> %d" % (k, v))

P("")
P("  --- games/<x>/main.yml 的完整键集（取一个样本）---")
for r in rows:
    if isinstance(r[7], dict) and len(r[7]) > 10:
        P("      %s" % r[0][:50])
        P("      %s" % yaml.safe_dump(r[7], allow_unicode=True, default_flow_style=False, sort_keys=False)[:1400])
        break

OUT.close()
print("done")
