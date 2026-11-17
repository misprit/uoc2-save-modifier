"""挑几个真实单位类型（含 equipment / max_st / movement），供 GUI 视觉稿用真贴图。"""

from __future__ import annotations

from pathlib import Path

UT = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\data\entity_types\unit_types")
SUR = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\assets\surfaces\unit")

want = ["us_arm_42", "us_inf_42", "ger_pz_dlc7", "bel_cav_40", "yug_cav_41", "sws_mtn_40",
        "uk_arm_div_late_dlc6", "us_mot_dlc7", "ger_inf_40", "sws_inf_40"]

for name in want:
    f = UT / f"{name}.yml"
    if not f.is_file():
        print(f"{name}: 无类型文件")
        continue
    data = {}
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    d = SUR / name
    art = [p.name for p in d.iterdir() if p.suffix.lower() == ".png"] if d.is_dir() else []
    print(f"{name}: movement={data.get('movement')} eq={data.get('equipment')}/{data.get('equipment_q')} "
          f"max_st={data.get('max_st')} max_spec={data.get('max_spec')} nat={data.get('nationality')} 贴图={sorted(art)}")

print("\n--- 所有 max_st=6 且 movement=infantry 的类型（取 8 个）---")
n = 0
for f in sorted(UT.glob("*.yml")):
    text = f.read_text(encoding="utf-8", errors="replace")
    if "max_st: 6" in text and "movement: infantry" in text and (SUR / f.stem).is_dir():
        print("   ", f.stem)
        n += 1
        if n >= 8:
            break
