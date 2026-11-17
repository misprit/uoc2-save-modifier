# -*- coding: utf-8 -*-
"""E61b: 改名单位的落点（精简版）"""
import os, io, zipfile, yaml, json, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
STG = os.path.join(PK, "dlc4/data/campaigns/stalingrad.usc")
OUT = io.open(r"D:\MiniMax\_analysis\e61_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")
    OUT.flush()

P("=" * 74)
P("【1】stalingrad.usc 包里哪些文件提到 id 786 / “苏联警卫”")
P("=" * 74)
for rt, _, fn in os.walk(STG):
    for x in sorted(fn):
        fp = os.path.join(rt, x)
        if not x.endswith((".yml", ".yaml")):
            continue
        t = open(fp, encoding="utf-8", errors="replace").read()
        if "苏联警卫" in t or ("id: 786" in t):
            P("  %-58s %d bytes  命中: %s" % (os.path.relpath(fp, STG).replace("\\", "/"), len(t),
               ("中文名" if "苏联警卫" in t else "") + (" id786" if "id: 786" in t else "")))

P("")
P("  --- 精确定位 id=786 的场景文件条目 ---")
for rt, _, fn in os.walk(os.path.join(STG, "scenarios")):
    for x in sorted(fn):
        if not x.endswith((".yml", ".yaml")):
            continue
        fp = os.path.join(rt, x)
        try:
            o = yaml.safe_load(open(fp, encoding="utf-8", errors="replace").read())
        except Exception:
            continue
        if isinstance(o, list):
            for e in o:
                if isinstance(e, dict) and e.get("id") == 786:
                    P("    %s -> %s" % (os.path.relpath(fp, STG).replace("\\", "/"),
                                       yaml.safe_dump(e, allow_unicode=True, default_flow_style=False).replace("\n", " ")[:260]))
        elif isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, list):
                    for e in v:
                        if isinstance(e, dict) and e.get("id") == 786:
                            P("    %s :: %s -> %s" % (os.path.relpath(fp, STG).replace("\\", "/"), k,
                                yaml.safe_dump(e, allow_unicode=True, default_flow_style=False).replace("\n", " ")[:260]))

P("")
P("=" * 74)
P("【2】存档 Stalingrad-Conference3-1.usg 里 id=786 的改名出现在哪些文件")
P("=" * 74)
SAV = os.path.join(G, r"Old Saves\Stalingrad\Stalingrad-Conference3-1.usg")
with zipfile.ZipFile(SAV) as zf:
    names = zf.namelist()
    root = yaml.safe_load(zf.read("units.yml"))
    lst = root if isinstance(root, list) else []
    hit = [e for e in lst if isinstance(e, dict) and e.get("id") == 786]
    P("  根 units.yml: 条目 %d 个, 含 id=786: %s" % (len(lst), "是" if hit else "否"))
    if hit:
        P("    %s" % yaml.safe_dump(hit[0], allow_unicode=True, default_flow_style=False)[:420])
    P("  根 units.yml 中 name_brief 非 id_ 开头的条目数: %d" %
      len([e for e in lst if isinstance(e, dict) and e.get("name_brief") and not str(e["name_brief"]).startswith("id_")]))
    doc = yaml.safe_load(zf.read("document/units.yml"))
    P("  document/units.yml: 条目 %d 个, 含 id=786: %s, 非 id_ 名条目数: %d" %
      (len(doc), "是" if any(isinstance(e, dict) and e.get("id") == 786 for e in doc) else "否",
       len([e for e in doc if isinstance(e, dict) and e.get("name_brief") and not str(e["name_brief"]).startswith("id_")])))
    gs = sorted(set(n.split("/")[1] for n in names if n.startswith("games/") and n.count("/") >= 2))
    P("  games/ 场景: %s" % gs)
    for g in gs:
        m = "games/%s/units.yml" % g
        if m in names:
            u = yaml.safe_load(zf.read(m))
            if isinstance(u, list) and u and isinstance(u[0], dict):
                n786 = [e for e in u if e.get("id") == 786]
                P("    %s -> 完整对象 %d 条, 含 id786=%s, 明文改名数=%d" %
                  (m, len(u), "是" if n786 else "否",
                   len([e for e in u if e.get("name_brief") and not str(e["name_brief"]).startswith("id_")])))
            else:
                P("    %s -> ID清单 %d 条" % (m, len(u)))

P("")
P("=" * 74)
P("【3】根 units.yml 与 document/units.yml 的 id 集合关系（10 个存档抽样）")
P("=" * 74)
sample = []
for dp, dn, fs in os.walk(G):
    for f in sorted(fs):
        if f.lower().endswith(".usg"):
            sample.append(os.path.join(dp, f))
sample = sample[:12]
for p in sample:
    rel = os.path.relpath(p, G)
    try:
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            if "units.yml" not in names or "document/units.yml" not in names:
                P("  %-46s 缺文件 (根units=%s, doc=%s)" % (rel[:46], "units.yml" in names, "document/units.yml" in names))
                continue
            a = yaml.safe_load(zf.read("units.yml"))
            b = yaml.safe_load(zf.read("document/units.yml"))
            A = set(e.get("id") for e in a) if isinstance(a, list) else set()
            B = set(e.get("id") for e in b) if isinstance(b, list) else set()
            ra = {e.get("id"): str(e.get("name_brief")) for e in a} if isinstance(a, list) else {}
            rb = {e.get("id"): str(e.get("name_brief")) for e in b} if isinstance(b, list) else {}
            diff = [i for i in (A & B) if ra[i] != rb[i]]
            P("  %-46s 根=%-5d doc=%-5d 根⊂doc=%-5s doc⊂根=%-5s 同id不同名=%d" %
              (rel[:46], len(A), len(B), A <= B, B <= A, len(diff)))
            if diff[:2]:
                P("        例: id%s 根=%s | doc=%s" % (diff[:2], ra[diff[0]][:40], rb[diff[0]][:40]))
    except Exception as e:
        P("  %s ERR %s" % (rel, e))

OUT.close()
print("done")
