# -*- coding: utf-8 -*-
"""E102: 里程碑三元组普查（修正解析）+ 战役包定义表 + campaign_doc_dir 定位"""
import os, io, marshal, types, dis, sys, zipfile, re

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
SAVES = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e102_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

# ---------- A. 用 PyYAML 正确解析，做全量普查 ----------
try:
    import yaml
except ImportError:
    yaml = None

def save_list():
    out = []
    for dp, dn, fn in os.walk(SAVES):
        for f in fn:
            if f.endswith(".usg"):
                out.append(os.path.join(dp, f))
    return out

W("=" * 92)
W("[A] 全存档里程碑三元组普查（YAML 精确解析）")
W("=" * 92)
if yaml is None:
    W("  !! 无 yaml 模块")
else:
    tot_root = 0
    ok_sub = 0
    bad = []
    rows = []
    medal_ok = 0
    medal_tot = 0
    for sp in save_list():
        rel = os.path.relpath(sp, SAVES)
        try:
            with zipfile.ZipFile(sp) as z:
                names = set(z.namelist())
                if "main.yml" not in names:
                    continue
                root = yaml.safe_load(z.read("main.yml"))
                if not isinstance(root, dict):
                    continue
                root_ms = root.get("milestones") or []
                if not isinstance(root_ms, list):
                    root_ms = [root_ms]
                cid = root.get("campaign_id")
                d = {}
                if "document/main.yml" in names:
                    d = yaml.safe_load(z.read("document/main.yml")) or {}
                defs = (d.get("milestones") or {}) if isinstance(d, dict) else {}
                medals = []
                if "document/medals.yml" in names:
                    mm = yaml.safe_load(z.read("document/medals.yml")) or []
                    medals = mm if isinstance(mm, list) else []
                tot_root += len(root_ms)
                if set(root_ms) <= set(defs):
                    ok_sub += 1
                else:
                    bad.append((rel, cid, sorted(set(root_ms) - set(defs))))
                # 奖章判定：medal.milestones ⊆ root_ms
                for md in medals:
                    medal_tot += 1
                    need = md.get("milestones") or []
                    if set(need) <= set(root_ms):
                        medal_ok += 1
                rows.append((rel, cid, len(root_ms), len(defs), len(medals),
                             root.get("score"), root.get("prestige")))
        except Exception as e:
            W("  !! %s : %s" % (rel, e))
    W("  可解析存档数: %d" % len(rows))
    W("  根表 milestones 条目总数: %d" % tot_root)
    W("  根表 ⊆ document 定义表: %d / %d" % (ok_sub, len(rows)))
    W("  不满足的: %s" % (bad[:5] if bad else "无"))
    W("  奖章判定 medal.milestones ⊆ 根表: %d / %d" % (medal_ok, medal_tot))
    W("")
    W("  rel | campaign | root条 | 定义条 | 奖章数 | score | prestige")
    for r in rows:
        W("   %-56s %-12s %-5s %-6s %-6s %-7s %s" % (r[0][:56], r[1], r[2], r[3], r[4], r[5], r[6]))

# ---------- B. 战役包里的定义表 ----------
W("")
W("=" * 92)
W("[B] 战役包（_packages/<dlc>/data/campaigns/<id>.usc/main.yml）的 milestones 定义表")
W("=" * 92)
PKGROOT = os.path.join(GAME, "_packages")
for dlc in sorted(os.listdir(PKGROOT)):
    cdir = os.path.join(PKGROOT, dlc, "data", "campaigns")
    if not os.path.isdir(cdir):
        continue
    for camp in sorted(os.listdir(cdir)):
        mp = os.path.join(cdir, camp, "main.yml")
        if not os.path.isfile(mp):
            continue
        if yaml is None: break
        try:
            dd = yaml.safe_load(open(mp, encoding="utf-8")) or {}
        except Exception as e:
            W("   %s/%s  解析失败 %s" % (dlc, camp, e)); continue
        ms = dd.get("milestones")
        if isinstance(ms, dict):
            W("   %-8s %-16s milestones 定义 %3d 项; 顶层键 %d: %s" % (
                dlc, camp, len(ms), len(dd), sorted(dd.keys())[:12]))
        else:
            W("   %-8s %-16s milestones = %r" % (dlc, camp, ms))

# ---------- C. campaign_doc_dir_abs 定位 ----------
W("")
W("=" * 92)
W("[C] 'campaign_doc' 相关名称在全 pyc 的出现（co_names）")
W("=" * 92)
def load(p):
    with open(p, "rb") as f:
        return marshal.loads(f.read()[16:])
def walk(code, prefix=""):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield prefix + c.co_name, c
            for n, cc in walk(c, prefix + c.co_name + "."):
                yield n, cc
for dirpath, dirnames, filenames in os.walk(LIB):
    for fn in sorted(filenames):
        if not fn.endswith(".pyc"): continue
        p = os.path.join(dirpath, fn)
        try: r = load(p)
        except Exception: continue
        rel = os.path.relpath(p, LIB)
        for n, c in walk(r):
            for k in c.co_names:
                if "campaign_doc" in k:
                    W("   %-30s %-44s name=%s" % (rel, n, k))

W("")
W("  --- uoc2/init.pyc 顶层函数 ---")
ip = os.path.join(LIB, "init.pyc")
if os.path.exists(ip):
    ri = load(ip)
    fi = dict(walk(ri))
    for n in fi:
        W("      %s" % n)
    W("  co_names: %s" % (sorted(set(ri.co_names)),))

W("")
W("  --- _Paths.__init__ 完整反汇编（找路径名列表与装饰器） ---")
r = load(os.path.join(LIB, "paths.pyc"))
fp = dict(walk(r))
c = fp.get("_Paths.__init__")
if c:
    for i, x in enumerate(dis.get_instructions(c)):
        a = x.argrepr
        if len(a) > 100: a = a[:100] + "..."
        W("      %-4d %-24s %s" % (i, x.opname, a))

OUT.close()
print("done")
