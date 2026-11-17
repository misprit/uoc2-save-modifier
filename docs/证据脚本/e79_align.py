# -*- coding: utf-8 -*-
"""E79: required_tokens(进入条件) 与 scenarios/<场景>/variants/<变体>/ 能不能机械对齐"""
import os, io, yaml, json, collections

PK = os.path.join(r"D:\SteamLibrary\steamapps\common\Unity of Command 2", "_packages")
OUT = io.open(r"D:\MiniMax\_analysis\e79_out.txt", "w", encoding="utf-8")
def W(s):
    OUT.write(s + "\n")

WEST = os.path.join(PK, "base", "data", "campaigns", "west.usc")

W("=" * 78)
W("【1】west.usc：所有段的 data.yml（进入条件）+ 对应场景的 variants/ 目录")
W("=" * 78)
fronts = os.path.join(WEST, "fronts")
seg_rows = []
for front in sorted(os.listdir(fronts)):
    sd = os.path.join(fronts, front, "segments")
    if not os.path.isdir(sd):
        continue
    for seg in sorted(os.listdir(sd)):
        d = os.path.join(sd, seg)
        dp = os.path.join(d, "data.yml")
        if not os.path.isfile(dp):
            continue
        o = yaml.safe_load(open(dp, encoding="utf-8", errors="replace").read()) or {}
        scen_dir = os.path.join(WEST, "scenarios")
        variants = {}
        for s in sorted(os.listdir(scen_dir)):
            vd = os.path.join(scen_dir, s, "variants")
            if os.path.isdir(vd):
                v = sorted(os.listdir(vd))
                if v:
                    variants[s] = v
        seg_rows.append((front, seg, o, variants))

for front, seg, o, variants in seg_rows:
    W("")
    W("  【%s / %s】" % (front, seg))
    W("    data.yml: level=%s  name_brief=%s  show_in_front=%s" % (o.get("level"), o.get("name_brief"), o.get("show_in_front")))
    W("    situations(这一段包含的场景, 按顺序) = %s" % (o.get("situations"),))
    rt = o.get("required_tokens") or []
    if not rt:
        W("    required_tokens = []  (无条件进入)")
    for r in rt:
        W("    required_tokens: scenario=%-22s tokens=%-28s variant=%s" %
          (r.get("scenario"), r.get("tokens"), r.get("variant")))
    # 这段涉及的场景有哪些变体
    involved = []
    for s in (o.get("situations") or []):
        for item in s:
            involved.append(item)
    for s in involved:
        if s in variants:
            W("      场景 %-22s 的 variants/: %s" % (s, variants[s]))

W("")
W("=" * 78)
W("【2】机器可对齐性：required_tokens.variant 的取值 ⊆ 场景 variants/ 目录名？")
W("=" * 78)
allvars = set()
for s in sorted(os.listdir(os.path.join(WEST, "scenarios"))):
    vd = os.path.join(WEST, "scenarios", s, "variants")
    if os.path.isdir(vd):
        allvars |= set(os.listdir(vd))
declared = set()
for front, seg, o, variants in seg_rows:
    for r in (o.get("required_tokens") or []):
        if r.get("variant"):
            declared.add(r["variant"])
W("  west.usc 里 variants/ 目录名共 %d 个: %s" % (len(allvars), sorted(allvars)))
W("  data.yml 里 required_tokens.variant 声明了 %d 个: %s" % (len(declared), sorted(declared)))
W("  声明 ⊆ 实际存在? %s" % (declared <= allvars))
W("  未被任何 required_tokens 声明的变体: %s" % sorted(allvars - declared))

W("")
W("=" * 78)
W("【3】全 15 个战役包：这种「段图 + required_tokens + variants」结构是否一致？")
W("=" * 78)
for dlc in sorted(os.listdir(PK)):
    cd = os.path.join(PK, dlc, "data", "campaigns")
    if not os.path.isdir(cd):
        continue
    for camp in sorted(os.listdir(cd)):
        root = os.path.join(cd, camp)
        if not os.path.isdir(root):
            continue
        nseg = ntok = nvar = nscen = 0
        for rt_, dn_, fn_ in os.walk(root):
            rel = os.path.relpath(rt_, root).replace("\\", "/")
            parts = rel.split("/")
            if len(parts) >= 3 and parts[0] == "fronts" and parts[2] == "segments":
                if "data.yml" in fn_:
                    nseg += 1
                    try:
                        o = yaml.safe_load(open(os.path.join(rt_, "data.yml"), encoding="utf-8", errors="replace").read()) or {}
                        ntok += len(o.get("required_tokens") or [])
                    except Exception:
                        pass
            if len(parts) == 2 and parts[0] == "scenarios":
                nscen += 1
                if "variants" in dn_:
                    nvar += 1
        W("  %-12s %-14s 场景 %2d  变体覆盖 %2d  段 %2d  required_tokens 条目 %3d" % (dlc, camp, nscen, nvar, nseg, ntok))
OUT.close()
print("done")
