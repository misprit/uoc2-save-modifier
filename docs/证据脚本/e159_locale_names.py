"""e159 —— 中文名从哪来？核心库现在解析不了。

**结论**：游戏里所有**中文显示名**都在游戏包的
`_packages/base/localization/chi/strings.yml`（扁平 id → 文本，16786 条）。
实体类型只存**键**，不存中文：

| 对象 | 键所在 | 字段 | 例 |
|---|---|---|---|
| 单位类型 | `entity_types/unit_types/*.yml` | `name_brief` | `id_aus_inf_41_brief` → 澳大利亚步兵 |
| 特种兵 | `entity_types/specialists/*.yml` | `name_brief` / `name_full` | `id_bel_arty_towed_40_brief` → 155L Mod.1917 |
| 卡牌 | `entity_types/cards/*.yml` | `title` / `subtitle` | `id_card_Ju_87` → Ju 87；`id_card_PRECISION_BOMBING` → 精准轰炸 |
| 总部 | **存档 `hqs.yml` 的每一条** | `name_brief` / `name_full` / `name_super_brief` | `id_hq_name_brief_AOK_17` |
| 通用文本 | — | — | `id_n_steps_infantry` → `{}步兵战力（{}）` |

**核心库现在完全没有 locale 能力** ——
`Catalog.unit_type_names()` / `hq_type_names()` / `spec_type_names()`
返回的都是**英文类型标识符**（`aus_inf_41` / `aus_hq` / `bel_arty_towed_40`），
不是中文显示名。

⇒ GUI 要显示中文，要么自己读这个 2 MB 的 yml，要么让核心库加一个 lookup
（见《GUI设计规范.md》§8.1）。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e159_locale_names.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths, open_save  # noqa: E402
from save_modifier_core import catalog as catmod  # noqa: E402

LOCALE_REL = Path("localization") / "chi" / "strings.yml"


def locale_path() -> Path | None:
    for pkg in CorePaths.discover().packages():
        p = pkg / LOCALE_REL
        if p.is_file():
            return p
    return None


def main() -> None:
    cat = catmod.default()
    lp = locale_path()
    if lp is None:
        print("找不到 localization/chi/strings.yml")
        return
    print("locale 文件:", lp, f"({lp.stat().st_size} B)")

    loc = catmod.yamlio.load(lp.read_bytes())
    print("条目总数:", len(loc))
    for pat in ("id_card_", "id_unit_", "id_hq_"):
        ks = [k for k in loc if isinstance(k, str) and k.startswith(pat)]
        print(f"  {pat:12s} {len(ks):6d} 条   例: {ks[:2]}")

    print("\n=== A. 单位类型 / 特种兵：name_brief 是 locale 键 ===")
    for kind, t in (("unit_types", "aus_inf_41"), ("unit_types", "ger_pz_dlc7"),
                    ("unit_types", "us_inf_42"), ("specialists", "bel_arty_towed_40")):
        d = cat._load(kind, t) or {}
        nb = d.get("name_brief")
        nf = d.get("name_full")
        print(f"  {kind}/{t:20s} brief={nb!r} -> {loc.get(nb, '<无>')!r}")
        if nf:
            print(f"  {'':27s} full ={nf!r} -> {loc.get(nf, '<无>')!r}")

    print("\n=== B. 卡牌：title / subtitle 是 locale 键 ===")
    for t in ("precision_bombing_axis", "tactical_para_german", "store_axis", "truck_axis"):
        d = cat.card_type(t) or {}
        ti, su = d.get("title"), d.get("subtitle")
        print(f"  {t:24s} title={ti!r} -> {loc.get(ti, '<无>')!r}")
        print(f"  {'':26s} sub  ={su!r} -> {loc.get(su, '<无>')!r}")

    print("\n=== C. 总部：名字键在存档 hqs.yml 里，不在实体类型里 ===")
    paths = CorePaths.discover()
    with open_save("campaigns/Stalingrad.usg", paths) as sv:
        hqs = sv.root_hqs()
        h = hqs[0]
        for k in ("name_brief", "name_full", "name_super_brief"):
            v = h.get(k)
            print(f"  hq#{h.get('id')} {k:18s} = {v!r} -> {loc.get(v, '<无>')!r}")
        print(f"  （总部类型定义 entity_types/hq_types/*.yml 里**没有** name 字段）")

    print("\n=== D. 核心库现在给的是英文标识符，不是中文 ===")
    for fn in ("unit_type_names", "hq_type_names", "spec_type_names"):
        names = getattr(cat, fn)()
        print(f"  Catalog.{fn}() → {names[:3]} …（共 {len(names)}）")


if __name__ == "__main__":
    main()
