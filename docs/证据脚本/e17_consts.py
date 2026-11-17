# -*- coding: utf-8 -*-
"""E17: tot_st / exp / unit_exp_step_loss_* 常量 + 登陆场景数据普查"""
import os, io, marshal, dis, types, zipfile, yaml, collections

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e17_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=70):
    P(f"  --- {label}  (line={code_obj.co_firstlineno})")
    buf = io.StringIO(); dis.dis(code_obj, file=buf, depth=0)
    for l in buf.getvalue().split("\n")[:maxlines]:
        P("      " + l)

P("=" * 100); P("[A] tot_st / tot_specs / exp 属性"); P("=" * 100)
uc = load("uoc2\\state\\entities\\unit.pyc")
for path, fn, ln in walk_all(uc):
    if fn.co_name in ("tot_st", "tot_specs", "exp", "tot_act"):
        dump(path, fn, 45)
        P("")

P("=" * 100); P("[B] unit_exp_step_loss_standard / elite 的取值"); P("=" * 100)
for dirpath, _, files in os.walk(LIB):
    for f in files:
        if not f.endswith(".pyc"):
            continue
        fp = os.path.join(dirpath, f)
        try:
            c = marshal.loads(open(fp, "rb").read()[16:])
        except Exception:
            continue
        for path, fn, ln in walk_all(c):
            names = list(fn.co_names)
            if "unit_exp_step_loss_standard" in names:
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln}")
                consts = [x for x in fn.co_consts if isinstance(x, (int, float))]
                P(f"      数字常量: {consts}")
                buf = io.StringIO(); dis.dis(fn, file=buf, depth=0)
                txt = buf.getvalue().split("\n")
                for i, l in enumerate(txt):
                    if "unit_exp_step_loss" in l:
                        for x in txt[max(0, i-4):i+8]:
                            P("          " + x)
                        P("")

# ---------------------------------------------------------------
P(""); P("=" * 100); P("[C] 存档 document/ 里各场景的 prepositioned_assets 普查"); P("=" * 100)

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

p = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(p) as zf:
    names = zf.namelist()
    scen_files = sorted({n.split("/")[2] for n in names
                         if n.startswith("document/scenarios/") and n.count("/") >= 3
                         and n.split("/")[2] != ""})
    P(f"  Stalingrad.usg 内场景数 = {len(scen_files)}")
    kinds = collections.Counter()
    rows = []
    for s in scen_files:
        ppa = zl(zf, f"document/scenarios/{s}/prepositioned_assets.yml")
        enr = zl(zf, f"document/scenarios/{s}/enroute_units.yml")
        if ppa is None and enr is None:
            continue
        types_ = collections.Counter()
        emb = []
        if ppa:
            for a in ppa:
                types_[a.get("type")] += 1
                u = a.get("unit") or {}
                if a.get("type") != "bb" and u.get("id"):
                    emb.append((a.get("id"), a.get("type"), u.get("id"),
                                (u.get("act_st") or 0) + (u.get("sup_st") or 0),
                                [sp.get("type") for sp in (u.get("specs") or [])]))
        kinds.update(types_)
        rows.append((s, dict(types_), len(enr) if enr else 0, emb))
    P(f"  资产类型总计: {dict(kinds)}")
    P(f"  含资产或增援的场景 {len(rows)} 个:")
    for s, tc, nenr, emb in rows:
        if tc and tc.get("bb", 0) == len(tc) and not emb:
            continue
        P(f"    {s:26s} 资产={tc}  增援={nenr}")
        for e in emb:
            P(f"        ppa id={e[0]} type={e[1]} unit={e[2]} target_steps={e[3]} specs={e[4]}")

OUT.close()
print("done")
