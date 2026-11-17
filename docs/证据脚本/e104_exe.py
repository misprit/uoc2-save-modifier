# -*- coding: utf-8 -*-
"""E104: uoc2.exe 里 steam_api 相关字符串（原生实现线索）"""
import os, io, re

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
OUT = io.open(r"D:\MiniMax\_analysis\e104_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

exe = os.path.join(GAME, "uoc2.exe")
W("exe: %s  size=%d" % (exe, os.path.getsize(exe)))
data = open(exe, "rb").read()

def strings_ascii(buf, minlen=5):
    out = []
    cur = bytearray()
    for b in buf:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= minlen:
                out.append(cur.decode("ascii"))
            cur = bytearray()
    if len(cur) >= minlen:
        out.append(cur.decode("ascii"))
    return out

S = strings_ascii(data, 5)
W("ASCII 字符串总数: %d" % len(S))

PATTERNS = ["get_stat_value", "inc_stat", "store_stats", "set_stat_value",
            "steam_api", "SteamUserStats", "SetStat", "GetStat", "StoreStats",
            "steam_api64", "SteamAPI", "steamclient", "ISteamUserStats",
            "ms_", "achievement"]
for p in PATTERNS:
    hits = [s for s in S if p.lower() in s.lower()]
    W("")
    W("=== %s : %d 命中 ===" % (p, len(hits)))
    seen = set()
    for h in hits:
        if h in seen: continue
        seen.add(h)
        if len(h) > 200: h = h[:200] + "..."
        W("   %s" % h)
        if len(seen) > 40:
            W("   ...")
            break

# DLL 依赖
W("")
W("=== 游戏目录下的 steam 相关 dll ===")
for dp, dn, fn in os.walk(GAME):
    if dp.count(os.sep) > GAME.count(os.sep) + 2:
        dn[:] = []
        continue
    for f in fn:
        if "steam" in f.lower():
            W("   %s" % os.path.join(dp, f).replace(GAME, ""))

OUT.close()
print("done")
