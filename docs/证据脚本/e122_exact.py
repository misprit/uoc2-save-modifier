import sys, zipfile, difflib
from pathlib import Path
sys.path.insert(0, r"E:\Workspace\projects\统一指挥数据整理\uoc2-save-modifier\src")
import yaml
from save_modifier_core import yamlio

class GameDumper(yaml.SafeDumper):
    def check_short_list(self, l):
        s = 1 <= len(l) < 5 and all(isinstance(e, (int, float, str)) for e in l)
        return self.represent_sequence('tag:yaml.org,2002:seq', l, flow_style=s)
    def str_representer(self, data):
        if len(data) > 100:
            return self.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return self.represent_scalar('tag:yaml.org,2002:str', data)
    def float_representer(self, data):
        return self.represent_scalar('tag:yaml.org,2002:float', str(float(data)))
    def bool_representer(self, data):
        return self.represent_bool(data)
    def int_representer(self, data):
        return self.represent_int(data)
GameDumper.add_representer(list, GameDumper.check_short_list)
GameDumper.add_representer(str, GameDumper.str_representer)
GameDumper.add_representer(float, GameDumper.float_representer)
GameDumper.add_representer(bool, GameDumper.bool_representer)
GameDumper.add_representer(int, GameDumper.int_representer)

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
            for sk in (False, True):
                out=yaml.dump(data, Dumper=GameDumper, default_flow_style=False, allow_unicode=False, sort_keys=sk).encode("utf-8")
                if sk is False:
                    if out==raw: ok+=1
                    else:
                        bad+=1; badlist.append((sv.name,name,raw,out))
                else:
                    if out!=raw: badlist.append((sv.name,name+"[sk=T]",raw,out))
print(f"游戏 dumper（1<=len<5, au=F）: 一致 {ok} / 不一致 {bad} / 共 {ok+bad}")
for sv,name,raw,out in badlist[:3]:
    print(f"\n=== {sv} :: {name} ===")
    d=list(difflib.unified_diff(raw.decode('utf-8').splitlines(), out.decode('utf-8').splitlines(), n=1))
    print("\n".join(d[:24]))
