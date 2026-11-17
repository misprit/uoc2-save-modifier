# -*- coding: utf-8 -*-
"""E107: 「直接写明文」能否正确显示 —— 本地化回退行为 + 存档里是否已有明文名"""
import os, io, marshal, types, dis, zipfile, re, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib")
SAVES = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e107_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

def load(p):
    with open(p, "rb") as f:
        return marshal.loads(f.read()[16:])
def walk(code, prefix=""):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield prefix + c.co_name, c
            for n, cc in walk(c, prefix + c.co_name + "."):
                yield n, cc
def dump(c, lim=200):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 100: a = a[:100] + "..."
        W("      %-24s %s" % (x.opname, a))
def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

# ============ A. tools/localization.pyc 的 get() 回退 ============
W("=" * 92)
W("[A] tools/localization.pyc —— 本地化查找与缺 key 回退")
W("=" * 92)
p = os.path.join(LIB, "tools", "localization.pyc")
if os.path.exists(p):
    r = load(p)
    funcs = dict(walk(r))
    W("  全部函数: %s" % (list(funcs.keys()),))
    for nm in funcs:
        if nm in ("LocalizationManager", "LocalizationManager.get", "get", "Localization",
                  "LocalizationManager.load", "LocalizationManager._get"):
            c = funcs[nm]
            W("")
            W("  === %s ===" % nm)
            W("  常量: %s" % (consts(c)[:26],))
            W("  局部: %s" % (c.co_varnames,))
            dump(c, 160)
else:
    W("  !! 不存在 %s" % p)

# ============ B. 存档里是否已有明文 name_brief ============
W("")
W("=" * 92)
W("[B] 70 存档普查：根 units.yml / 名册 units.yml 里的 name_brief 是否已有明文")
W("=" * 92)
import yaml
plain_roots = []
plain_rosters = []
total_units = 0
plain_units = 0
samples = []
def save_list():
    out = []
    for dp, dn, fn in os.walk(SAVES):
        for f in fn:
            if f.endswith(".usg"):
                out.append(os.path.join(dp, f))
    return out

for sp in save_list():
    rel = os.path.relpath(sp, SAVES)
    try:
        with zipfile.ZipFile(sp) as z:
            names = set(z.namelist())
            for nm, tag in (("units.yml", "root"), ("document/units.yml", "roster")):
                if nm not in names:
                    continue
                d = yaml.safe_load(z.read(nm)) or []
                if not isinstance(d, list):
                    continue
                for u in d:
                    if not isinstance(u, dict):
                        continue
                    nb = u.get("name_brief")
                    if nb is None:
                        continue
                    total_units += 1
                    if isinstance(nb, str) and not nb.startswith("id_"):
                        plain_units += 1
                        if len(samples) < 25:
                            samples.append((rel, tag, u.get("id"), nb))
    except Exception:
        pass

W("  根表+名册 单位条目总数: %d" % total_units)
W("  其中 name_brief 不是 id_ 开头的（疑似明文）: %d" % plain_units)
W("  样本:")
for s in samples:
    W("    %-42s %-7s id=%-5s %r" % s)

# ============ C. name_brief 在 schema 里的约束 ============
W("")
W("=" * 92)
W("[C] name_brief 的 schema 约束（doc_units_schema / campaign_unit_schema）")
W("=" * 92)
for rel in ("uoc2/state/campaign/campaign_data_validation.pyc",
            "uoc2/state/entities/data_validation/unit.pyc"):
    p = os.path.join(LIB, rel.replace("/", os.sep))
    if not os.path.exists(p):
        W("  缺 %s" % rel); continue
    r = load(p)
    funcs = dict(walk(r))
    for nm, c in funcs.items():
        if "name_brief" in c.co_names or any(
                isinstance(k, str) and "name_brief" in k for k in c.co_consts):
            W("")
            W("  === %s :: %s ===" % (rel, nm))
            ins = list(dis.get_instructions(c))
            for i, x in enumerate(ins):
                if "name_brief" in x.argrepr:
                    for j in range(max(0, i - 4), min(len(ins), i + 8)):
                        a = ins[j].argrepr
                        if len(a) > 90: a = a[:90] + "..."
                        W("        %-22s %s" % (ins[j].opname, a))
                    W("        ---")

OUT.close()
print("done")
