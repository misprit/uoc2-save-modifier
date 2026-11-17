# -*- coding: utf-8 -*-
"""E76b: 用游戏自己的 paths 模块问出「包扫描顺序/位置」"""
import os, io, sys, importlib, json

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
OUT = io.open(r"D:\MiniMax\_analysis\e76_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

sys.frozen = True
sys.executable = os.path.join(GAME, "uoc2.exe")
sys.path.append(os.path.join(GAME, "lib"))
import numpy, yaml
paths = importlib.import_module("uoc2.paths")
inst = paths.init_paths()
W("init_paths() 返回: %r" % (inst,))
W("模块属性: %s" % [a for a in dir(paths) if not a.startswith("__")])

p = inst
if not hasattr(p, "all_package_dirs"):
    for name in dir(paths):
        v = getattr(paths, name)
        if hasattr(v, "all_package_dirs") and not isinstance(v, type):
            p = v
            break
W("使用的实例: %r" % (p,))
for attr in ["root_dir", "game_package_dir", "user_package_dir", "data_dir", "settings_file", "user_dir"]:
    try:
        v = getattr(p, attr)
        W("  %-20s %s" % (attr, v))
    except Exception as e:
        W("  %-20s ERR %s" % (attr, e))
W("")
for meth in ["game_packages", "all_non_game_package_dirs", "all_package_dirs",
             "get_editable_packages", "get_non_editable_packages"]:
    try:
        v = getattr(p, meth)
        v = v() if callable(v) else v
        W("  %-26s %s" % (meth, v))
    except Exception as e:
        W("  %-26s ERR %s" % (meth, e))
OUT.close()
print("done")
