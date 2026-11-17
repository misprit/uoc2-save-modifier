# -*- coding: utf-8 -*-
"""E24: 场景单位 schema —— 场景文件里到底有没有 type 字段"""
import sys, os, io, importlib, json

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
sys.frozen = True
sys.executable = os.path.join(GAME, "uoc2.exe")
sys.path.append(os.path.join(GAME, "lib"))
import numpy, yaml  # 必须先导入，否则被游戏 lib 里的 numpy 抢占
paths = importlib.import_module("uoc2.paths")
paths.init_paths()
um = importlib.import_module("uoc2.state.entities.data_validation.unit")

OUT = io.open(r"D:\MiniMax\_analysis\e24_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

P("模块成员: %s" % [n for n in dir(um) if not n.startswith("_")])

for name in ("campaign_unit_schema", "scenario_unit_schema", "unit_schema"):
    v = getattr(um, name, None)
    P("")
    P("=" * 90)
    P(f"{name} = {type(v).__name__}")
    P("=" * 90)
    if isinstance(v, dict):
        for k, val in v.items():
            P(f"  {k!r:28s} -> {val!r}")
    else:
        P(f"  {v!r}")

OUT.close()
print("done")
