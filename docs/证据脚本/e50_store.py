# -*- coding: utf-8 -*-
"""E50: 商店相关代码 —— price / quantity 的语义（是否 0 有特殊含义）"""
import os, io, marshal, types, dis, re

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e50_out.txt", "w", encoding="utf-8")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from walk(k, path + "/" + k.co_name)

# 找出所有含 store 关键字的 pyc
hits = []
for dp, _, fs in os.walk(LIB):
    for f in fs:
        if f.endswith(".pyc"):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, LIB)
            try:
                c = load(rel)
            except Exception:
                continue
            names = set()
            strs = set()
            for _, code in walk(c):
                names.update(code.co_names)
                strs.update(x for x in code.co_consts if isinstance(x, str))
            if ("store" in names or "quantity" in names or "price" in names):
                hits.append((rel, sorted(n for n in names if "store" in n.lower() or n in ("quantity","price","sold","stock"))))
OUT.write("=== 含 store/quantity/price 关键字的模块 ===\n")
for rel, ns in hits:
    OUT.write("  %-56s %s\n" % (rel, ns[:14]))

# 重点看 store 相关类的属性与逻辑
OUT.write("\n=== 商店类的定义与常量 ===\n")
for rel, _ in hits:
    if "store" not in rel.lower() and "shop" not in rel.lower():
        continue
    c = load(rel)
    for path, code in walk(c):
        if re.search(r"store|shop|quantity|price", path, re.I):
            OUT.write("\n  --- %s :: %s (line=%d)\n" % (rel, path, code.co_firstlineno))
            OUT.write("      names: %s\n" % sorted(set(code.co_names)))
            OUT.write("      consts: %s\n" % [x for x in code.co_consts if isinstance(x, (str, int, float))][:20])
OUT.close()
print("ok")
