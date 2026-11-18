"""e153 —— 存档 5 张 L1 表的字段结构全量取证。

回答：总部 / 卡牌 / 商店 / 单位 / 进度 各自有哪些字段，哪些能改。
依据：真实存档 `campaigns/Stalingrad.usg`（4 个战役存档里最大的一个）。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e153_save_structures.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths, list_saves, open_save  # noqa: E402


def keysets(rows) -> list[tuple[tuple[str, ...], int]]:
    """一组 dict 的字段组合统计（降序）。"""
    c: collections.Counter = collections.Counter()
    for r in rows:
        if isinstance(r, dict):
            c[tuple(sorted(r.keys()))] += 1
    return c.most_common()


def main() -> None:
    paths = CorePaths.discover()
    saves = [s for s in list_saves(paths) if s.kind == "campaign" and not s.archived]
    if not saves:
        print("没找到战役存档")
        return
    saves.sort(key=lambda s: -(s.size or 0))
    target = saves[0]
    print("存档根:", paths.save_root)
    print("存档总数:", len(list_saves(paths)), " 战役存档:", len(saves))
    print("选定:", target.save_id, target.size, "B")

    with open_save(target.save_id, paths) as sv:
        names = sv.list_names()
        print("\n=== A. ZIP 分层 ===")
        print("L1 根目录:", [n for n in names if "/" not in n])
        for pref in ("document/", "games/", "game/"):
            sub = [n for n in names if n.startswith(pref)]
            if sub:
                tops = sorted({n[len(pref):].split("/")[0] for n in sub})
                print(f"{pref}*  {len(sub)} 条，一级子目录 {len(tops)}: {tops}")

        print("\n=== B. units.yml（单位）===")
        units = sv.root_units()
        print("单位数:", len(units))
        for ks, n in keysets(units):
            print(f"  x{n}: {list(ks)}")
        print("  specs 的结构:", units[0].get("specs"), "← 只有 type 引用 + 状态标志，无数值")
        for u in units:
            if u.get("specs"):
                print("  带 specs 的单位示例:", {k: u[k] for k in ("id", "type", "specs")})
                break

        print("\n=== C. hqs.yml（总部）===")
        hqs = sv.root_hqs()
        print("总部数:", len(hqs))
        for ks, n in keysets(hqs):
            print(f"  x{n}: {list(ks)}")
        h = hqs[0]
        print(f"  示例 id={h.get('id')} name={h.get('name_brief')}")
        print(f"    经验 xp={h.get('xp')} / xp_target={h.get('xp_target')}")
        print(f"    指挥点 cp={h.get('cp')} / max_cp={h.get('max_cp')}")
        print(f"    分支等级 branch_levels={h.get('branch_levels')}")
        print(f"    兵库 force_pool={h.get('force_pool')}")

        print("\n=== D. cards.yml（卡牌）===")
        cards = sv.root_cards()
        print("手牌数:", len(cards))
        for ks, n in keysets(cards):
            print(f"  x{n}: {list(ks)}")
        for c in cards:
            print("   ", c)
        print("  main.yml.card_store（当前会议发到手里的牌）:", sv.card_store())

        print("\n=== E. store.yml（商店）===")
        store = sv.root_store()
        for front, blob in store.items():
            print(f"  front {front!r}: 键 = {list(blob.keys()) if isinstance(blob, dict) else type(blob)}")
            if isinstance(blob, dict):
                for sub, items in blob.items():
                    print(f"    {sub}: {len(items) if isinstance(items, list) else items}")
                    if isinstance(items, list):
                        for i, e in enumerate(items):
                            print(f"      [{i}] {e}")


if __name__ == "__main__":
    main()
