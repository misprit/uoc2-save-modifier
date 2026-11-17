# -*- coding: utf-8 -*-
"""E18: 登陆/空降场景的实证 —— 根表里的单位是否已被初始化重组"""
import os, io, marshal, dis, types, zipfile, yaml, collections

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e18_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

# ---------- 1) 找 tot_st 与常量值 ----------
def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

P("=" * 100); P("[A] tot_st 的定义位置（全 uoc2 搜索）"); P("=" * 100)
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
            if fn.co_name in ("tot_st", "tot_specs", "exp"):
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln}")
                buf = io.StringIO(); dis.dis(fn, file=buf, depth=0)
                for l in buf.getvalue().split("\n")[:30]:
                    P("      " + l)

P(""); P("=" * 100); P("[B] unit_exp_step_loss_* 的数值来源"); P("=" * 100)
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
            if "unit_exp_step_loss_standard" in fn.co_names and \
               any(isinstance(x, (int, float)) for x in fn.co_consts):
                nums = [x for x in fn.co_consts if isinstance(x, (int, float))]
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln} 数字常量={nums}")

# ---------- 2) 实证 ----------
P(""); P("=" * 100); P("[C] 70 个存档：当前战斗场景是否含 lci/para_plane，根表值 vs 场景目标"); P("=" * 100)

saves = []
for dirpath, _, files in os.walk(G):
    for f in files:
        if f.lower().endswith(".usg"):
            saves.append(os.path.join(dirpath, f))
saves.sort()

hit = 0
for p in saves:
    rel = os.path.relpath(p, G)
    try:
        zf = zipfile.ZipFile(p)
    except Exception:
        continue
    names = zf.namelist()
    m = zl(zf, "main.yml") or {}
    scen = ((m.get("in_state") or {}).get("scenario"))
    if not scen:
        zf.close(); continue
    ppa = zl(zf, f"document/scenarios/{scen}/prepositioned_assets.yml")
    if not ppa:
        zf.close(); continue
    emb = [(a.get("id"), a.get("type"), (a.get("unit") or {})) for a in ppa
           if a.get("type") != "bb" and (a.get("unit") or {}).get("id")]
    if not emb:
        zf.close(); continue
    root = zl(zf, "units.yml") or []
    rootmap = {u["id"]: u for u in root}
    enr = zl(zf, f"document/scenarios/{scen}/enroute_units.yml") or []
    enr_ids = [(e.get("on_turn"), (e.get("unit") or {}).get("id")) for e in enr]
    P("")
    P(f"### {rel}   scenario={scen}")
    P(f"    场景资产携带单位: {[(e[0], e[1], e[2].get('id')) for e in emb]}")
    P(f"    场景增援 (on_turn, id): {enr_ids[:12]}{' ...' if len(enr_ids)>12 else ''}")
    for pid, ptype, u in emb:
        uid = u.get("id")
        tgt_steps = (u.get("act_st") or 0) + (u.get("sup_st") or 0)
        tgt_specs = [s.get("type") for s in (u.get("specs") or [])]
        r = rootmap.get(uid)
        if r is None:
            P(f"    [资产{pid} {ptype}] unit {uid}: 根表【不存在】")
            continue
        P(f"    [资产{pid} {ptype}] unit {uid}: 目标 steps={tgt_steps} specs={tgt_specs}")
        P(f"        根表实际: act_st={r.get('act_st')} sup_st={r.get('sup_st')} "
          f"xp={r.get('xp')} kia={r.get('kia')} specs={[s.get('type') for s in (r.get('specs') or [])]}")
    hit += 1
zf.close()
P("")
P(f"命中存档数 = {hit}")

OUT.close()
print("done")
