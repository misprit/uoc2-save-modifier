"""e157 —— 卡牌商店：会议阶段激活时的存档长什么样？

背景：用户指出「卡牌商店确实存在，只是我拿的存档不在会议阶段，
所以 `main.yml.card_store` 是 None，看起来像没有卡牌商店」。
本脚本用**会议阶段激活卡牌商店**的存档复核。

存档：C:\\Users\\misprit\\.minimax\\v2\\assets\\2026\\11\\18\\11-15-18-766-\
      asset_20261118-111518-766_c2c3a7a10319_1c0b943e-Blitzkrieg-ahistorical-Conference4-alter.usg

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e157_card_store.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths, open_save  # noqa: E402

SAVE = Path(
    r"C:\Users\misprit\.minimax\v2\assets\2026\11\18\11-15-18-766-"
    r"asset_20261118-111518-766_c2c3a7a10319_1c0b943e-Blitzkrieg-ahistorical-Conference4-alter.usg"
)


def keysets(rows):
    c: collections.Counter = collections.Counter()
    for r in rows:
        if isinstance(r, dict):
            c[tuple(sorted(r.keys()))] += 1
    return c.most_common()


def dump(obj, indent=0, maxdepth=4):
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and maxdepth > 0:
                print(f"{pad}{k}:")
                dump(v, indent + 1, maxdepth - 1)
            else:
                print(f"{pad}{k}: {v!r}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)) and maxdepth > 0:
                print(f"{pad}[{i}]:")
                dump(v, indent + 1, maxdepth - 1)
            else:
                print(f"{pad}[{i}]: {v!r}")
    else:
        print(f"{pad}{obj!r}")


def main() -> None:
    paths = CorePaths.discover()
    print("存档:", SAVE.name, SAVE.stat().st_size, "B")
    with open_save(str(SAVE), paths) as sv:
        names = sv.list_names()
        print("\n=== A. ZIP 分层 ===")
        print("L1 根目录:", [n for n in names if "/" not in n])
        for pref in ("document/", "games/", "game/"):
            sub = [n for n in names if n.startswith(pref)]
            if sub:
                tops = sorted({n[len(pref):].split("/")[0] for n in sub})
                print(f"{pref}*  {len(sub)} 条，一级子目录 {len(tops)}: {tops[:20]}")

        main_ = sv.root_main()
        in_state = main_.get("in_state") or {}
        print("\n=== B. main.yml 顶层键 ===")
        print(sorted(main_.keys()))
        print(f"\n campaign_id = {main_.get('campaign_id')!r}")
        print(f" conference = {in_state.get('conference')!r}  front = {in_state.get('front')!r}")
        print(f" conference_start_state = {main_.get('conference_start_state')!r}")

        print("\n=== C. ★ card_store（卡牌商店！）===")
        cs = main_.get("card_store")
        if cs is None:
            print("  None")
        else:
            print(f"  类型 {type(cs).__name__}，{len(cs) if hasattr(cs, '__len__') else '?'} 条")
            if isinstance(cs, dict):
                print("  顶层键:", list(cs.keys()))
                for k, v in cs.items():
                    print(f"  --- {k} --- ({type(v).__name__})")
                    dump(v, 2, 4)
            elif isinstance(cs, list):
                for i, e in enumerate(cs):
                    print(f"  --- [{i}] ---")
                    dump(e, 2, 4)

        print("\n=== D. cards.yml（手牌）===")
        cards = sv.root_cards()
        print("张数:", len(cards))
        for ks, n in keysets(cards):
            print(f"  x{n}: {list(ks)}")
        for c in cards:
            print("   ", c)

        print("\n=== E. 其余 L1 表的规模 ===")
        print("units:", len(sv.root_units()), " hqs:", len(sv.root_hqs()))
        store = sv.root_store()
        print("store 战线:", list(store.keys()))
        for f, blob in store.items():
            if isinstance(blob, dict):
                for sub, items in blob.items():
                    print(f"   {f}.{sub}: {len(items) if isinstance(items, list) else items}")

        print("\n=== F. L2 里的会议文件（抽卡概率 / 卡牌商店定义）===")
        for n in sorted(names):
            if "conference" in n.lower() and n.endswith(".yml"):
                d = sv.read_yaml(n, None)
                if isinstance(d, dict):
                    ks = list(d.keys())
                    hit = [k for k in ks if "card" in k.lower()]
                    if hit:
                        print(f"  {n}: 全部键={ks}")
                        for k in hit:
                            print(f"     {k} = {str(d[k])[:400]}")


if __name__ == "__main__":
    main()
