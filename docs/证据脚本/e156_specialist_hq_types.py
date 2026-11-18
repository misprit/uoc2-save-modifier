"""e156 —— 特种兵与总部：数值在哪？存档里能改什么？

**特种兵（结论：数值不可改，"挂了谁"可改）**
  * 数值全在 `entity_types/specialists/*.yml`（375 个类型）：
    faction / nationality / name_brief / name_full / attack / defense /
    armor / artillery / att_idx / dfe_idx / flags
  * 存档 `units.yml` 的 `specs` = `[{active, captured, idx, type}]`
    ⇒ **只有类型引用 + 3 个状态标志，一个数值都没有**。
  * ⇒ 改数值要改游戏包（mod 范畴，超出 L1 白名单）；改"谁挂了谁"在存档里，
    核心库已有 `unit_spec_add` / `unit_spec_remove`。

**总部（结论：可改的点很多）**
  * 存档 `hqs.yml` 的字段：`xp` / `xp_target`（经验与升级目标）、
    `branch_levels`（engineering / force_pool / intel / logistics / operations
    五个分支的 level + suppressed —— 这就是"总部升级"）、
    `force_pool`（总部兵库：`{delay, nationality, quantity, spec?|equipment?}`）、
    `cp` / `max_cp` / `supply` / `trucks` / `prisoners` / `loss_count` /
    `overrun` / `turn_disbanded` / `intels_revealed` / `general` / `template` …
  * 总部**类型定义** `entity_types/hq_types/*.yml`（213 个）给出
    每个分支的解锁 action 树（action / cost / level）与 `init_levels`。
  * ⇒ 总部页要展示：经验条（xp → xp_target）、五个分支等级、兵库清单。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e156_specialist_hq_types.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths  # noqa: E402
from save_modifier_core import catalog as catmod  # noqa: E402


def field_count(cat, kind: str) -> collections.Counter:
    c: collections.Counter = collections.Counter()
    for n in cat._index(kind):
        d = cat._load(kind, n) or {}
        for k in d:
            c[k] += 1
    return c


def main() -> None:
    paths = CorePaths.discover()
    cat = catmod.default()

    print("=" * 72)
    print("### A. 特种兵类型定义 entity_types/specialists/")
    sidx = cat._index("specialists")
    print("类型数:", len(sidx))
    for k, n in field_count(cat, "specialists").most_common():
        print(f"   {k}: {n}")
    sample = sorted(sidx)[0]
    print(f"\n--- 样例 {sample}.yml ---")
    print(sidx[sample].read_text(encoding="utf-8", errors="replace"))
    print("⇒ 上面这些数值（attack/defense/armor/artillery…）全在**游戏包里**，存档里没有。")

    print("\n### B. 总部类型定义 entity_types/hq_types/")
    hidx = cat._index("hq_types")
    print("类型数:", len(hidx))
    for k, n in field_count(cat, "hq_types").most_common():
        print(f"   {k}: {n}")
    hs = sorted(hidx)[0]
    print(f"\n--- 样例 {hs}.yml ---")
    print(hidx[hs].read_text(encoding="utf-8", errors="replace"))
    print("⇒ branches 给出每个分支的解锁 action 树；init_levels 是初始等级。")

    print("\n### C. 存档里总部的实际字段（来自 e153 的结论，这里复核）")
    from save_modifier_core import open_save
    with open_save("campaigns/Stalingrad.usg", paths) as sv:
        hqs = sv.root_hqs()
        print("总部数:", len(hqs))
        keys = sorted({k for h in hqs for k in h})
        print("字段全集:", keys)
        branches = collections.Counter()
        for h in hqs:
            for b in (h.get("branch_levels") or {}):
                branches[b] += 1
        print("branch_levels 里的分支:", dict(branches))
        fp_keys = collections.Counter()
        for h in hqs:
            for e in (h.get("force_pool") or []):
                for k in e:
                    fp_keys[k] += 1
        print("force_pool 条目字段:", dict(fp_keys))
        h = hqs[0]
        print(f"\n示例：id={h.get('id')} xp={h.get('xp')}/{h.get('xp_target')} "
              f"cp={h.get('cp')}/{h.get('max_cp')}")
        print("  branch_levels:", h.get("branch_levels"))
        print("  force_pool   :", h.get("force_pool"))


if __name__ == "__main__":
    main()
