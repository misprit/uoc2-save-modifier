# -*- coding: utf-8 -*-
"""E78: 静态提取的真实成本 —— 每个战役的文件清单 vs 分支逻辑的代码量"""
import os, io, marshal, types, dis, collections

GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
LIB = os.path.join(GAME, "lib", "uoc2")
OUT = io.open(r"D:\MiniMax\_analysis\e78_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

W("=" * 78)
W("【1】每个战役包的静态清单 —— 「接入一个新战役」到底要吞多少文件")
W("=" * 78)
rows = []
for dlc in sorted(os.listdir(PK)):
    cd = os.path.join(PK, dlc, "data", "campaigns")
    if not os.path.isdir(cd):
        continue
    for camp in sorted(os.listdir(cd)):
        root = os.path.join(cd, camp)
        if not os.path.isdir(root):
            continue
        nfile = nyml = nbytes = 0
        scen = var = front = conf = seg = 0
        for rt, dn, fn in os.walk(root):
            rel = os.path.relpath(rt, root).replace("\\", "/")
            parts = rel.split("/")
            for f in fn:
                nfile += 1
                nbytes += os.path.getsize(os.path.join(rt, f))
                if f.endswith((".yml", ".yaml")):
                    nyml += 1
            if len(parts) >= 2 and parts[0] == "scenarios":
                if len(parts) == 2:
                    scen += 1
                if "variants" in parts:
                    var += 1
            if parts[0] == "fronts":
                if len(parts) >= 2 and parts[1] == "conferences":
                    conf += 1
                if len(parts) >= 2 and parts[1] == "segments":
                    seg += 1
        rows.append((dlc, camp, nfile, nyml, nbytes, scen, var, conf, seg))
rows.sort(key=lambda r: -r[2])
W("  %-8s %-14s %6s %6s %10s %6s %6s %6s %6s" % ("dlc", "campaign", "文件", "yml", "字节", "场景", "变体", "会议", "段"))
for r in rows:
    W("  %-8s %-14s %6d %6d %10d %6d %6d %6d %6d" % r)
W("  %-8s %-14s %6d %6d %10d %6d %6d %6d %6d" % (
    "合计", "%d 个战役包" % len(rows),
    sum(r[2] for r in rows), sum(r[3] for r in rows), sum(r[4] for r in rows),
    sum(r[5] for r in rows), sum(r[6] for r in rows), sum(r[7] for r in rows), sum(r[8] for r in rows)))
W("")
W("  单个战役包内「变体覆盖」的分布（每个场景平均几个变体）:")
for dlc, camp, nf, ny, nb, scen, var, conf, seg in sorted(rows, key=lambda r: -r[6])[:6]:
    W("    %-14s 场景 %2d 个, 变体覆盖目录 %2d 个 -> 平均 %.1f 个变体/场景" % (camp, scen, var, var / max(scen, 1)))

W("")
W("=" * 78)
W("【2】entity_types（类型表）规模 —— 修改器真正需要的「类型」部分")
W("=" * 78)
ET = os.path.join(PK, "base", "data", "entity_types")
tot = 0
for sub in sorted(os.listdir(ET)):
    d = os.path.join(ET, sub)
    if os.path.isdir(d):
        n = len([x for x in os.listdir(d) if x.endswith((".yml", ".yaml"))])
        tot += n
        W("    %-16s %d" % (sub, n))
W("    %-16s %d" % ("合计", tot))
W("  ==> 这就是修改器要的「全部类型信息」，一次内置，永不变（§9.1.1 事实①）")

W("")
W("=" * 78)
W("【3】「进入条件 / 历史线 vs 幻想线 / 变体选择」的逻辑有多大？")
W("=" * 78)
def load(p):
    with open(p, "rb") as f:
        return marshal.loads(f.read()[16:])
def walk(code, prefix=""):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield prefix + c.co_name, c
            for n, cc in walk(c, prefix + c.co_name + "."):
                yield n, cc

root = load(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
TARGET = ["_situation_scenarios", "_situation_scenarios_to_play", "_get_situation_scenario_variant",
          "_scenario_token", "_has_segment_token", "_has_tokens", "_standalone_branching_tokens",
          "_set_branching_tokens_map", "_track_scenarios", "_scenarios_to_state",
          "_iterate_front_conference", "_iterate_fronts", "_get_action_object",
          "_get_strategic_tokens", "_has_or_can_have_tokens", "_get_situation_scenario_variant",
          "_get_next_conference", "get_situation_scenarios"]
found = {}
for n, c in walk(root):
    if c.co_name in TARGET:
        found.setdefault(c.co_name, []).append((n, c))
tot_ins = 0
for t in TARGET:
    if t not in found:
        W("  %-36s (未找到)" % t); continue
    for n, c in found[t]:
        ins = list(dis.get_instructions(c))
        tot_ins += len(ins)
        W("  %-36s 字节码指令 %4d 条" % (n, len(ins)))
W("  合计 %d 条字节码指令" % tot_ins)

W("")
W("  --- front/segment 的数据结构长什么样（段目录里有什么文件）---")
west = os.path.join(PK, "base", "data", "campaigns", "west.usc")
segroot = os.path.join(west, "fronts", "italy", "segments")
for s in sorted(os.listdir(segroot))[:4]:
    d = os.path.join(segroot, s)
    if not os.path.isdir(d):
        continue
    W("    %s/ -> %s" % (s, sorted(os.listdir(d))))
    for f in sorted(os.listdir(d)):
        fp = os.path.join(d, f)
        if f.endswith((".yml", ".yaml")):
            W("        %s (%d bytes): %s" % (f, os.path.getsize(fp),
              open(fp, encoding="utf-8", errors="replace").read()[:260].replace("\n", " | ")))
W("")
W("  --- 会议定义文件（进入条件的另一半）---")
for f in sorted(os.listdir(os.path.join(west, "fronts", "italy", "conferences")))[:3]:
    fp = os.path.join(west, "fronts", "italy", "conferences", f)
    W("    %s (%d bytes): %s" % (f, os.path.getsize(fp),
      open(fp, encoding="utf-8", errors="replace").read()[:300].replace("\n", " | ")))
OUT.close()
print("done")
