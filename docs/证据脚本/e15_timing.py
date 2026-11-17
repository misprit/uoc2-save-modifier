# -*- coding: utf-8 -*-
"""E15: 调用时机 / apply_recovery 语义 / tot_st 定义 / pp_assets 来源"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e15_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=200):
    P(f"  --- {label}  (line={code_obj.co_firstlineno})")
    buf = io.StringIO()
    dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)

# 1) 谁调用 adjust_units_between_situations / campaign_agree_on_unit
P("=" * 100); P("[A] adjust_units_between_situations 的调用者（全 lib 扫描）"); P("=" * 100)
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
            if "adjust_units_between_situations" in fn.co_names or "adjust_units_between_situations" in fn.co_consts:
                P(f"  {os.path.relpath(fp, LIB)} :: {path}  line={ln}  args={fn.co_varnames[:fn.co_argcount]}")
                P(f"      names: {[n for n in fn.co_names if 'adjust' in n or 'unit' in n.lower()][:15]}")
                P(f"      strings: {[s for s in fn.co_consts if isinstance(s,str) and len(s)<60][:12]}")

# 2) Game.new 里调用点
P(""); P("=" * 100); P("[B] Game.new 中调用点附近"); P("=" * 100)
gc = load("uoc2\\state\\game\\game.pyc")
for path, fn, ln in walk_all(gc):
    if fn.co_name == "new":
        buf = io.StringIO(); dis.dis(fn, file=buf, depth=0)
        txt = buf.getvalue().split("\n")
        for i, l in enumerate(txt):
            if "adjust_units" in l or "adjust_units" in str(txt[max(0,i-12):i+2]):
                P(f"    --- {path} line={ln} 片段:")
                for x in txt[max(0,i-14):i+6]:
                    P("        " + x)
                P("")

# 3) apply_recovery_steps / apply_recovery_specs / tot_st / deploy_calc_xp
P("=" * 100); P("[C] unit.pyc: apply_recovery_steps / apply_recovery_specs / tot_st / deploy_calc_xp"); P("=" * 100)
uc = load("uoc2\\state\\entities\\unit.pyc")
for path, fn, ln in walk_all(uc):
    if fn.co_name in ("apply_recovery_steps", "apply_recovery_specs", "deploy_calc_xp"):
        dump(path, fn, 120)
        P("")
for path, fn, ln in walk_all(uc):
    if fn.co_name == "tot_st":
        P(f"  --- tot_st  property  line={ln}")
        buf = io.StringIO(); dis.dis(fn, file=buf, depth=0)
        for l in buf.getvalue().split("\n")[:40]:
            P("      " + l)

# 4) pp_assets 从哪来
P(""); P("=" * 100); P("[D] pp_assets / prepositioned_assets.yml 的来源"); P("=" * 100)
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
            strs = [s for s in fn.co_consts if isinstance(s, str)]
            if any("prepositioned_assets" in s for s in strs) or "pp_assets" in fn.co_names:
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln}")
                P(f"      names: {[n for n in fn.co_names if 'pp' in n or 'asset' in n.lower()][:12]}")
                P(f"      strings: {[s for s in strs if len(s)<60][:12]}")

OUT.close()
print("done")
