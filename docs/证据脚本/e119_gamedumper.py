"""实验：复刻游戏自己的 YAML 序列化器（字节码还原），检查往返是否字节一致。

游戏的 tools/yaml_.py（字节码实证）：
    yaml.dump(obj, Dumper=_Dumper, default_flow_style=False)
  _Dumper.add_representer(list,  check_short_list)   # 1<=len<=5 且全是标量 ⇒ 流式
  _Dumper.add_representer(set,   set_representer)     # sorted
  _Dumper.add_representer(str,   str_representer)      # len>100 ⇒ 块样式 '|'
  _Dumper.add_representer(int,   int_representer)
  _Dumper.add_representer(float, float_representer)    # str(float(x))
  _Dumper.add_representer(bool,  bool_representer)
  yaml.dump(..., default_flow_style=False)  ⇒ 字典/长列表一律块样式
"""
import sys, zipfile, io
from pathlib import Path
sys.path.insert(0, r"E:\Workspace\projects\统一指挥数据整理\uoc2-save-modifier\src")
import yaml
from save_modifier_core import yamlio


class GameDumper(yaml.SafeDumper):
    def check_short_list(self, l):
        s = 1 <= len(l) <= 5 and all(isinstance(e, (int, float, str)) for e in l)
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


def game_dump(data, allow_unicode, sort_keys):
    return yaml.dump(data, Dumper=GameDumper, default_flow_style=False,
                      allow_unicode=allow_unicode, sort_keys=sort_keys).encode("utf-8")


root = Path.home() / "AppData" / "Local" / ".uoc2" / "save"
saves = []
for d in ("campaigns", "games", "Old Saves"):
    p = root / d
    if p.is_dir():
        saves += list(p.rglob("*.usg"))

L1 = ("main.yml", "units.yml", "hqs.yml", "cards.yml", "store.yml")
variants = {
    "au=T sk=F": dict(allow_unicode=True, sort_keys=False),
    "au=T sk=T": dict(allow_unicode=True, sort_keys=True),
    "au=F sk=T": dict(allow_unicode=False, sort_keys=True),
    "au=F sk=F": dict(allow_unicode=False, sort_keys=False),
}
stats = {k: [0, 0] for k in variants}   # [一致, 不一致]
total = 0
for sv in saves:
    try:
        with zipfile.ZipFile(sv) as zf:
            for name in zf.namelist():
                if name not in L1:
                    continue
                raw = zf.read(name)
                try:
                    data = yamlio.load(raw)
                except Exception:
                    continue
                if data is None:
                    continue
                total += 1
                for k, kw in variants.items():
                    try:
                        out = game_dump(data, **kw)
                    except Exception as e:
                        stats[k][0] += 0
                        continue
                    if out == raw:
                        stats[k][0] += 1
                    else:
                        stats[k][1] += 1
    except Exception:
        continue

print(f"L1 条目总数: {total}")
for k, (ok, bad) in stats.items():
    print(f"  {k:12s} 字节一致 {ok:5d}  不一致 {bad:5d}  ⇒ {ok/max(1,ok+bad)*100:.1f}%")
