"""e163 —— 「战役默认特种兵」口径的实证（U10 拍板依据）。

**背景**：2026-11-18 用户提出 —— 备选池默认只显示「本战役我方默认的特种兵」，
理由是（a）防止游戏出怪 bug、（b）375 种太多玩家改不动、
（c）1939 年的战役挂 1945 年的特种兵很出戏；并留一个「显示全部」的开关。

**最终口径（用户拍板 + 本脚本实证后微调）**

```
战役默认池 = { 该战役 所有战线×所有会议 的商店 spec }
           ∪ { 该战役 所有场景 units.yml 里 specs[].type 出现过的 }
最终候选   = 战役默认池 ∩ e162 规则可挂集合
```

**结论（全部来自实测）**

| 问题 | 答案 | 出处 |
|---|---|---|
| 游戏自己按战役过滤特种兵吗？ | **不过滤** —— `get_available_spec_types` = 全部 375 种过阵营+国籍规则 | `e162` |
| 商店里是敌国的吗？ | **不是** —— 每个战役的商店**只卖玩家一方阵营**（allies / axis / soviet 各自纯净） | ① |
| 年代对吗？ | **对** —— blitzkrieg 只有 `_39/_40/_42`、barbarossa 只有 `_40/_41/_42`、desert 只有 `_42` | ① |
| 能靠名字后缀判年代吗？ | **不能** —— DLC 战役用 `_dlcN` 命名（`ger_at_dlc10`），18~41 个条目全无年份 | ① |
| **只用商店够吗？** | **不够** —— 商店会漏掉 **113 种**游戏自己在该战役场景里挂过的特种兵（`us_spec_42` / `ff_recon_42` / `ger_at_40` …） | ② |
| **加上场景就够了吗？** | **够了** —— 补齐后**漏 0 种**（玩家阵营口径，跨全部 15 个战役） | ② |
| 候选收敛到多少？ | 玩家方单位类型：e162 规则 30 / 61.9 / 98.4 种 → **∩战役默认池 = 8.1 / 11.0 / 22.2 种** | ③ |
| 会崩溃吗？ | **不会** —— 375 个类型**全部有贴图**，商店条目 100% 能在类型表里查到 | ④ |
| 全游戏覆盖 | 205 / 375 种（54.7%）至少被某个战役卖过；170 种从没被卖过 | ⑤ |
| 敌国单位的坑 | **真实存在** —— 苏联战役里的德国单位 ∩ 战役默认池 = **0 种** ⇒ 必须有兜底 | ⑥ |

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e163_spec_scope.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths, yamlio  # noqa: E402


def _load_dir(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(path.glob("*.yml")):
        d = yamlio.load(p.read_bytes())
        if isinstance(d, dict):
            out[p.stem] = d
    return out


def main() -> int:
    paths = CorePaths.discover()
    pkgs = paths.packages()

    et = surf = None
    for pkg in pkgs:
        d = pkg / "data" / "entity_types"
        if et is None and (d / "specialists").is_dir():
            et = d
        a = pkg / "assets" / "surfaces" / "specialist"
        if surf is None and a.is_dir():
            surf = a
    if et is None or surf is None:
        raise SystemExit("找不到 entity_types/ 或 surfaces/specialist/")

    SPEC = _load_dir(et / "specialists")
    UT = _load_dir(et / "unit_types")
    NAT: dict[str, dict] = {}
    for fn in ("nationalities.yml", "nationalities_2.yml"):
        p = et / fn
        if p.is_file():
            d = yamlio.load(p.read_bytes()) or {}
        else:
            d = {}
        NAT.update({k: v for k, v in d.items() if isinstance(v, dict)})
    dirs = {p.name for p in surf.iterdir() if p.is_dir()}

    def can_add(spec: dict, unit: dict) -> bool:
        """复刻 `UnitState._can_add_specialist_no_len`（captured=False）。"""
        if unit.get("faction") != spec.get("faction"):
            return False
        if unit.get("nationality") != spec.get("nationality"):
            nat = NAT.get(unit.get("nationality")) or {}
            if nat.get("parent_nationality") != spec.get("nationality"):
                return False
        return True

    # ---- 扫战役包 ----
    camp_store: dict[str, set[str]] = defaultdict(set)
    camp_conf: dict[str, int] = defaultdict(int)
    camp_used: dict[str, set[str]] = defaultdict(set)   # 场景里游戏自己挂过的
    for pkg in pkgs:
        camp = pkg / "data" / "campaigns"
        if not camp.is_dir():
            continue
        for c in sorted(camp.iterdir()):
            if not c.is_dir():
                continue
            cid = f"{pkg.name}/{c.stem}"
            for cf in sorted(c.rglob("conferences/*.yml")):
                camp_conf[cid] += 1
                d = yamlio.load(cf.read_bytes()) or {}
                for e in (d.get("store") or []) + (d.get("elite_store") or []):
                    if isinstance(e, dict) and e.get("spec"):
                        camp_store[cid].add(str(e["spec"]))
            for uf in sorted(c.rglob("scenarios/*/units.yml")):
                d = yamlio.load(uf.read_bytes())
                if not isinstance(d, list):
                    continue
                for u in d:
                    if not isinstance(u, dict):
                        continue
                    for s in (u.get("specs") or []):
                        if isinstance(s, dict) and s.get("type"):
                            camp_used[cid].add(str(s["type"]))

    # 战役玩家阵营 = 商店里出现最多的 faction
    camp_pf: dict[str, str] = {}
    for cid, s in camp_store.items():
        f = defaultdict(int)
        for n in s:
            f[(SPEC.get(n) or {}).get("faction")] += 1
        if f:
            camp_pf[cid] = max(f.items(), key=lambda kv: kv[1])[0]

    # 战役默认池 = 商店 ∪ 场景
    camp_pool: dict[str, set[str]] = {
        cid: camp_store.get(cid, set()) | camp_used.get(cid, set())
        for cid in camp_store
    }

    print("=" * 90)
    print("① 每个战役的商店集合：只卖玩家一方阵营 + 年代自洽")
    print("=" * 90)
    print(f"{'战役':<22} {'会议':>4} {'商店种数':>8}  {'阵营分布':<26} {'年份后缀'}")
    print("-" * 90)
    for cid in sorted(camp_store):
        s = camp_store[cid]
        fac = defaultdict(int)
        for n in s:
            fac[(SPEC.get(n) or {}).get("faction")] += 1
        yrs = sorted({m.group(1) for n in s if (m := re.search(r"_(\d{2})", n))})
        noyear = sum(1 for n in s if not re.search(r"_(\d{2})", n))
        ys = ",".join(yrs) if yrs else f"(无年份后缀 {noyear} 个)"
        print(f"{cid:<22} {camp_conf[cid]:>4} {len(s):>8}  {str(dict(fac)):<26} {ys}")

    print()
    print("=" * 90)
    print("② 假阴性检验：游戏在该战役场景里真实挂过的特种兵，口径有没有漏？")
    print("=" * 90)
    print(f"{'战役':<22} {'玩家阵营':<8} {'商店':>5} {'∪场景':>6} "
          f"{'玩家方用到':>10} {'商店漏':>7} {'∪场景漏':>8}")
    print("-" * 90)
    miss_a = miss_ap = 0
    for cid in sorted(camp_store):
        store = camp_store[cid]
        used = camp_used.get(cid, set())
        pf = camp_pf.get(cid)
        used_pf = {n for n in used if (SPEC.get(n) or {}).get("faction") == pf}
        ma = sorted(used_pf - store)
        mp = sorted(used_pf - camp_pool[cid])
        miss_a += len(ma)
        miss_ap += len(mp)
        print(f"{cid:<22} {pf:<8} {len(store):>5} {len(camp_pool[cid]):>6} "
              f"{len(used_pf):>10} {len(ma):>7} {len(mp):>8}")
    verdict_a = "A 不可用（会隐藏游戏自己在用的特种兵）" if miss_a else "A 可用"
    verdict_ap = ("口径 A' 完美（零假阴性）✓" if miss_ap == 0
                  else "口径 A' 仍有漏 ✗")
    print(f"  ⇒ 口径 A（只用商店）漏 {miss_a} 种；口径 A'（商店 ∪ 场景）漏 {miss_ap} 种")
    print(f"  ⇒ {verdict_a}；{verdict_ap}")

    print()
    print("=" * 90)
    print("③ 候选量对比（只统计玩家阵营的单位类型）")
    print("=" * 90)
    for cid in sorted(camp_store):
        pf = camp_pf.get(cid)
        store = camp_store[cid]
        pool = camp_pool[cid]
        types = [(ut, u) for ut, u in UT.items() if u.get("faction") == pf]
        if not types:
            continue

        def avg(p: set[str]) -> float:
            tot = n = 0
            for _ut, u in types:
                c = [x for x, s in SPEC.items() if can_add(s, u)]
                if not c:
                    continue
                tot += len([x for x in c if x in p])
                n += 1
            return tot / max(1, n)

        a0, a1, a2 = avg(set(SPEC)), avg(store), avg(pool)
        print(f"  {cid:<22} 玩家方单位类型 {len(types):>3} 个 | 仅 e162规则 {a0:>5.1f} | "
              f"∩商店 {a1:>5.1f} | ∩战役默认池 {a2:>5.1f}"
              f"   （商店池 {len(store)} / 默认池 {len(pool)}）")

    print()
    print("=" * 90)
    print("④ 资源健全性：375 个类型是否都有贴图？商店条目是否都查得到类型？")
    print("=" * 90)
    no_art = sorted(set(SPEC) - dirs)
    dangling = sorted({n for s in camp_store.values() for n in s} - set(SPEC))
    print(f"  有类型没贴图 = {len(no_art)} 个 {no_art}")
    print(f"  商店条目查不到类型 = {len(dangling)} 个 {dangling}")
    print(f"  ⇒ {'无崩溃级风险 ✓' if not no_art and not dangling else '有风险 ✗'}")

    print()
    print("=" * 90)
    print("⑤ 全游戏覆盖率")
    print("=" * 90)
    all_store = set().union(*camp_store.values()) if camp_store else set()
    all_pool = set().union(*camp_pool.values()) if camp_pool else set()
    print(f"  被某个战役商店卖过 = {len(all_store)} 种（{len(all_store)/375*100:.1f}%）")
    print(f"  被某个战役默认池覆盖 = {len(all_pool)} 种（{len(all_pool)/375*100:.1f}%）")
    fac = defaultdict(int)
    for n in set(SPEC) - all_pool:
        fac[(SPEC.get(n) or {}).get("faction")] += 1
    print(f"  任何战役都没覆盖 = {len(SPEC) - len(all_pool)} 种 {dict(fac)}")

    print()
    print("=" * 90)
    print("⑥ 坑 1 实证：敌国单位的候选交集为空")
    print("=" * 90)
    for cid in sorted(camp_store):
        pool = camp_pool[cid]
        facs = {(SPEC.get(n) or {}).get("faction") for n in camp_store[cid]}
        other = [ut for ut, u in UT.items() if u.get("faction") not in facs]
        if not other:
            continue
        ut = other[0]
        u = UT[ut]
        cands = [n for n, s in SPEC.items() if can_add(s, u)]
        inter = [n for n in cands if n in pool]
        print(f"  {cid:<22} 敌国单位 {ut:<14} 规则内 {len(cands):>3} 种 → ∩默认池 {len(inter):>2} 种"
              f"   {'← 空！必须兜底' if not inter else ''}")

    print()
    print("=" * 90)
    print("⑦ 兜底口径（找不到战役包时）：仅 e162 规则的候选量")
    print("=" * 90)
    for ut in ("us_arm_42", "ger_inf_40", "sov_inf_41"):
        u = UT.get(ut)
        if not u:
            continue
        cands = [n for n, s in SPEC.items() if can_add(s, u)]
        print(f"  {ut:<14} {len(cands):>3} 种")
    return 0


if __name__ == "__main__":
    sys.exit(main())
