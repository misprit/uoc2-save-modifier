import sys, zipfile
from pathlib import Path
sys.path.insert(0, r"E:\Workspace\projects\统一指挥数据整理\uoc2-save-modifier\src")
sys.path.insert(0, r"D:\MiniMax\_analysis")
from e119_gamedumper import GameDumper, game_dump
from save_modifier_core import yamlio

root = Path.home()/"AppData"/"Local"/".uoc2"/"save"
saves=[]
for d in ("campaigns","games","Old Saves"):
    p=root/d
    if p.is_dir(): saves += list(p.rglob("*.usg"))
L1=("main.yml","units.yml","hqs.yml","cards.yml","store.yml")
bad=[]
nonascii=[]
for sv in saves:
    with zipfile.ZipFile(sv) as zf:
        for name in zf.namelist():
            if name not in L1: continue
            raw=zf.read(name)
            try: data=yamlio.load(raw)
            except Exception: continue
            if data is None: continue
            out=game_dump(data, allow_unicode=False, sort_keys=False)
            if out!=raw:
                bad.append((sv.name,name,raw,out))
            if any(b>=0x80 for b in raw):
                nonascii.append((sv.name,name))
print("不一致条目数:", len(bad))
for sv,name,raw,out in bad[:4]:
    print(f"\n=== {sv} :: {name} ===")
    import difflib
    d=list(difflib.unified_diff(raw.decode('utf-8').splitlines(), out.decode('utf-8').splitlines(), n=1))
    print("\n".join(d[:28]))
print("\n含非 ASCII 的条目:", len(nonascii))
for x in nonascii[:6]: print("  ", x)
