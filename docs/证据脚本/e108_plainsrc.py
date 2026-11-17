# -*- coding: utf-8 -*-
"""E108: 明文 name_brief 的来源 —— 游戏自己就这么写吗？ + is_str_id 判定规则"""
import os, io, marshal, types, dis, zipfile, re, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib")
SAVES = r"C:\Users\misprit\AppData\Local\.uoc2\save"
PKGROOT = os.path.join(GAME, "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e108_out.txt", "w", encoding="utf-8")
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
def dump(c, lim=160):
    for i, x in enumerate(dis.get_instructions(c)):
        if i > lim:
            W("      ...(truncated)"); break
        a = x.argrepr
        if len(a) > 100: a = a[:100] + "..."
        W("      %-24s %s" % (x.opname, a))
def consts(c):
    return [x for x in c.co_consts if isinstance(x, (str, int, float, type(None)))]

# ---------- A. is_str_id / isascii / _MyDefaultDict.__missing__ ----------
W("=" * 92)
W("[A] LocalizationManager.is_str_id / isascii / get_unformatted")
W("=" * 92)
r = load(os.path.join(LIB, "tools", "localization.pyc"))
funcs = dict(walk(r))
for nm in ("LocalizationManager.is_str_id", "LocalizationManager.isascii",
           "LocalizationManager.get_unformatted", "LocalizationManager.has_str_id",
           "_MyDefaultDict.__missing__"):
    c = funcs.get(nm)
    if not c:
        W("  !! MISSING %s" % nm); continue
    W("")
    W("  === %s ===" % nm)
    W("  常量: %s" % (consts(c)[:26],))
    dump(c, 120)

# ---------- B. 游戏包里的明文 name_brief ----------
W("")
W("=" * 92)
W("[B] 游戏包（只读原件）里的 name_brief 明文普查 —— 证明游戏自己就这么写")
W("=" * 92)
import yaml
plain_pk = []
tot_pk = 0
for dlc in sorted(os.listdir(PKGROOT)):
    for rel in ("data/campaigns", "data/scenarios"):
        base = os.path.join(PKGROOT, dlc, rel)
        if not os.path.isdir(base):
            continue
        for camp in sorted(os.listdir(base)):
            for u in (os.path.join(base, camp, "units.yml"),
                      os.path.join(base, camp, "document", "units.yml")):
                if not os.path.isfile(u):
                    continue
                try:
                    d = yaml.safe_load(open(u, encoding="utf-8")) or []
                except Exception:
                    continue
                if not isinstance(d, list):
                    continue
                for it in d:
                    if not isinstance(it, dict):
                        continue
                    nb = it.get("name_brief")
                    if nb is None:
                        continue
                    tot_pk += 1
                    if isinstance(nb, str) and not nb.startswith("id_"):
                        plain_pk.append((dlc, rel, camp, os.path.basename(os.path.dirname(u)),
                                         it.get("id"), nb))
W("  游戏包内 units.yml 单位条目: %d" % tot_pk)
W("  其中明文 name_brief: %d" % len(plain_pk))
for s in plain_pk[:30]:
    W("    %-6s %-16s %-14s %-14s id=%-5s %r" % (s[0], s[1], s[2], s[3], s[4], s[5]))

# ---------- C. 存档里明文名的分布 ----------
W("")
W("=" * 92)
W("[C] 存档里明文 name_brief 的分布（按表 / 按存档）")
W("=" * 92)
per_table = collections.Counter()
per_save = collections.Counter()
ids = collections.Counter()
for dp, dn, fn in os.walk(SAVES):
    for f in fn:
        if not f.endswith(".usg"):
            continue
        sp = os.path.join(dp, f)
        rel = os.path.relpath(sp, SAVES)
        try:
            with zipfile.ZipFile(sp) as z:
                for nm in z.namelist():
                    if not nm.endswith("units.yml"):
                        continue
                    try:
                        d = yaml.safe_load(z.read(nm)) or []
                    except Exception:
                        continue
                    if not isinstance(d, list):
                        continue
                    for it in d:
                        if not isinstance(it, dict):
                            continue
                        nb = it.get("name_brief")
                        if isinstance(nb, str) and nb and not nb.startswith("id_"):
                            per_table[nm] += 1
                            per_save[rel] += 1
                            ids[(it.get("id"), nb)] += 1
        except Exception:
            pass
W("  按表: %s" % dict(per_table))
W("  涉及的存档数: %d" % len(per_save))
W("  去重后的 (id, 明文) 组合: %d" % len(ids))
W("  全部去重组合:")
for (i, nb), cnt in sorted(ids.items(), key=lambda kv: -kv[1])[:40]:
    W("    id=%-6s %-30r 出现 %d 次" % (i, nb, cnt))

OUT.close()
print("done")
