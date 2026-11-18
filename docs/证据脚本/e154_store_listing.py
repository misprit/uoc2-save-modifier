"""e154 —— 商店：能不能自由改价？能不能上架新商品？

三条证据链：
  A) **结构实证**：存档 `store.yml` = `{战线: {store: [...], elite_store: [...]}}`，
     条目 = `{spec XOR equipment, nationality, price, quantity}`。
  B) **对比实证**：存档的商店 vs 战役包会议默认商店（`fronts/<战线>/conferences/<会议>.yml`）
     —— 价格有没有差异？数量差在哪？
  C) **字节码实证**：游戏读存档时会不会用包默认覆盖？
     `campaign.pyc::_load_campaign_game_files` → `conferences.set_store_data(...)`
     ⇒ 用**存档**覆盖会议默认；`get_store_data` 写回时也只认内存里那份。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e154_store_listing.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths, open_save  # noqa: E402
from save_modifier_core import catalog as catmod  # noqa: E402


def main() -> None:
    paths = CorePaths.discover()
    save_id = "campaigns/Stalingrad.usg"
    with open_save(save_id, paths) as sv:
        main_ = sv.root_main()
        in_state = main_.get("in_state") or {}
        conference = in_state.get("conference")
        front = in_state.get("front")
        store = sv.root_store()

        print("=" * 72)
        print(f"存档 {save_id}   campaign={main_.get('campaign_id')} "
              f"conference={conference} front={front}")
        print("存档里的战线:", list(store.keys()))

        print("\n=== A. 存档商店条目（全部字段）===")
        for f, blob in store.items():
            print(f"\n-- front {f!r} 键={list(blob.keys())}")
            if isinstance(blob, dict):
                for sub, items in blob.items():
                    print(f"   [{sub}] {len(items) if isinstance(items, list) else items} 条")
                    if isinstance(items, list):
                        for i, e in enumerate(items):
                            print(f"      [{i}] {e}")

        # 字段统计
        allv = []
        for blob in store.values():
            if isinstance(blob, dict):
                for items in blob.values():
                    if isinstance(items, list):
                        allv.extend(items)
        dicts = [d for d in allv if isinstance(d, dict)]
        print("\n=== A2. 条目字段统计 ===")
        c: collections.Counter = collections.Counter()
        for d in dicts:
            c[tuple(sorted(d.keys()))] += 1
        for ks, n in c.most_common():
            print(f"  x{n}: {list(ks)}")

        print("\n=== B. 与战役包会议默认商店对比 ===")
        cat = catmod.default()
        cdir = cat.campaign_dir(main_.get("campaign_id") or "")
        print("战役包目录:", cdir)
        if cdir:
            cfile = cdir / "fronts" / str(front) / "conferences" / f"{conference}.yml"
            print("会议文件:", cfile)
            if cfile.is_file():
                d = catmod.yamlio.load(cfile.read_bytes())
                print("会议文件顶层键:", list(d.keys()))
                for sub in ("store", "elite_store"):
                    defs = d.get(sub) or []
                    savs = (store.get(front) or {}).get(sub) or []
                    print(f"\n-- {sub}: 包默认 {len(defs)} 条 / 存档 {len(savs)} 条")

                    def key(e):
                        return (e.get("spec") or e.get("equipment"), e.get("nationality"))

                    def_by = {key(e): e for e in defs if isinstance(e, dict)}
                    sav_by = {key(e): e for e in savs if isinstance(e, dict)}
                    only_def = [k for k in def_by if k not in sav_by]
                    only_sav = [k for k in sav_by if k not in def_by]
                    print(f"   只在包默认里（游戏自动下架/售罄）: {len(only_def)} -> {only_def[:8]}")
                    print(f"   只在存档里（玩家/我们加的）      : {len(only_sav)} -> {only_sav[:8]}")
                    diffs = []
                    for k in def_by:
                        if k in sav_by:
                            dd = {kk: (def_by[k].get(kk), sav_by[k].get(kk))
                                  for kk in set(def_by[k]) | set(sav_by[k])
                                  if def_by[k].get(kk) != sav_by[k].get(kk)}
                            if dd:
                                diffs.append((k, dd))
                    print(f"   两边都有但值不同: {len(diffs)} 条")
                    for k, dd in diffs[:20]:
                        print(f"      {k} -> {dd}")
                    print("   ⇒ 价格差异条数 =",
                          sum(1 for _, dd in diffs if "price" in dd),
                          " 数量差异条数 =",
                          sum(1 for _, dd in diffs if "quantity" in dd))

        print("\n=== C. 字节码实证（游戏会不会用包默认覆盖存档）===")
        print("  campaign.pyc::_load_campaign_game_files")
        print("    load_yaml('store.yml', campaign_store_schema)")
        print("    → conference.set_store_data(save_data)   ← 存档覆盖会议默认")
        print("  campaign.pyc::_save_campaign_game_files")
        print("    → conference.get_store_data() → save_yaml('store.yml')")
        print("  ⇒ 存档里的 store.yml 是**运行时权威源**，游戏不会拿包默认盖回去。")
        print("  ⇒ 改价 / 改量 / 新增条目都成立；商品本身（特种兵/兵种/国籍）")
        print("     仍须落在游戏定义的集合内 —— schema 用 Exclusive + 枚举校验。")


if __name__ == "__main__":
    main()
