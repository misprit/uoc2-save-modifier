# -*- coding: utf-8 -*-
"""E19: 变体覆盖 / tot_st 定义 / 对照组（非资产单位是否也被补齐战力）"""
import os, io, marshal, dis, types, zipfile, yaml

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e19_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

P("=" * 100); P("[A] tot_st / tot_specs 定义（entity.pyc 与所有 uoc2）"); P("=" * 100)
found = False
for dirpath, _, files in os.walk(os.path.join(LIB, "uoc2")):
    for f in files:
        if not f.endswith(".pyc"):
            continue
        fp = os.path.join(dirpath, f)
        try:
            c = marshal.loads(open(fp, "rb").read()[16:])
        except Exception:
            continue
        for path, fn, ln in walk_all(c):
            if fn.co_name in ("tot_st", "tot_specs"):
                found = True
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln}")
                buf = io.StringIO(); dis.dis(fn, file=buf, depth=0)
                for l in buf.getvalue().split("\n")[:40]:
                    P("      " + l)
if not found:
    P("  未找到名为 tot_st/tot_specs 的代码对象（可能是 C 扩展/属性表或父类里以别的形式定义）")

P(""); P("=" * 100); P("[B] 变体覆盖 —— 当前变体 vs 基础资产文件"); P("=" * 100)

CASES = [
    (r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "husky"),
    (r"Old Saves\Victory in the West\经典难度\west-MonteCassino.usg", "monte_cassino"),
    (r"Old Saves\Victory in the West\经典难度\west-LastWar.usg", "unthinkable"),
]
for rel, scen in CASES:
    p = os.path.join(G, rel)
    if not os.path.isfile(p):
        continue
    P("")
    P(f"### {os.path.basename(p)}  scenario={scen}")
    with zipfile.ZipFile(p) as zf:
        m = zl(zf, "main.yml") or {}
        ins = m.get("in_state") or {}
        P(f"    in_state.variant = {ins.get('variant')!r}   in_state.scenario = {ins.get('scenario')!r}")
        # 列出所有变体资产文件
        vnames = sorted(n for n in zf.namelist()
                        if n.startswith(f"document/scenarios/{scen}/variants/") and n.endswith("prepositioned_assets.yml"))
        P(f"    变体资产文件: {vnames}")
        base = zl(zf, f"document/scenarios/{scen}/prepositioned_assets.yml") or []
        P(f"    基础文件 assets: {[(a.get('id'), a.get('type'), (a.get('unit') or {}).get('id')) for a in base]}")
        for vn in vnames:
            vv = zl(zf, vn) or []
            P(f"    {vn}: {[(a.get('id'), a.get('type'), (a.get('unit') or {}).get('id')) for a in vv]}")
        # 变体 units.yml / enroute_units.yml
        for vn in sorted(set(n.split("/")[3] for n in zf.namelist()
                             if n.startswith(f"document/scenarios/{scen}/variants/"))):
            u = zl(zf, f"document/scenarios/{scen}/variants/{vn}/units.yml")
            e = zl(zf, f"document/scenarios/{scen}/variants/{vn}/enroute_units.yml")
            P(f"      变体 {vn}: units.yml={len(u) if u else None}  enroute_units.yml={len(e) if e else None}")

P(""); P("=" * 100); P("[C] 对照组：场景初始单位（非资产承载）的 act_st 是否被补到场景值"); P("=" * 100)
rel, scen = r"Old Saves\Victory in the West\经典难度\west-Husky.usg", "husky"
p = os.path.join(G, rel)
with zipfile.ZipFile(p) as zf:
    root = {u["id"]: u for u in (zl(zf, "units.yml") or [])}
    scen_u = zl(zf, f"document/scenarios/{scen}/units.yml") or []
    ppa = zl(zf, f"document/scenarios/{scen}/prepositioned_assets.yml") or []
    asset_ids = {(a.get("unit") or {}).get("id") for a in ppa if a.get("type") != "bb"}
    P(f"    场景初始单位 {len(scen_u)} 个；其中被资产承载的 {len(asset_ids)} 个")
    P(f"    {'id':>6} {'场景act+sup':>12} {'根表act+sup':>12} {'是否资产单位':>12}  specs 场景→根表")
    same = diff = 0
    for u in scen_u[:14]:
        i = u["id"]
        t = (u.get("act_st") or 0) + (u.get("sup_st") or 0)
        r = root.get(i)
        if not r:
            continue
        rt = (r.get("act_st") or 0) + (r.get("sup_st") or 0)
        is_asset = i in asset_ids
        P(f"    {i:>6} {t:>12} {rt:>12} {str(is_asset):>12}  "
          f"{[s.get('type') for s in (u.get('specs') or [])]} → {[s.get('type') for s in (r.get('specs') or [])]}")
    # 统计：非资产单位里 场景act+sup == 根表act+sup 的比例
    ok = tot = 0
    for u in scen_u:
        i = u["id"]
        r = root.get(i)
        if not r or i in asset_ids:
            continue
        tot += 1
        if (u.get("act_st") or 0) + (u.get("sup_st") or 0) == (r.get("act_st") or 0) + (r.get("sup_st") or 0):
            ok += 1
    P(f"    非资产单位中『场景战力 == 根表战力』的: {ok}/{tot}")
    ok2 = tot2 = 0
    for u in scen_u:
        i = u["id"]
        r = root.get(i)
        if not r or i not in asset_ids:
            continue
        tot2 += 1
        if (u.get("act_st") or 0) + (u.get("sup_st") or 0) == (r.get("act_st") or 0) + (r.get("sup_st") or 0):
            ok2 += 1
    P(f"    资产单位中  『场景战力 == 根表战力』的: {ok2}/{tot2}")

OUT.close()
print("done")
