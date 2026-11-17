import zipfile, re
from pathlib import Path
root = Path.home()/"AppData"/"Local"/".uoc2"/"save"
saves=[]
for d in ("campaigns","games","Old Saves"):
    p=root/d
    if p.is_dir(): saves += list(p.rglob("*.usg"))
pat = re.compile(rb'[^\x00-\x7f]')
esc = re.compile(rb'\\u[0-9A-Fa-f]{4}')
n_raw=n_esc=0
samples=[]
for sv in saves:
    with zipfile.ZipFile(sv) as zf:
        for name in zf.namelist():
            if name not in ("main.yml","units.yml","hqs.yml","cards.yml","store.yml"): continue
            raw=zf.read(name)
            if pat.search(raw):
                n_raw+=1
                if len(samples)<4:
                    for line in raw.split(b"\n"):
                        if pat.search(line) or esc.search(line):
                            samples.append((sv.name,name,line[:120]))
                            break
            if esc.search(raw): n_esc+=1
print(f"含原始非 ASCII 字节的 L1 条目: {n_raw}")
print(f"含 \\uXXXX 转义的 L1 条目: {n_esc}")
for s in samples: print("  ", s)
