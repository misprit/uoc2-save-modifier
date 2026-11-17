# -*- coding: utf-8 -*-
"""E56: 独立场景存档 vs 战役存档 —— document/ 缺失、场景预设来源、静态数据可替代性"""
import os, io, zipfile, yaml, collections, json, hashlib

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e56_out.txt", "w", encoding="utf-8")
def P(*a):
    s = " ".join(str(x) for x in a)
    OUT.write(s + "\n")

SA = r"C:\Users\misprit\AppData\Local\.uoc2\save\games\west_unthinkable.usg"
CP = r"C:\Users\misprit\AppData\Local\.uoc2\save\campaigns\Stalingrad.usg"

P("=" * 70)
P("【1】独立场景存档 west_unthinkable.usg 完整条目树")
P("=" * 70)
with zipfile.ZipFile(SA) as zf:
    names = zf.namelist()
    top = collections.Counter()
    for n in names:
        seg = n.split("/")
        top[seg[0] + ("/" if len(seg) > 1 else "")] += 1
    for k, v in sorted(top.items()):
        P("  %-40s %d" % (k, v))
    P("  --- 一级/二级条目全览 ---")
    for n in sorted(names):
        if n.count("/") <= 2:
            P("    %s" % n)
    P("  --- main.yml 全文 ---")
    m = yaml.safe_load(zf.read("main.yml"))
    P(yaml.safe_dump(m, allow_unicode=True, default_flow_style=False, sort_keys=False))
    P("  --- 根级 yaml 清单 ---")
    for n in sorted(names):
        if n.count("/") == 1 and n.endswith(".yml"):
            P("    %-24s %d bytes" % (n, len(zf.read(n))))

P("")
P("=" * 70)
P("【2】战役存档 Stalingrad.usg 顶层条目")
P("=" * 70)
with zipfile.ZipFile(CP) as zf:
    cnames = zf.namelist()
    top = collections.Counter()
    for n in cnames:
        seg = n.split("/")
        top[seg[0] + ("/" if len(seg) > 1 else "")] += 1
    for k, v in sorted(top.items()):
        P("  %-40s %d" % (k, v))
    P("  --- main.yml 全文 ---")
    cm = yaml.safe_load(zf.read("main.yml"))
    P(yaml.safe_dump(cm, allow_unicode=True, default_flow_style=False, sort_keys=False))

P("")
P("=" * 70)
P("【3】存档 main.yml 的键 -> 出现文件普查（全部 70 存档）")
P("=" * 70)
keycnt = collections.Counter()
filemap = collections.defaultdict(collections.Counter)
allfiles = collections.Counter()
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        p = os.path.join(dp, f)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            for n in names:
                if n.count("/") == 1 and n.endswith(".yml"):
                    allfiles[n] += 1
            if "main.yml" in names:
                try:
                    mm = yaml.safe_load(zf.read("main.yml")) or {}
                except Exception:
                    continue
                for k in mm:
                    keycnt[k] += 1
                    filemap[k]["main.yml"] += 1
P("  main.yml 顶层键出现次数:")
for k, v in keycnt.most_common():
    P("    %-28s %d" % (k, v))
P("")
P("  根级 yml 文件出现次数:")
for k, v in allfiles.most_common():
    P("    %-28s %d" % (k, v))

P("")
P("=" * 70)
P("【4】standalone_scenario 的值来源与场景预设定位")
P("=" * 70)
# 找游戏包里 normandy_breakout / unthinkable 场景目录
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
pk = os.path.join(GAME, "_packages")
found = collections.defaultdict(list)
for dlc in sorted(os.listdir(pk)):
    cdir = os.path.join(pk, dlc, "data", "campaigns")
    if not os.path.isdir(cdir):
        continue
    for camp in sorted(os.listdir(cdir)):
        scen = os.path.join(cdir, camp, "scenarios")
        if not os.path.isdir(scen):
            continue
        for s in sorted(os.listdir(scen)):
            if s in ("normandy_breakout", "unthinkable"):
                found[s].append((dlc, camp, os.path.join(scen, s)))
for s, lst in found.items():
    P("  场景 %s:" % s)
    for dlc, camp, path in lst:
        files = sorted(os.listdir(path))
        P("    %s / %s -> %s" % (dlc, camp, os.path.join("data", "campaigns", camp, "scenarios", s)))
        P("      文件(%d): %s" % (len(files), files[:20]))

P("")
P("  --- west.usc 场景目录清单 ---")
west = os.path.join(pk, "base", "data", "campaigns", "west.usc", "scenarios")
if os.path.isdir(west):
    ws = sorted(os.listdir(west))
    P("    共 %d 个: %s" % (len(ws), ws))

P("")
P("=" * 70)
P("【5】独立场景存档里的 game/ 内容 vs 战役存档 games/")
P("=" * 70)
with zipfile.ZipFile(SA) as zf:
    for n in sorted(zf.namelist()):
        if n.startswith("game/"):
            P("    %s (%d bytes)" % (n, zf.getinfo(n).file_size))

OUT.close()
print(open(r"D:\MiniMax\_analysis\e56_out.txt", encoding="utf-8").read())
