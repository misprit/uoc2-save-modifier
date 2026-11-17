# -*- coding: utf-8 -*-
"""E101: 里程碑普查 —— 根表 achievements vs document 定义表 vs medals；
   并定位 app.paths.campaign_doc_dir_abs"""
import os, io, marshal, types, dis, sys, zipfile, re, json

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
SAVES = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e101_out.txt", "w", encoding="utf-8")
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

def dump(c, lim=260):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 88: a = a[:88] + "..."
        W("      %-24s %s" % (x.opname, a))

# ============ A. 普查 ============
W("=" * 92)
W("[A] 全存档普查：根 main.yml.milestones vs document/main.yml.milestones vs document/medals.yml")
W("=" * 92)
def save_list():
    out = []
    for dp, dn, fn in os.walk(SAVES):
        for f in fn:
            if f.endswith(".usg"):
                out.append(os.path.join(dp, f))
    return out

def inl(text, key):
    """取 'key: [a, b, c]' 内联列表；若无则取块列表"""
    m = re.search(r"^%s:\s*\[(.*?)\]\s*$" % re.escape(key), text, re.M)
    if m:
        raw = m.group(1).strip()
        if not raw:
            return []
        return [x.strip().strip("'\"") for x in raw.split(",") if x.strip()]
    m = re.search(r"^%s:\s*$((?:\n[ \t]*-.*)*)" % re.escape(key), text, re.M)
    if m:
        return re.findall(r"-\s*(\S+)", m.group(1))
    m = re.search(r"^%s:\s*(\S+)\s*$" % re.escape(key), text, re.M)
    if m:
        return [m.group(1)]
    return None

rows = []
tot_root = 0
tot_def = 0
subset_ok = 0
subset_bad = []
for sp in save_list():
    rel = os.path.relpath(sp, SAVES)
    try:
        with zipfile.ZipFile(sp) as z:
            names = set(z.namelist())
            if "main.yml" not in names:
                continue
            root = z.read("main.yml").decode("utf-8", "replace")
            got = inl(root, "milestones")
            root_ms = got if got is not None else []
            got2 = inl(root, "campaign_id")
            cid = got2[0] if got2 else "?"
            defs = None
            dpath = None
            for cand in ("document/main.yml",):
                if cand in names:
                    dpath = cand
                    dt = z.read(cand).decode("utf-8", "replace")
                    dd = inl(dt, "milestones")
                    defs = dd if dd is not None else []
                    break
            medals = None
            if "document/medals.yml" in names:
                mt = z.read("document/medals.yml").decode("utf-8", "replace")
                medals = mt
            rows.append((rel, cid, root_ms, defs, (medals[:400] if medals else None)))
            tot_root += len(root_ms)
            tot_def += len(defs or [])
            if defs is not None and set(root_ms) <= set(defs):
                subset_ok += 1
            else:
                subset_bad.append((rel, cid, sorted(set(root_ms) - set(set(defs or [])))))
    except Exception as e:
        W("  !! %s : %s" % (rel, e))

W("  存档数（可解析）: %d" % len(rows))
W("  根表 milestones 条目总数: %d" % tot_root)
W("  document 定义表条数合计: %d" % tot_def)
W("  根表 ⊆ 定义表 的存档数: %d / %d" % (subset_ok, len(rows)))
if subset_bad:
    W("  !! 不满足子集关系的存档:")
    for r in subset_bad[:10]:
        W("       %s (%s) 多出: %s" % r)
W("")
W("  逐存档（campaign_id / 根表条数 / 定义表条数 / 根表内容）:")
for rel, cid, rms, defs, med in rows:
    W("   %-58s %-12s root=%-3d def=%-4s %s" % (
        rel[:58], cid, len(rms), ("%d" % len(defs)) if defs is not None else "-",
        (",".join(rms[:8]) + ("..." if len(rms) > 8 else ""))))

# 奖章样本
W("")
W("  --- document/medals.yml 样本 ---")
for rel, cid, rms, defs, med in rows:
    if med:
        W("   === %s (%s) ===" % (rel, cid))
        W("   " + med.replace("\n", "\n   "))
        break

# ============ B. campaign_doc_dir_abs 定位 ============
W("")
W("=" * 92)
W("[B] app.paths.campaign_doc_dir_abs 定位")
W("=" * 92)
r = load(os.path.join(LIB, "paths.pyc"))
funcs = dict(walk(r))
c = funcs.get("_Paths.__init__")
if c:
    ins = list(dis.get_instructions(c))
    for i, x in enumerate(ins):
        if "campaign_doc" in x.argrepr or "addable_path" in x.argrepr:
            W("  [%d] %-22s %s" % (i, x.opname, x.argrepr[:80]))
W("")
W("  --- _Paths.__init__ 中与 path 列表相关的片段 ---")
for i, x in enumerate(ins):
    if x.opname == "BUILD_LIST" or x.opname == "LOAD_CONST" and isinstance(x.argval, tuple) and any(
            isinstance(v, str) and "campaign" in v for v in x.argval):
        W("  [%d] %-22s %s" % (i, x.opname, x.argrepr[:120]))

# globals.pyc
W("")
W("  --- globals.pyc ---")
gp = os.path.join(LIB, "globals.pyc")
if os.path.exists(gp):
    rg = load(gp)
    fg = dict(walk(rg))
    for n, cc in fg.items():
        W("      %s" % n)
    W("  module co_names: %s" % (sorted(set(rg.co_names)),))

# 实跑 dir()
W("")
W("  --- 实跑 dir(paths) 含 campaign 的属性 ---")
try:
    import numpy, yaml  # noqa
    sys.frozen = True
    sys.executable = os.path.join(GAME, "uoc2.exe")
    sys.path.append(os.path.join(GAME, "lib"))
    import importlib
    pm = importlib.import_module("uoc2.paths")
    inst = pm.init_paths()
    W("     %s" % [a for a in dir(inst) if "campaign" in a.lower()])
    W("  addable_paths: %s" % (getattr(inst, "_addable_paths", "N/A"),))
    W("  addables keys: %s" % (list(getattr(inst, "_addables", {}).keys())[:30],))
except Exception as e:
    W("  运行失败: %r" % (e,))

OUT.close()
print("done")
