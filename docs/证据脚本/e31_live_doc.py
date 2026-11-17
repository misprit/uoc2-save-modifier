# -*- coding: utf-8 -*-
"""E31: 存档里的 document/ 是不是运行时活的战役文档？"""
import os, io, zipfile, yaml, marshal, dis, types

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
PKG = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\data\campaigns\west.usc"
LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e31_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

# --- 1) 存档 document/units.yml  vs  游戏包 west.usc/units.yml ---
P("=" * 100); P("[A] 存档里的 document/units.yml 与游戏包对比"); P("=" * 100)
pkg_path = os.path.join(PKG, "units.yml")
P(f"  游戏包存在: {os.path.isfile(pkg_path)}")
pkg_units = yaml.safe_load(open(pkg_path, encoding="utf-8")) or []
pkg_ids = {u["id"] for u in pkg_units}
P(f"  游戏包 west.usc/units.yml: {len(pkg_units)} 个, id 范围 {min(pkg_ids)}..{max(pkg_ids)}")

p = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(p) as zf:
    save_units = zl(zf, "document/units.yml") or []
    save_ids = {u["id"] for u in save_units}
    P(f"  存档 Stalingrad.usg 的 document/units.yml: {len(save_units)} 个, id 范围 {min(save_ids)}..{max(save_ids)}")
    P(f"  仅在存档里的 id: {sorted(save_ids - pkg_ids)}")
    P(f"  仅在游戏包里的 id: {sorted(pkg_ids - save_ids)[:20]}")
    # 同一 id 的 type 是否一致
    pkgmap = {u["id"]: u for u in pkg_units}
    diff = [(u["id"], pkgmap.get(u["id"], {}).get("type"), u.get("type"))
            for u in save_units if u["id"] in pkgmap and pkgmap[u["id"]].get("type") != u.get("type")]
    P(f"  同一 id 但 type 不同的: {len(diff)} 个 -> {diff[:8]}")
    # 存档 document/ 与游戏包的文件差异总数
    names = [n for n in zf.namelist() if n.startswith("document/")]
    P(f"  存档 document/ 条目数: {len(names)}")

# --- 2) 谁构造 Campaign / CampaignDoc（读档路径）---
P(""); P("=" * 100); P("[B] 读档时 CampaignDoc 从哪来"); P("=" * 100)

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

for dirpath, _, files in os.walk(os.path.join(LIB, "uoc2")):
    for f in files:
        if not f.endswith(".pyc"):
            continue
        fp = os.path.join(dirpath, f)
        try:
            c = load(os.path.relpath(fp, LIB))
        except Exception:
            continue
        for path, fn, ln in walk_all(c):
            names = list(fn.co_names)
            strs = [s for s in fn.co_consts if isinstance(s, str)]
            if "Campaign" in names and ("load_yaml" in names or "read_serialization" in names
                                         or "CampaignDoc" in names):
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln}")
                P(f"      names: {names[:20]}")
                P(f"      strings: {[s for s in strs if len(s)<50][:14]}")

OUT.close()
print("done")
