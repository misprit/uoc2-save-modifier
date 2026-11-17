# -*- coding: utf-8 -*-
"""E5: 场景预设为何没有 type？games/<场景>/enroute_units.yml 是什么？字节码反查单位装载路径"""
import os, io, zipfile, yaml, marshal, dis, types

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e5_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

def zl(zf, n, d=None):
    try:
        return yaml.safe_load(zf.read(n).decode("utf-8"))
    except KeyError:
        return d

p = os.path.join(G, r"campaigns\Stalingrad.usg")
with zipfile.ZipFile(p) as zf:
    names = zf.namelist()

    P("=" * 100)
    P("[A] document/scenarios/road_to_stalingrad/ 全部文件")
    P("=" * 100)
    for n in sorted(x for x in names if x.startswith("document/scenarios/road_to_stalingrad/")):
        P(f"    {n}")

    P("")
    P("=" * 100)
    P("[B] games/road_to_stalingrad/enroute_units.yml 全文（实时行军文件）")
    P("=" * 100)
    v = zl(zf, "games/road_to_stalingrad/enroute_units.yml")
    P(f"    类型 {type(v).__name__} 长度 {len(v) if hasattr(v,'__len__') else '?'}")
    P("      " + yaml.safe_dump(v, allow_unicode=True, sort_keys=False).replace("\n", "\n      "))

    P("")
    P("=" * 100)
    P("[C] games/road_to_stalingrad/hqs.yml 前 2 条（总部格式）")
    P("=" * 100)
    h = zl(zf, "games/road_to_stalingrad/hqs.yml")
    P(f"    类型 {type(h).__name__} 长度 {len(h)}")
    P("      " + yaml.safe_dump(h[:2] if isinstance(h, list) else h, allow_unicode=True,
                              sort_keys=False).replace("\n", "\n      "))

    P("")
    P("=" * 100)
    P("[D] 场景预设条目 vs 根总表条目（id=2）—— type 从哪来？")
    P("=" * 100)
    scen_u = {u["id"]: u for u in zl(zf, "document/scenarios/road_to_stalingrad/units.yml")}
    root_u = {u["id"]: u for u in zl(zf, "units.yml")}
    for i in (2, 20, 95):
        s = scen_u.get(i); r = root_u.get(i)
        P(f"    --- id {i}")
        P(f"        场景预设: {s}")
        P(f"        根总表  : {r}")

    P("")
    P("=" * 100)
    P("[E] 根总表里 type 与 name_brief 的对应（看 type 能否由 name 反查）")
    P("=" * 100)
    n2t = {}
    for u in zl(zf, "units.yml"):
        n2t.setdefault(u.get("name_brief"), set()).add(u.get("type"))
    multi = {k: v for k, v in n2t.items() if len(v) > 1}
    P(f"    name_brief -> type 一对多的数量: {len(multi)} / {len(n2t)}")
    for k, v in list(multi.items())[:5]:
        P(f"        {k!r} -> {v}")
    # hq_id -> type
    h2t = {}
    for u in zl(zf, "units.yml"):
        h2t.setdefault(u.get("hq_id"), set()).add(u.get("type"))
    multi2 = {k: v for k, v in h2t.items() if len(v) > 1}
    P(f"    hq_id -> type 一对多的数量: {len(multi2)} / {len(h2t)}")
    for k, v in list(multi2.items())[:5]:
        P(f"        hq_id {k} -> {v}")

    P("")
    P("=" * 100)
    P("[F] 字节码：campaign.pyc 中引用 'units.yml' 的函数")
    P("=" * 100)
    LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib"

    def load(rel):
        fp = os.path.join(LIB, rel)
        return marshal.loads(open(fp, "rb").read()[16:])

    def show(code, path="", depth=0):
        for c in code.co_consts:
            if isinstance(c, types.CodeType):
                consts = [x for x in c.co_consts if isinstance(x, str)]
                if any(s in ("units.yml", "campaign_units.yml") for s in consts):
                    P(f"    {'  '*depth}{path}/{c.co_name}  args={c.co_varnames[:c.co_argcount]}")
                    P(f"    {'  '*depth}  字符串常量: {[s for s in consts if len(s)<80]}")
                    P(f"    {'  '*depth}  名称常量: {[n for n in c.co_names]}")
                    P(f"    {'  '*depth}  调用: {[n for n in c.co_names if n in ('open','read','write','yaml_load','yaml_dump','save','load','save_campaign','load_campaign')]}")
                show(c, path + "/" + c.co_name, depth + 1)

    for rel in ["uoc2\\state\\campaign\\campaign.pyc",
                "uoc2\\state\\entities\\unit.pyc",
                "uoc2\\state\\scenario\\scenario.pyc",
                "uoc2\\state\\gamelike\\gamelike.pyc"]:
        P(f"  --- {rel}")
        try:
            show(load(rel))
        except Exception as e:
            P(f"      读取失败 {e}")

    P("")
    P("=" * 100)
    P("[G] campaign.pyc 全部字符串常量里与单位/名册有关的")
    P("=" * 100)
    code = load("uoc2\\state\\campaign\\campaign.pyc")
    allstr = set()
    def walk(c):
        for k in c.co_consts:
            if isinstance(k, str):
                allstr.add(k)
            elif hasattr(k, "co_consts"):
                walk(k)
    walk(code)
    for s in sorted(allstr):
        if any(w in s.lower() for w in ("unit", "roster", "campaign", "save", "load", "write", "read")) and len(s) < 70:
            P(f"    {s!r}")

OUT.close()
print("done")
