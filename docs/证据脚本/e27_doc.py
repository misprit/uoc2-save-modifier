# -*- coding: utf-8 -*-
"""E27: 存档里的 document/ 到底是运行时数据源，还是只是包副本？"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e27_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=120):
    P(f"  --- {label}  (line={code_obj.co_firstlineno})")
    buf = io.StringIO(); dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)

P("=" * 100); P("[A] campaign_doc.pyc 的 get_doc_unit / 单位名册来源"); P("=" * 100)
try:
    cc = load("uoc2\\state\\campaign\\campaign_doc.pyc")
    for path, fn, ln in walk_all(cc):
        P(f"  {path} line={ln} args={fn.co_varnames[:fn.co_argcount]}")
    for path, fn, ln in walk_all(cc):
        if fn.co_name in ("get_doc_unit", "_load_units", "load_doc", "_load_doc_units"):
            dump(path, fn, 130)
            P("")
except Exception as e:
    P(f"  读取失败: {e}")

P(""); P("=" * 100); P("[B] _document_save_units 在哪、写向哪"); P("=" * 100)
for dirpath, _, files in os.walk(os.path.join(LIB, "uoc2")):
    for f in files:
        if not f.endswith(".pyc"):
            continue
        fp = os.path.join(dirpath, f)
        try:
            c = marshal.loads(open(fp, "rb").read()[16:])
        except Exception:
            continue
        for path, fn, ln in walk_all(c):
            if "_document_save_units" in fn.co_names:
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln}")
                P(f"      names: {[n for n in fn.co_names]}")
                P(f"      strings: {[s for s in fn.co_consts if isinstance(s,str) and len(s)<60]}")

P(""); P("=" * 100); P("[C] 'document' 这个目录名在字节码里的出现处"); P("=" * 100)
for dirpath, _, files in os.walk(os.path.join(LIB, "uoc2")):
    for f in files:
        if not f.endswith(".pyc"):
            continue
        fp = os.path.join(dirpath, f)
        try:
            c = marshal.loads(open(fp, "rb").read()[16:])
        except Exception:
            continue
        for path, fn, ln in walk_all(c):
            strs = [s for s in fn.co_consts if isinstance(s, str)]
            hits = [s for s in strs if s == "document" or s.startswith("document/")]
            if hits:
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln}  hits={hits[:5]}")
                P(f"      names: {[n for n in fn.co_names][:16]}")

P(""); P("=" * 100); P("[D] campaign_doc 的 units 从哪加载（找 units.yml 的加载点）"); P("=" * 100)
try:
    cc = load("uoc2\\state\\campaign\\campaign_doc.pyc")
    for path, fn, ln in walk_all(cc):
        strs = [s for s in fn.co_consts if isinstance(s, str)]
        if any(s == "units.yml" for s in strs):
            dump(path, fn, 130)
            P("")
except Exception as e:
    P(f"  {e}")

OUT.close()
print("done")
