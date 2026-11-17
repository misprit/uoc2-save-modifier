# -*- coding: utf-8 -*-
"""E74: 修改器启动时读取游戏包的实际耗时（冷/热盘），以及必须读 vs 可以缓存的拆分"""
import os, io, time, yaml, json, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e74_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def timed(label, fn):
    t0 = time.perf_counter()
    r = fn()
    dt = (time.perf_counter() - t0) * 1000
    P("  %-52s %8.1f ms   (%s)" % (label, dt, r))
    return dt

def count_files(d, exts=(".yml", ".yaml")):
    n = 0
    for rt, _, fn in os.walk(d):
        n += sum(1 for x in fn if x.endswith(exts))
    return n

P("=" * 76)
P("【1】entity_types 各子目录规模与解析耗时（修改器下拉数据源）")
P("=" * 76)
ET = os.path.join(PK, "base", "data", "entity_types")
total = 0
for sub in sorted(os.listdir(ET)):
    d = os.path.join(ET, sub)
    if not os.path.isdir(d):
        continue
    n = count_files(d)
    total += n
    def load(d=d):
        c = 0
        for f in sorted(os.listdir(d)):
            if f.endswith((".yml", ".yaml")):
                try:
                    yaml.safe_load(open(os.path.join(d, f), encoding="utf-8", errors="replace").read())
                    c += 1
                except Exception:
                    pass
        return "%d 个已解析" % c
    timed("%s/ (%d 个 yml)" % (sub, n), load)
P("  entity_types 合计 %d 个 yml" % total)

P("")
P("=" * 76)
P("【2】战役包整棵树的解析耗时（最坏情况：整个战役包全读）")
P("=" * 76)
for dlc, camp in [("base", "west"), ("dlc4", "stalingrad"), ("dlc3", "moscow")]:
    cd = os.path.join(PK, dlc, "data", "campaigns", camp + ".usc")
    n = count_files(cd)
    def load(cd=cd):
        c = 0
        for rt, _, fn in os.walk(cd):
            for f in fn:
                if f.endswith((".yml", ".yaml")):
                    try:
                        yaml.safe_load(open(os.path.join(rt, f), encoding="utf-8", errors="replace").read())
                        c += 1
                    except Exception:
                        pass
        return "%d 个已解析" % c
    timed("%s.usc 全树 (%d 个 yml)" % (camp, n), load)

P("")
P("=" * 76)
P("【3】只读当前需要的那几个文件（真实最小开销）")
P("=" * 76)
WEST = os.path.join(PK, "base", "data", "campaigns", "west.usc")
def only_types():
    c = 0
    for f in sorted(os.listdir(os.path.join(ET, "specialists"))):
        if f.endswith(".yml"):
            yaml.safe_load(open(os.path.join(ET, "specialists", f), encoding="utf-8", errors="replace").read()); c += 1
    return "%d 个特种兵" % c
timed("只读 specialists/ (375 个)", only_types)

def one_scenario():
    d = os.path.join(WEST, "scenarios", "overlord")
    c = 0
    for f in sorted(os.listdir(d)):
        if f.endswith(".yml"):
            yaml.safe_load(open(os.path.join(d, f), encoding="utf-8", errors="replace").read()); c += 1
    return "%d 个 yml" % c
timed("只读一个场景目录 (overlord)", one_scenario)

def listdir_only():
    n = 0
    for rt, dn, fn in os.walk(ET):
        n += len(fn)
    return "%d 个文件" % n
timed("只 listdir 不解析 (entity_types)", listdir_only)

P("")
P("=" * 76)
P("【4】解析一个 .usg 存档（对照：修改器本来就得读的量级）")
P("=" * 76)
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
import zipfile
def load_save():
    p = os.path.join(G, r"campaigns\Stalingrad.usg")
    c = 0
    with zipfile.ZipFile(p) as zf:
        for n in zf.namelist():
            if n.endswith(".yml") and n.count("/") == 0:
                yaml.safe_load(zf.read(n)); c += 1
        for n in zf.namelist():
            if n.startswith("document/") and n.endswith(".yml") and n.count("/") == 1:
                yaml.safe_load(zf.read(n)); c += 1
    return "%d 个根+document yml" % c
timed("解 ZIP + 解析根 & document/*.yml", load_save)

def zip_only():
    p = os.path.join(G, r"campaigns\Stalingrad.usg")
    with zipfile.ZipFile(p) as zf:
        d = zf.read("document/units.yml")
    return "%d bytes" % len(d)
timed("只解 ZIP + 读 1 个条目", zip_only)

P("")
P("=" * 76)
P("【5】本地化字符串表（显示中文名要用）")
P("=" * 76)
LOC = os.path.join(PK, "base", "localization")
for lang in sorted(os.listdir(LOC)):
    d = os.path.join(LOC, lang)
    if not os.path.isdir(d):
        continue
    n = count_files(d)
    def load(d=d):
        c = 0
        for rt, _, fn in os.walk(d):
            for f in fn:
                if f.endswith((".yml", ".yaml")):
                    try:
                        yaml.safe_load(open(os.path.join(rt, f), encoding="utf-8", errors="replace").read()); c += 1
                    except Exception:
                        pass
        return "%d 个已解析" % c
    timed("localization/%s (%d 个 yml)" % (lang, n), load)

P("")
P("=" * 76)
P("【6】mod 目录：游戏会不会从第二个位置加载包？")
P("=" * 76)
for p in [os.path.join(PKG if (PKG := os.environ.get("LOCALAPPDATA")) else "", ".uoc2", "_packages"),
          os.path.join(GAME, "_packages")]:
    P("  %s -> %s" % (p, "存在" if os.path.isdir(p) else "不存在"))
    if os.path.isdir(p):
        P("      子项: %s" % sorted(os.listdir(p))[:20])
OUT.close()
print("done")
