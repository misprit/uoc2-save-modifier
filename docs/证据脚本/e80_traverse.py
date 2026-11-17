# -*- coding: utf-8 -*-
"""E80: 「每次启动遍历游戏文档 / 更新特种兵库」的精确成本拆解"""
import os, io, time, yaml, json, pickle, hashlib, collections, sys

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e80_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")
def T(label, fn, rep=1):
    t0 = time.perf_counter()
    r = None
    for _ in range(rep):
        r = fn()
    dt = (time.perf_counter() - t0) * 1000 / rep
    W("  %-56s %9.1f ms   %s" % (label, dt, r))
    return dt

# ---------- 收集文件清单 ----------
def collect(roots):
    out = []
    for root in roots:
        for rt, dn, fn in os.walk(root):
            for f in fn:
                p = os.path.join(rt, f)
                if f.endswith((".yml", ".yaml")):
                    out.append(p)
    return out

GAME_ROOTS = [os.path.join(PK, d, "data") for d in sorted(os.listdir(PK))
               if os.path.isdir(os.path.join(PK, d, "data"))]
LOC = os.path.join(PK, "base", "localization")
ALL_YML = collect(GAME_ROOTS) + collect([LOC])
ET = os.path.join(PK, "base", "data", "entity_types")
SPEC = os.path.join(ET, "specialists")
SPEC_YML = sorted(os.path.join(SPEC, f) for f in os.listdir(SPEC) if f.endswith((".yml", ".yaml")))

W("=" * 84)
W("【0】规模")
W("=" * 84)
W("  全游戏包 yml 总数 = %d   (entity_types %d + 战役包 %d + 本地化 %d)" % (
    len(ALL_YML),
    len(collect([ET])),
    len(collect([os.path.join(PK, d, "data", "campaigns") for d in sorted(os.listdir(PK))
                  if os.path.isdir(os.path.join(PK, d, "data", "campaigns"))])),
    len(collect([LOC]))))

W("")
W("=" * 84)
W("【1】「更新特种兵库」的精确成本（这是用户问的那个步骤）")
W("=" * 84)
def parse_specs():
    n = 0
    for p in SPEC_YML:
        try:
            yaml.safe_load(open(p, encoding="utf-8", errors="replace").read()); n += 1
        except Exception:
            pass
    return "%d 个已解析" % n
T("A. 解析 specialists/ 全部 375 个 yml", parse_specs)

def stat_specs():
    out = []
    for p in SPEC_YML:
        st = os.stat(p)
        out.append((p, st.st_mtime_ns, st.st_size))
    return "%d 个条目" % len(out)
T("B. 只 stat（mtime+size），不解析", stat_specs)

def stat_specs_hash():
    out = {}
    for p in SPEC_YML:
        st = os.stat(p)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        out[p] = (st.st_mtime_ns, st.st_size, h)
    return "%d 个条目" % len(out)
T("C. stat + 全文 SHA256", stat_specs_hash)

# 预编译缓存的读取成本
cache = {}
for p in SPEC_YML:
    try:
        cache[os.path.basename(p)] = yaml.safe_load(open(p, encoding="utf-8", errors="replace").read())
    except Exception:
        pass
cj = json.dumps(cache, ensure_ascii=False, sort_keys=True)
cp = pickle.dumps(cache, protocol=4)
W("    （预编译产物大小：JSON %.1f KB / pickle %.1f KB）" % (len(cj) / 1024, len(cp) / 1024))
open(r"D:\MiniMax\_analysis\_e80_specs.json", "w", encoding="utf-8").write(cj)
open(r"D:\MiniMax\_analysis\_e80_specs.pkl", "wb").write(cp)
T("D. 读预编译 JSON 再 json.loads（内置基线的加载成本）",
  lambda: "%d 个" % len(json.loads(open(r"D:\MiniMax\_analysis\_e80_specs.json", encoding="utf-8").read())))
T("E. 读预编译 pickle 再 loads（更快）",
  lambda: "%d 个" % len(pickle.loads(open(r"D:\MiniMax\_analysis\_e80_specs.pkl", "rb").read())))

W("")
W("=" * 84)
W("【2】「遍历游戏文档」的全量成本（所有包 + entity_types + 本地化）")
W("=" * 84)
def walk_all():
    n = 0
    for root in GAME_ROOTS + [LOC]:
        for rt, dn, fn in os.walk(root):
            n += len(fn)
    return "%d 个文件" % n
T("F. os.walk 全部（只列目录，不 stat 不解析）", walk_all)

def stat_all():
    n = 0
    for p in ALL_YML:
        st = os.stat(p); n += 1
    return "%d 个 yml 已 stat" % n
T("G. stat 全部 yml（不解析）", stat_all)

def parse_all():
    n = 0
    for p in ALL_YML:
        try:
            yaml.safe_load(open(p, encoding="utf-8", errors="replace").read()); n += 1
        except Exception:
            pass
    return "%d 个已解析" % n
T("H. ★ 全量 YAML 解析（这就是「每次遍历游戏文档」）", parse_all)

W("")
W("=" * 84)
W("【3】增量模式：stat 全部 + 只解析「变了」的文件")
W("=" * 84)
# 模拟：上次扫描的快照
snap = {p: (os.stat(p).st_mtime_ns, os.stat(p).st_size) for p in ALL_YML}
W("  基线快照: %d 个条目" % len(snap))
def incr_scan():
    changed = []
    seen = set()
    for p in ALL_YML:
        seen.add(p)
        st = os.stat(p)
        if snap.get(p) != (st.st_mtime_ns, st.st_size):
            changed.append(p)
    for p in snap:
        if p not in seen:
            changed.append(p)
    return "%d 个变化, %d 个未变" % (len(changed), len(ALL_YML) - len(changed))
T("I. 增量扫描（stat + 比对快照，不解析）", incr_scan)

def incr_parse():
    changed = []
    for p in ALL_YML:
        st = os.stat(p)
        if snap.get(p) != (st.st_mtime_ns, st.st_size):
            changed.append(p)
    n = 0
    for p in changed:
        try:
            yaml.safe_load(open(p, encoding="utf-8", errors="replace").read()); n += 1
        except Exception:
            pass
    return "%d 个变化并解析" % n
T("J. ★ 增量扫描 + 只解析变化的文件", incr_parse)

W("")
W("=" * 84)
W("【4】把「变更检测」从 mtime 换成「目录树指纹」的代价")
W("=" * 84)
def tree_fingerprint():
    h = hashlib.sha256()
    for root in sorted(GAME_ROOTS) + [LOC]:
        for rt, dn, fn in os.walk(root):
            dn.sort()
            for f in sorted(fn):
                p = os.path.join(rt, f)
                st = os.stat(p)
                h.update(("%s|%d|%d\n" % (p, st.st_mtime_ns, st.st_size)).encode())
    return h.hexdigest()[:16]
T("K. 全部文件的 (path,mtime,size) 指纹", tree_fingerprint)

W("")
W("=" * 84)
W("【5】对照：读一个存档本身要多少")
W("=" * 84)
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
import zipfile
def read_save():
    p = os.path.join(G, r"campaigns\Stalingrad.usg")
    c = 0
    with zipfile.ZipFile(p) as zf:
        for n in zf.namelist():
            if n.endswith(".yml") and n.count("/") <= 1:
                yaml.safe_load(zf.read(n)); c += 1
    return "%d 个根 yml" % c
T("L. 解 ZIP + 解析根 yml（打开一个存档）", read_save)
OUT.close()
print("done")
