# -*- coding: utf-8 -*-
"""E100: paths.campaign_doc_dir_abs 定位 + 里程碑定义来源（包 vs 存档）"""
import os, io, marshal, types, dis, sys

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e100_out.txt", "w", encoding="utf-8")
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

# ---- 1. paths.pyc 模块级结构
W("=" * 92)
W("[1] paths.pyc 模块级结构（类、基类、函数名全集）")
W("=" * 92)
r = load(os.path.join(LIB, "paths.pyc"))
W("  co_names: %s" % (sorted(set(r.co_names)),))
W("")
funcs = dict(walk(r))
for n, c in funcs.items():
    if c.co_name in ("_Paths", "__init__", "_addable_path_decorator", "_build_package_list"):
        W("  === %s ===" % n)
        W("      常量: %s" % ([x for x in c.co_consts if not isinstance(x, types.CodeType)],))
        W("      局部: %s" % (c.co_varnames,))

# ---- 2. 所有 pyc 中出现 'campaign_doc' 的字符串常量
W("")
W("=" * 92)
W("[2] 全 pyc: 字符串常量里含 'campaign_doc' 的")
W("=" * 92)
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: rr = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(rr):
            for k in c.co_consts:
                if isinstance(k, str) and "campaign_doc" in k:
                    W("  %-30s %-40s %r" % (rel, n, k))

# ---- 3. 实跑 paths.campaign_doc_dir_abs
W("")
W("=" * 92)
W("[3] 实跑 paths.init_paths() -> campaign_doc_dir_abs('west.usc') 等")
W("=" * 92)
try:
    import numpy, yaml  # noqa
    sys.frozen = True
    sys.executable = os.path.join(GAME, "uoc2.exe")
    sys.path.append(os.path.join(GAME, "lib"))
    import importlib
    paths = importlib.import_module("uoc2.paths")
    inst = paths.init_paths()
    W("  all_package_dirs: %s" % (inst.all_package_dirs(),))
    W("  game_packages: %s" % (getattr(inst, "game_packages", "N/A"),))
    for nm in ("campaign_doc_dir_abs", "campaign_dir", "addable_dir"):
        fn = getattr(inst, nm, None)
        W("  hasattr %s -> %s" % (nm, fn))
    for cn in ("west", "stalingrad"):
        try:
            W("  campaign_doc_dir_abs(%r) = %r" % (cn + ".usc", inst.campaign_doc_dir_abs(cn + ".usc")))
        except Exception as e:
            W("  campaign_doc_dir_abs(%r) ERR %s" % (cn + ".usc", e))
    for cn in ("west", "stalingrad"):
        try:
            W("  addable_dir(%r) = %r" % (cn, inst.addable_dir(cn)))
        except Exception as e:
            W("  addable_dir(%r) ERR %s" % (cn, e))
except Exception as e:
    W("  运行失败: %r" % (e,))

# ---- 4. 存档根 main.yml 的 milestones 实测样本
W("")
W("=" * 92)
W("[4] 存档根 main.yml 的 milestones 字段实测")
W("=" * 92)
import zipfile, re
SAVES = r"C:\Users\misprit\AppData\Local\.uoc2\save"
def find_saves():
    out = []
    for dp, dn, fn in os.walk(SAVES):
        for f in fn:
            if f.endswith(".usg"):
                out.append(os.path.join(dp, f))
    return out
cnt = 0
for sp in find_saves():
    try:
        with zipfile.ZipFile(sp) as z:
            names = z.namelist()
            for nm in names:
                if nm == "main.yml" or nm.endswith("/main.yml"):
                    raw = z.read(nm).decode("utf-8", "replace")
                    m = re.search(r"^milestones:.*?(?=^\S|\Z)", raw, re.S | re.M)
                    if m:
                        seg = m.group(0)
                        lst = re.findall(r"-\s*(\S+)", seg)
                        W("  %-46s %-14s milestones=%d %s" % (
                            os.path.basename(sp)[:46], nm, len(lst), lst[:6]))
                        cnt += 1
    except Exception:
        pass
    if cnt >= 25: break

OUT.close()
print("done")
