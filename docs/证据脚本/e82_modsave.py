# -*- coding: utf-8 -*-
"""E82: mod 覆盖的场景，修改器能不能从存档里直接读出来？（用 fall_blau_2 实测）"""
import os, io, zipfile, hashlib, marshal, types, dis, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
LIB = os.path.join(GAME, "lib", "uoc2")
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
MOD = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "_packages", "fall_blau_2")
MODUSC = os.path.join(MOD, "data", "scenarios", "fall_blau_2.usc")
STG = os.path.join(PK, "dlc4", "data", "campaigns", "stalingrad.usc")
OUT = io.open(r"D:\MiniMax\_analysis\e82_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")
def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]

SAV = os.path.join(G, r"campaigns\Stalingrad.usg")

W("=" * 80)
W("【1】mod 包里的 fall_blau_2 场景文件 vs 原版 stalingrad.usc/scenarios/")
W("=" * 80)
modscen = os.path.join(MODUSC, "scenarios", "fall_blau_2")
W("  mod 场景目录: %s" % modscen)
modfiles = sorted(os.listdir(modscen))
W("  文件: %s" % modfiles)
base_scen = os.path.join(STG, "scenarios")
W("  原版 stalingrad.usc/scenarios/ 里有没有 fall_blau_2? %s" % (os.path.isdir(os.path.join(base_scen, "fall_blau_2"))))
W("  原版 stalingrad.usc/scenarios/ 共 %d 个: %s" % (len(os.listdir(base_scen)), sorted(os.listdir(base_scen))))

W("")
W("=" * 80)
W("【2】★ 存档里有没有这个 mod 场景？内容与 mod 包是否一致？")
W("=" * 80)
with zipfile.ZipFile(SAV) as zf:
    names = zf.namelist()
    insc = sorted(n for n in names if n.startswith("document/scenarios/fall_blau_2/"))
    W("  存档 document/scenarios/fall_blau_2/ 下 %d 个条目:" % len(insc))
    for n in insc:
        W("      %s (%d bytes)" % (n, zf.getinfo(n).file_size))
    W("")
    W("  逐文件与 mod 包比对:")
    same = diff = only = 0
    for f in modfiles:
        m = "document/scenarios/fall_blau_2/%s" % f
        fp = os.path.join(modscen, f)
        if m in names and os.path.isfile(fp):
            ok = sha(zf.read(m)) == sha(open(fp, "rb").read())
            W("      %-26s %s" % (f, "★字节级相同" if ok else "!! 不同 !!"))
            same += ok; diff += (not ok)
        else:
            W("      %-26s 存档里没有 / 包里不是文件" % f)
    # 反向：存档有但包里没有的
    extra = [n for n in insc if os.path.basename(n) not in modfiles]
    W("  存档有但 mod 包里没有的: %s" % (extra or "无"))
    W("")
    W("  存档里 fall_blau_2 的 variants/:")
    var = sorted(n for n in names if n.startswith("document/scenarios/fall_blau_2/variants/"))
    for v in var:
        W("      %s" % v)
    modvar = os.path.join(modscen, "variants")
    if os.path.isdir(modvar):
        W("  mod 包里的 variants/: %s" % sorted(os.listdir(modvar)))

W("")
W("=" * 80)
W("【3】存档里 mod 场景 vs 原版包：该场景是 mod 独有的吗？原版有没有同名？")
W("=" * 80)
with zipfile.ZipFile(SAV) as zf:
    names = zf.namelist()
    allscen = sorted(set(n.split("/")[2] for n in names if n.startswith("document/scenarios/") and n.count("/") >= 3))
    W("  存档 document/scenarios/ 共 %d 个场景" % len(allscen))
    W("  含 fall_blau_2? %s" % ("fall_blau_2" in allscen))
    base = set(os.listdir(base_scen))
    W("  原版包 %d 个场景" % len(base))
    W("  ★ 存档比原版多出的场景: %s" % sorted(set(allscen) - base))
    W("  ★ 原版有但存档没有的: %s" % sorted(base - set(allscen)))

W("")
W("=" * 80)
W("【4】玩过的 mod 场景在 games/ 里留下了什么？")
W("=" * 80)
with zipfile.ZipFile(SAV) as zf:
    names = zf.namelist()
    gm = [n for n in names if n.startswith("games/fall_blau_2/")]
    W("  games/fall_blau_2/ 下 %d 个条目:" % len(gm))
    for n in sorted(gm):
        W("      %s (%d bytes)" % (n, zf.getinfo(n).file_size))

W("")
W("=" * 80)
W("【5】游戏的「覆盖 / addable」机制在 paths.pyc 里长什么样")
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
def strconsts(code):
    o = []
    for c in code.co_consts:
        if isinstance(c, str):
            o.append(c)
        elif isinstance(c, types.CodeType):
            o.extend(strconsts(c))
    return o

root = load(os.path.join(LIB, "paths.pyc"))
for target in ["addable_dir", "addable_from_dir", "has_addable", "cache_addables", "get_yml", "_build_package_list", "init_packages"]:
    for n, c in walk(root):
        if c.co_name == target:
            W("")
            W("  === %s ===" % n)
            W("      字符串: %s" % [s for s in strconsts(c)][:16])
            for i, x in enumerate(dis.get_instructions(c)):
                if i > 70:
                    W("      ..."); break
                W("      %-26s %s" % (x.opname, x.argrepr))
            break
OUT.close()
print("done")
