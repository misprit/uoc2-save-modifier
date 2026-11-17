import sys, zipfile
from pathlib import Path
sys.path.insert(0, r"E:\Workspace\projects\统一指挥数据整理\uoc2-save-modifier\src")
from save_modifier_core import yamlio
print("C 解析器:", yamlio.has_fast_loader(), " C 序列化器:", yamlio.has_fast_dumper())
root = Path.home()/"AppData"/"Local"/".uoc2"/"save"
saves=[]
for d in ("campaigns","games","Old Saves"):
    p=root/d
    if p.is_dir(): saves += list(p.rglob("*.usg"))
L1=("main.yml","units.yml","hqs.yml","cards.yml","store.yml")
ok=bad=0; badlist=[]
for sv in saves:
    with zipfile.ZipFile(sv) as zf:
        for name in zf.namelist():
            if name not in L1: continue
            raw=zf.read(name)
            try: data=yamlio.load(raw)
            except Exception: continue
            if data is None: continue
            out=yamlio.dump(data)
            if out==raw: ok+=1
            else:
                bad+=1; badlist.append((sv.name,name,raw,out))
print(f"核心库 dump 往返: 字节一致 {ok} / 不一致 {bad} / 共 {ok+bad}")
for sv,name,raw,out in badlist[:3]:
    import difflib
    print(f"--- {sv} :: {name} ---")
    d=list(difflib.unified_diff(raw.decode('utf-8').splitlines(), out.decode('utf-8').splitlines(), n=1))
    print("\n".join(d[:20]))
