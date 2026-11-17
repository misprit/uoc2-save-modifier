# -*- coding: utf-8 -*-
"""E75: mod 内容长什么样、放在哪、游戏怎么加载它"""
import os, io, marshal, types, dis, yaml, json

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME, "lib", "uoc2")
USERPK = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e75_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

P("=" * 76)
P("【1】%LOCALAPPDATA%\\.uoc2\\_packages 完整结构")
P("=" * 76)
for rt, dn, fn in os.walk(USERPK):
    rel = os.path.relpath(rt, USERPK).replace("\\", "/")
    P("  %s/" % rel)
    for f in sorted(fn):
        fp = os.path.join(rt, f)
        P("      %-44s %d bytes" % (f, os.path.getsize(fp)))

P("")
P("=" * 76)
P("【2】这些 mod 文件里有没有新增的特种兵/类型？")
P("=" * 76)
for rt, dn, fn in os.walk(USERPK):
    for f in sorted(fn):
        if not f.endswith((".yml", ".yaml")):
            continue
        fp = os.path.join(rt, f)
        t = open(fp, encoding="utf-8", errors="replace").read()
        try:
            o = yaml.safe_load(t)
        except Exception as e:
            P("  %s 解析失败: %s" % (os.path.relpath(fp, USERPK), e)); continue
        if isinstance(o, dict):
            P("  %-50s 顶层键: %s" % (os.path.relpath(fp, USERPK).replace("\\", "/"), list(o)[:14]))
            for k in list(o)[:3]:
                v = o[k]
                if isinstance(v, dict):
                    P("       %s -> %s" % (k, list(v)[:10]))
                elif isinstance(v, list):
                    P("       %s -> list(%d) 首项=%s" % (k, len(v), json.dumps(v[0], ensure_ascii=False, default=str)[:180] if v else "-"))
        elif isinstance(o, list):
            P("  %-50s list(%d) 首项=%s" % (os.path.relpath(fp, USERPK).replace("\\", "/"), len(o),
              json.dumps(o[0], ensure_ascii=False, default=str)[:200] if o else "-"))

def strconsts(code):
    o = []
    for c in code.co_consts:
        if isinstance(c, str):
            o.append(c)
        elif isinstance(c, types.CodeType):
            o.extend(strconsts(c))
    return o

P("")
P("=" * 76)
P("【3】游戏怎么找到 _packages（两处位置？）")
P("=" * 76)
def load(pyc):
    with open(pyc, "rb") as f:
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

for rel in [r"paths.pyc", r"state\campaign\campaign_ctrl.pyc"]:
    p = os.path.join(LIB, rel)
    if not os.path.isfile(p):
        P("  缺 %s" % rel); continue
    root = load(p)
    for n, c in walk(root):
        ss = [s for s in strconsts(c)]
        if any("_packages" in s or "packages" == s for s in ss):
            P("  --- %s :: %s ---" % (rel, n))
            P("      字符串: %s" % [s for s in ss if "package" in s.lower() or "_packages" in s][:14])

def strconsts(code):
    o = []
    for c in code.co_consts:
        if isinstance(c, str):
            o.append(c)
        elif isinstance(c, types.CodeType):
            o.extend(strconsts(c))
    return o

P("")
P("  --- paths.pyc 全部函数名 ---")
root = load(os.path.join(LIB, "paths.pyc"))
P("  %s" % ", ".join(sorted(set(c.co_name for n, c in walk(root)))))
P("")
P("  --- paths.pyc 里含 packages 的函数反汇编 ---")
for n, c in walk(root):
    ss = strconsts(c)
    if any("package" in s.lower() for s in ss):
        P("  === %s ===" % n)
        for i, x in enumerate(dis.get_instructions(c)):
            if i > 90:
                P("      ..."); break
            P("      %-26s %s" % (x.opname, x.argrepr))
OUT.close()
print("done")
