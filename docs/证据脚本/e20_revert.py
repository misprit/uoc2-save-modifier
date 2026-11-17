# -*- coding: utf-8 -*-
"""E20: Game.new 的调用者 / 回滚（重打上一场）是否重跑初始化"""
import os, io, marshal, dis, types

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Guard 2\lib"
LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"
OUT = io.open(r"D:\MiniMax\_analysis\e20_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def load(rel):
    return marshal.loads(open(os.path.join(LIB, rel), "rb").read()[16:])

def walk_all(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k, k.co_firstlineno
            yield from walk_all(k, path + "/" + k.co_name)

def dump(label, code_obj, maxlines=140):
    P(f"  --- {label}  (line={code_obj.co_firstlineno})")
    buf = io.StringIO(); dis.dis(code_obj, file=buf, depth=0)
    txt = buf.getvalue().split("\n")
    for ln in txt[:maxlines]:
        P("      " + ln)

P("=" * 100); P("[A] 谁调用 Game.new（全 uoc2 搜索 'new' + Game 上下文）"); P("=" * 100)
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
            names = list(fn.co_names)
            if "Game" in names and "new" in names:
                P(f"  {os.path.relpath(fp, LIB)} :: {path} line={ln} args={fn.co_varnames[:fn.co_argcount]}")
                P(f"      names: {names[:20]}")
                P(f"      strings: {[s for s in strs if len(s)<55][:12]}")

P(""); P("=" * 100); P("[B] 回滚相关函数（revert / last_game / reset_conference）"); P("=" * 100)
for rel in ["uoc2\\state\\campaign\\campaign.pyc", "uoc2\\main_screen\\ctrl.pyc",
            "uoc2\\main_screen\\campaign_ctrl.pyc"]:
    try:
        c = load(rel)
    except Exception as e:
        P(f"  跳过 {rel}: {e}"); continue
    P(f"  --- {rel}")
    for path, fn, ln in walk_all(c):
        if any(k in fn.co_name.lower() for k in ("revert", "reset", "restart", "new_game", "start_game")):
            strs = [s for s in fn.co_consts if isinstance(s, str)]
            P(f"      {path} line={ln} args={fn.co_varnames[:fn.co_argcount]}")
            P(f"         names: {[n for n in fn.co_names][:18]}")
            P(f"         strings: {[s for s in strs if len(s)<55][:10]}")

P(""); P("=" * 100); P("[C] campaign.pyc 的 revert 相关函数完整反汇编"); P("=" * 100)
cc = load("uoc2\\state\\campaign\\campaign.pyc")
for path, fn, ln in walk_all(cc):
    if "revert" in fn.co_name.lower():
        dump(path, fn, 130)
        P("")

OUT.close()
print("done")
