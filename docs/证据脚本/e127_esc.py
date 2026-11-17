import zipfile, re
from pathlib import Path
root = Path.home()/"AppData"/"Local"/".uoc2"/"save"
saves=[]
for d in ("campaigns","games","Old Saves"):
    p=root/d
    if p.is_dir(): saves += list(p.rglob("*.usg"))
esc = re.compile(rb'\\u[0-9A-Fa-f]{4}')
shown=0
for sv in saves:
    with zipfile.ZipFile(sv) as zf:
        for name in zf.namelist():
            if name not in ("main.yml","units.yml","hqs.yml","cards.yml","store.yml"): continue
            raw=zf.read(name)
            for line in raw.split(b"\n"):
                if esc.search(line):
                    print(f"{sv.name} :: {name} :: {line[:150]}")
                    shown+=1
                    break
            if shown>=8: break
    if shown>=8: break
