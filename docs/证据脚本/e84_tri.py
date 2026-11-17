# -*- coding: utf-8 -*-
"""E84: 证明 mod 确实覆盖了原版场景（base vs mod vs save 三方），并跑通包优先级"""
import os, io, zipfile, hashlib, sys, importlib

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
MOD = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "_packages", "fall_blau_2")
MODSCEN = os.path.join(MOD, "data", "scenarios", "fall_blau_2.usc", "scenarios", "fall_blau_2")
BASESCEN = os.path.join(PK, "dlc4", "data", "campaigns", "stalingrad.usc", "scenarios", "fall_blau_2")
SAV = os.path.join(G, r"campaigns\Stalingrad.usg")
OUT = io.open(r"D:\MiniMax\_analysis\e84_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")
def sha(b):
    return hashlib.sha256(b).hexdigest()[:12]

W("=" * 84)
W("【1】★ base vs mod vs save 三方比对 —— mod 到底改了什么")
W("=" * 84)
files = sorted(set(os.listdir(MODSCEN)) | set(os.listdir(BASESCEN)) - {"variants"})
files = [f for f in files if f != "variants"]
with zipfile.ZipFile(SAV) as zf:
    names = set(zf.namelist())
    W("  %-24s %-12s %-12s %-12s %s" % ("文件", "base", "mod", "save", "结论"))
    for f in files:
        bp = os.path.join(BASESCEN, f)
        mp = os.path.join(MODSCEN, f)
        sp = "document/scenarios/fall_blau_2/%s" % f
        b = open(bp, "rb").read() if os.path.isfile(bp) else None
        m = open(mp, "rb").read() if os.path.isfile(mp) else None
        s = zf.read(sp) if sp in names else None
        tag = []
        if m is not None and b is not None:
            tag.append("mod==base" if m == b else "★mod≠base")
        if s is not None and m is not None:
            tag.append("save==mod" if s == m else "★save≠mod")
        if s is not None and b is not None:
            tag.append("save==base" if s == b else "★save≠base")
        W("  %-24s %-12s %-12s %-12s %s" % (
            f, sha(b) if b else "-", sha(m) if m else "-", sha(s) if s else "-", " | ".join(tag)))
    W("")
    W("  variants/rossosh/ 里 base 与 mod 的差异:")
    bv = os.path.join(BASESCEN, "variants", "rossosh")
    mv = os.path.join(MODSCEN, "variants", "rossosh")
    for f in sorted(set(os.listdir(bv)) | set(os.listdir(mv))):
        bp = os.path.join(bv, f); mp = os.path.join(mv, f)
        b = open(bp, "rb").read() if os.path.isfile(bp) else None
        m = open(mp, "rb").read() if os.path.isfile(mp) else None
        s = zf.read("document/scenarios/fall_blau_2/variants/rossosh/%s" % f) \
            if "document/scenarios/fall_blau_2/variants/rossosh/%s" % f in names else None
        W("    %-22s base=%s mod=%s save=%s  %s" % (
            f, sha(b) if b else "-", sha(m) if m else "-", sha(s) if s else "-",
            ("★mod≠base" if (m and b and m != b) else "") + (" | save==mod" if (s and m and s == m) else "")))

W("")
W("=" * 84)
W("【2】游戏自己的包加载顺序（init_packages 之后）")
W("=" * 84)
sys.frozen = True
sys.executable = os.path.join(GAME, "uoc2.exe")
import numpy, yaml
sys.path.append(os.path.join(GAME, "lib"))
paths = importlib.import_module("uoc2.paths")
p = paths.init_paths()
try:
    p.init_packages()
except Exception as e:
    W("  init_packages ERR %s" % e)
W("  _packages（按优先级，先命中先生效）:")
for i, pk in enumerate(getattr(p, "_packages", []) or []):
    W("      %2d. %s" % (i, pk))
W("  all_package_dirs  = %s" % p.all_package_dirs())
W("  get_editable_packages = %s" % p.get_editable_packages())
for rel in [r"data/campaigns/stalingrad.usc/scenarios/fall_blau_2/units.yml",
            r"data/campaigns/stalingrad.usc/scenarios/fall_blau_2/main.yml",
            r"data/entity_types/specialists/ger_eng_39.yml"]:
    try:
        W("  get_yml(%s) -> %s" % (rel, p.get_yml(rel)))
    except Exception as e:
        W("  get_yml(%s) ERR %s" % (rel, e))
OUT.close()
print("done")
