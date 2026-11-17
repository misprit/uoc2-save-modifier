import os, zipfile, yaml, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
c = collections.Counter(); keys = collections.Counter(); lg_keys = collections.Counter()
for dp, _, fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"):
            continue
        with zipfile.ZipFile(os.path.join(dp, f)) as zf:
            names = zf.namelist()
            m = yaml.safe_load(zf.read("main.yml")) or {}
            kind = "独立" if m.get("standalone_scenario") else "战役"
            ins = m.get("in_state") or {}
            c[(kind, "conference非空", bool(ins.get("conference")))] += 1
            c[(kind, "variant非空", bool(ins.get("variant")))] += 1
            c[(kind, "fronts有segment", any((v or {}).get("segment") for v in (ins.get("fronts") or {}).values()))] += 1
            c[(kind, "level", m.get("level"))] += 1
            c[(kind, "completed", (ins.get("completed")))] += 1
            keys[(kind, len(m))] += 1
            if "last_game/main.yml" in names:
                lg = yaml.safe_load(zf.read("last_game/main.yml")) or {}
                lg_keys[(kind, tuple(sorted(lg)) == tuple(sorted(m)))] += 1
for k, v in sorted(c.items(), key=lambda x: str(x[0])):
    print(k, v)
print("--- main.yml 顶层键数分布 ---")
for k, v in sorted(keys.items()):
    print(k, v)
print("--- last_game/main.yml 键集 == 根 main.yml 键集 ---")
for k, v in sorted(lg_keys.items()):
    print(k, v)
