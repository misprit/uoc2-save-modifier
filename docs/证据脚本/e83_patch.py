# -*- coding: utf-8 -*-
"""E83: .patch.yml 与 addable 机制在磁盘上的实际存在情况 + 完整 get_yml 逻辑"""
import os, io, marshal, types, dis, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
LIB = os.path.join(GAME, "lib", "uoc2")
UP = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e83_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

W("=" * 80)
W("【1】磁盘上有没有 .patch.yml 文件？有没有 addable 目录？")
W("=" * 80)
for label, root in [("游戏包", PK), ("用户包", UP)]:
    pat = []
    add = []
    for rt, dn, fn in os.walk(root):
        for f in fn:
            if f.endswith(".patch.yml"):
                pat.append(os.path.join(rt, f))
        for d in dn:
            if d == "addable":
                add.append(os.path.join(rt, d))
    W("  %s: .patch.yml 文件 %d 个; addable 目录 %d 个" % (label, len(pat), len(add)))
    for p in pat[:5]:
        W("      %s" % p)
    for p in add[:5]:
        W("      %s" % p)

W("")
W("=" * 80)
W("【2】完整 get_yml 逻辑（.patch.yml 分支）")
W("=" * 80)
def load(p):
    with open(p, "rb") as f:
        return marshal.loads(f.read()[16:])
def walk(code, prefix=""):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield prefix + c.co_name, c
            for n, cc in walk(c, prefix + c.co_name + "."):
                yield n, cc

root = load(os.path.join(LIB, "paths.pyc"))
for n, c in walk(root):
    if c.co_name == "get_yml":
        for i, x in enumerate(dis.get_instructions(c)):
            W("      %-26s %s" % (x.opname, x.argrepr))
        break

W("")
W("=" * 80)
W("【3】_packages 的构造顺序（谁覆盖谁）")
W("=" * 80)
for n, c in walk(root):
    if c.co_name == "_build_package_list":
        ins = list(dis.get_instructions(c))
        for i, x in enumerate(ins):
            W("      %-26s %s" % (x.opname, x.argrepr))
        break

W("")
W("=" * 80)
W("【4】实跑：get_yml 的真实行为（用游戏自己的 paths 实例）")
W("=" * 80)
import sys
sys.frozen = True
sys.executable = os.path.join(GAME, "uoc2.exe")
import numpy, yaml
sys.path.append(os.path.join(GAME, "lib"))
import importlib
paths = importlib.import_module("uoc2.paths")
p = paths.init_paths()
try:
    W("  _packages 顺序（按加载优先级）:")
    for i, pk in enumerate(p._packages):
        W("      %2d. %s" % (i, pk))
except Exception as e:
    W("  ERR %s" % e)
for rel in [r"data/campaigns/stalingrad.usc/scenarios/fall_blau_2/units.yml",
            r"data/campaigns/stalingrad.usc/scenarios/fall_blau_2/main.yml",
            r"data/entity_types/specialists/ger_eng_39.yml"]:
    try:
        W("  get_yml(%s) -> %s" % (rel, p.get_yml(rel)))
    except Exception as e:
        W("  get_yml(%s) ERR %s" % (rel, e))
OUT.close()
print("done")
