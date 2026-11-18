"""e160 —— 卡牌商店「能自然生成什么」：把游戏自己的抽卡算法复刻出来。

**为什么需要这个脚本**
用户担心：登陆 / 空降类卡牌会召唤单位，战役里没有这个单位时游戏会崩。
⇒ 改卡牌时**只允许改成商店本来就能自然生成的那几张**。

**游戏怎么生成货架**（字节码实证，见 §7.5）
`campaign.pyc::set_conference` → `create_random_card_data(limit, all_free)`
→ `Campaign.get_cards_probabilities(conf, player_faction, without_unit)`
→ 每个 meta_type 先 `random.choice(d.card_types_with_unit_ids)`，
   再按 `probability` 权重 `random.choices` 抽。

**候选集怎么来的**（`Campaign.get_cards_probabilities`，逐条复刻）：
对每个 `p > 0` 的 meta_type，遍历
`card_types.get_card_types_of(player_faction, meta_type)` —— 即
**meta_type 匹配 且 faction == 玩家阵营** 的所有卡牌：

* `has_unit` 为假 ⇒ 直接进候选（`(card_type, None)`）；
* `has_unit` 为真 ⇒ 必须同时满足
  1. 该卡不在 `main.yml.used_card_types_with_unit` 里；
  2. 该卡不在当前手牌里；
  3. `campaign_doc.get_card_type_unit_id(card_type)` 有值
     ⇒ 即 `document/main.yml.card_type_units` 里有登记（**本战役才有的单位**）；
  4. 该 `unit_id` 对应的单位在存档里不存在，或存在但**没阵亡**（`kia` 为假）。
     —— 若单位已阵亡，这张卡的"单位名额"已被用掉，不再上架。

**本脚本做什么**
1. 用上面的规则算出每个存档的**可上架卡牌集合**；
2. 与存档里真实的 `card_store` 对照 —— 真实的每一张都必须落在集合内；
3. 列出被屏蔽的卡牌**和屏蔽原因**（给 GUI 提示用）。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e160_card_whitelist.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths, open_save  # noqa: E402
from save_modifier_core import catalog as catmod  # noqa: E402

# 基础权重表（e158 从 `card_types.pyc` 的 `card_meta_types_base_probabilities` 解出）
BASE_WEIGHTS: dict[str, float] = {
    "truck": 15, "air_attack": 15, "long_range_recon": 15,
    "air_supply": 6, "naval_bombardment": 6, "saturation_strike": 6,
    "espionage": 6, "flying_artillery": 6,
    "tactical_naval_assault": 3, "tactical_para": 3, "divisional_para": 3,
    "sabotage": 3, "store": 3, "precision_bombing": 3, "air_fleet": 3,
    "power_hq": 3, "arty_prep": 3, "air_hq": 3,
}

CONFERENCE_SAVE = Path(
    r"C:\Users\misprit\.minimax\v2\assets\2026\11\18\11-15-18-766-"
    r"asset_20261118-111518-766_c2c3a7a10319_1c0b943e-Blitzkrieg-ahistorical-Conference4-alter.usg"
)


def probabilities(save, campaign_id: str, conf: str | None, fronts: list[str],
                  cat) -> dict[str, float]:
    """基础表 → 会议文件覆盖 → 各前线 scales 缩放。

    **权威源是存档 L2**（游戏把 campaign_doc 从存档里加载）：
      `document/conferences/<conf>.yml`            → card_probabilities
      `document/fronts/<front>/conferences/<conf>.yml` → card_probability_scales
    存档里没有才退回游戏包（`catalog.campaign_dir`）。
    """
    prob = dict(BASE_WEIGHTS)
    if not conf:
        return prob

    over: dict = {}
    scales: dict = {}
    for n in save.list_names():
        if not n.endswith(".yml"):
            continue
        if n == f"document/conferences/{conf}.yml":
            d = save.read_yaml(n, None)
            if isinstance(d, dict):
                over = d.get("card_probabilities") or {}
        elif n.endswith(f"/conferences/{conf}.yml"):
            d = save.read_yaml(n, None)
            if isinstance(d, dict):
                for c, v in (d.get("card_probability_scales") or {}).items():
                    scales.setdefault(c, v)
    if not over and not scales:
        cdir = cat.campaign_dir(campaign_id)
        if cdir and cdir.is_dir():
            for f in sorted(cdir.rglob("conferences/*.yml")):
                d = catmod.yamlio.load(f.read_bytes())
                if not isinstance(d, dict):
                    continue
                rel = f.relative_to(cdir).as_posix()
                if rel == f"conferences/{conf}.yml":
                    over = d.get("card_probabilities") or {}
                if rel.endswith(f"/conferences/{conf}.yml"):
                    for c, v in (d.get("card_probability_scales") or {}).items():
                        scales.setdefault(c, v)
    prob.update(over)
    for c, v in scales.items():
        prob[c] = prob.get(c, 0) * v
    return prob


def compute_whitelist(save_path: Path, cat, paths) -> dict:
    """复刻 Campaign.get_cards_probabilities，返回候选集与屏蔽原因。"""
    with open_save(str(save_path), paths) as sv:
        doc = sv.read_yaml("document/main.yml", None) or {}
        main_ = sv.root_main()
        store = main_.get("card_store") or []
        hand = sv.root_cards()
        used = main_.get("used_card_types_with_unit") or {}
        save_units = {u.get("id"): u for u in sv.root_units()}

        player_faction = doc.get("player_faction")
        ct_units = {e["card_type"]: e for e in (doc.get("card_type_units") or [])}
        in_state = main_.get("in_state") or {}
        conf = in_state.get("conference")
        fronts = list((in_state.get("fronts") or {}).keys())
        campaign_id = main_.get("campaign_id")

    prob = probabilities(sv, campaign_id, conf, fronts, cat)

    by_meta: dict = {}
    for name in cat.card_type_names():
        d = cat.card_type(name) or {}
        by_meta.setdefault((d.get("faction"), d.get("meta_type")), []).append((name, d))

    hand_types = {c.get("card_type") for c in hand}
    candidates: dict[str, list] = {}
    blocked: dict[str, str] = {}

    for name in cat.card_type_names():
        d = cat.card_type(name) or {}
        mt = d.get("meta_type")
        fac = d.get("faction")
        reasons = []
        if fac != player_faction:
            reasons.append(f"阵营 {fac} ≠ 玩家 {player_faction}")
        elif prob.get(mt, 0) <= 0:
            reasons.append(f"meta={mt} 本次会议概率 ≤ 0")
        elif d.get("has_unit"):
            if name in used:
                reasons.append("已召唤过（used_card_types_with_unit）")
            elif name in hand_types:
                reasons.append("手牌里已有同类型")
            elif name not in ct_units:
                reasons.append("本战役 card_type_units 里没有它 ⇒ 没有可召唤的单位")
            else:
                unit_id = ct_units[name].get("unit_id")
                unit = save_units.get(unit_id)
                if unit is not None and unit.get("kia"):
                    reasons.append(f"预留单位 {unit_id} 已阵亡，名额用掉")
        if reasons:
            blocked[name] = "；".join(reasons)
            continue
        candidates.setdefault(mt, []).append((name, None))

    allowed = {c for lst in candidates.values() for c, _ in lst}
    return {
        "player_faction": player_faction,
        "campaign_id": campaign_id,
        "conf": conf,
        "prob": prob,
        "candidates": candidates,
        "allowed": allowed,
        "blocked": blocked,
        "store": store,
        "hand_types": hand_types,
        "ct_units": ct_units,
        "used": used,
        "save_units": save_units,
    }


def report(title: str, save_path: Path, cat, paths) -> None:
    print("=" * 76)
    print(f"### {title}")
    r = compute_whitelist(save_path, cat, paths)
    print(f"  战役 = {r['campaign_id']}   会议 = {r['conf']}   "
          f"玩家阵营 = {r['player_faction']}")
    print(f"  card_type_units   = {r['ct_units']}")
    print(f"  used_card_types   = {r['used']}")
    print(f"  手牌类型          = {sorted(r['hand_types'])}")

    print("\n  --- 可上架的卡牌（候选集，按 meta_type）---")
    for mt in sorted(r["candidates"]):
        names = ", ".join(c for c, _ in r["candidates"][mt])
        print(f"    {mt:24s} p={r['prob'].get(mt):5} → {names}")
    print(f"  合计可上架 {len(r['allowed'])} / {len(cat.card_type_names())} 种")

    print("\n  --- 存档真实货架（对照）---")
    for e in r["store"]:
        print(f"    位置{e.get('position')} {e.get('card_type'):24s} "
              f"unit_id={e.get('unit_id')} is_free={e.get('is_free')}")
    real = {e.get("card_type") for e in r["store"]}
    print(f"  ⇒ 真实货架每张都在候选集内: {real <= r['allowed']}")
    missing = r["allowed"] - real
    print(f"  ⇒ 候选集里没抽到的（随机所致）: {sorted(missing)}")

    print("\n  --- 被屏蔽的卡牌 ---")
    for name in sorted(r["blocked"]):
        print(f"    {name:26s} {r['blocked'][name]}")


def main() -> None:
    paths = CorePaths.discover()
    cat = catmod.default()
    report("会议阶段存档（卡牌商店已激活）", CONFERENCE_SAVE, cat, paths)
    print()
    report("主样本存档 campaigns/Stalingrad.usg", Path("campaigns/Stalingrad.usg"), cat, paths)


if __name__ == "__main__":
    main()
