"""e155 —— 卡牌：有多少种？数值在哪？贴图怎么对应文件？

三条结论：
  A) ~~**没有"卡牌商店"**~~ —— **这条后来被推翻了（见 e157 / e158）**。
     卡牌商店确实存在，= 存档 `main.yml.card_store`，与手牌同字段。
     本脚本当时取样的存档不在会议阶段，`card_store` 是 `None`，
     误当成"功能不存在"。**别用"字段为空"推断"功能不存在"。**
     会议阶段的实测见 `e157_card_store.py`。
  B) 卡牌**数值**在 `entity_types/cards/*.yml`（39 个类型）：
     cost / description / faction / has_unit / image / layout / meta_type /
     persistent / recoup / reward / subtitle / theater_asset / title。
     存档 `cards.yml` 只存 `{card_type, is_free, position, unit_id, used}`。
  C) **贴图文件名不等于 `image` 字段** —— 实测 `image: cards/air_attack_allies`
     对应的实际文件是 `cards/bgt_air_attack_allies.png`。
     ⇒ 查找要按前缀依次试：`bgt_` → `bgmf_` → `bgm_` → `logo_` → 精确名 → 兜底。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e155_card_types.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths, open_save  # noqa: E402
from save_modifier_core import catalog as catmod  # noqa: E402

#: 贴图前缀的尝试顺序（实测：`image` 字段是逻辑名，文件名带前缀）
PREFIXES = ("bgt_", "bgmf_", "bgm_", "logo_")

#: 阵营后缀 —— 实测有些文件把阵营去掉了（`sabotage_allies` → `bgm_sabotage.png`）
FACTIONS = ("allies", "axis", "soviet")


def resolve_image(base: str, files: list[str], type_name: str = "") -> str | None:
    """逻辑图名 → 实际 PNG 文件名（找不到返回 None）。

    顺序：
      ① 前缀 + 原名      ② 原名
      ③ 去阵营后缀后重复 ①②
      ④ 类型名兜底（伞兵卡 `logo_divisional_para_allies_1.png`、
         空中舰队 `bgt_air_fleet_axis.png` —— 两者都跟 `image` 字段对不上）
    """
    cands: list[str] = []
    stripped = (base.rsplit("_", 1)[0]
                if base.rsplit("_", 1)[-1] in FACTIONS else base)
    for b in (base, stripped):
        cands.extend(f"{p}{b}.png" for p in PREFIXES)
        cands.append(f"{b}.png")
    if type_name:
        cands.extend(f"{p}{type_name}.png" for p in PREFIXES)
        cands.append(f"{type_name}.png")
    for c in cands:
        if c in files:
            return c
    hits = [f for f in files if base in f]
    return hits[0] if hits else None


def main() -> None:
    paths = CorePaths.discover()
    cat = catmod.default()

    print("=== A. 存档里的手牌 ===")
    with open_save("campaigns/Stalingrad.usg", paths) as sv:
        cards = sv.root_cards()
        print("cards.yml:", len(cards), "张")
        for c in cards:
            print("   ", c)
        print("main.yml.card_store（当前会议发到手里的牌）:", sv.card_store())
        print("\n--- L2 里的抽卡概率表 ---")
        for n in sv.list_names():
            if n.startswith("document/conferences/"):
                d = sv.read_yaml(n, None)
                if isinstance(d, dict) and "card_probabilities" in d:
                    print(f"   {n}: {d['card_probabilities']}")

    print("\n=== B. 卡牌类型定义 entity_types/cards/ ===")
    cidx = cat._index("cards")
    print("类型数:", len(cidx))
    fc: collections.Counter = collections.Counter()
    for n in cidx:
        d = cat._load("cards", n) or {}
        for k in d:
            fc[k] += 1
    for k, n in fc.most_common():
        print(f"   {k}: {n}")
    print("\n全部类型名:")
    for n in sorted(cidx):
        d = cat._load("cards", n) or {}
        print(f"   {n:32s} cost={d.get('cost')!s:5s} meta={d.get('meta_type')!s:22s} "
              f"asset={d.get('theater_asset')!s:20s} image={d.get('image')}")

    print("\n=== C. 贴图文件对应 ===")
    surf = None
    for p in paths.packages():
        d = p / "assets" / "surfaces"
        if d.is_dir():
            surf = d
            break
    print("surfaces:", surf)
    carddir = surf / "cards" if surf else None
    files = sorted(p.name for p in carddir.iterdir()) if carddir and carddir.is_dir() else []
    print(f"cards/ 共 {len(files)} 个 PNG")
    hit = miss = 0
    for n in sorted(cidx):
        d = cat._load("cards", n) or {}
        img = d.get("image") or ""
        base = img.split("/")[-1]
        r = resolve_image(base, files, n)
        flag = "OK " if r else "占位"
        if r:
            hit += 1
        else:
            miss += 1
        print(f"   {flag} {n:32s} image={img:34s} -> {r}")
    print(f"\n⇒ 能贴到图: {hit} 种，需要占位: {miss} 种")
    print("   前缀优先级:", " → ".join(PREFIXES), "→ 精确名 → 占位")


if __name__ == "__main__":
    main()
