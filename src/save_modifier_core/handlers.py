"""各编辑类型的应用逻辑。

每种 `Edit` 的处理分四步：

1. **能力位检查** —— 不满足就记错误（不静默忽略）；
2. **定位目标条目与对象** —— 找不到就记错误；
3. **改**（只改该改的字段，其余原样搬运）；
4. **产出摘要 + 警告**。

⚠️ **只改该改的字段** 是硬要求：
`main.yml` 改 `prestige` 时，`milestones` / `card_store` / `tokens` /
`tokens_map` / `renamed_hqs` / `reverted_games` / `used_card_types_with_unit`
必须**原样保留** —— 丢掉 `milestones` 游戏**不会报错**，会静默清空（§6.1b、§10 第 50 条）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .edits import Edit

__all__ = ["Outcome", "apply_edit"]


@dataclass
class Outcome:
    """一次编辑的结果。"""

    summary: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 单位字段

#: **允许改**的单位字段。`type` 不在其中 —— 它是只读信息（§5.4、§7.5）。
UNIT_FIELD_ALLOWED = {
    "xp", "act_st", "sup_st", "name_brief", "name_full",
    "uv", "entr", "supply", "ap",
}

#: 战斗外改会被场景预设覆盖的字段（§3.5.8 存活性矩阵）
UNIT_FIELD_RISKY = {"uv", "entr", "supply", "ap"}

#: 单位数值字段的取值范围（§5.2）
UNIT_FIELD_RANGE = {
    "xp": (0, 400),
    "entr": (0, 2),
    "supply": (0, 3),
    "ap": (0, 3),
    "act_st": (0, None),
    "sup_st": (0, None),
}


def _find_by_id(rows, obj_id):
    if not isinstance(rows, list):
        return None
    for r in rows:
        if isinstance(r, dict) and r.get("id") == obj_id:
            return r
    return None


# ---------------------------------------------------------------- 各 kind


def _progress(w, e: Edit) -> Outcome:
    """声望 / 分数（根 `main.yml`）。"""
    oc = Outcome()
    field = e.params.get("field")
    value = e.params.get("value")
    if field not in ("prestige", "score"):
        oc.errors.append(f"未知的进度字段 {field!r}（只能改 prestige / score）")
        return oc
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        oc.errors.append(f"{field} 必须是 ≥ 0 的整数，收到 {value!r}")
        return oc
    main = w.table("main.yml", {})
    if not isinstance(main, dict):
        oc.errors.append("根 main.yml 结构异常")
        return oc
    old = main.get(field)
    main[field] = value
    w.touch("main.yml")
    oc.summary = f"战役进度 {field}：{old} → {value}"
    return oc


def _unit_field(w, e: Edit) -> Outcome:
    """单位的某个字段（根 `units.yml`）。"""
    oc = Outcome()
    unit_id = e.params.get("unit_id")
    field = e.params.get("field")
    value = e.params.get("value")
    if not w.require(w.caps.can_edit_units, "units", "units.yml"):
        return oc
    if field == "type":
        oc.errors.append(
            "「编制（type）」是只读信息，修改器不提供改编制功能（§5.4、§7.5）。"
            "想让单位更强，请改战力（act_st）与特种兵（specs）。")
        return oc
    if field not in UNIT_FIELD_ALLOWED:
        oc.errors.append(
            f"不允许改单位字段 {field!r}；可改：{', '.join(sorted(UNIT_FIELD_ALLOWED))}")
        return oc

    units = w.table("units.yml", [])
    unit = _find_by_id(units, unit_id)
    if unit is None:
        oc.errors.append(f"存档里没有 id 为 {unit_id} 的单位")
        return oc

    if field in UNIT_FIELD_RANGE:
        lo, hi = UNIT_FIELD_RANGE[field]
        if not isinstance(value, int) or isinstance(value, bool):
            oc.errors.append(f"{field} 必须是整数，收到 {value!r}")
            return oc
        if value < lo or (hi is not None and value > hi):
            oc.errors.append(f"{field}={value} 越界（必须 {lo}..{hi}）")
            return oc

    if field in ("name_brief", "name_full"):
        if value is not None and not isinstance(value, str):
            oc.errors.append(f"{field} 必须是字符串或 null")
            return oc

    old = unit.get(field)
    unit[field] = value
    w.touch("units.yml")
    oc.summary = f"单位 {unit_id} 的 {field}：{old!r} → {value!r}"
    if field in UNIT_FIELD_RISKY:
        oc.warnings.append(
            f"单位 {unit_id} 的 {field} 在战斗外改，下一次开打时可能被场景预设覆盖（§3.5.8）")
    if field == "xp":
        oc.warnings.append(
            "登陆单位被补兵后 XP 会被重算掉一部分（§3.5.6）")
    if field in ("name_brief", "name_full") and isinstance(value, str):
        if value.startswith("id_") or value.startswith("idp_"):
            oc.warnings.append(
                f"{value!r} 看起来是本地化 id，游戏会去本地化表里查它；"
                "想显示固定文字请直接写明文（§5.5）")
    # 战力软上限提示 —— 上限来自类型的 max_st，不硬拦（§5.3、§10 第 8 条）
    if field in ("act_st", "sup_st") and w.catalog is not None:
        limit = w.catalog.max_st(unit.get("type"))
        if limit is not None:
            total = int(unit.get("act_st") or 0) + int(unit.get("sup_st") or 0)
            if total > limit:
                oc.warnings.append(
                    f"该单位战力合计 {total} 超过上限 {limit}"
                    f"（类型 {unit.get('type')} 的 max_st）—— 游戏可能读不出这个值")
    return oc


def _unit_spec_add(w, e: Edit) -> Outcome:
    """加特种（根 `units.yml`）。"""
    oc = Outcome()
    unit_id = e.params.get("unit_id")
    spec_type = e.params.get("spec_type")
    if not w.require(w.caps.can_edit_units, "units", "units.yml"):
        return oc
    if w.catalog is None:
        oc.errors.append("没有游戏包目录，无法校验特种兵类型 —— 请先让修改器定位到游戏安装目录")
        return oc
    if not w.catalog.has_spec_type(spec_type):
        oc.errors.append(
            f"特种兵类型 {spec_type!r} 不存在（游戏包里共 "
            f"{len(w.catalog.spec_type_names())} 个）")
        return oc

    units = w.table("units.yml", [])
    unit = _find_by_id(units, unit_id)
    if unit is None:
        oc.errors.append(f"存档里没有 id 为 {unit_id} 的单位")
        return oc

    specs = unit.setdefault("specs", [])
    cap = w.catalog.spec_cap(unit.get("type"))
    if len(specs) >= cap:
        oc.errors.append(
            f"该单位最多挂 {cap} 个特种（类型 {unit.get('type')} 的上限），"
            f"现在已有 {len(specs)} 个")
        return oc
    used = {s.get("idx") for s in specs if isinstance(s, dict)}
    free = next((i for i in (0, 1, 2) if i not in used), None)
    if free is None:
        oc.errors.append("没有空闲的特种槽位（idx 0..2）")
        return oc
    specs.append({"active": True, "captured": False,
                  "idx": free, "type": spec_type})
    w.touch("units.yml")
    oc.summary = f"单位 {unit_id} 加特种 {spec_type}（槽位 {free}）"
    oc.warnings.append(
        "登陆/空降单位进战斗时会按场景目标对账，多余的特种会被退回总部兵库（§3.5.5）")
    return oc


def _unit_spec_remove(w, e: Edit) -> Outcome:
    """卸特种（根 `units.yml`）。"""
    oc = Outcome()
    unit_id = e.params.get("unit_id")
    spec_type = e.params.get("spec_type")
    idx = e.params.get("idx")
    if not w.require(w.caps.can_edit_units, "units", "units.yml"):
        return oc
    units = w.table("units.yml", [])
    unit = _find_by_id(units, unit_id)
    if unit is None:
        oc.errors.append(f"存档里没有 id 为 {unit_id} 的单位")
        return oc
    specs = unit.get("specs") or []
    target = next((s for s in specs
                   if isinstance(s, dict)
                   and s.get("type") == spec_type
                   and (idx is None or s.get("idx") == idx)), None)
    if target is None:
        oc.errors.append(f"单位 {unit_id} 没有特种 {spec_type}"
                         + (f"（idx={idx}）" if idx is not None else ""))
        return oc
    specs.remove(target)
    unit["specs"] = specs
    w.touch("units.yml")
    oc.summary = f"单位 {unit_id} 卸特种 {spec_type}（槽位 {target.get('idx')}）"
    return oc


def _hq_force_pool(w, e: Edit) -> Outcome:
    """总部兵库数量（根 `hqs.yml`）。"""
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    index = e.params.get("index")
    quantity = e.params.get("quantity")
    if not w.require(w.caps.can_edit_force_pool, "force_pool", "hqs.yml"):
        return oc
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
        oc.errors.append(f"兵库数量必须是 ≥ 0 的整数，收到 {quantity!r}")
        return oc
    hqs = w.table("hqs.yml", [])
    hq = _find_by_id(hqs, hq_id)
    if hq is None:
        oc.errors.append(f"存档里没有 id 为 {hq_id} 的总部")
        return oc
    pool = hq.get("force_pool")
    if not isinstance(pool, list) or not (0 <= index < len(pool)):
        oc.errors.append(f"总部 {hq_id} 没有第 {index} 条兵库记录")
        return oc
    entry = pool[index]
    if not isinstance(entry, dict):
        oc.errors.append(f"总部 {hq_id} 的兵库第 {index} 条结构异常")
        return oc
    if "spec" in entry and "equipment" in entry:
        oc.errors.append("兵库条目同时有 spec 与 equipment（二选一），不能安全修改")
        return oc
    old = entry.get("quantity")
    entry["quantity"] = quantity
    w.touch("hqs.yml")
    oc.summary = (f"总部 {hq_id} 兵库第 {index} 条"
                  f"（{entry.get('spec') or entry.get('equipment')}）：{old} → {quantity}")
    return oc


def _card_add(w, e: Edit) -> Outcome:
    """加卡（根 `cards.yml`）。"""
    oc = Outcome()
    card_type = e.params.get("card_type")
    position = e.params.get("position")
    unit_id = e.params.get("unit_id")
    if not w.require(w.caps.can_edit_cards, "cards", "cards.yml"):
        return oc
    if w.catalog is None:
        oc.errors.append("没有游戏包目录，无法校验卡牌类型")
        return oc
    if not w.catalog.has_card_type(card_type):
        oc.errors.append(
            f"卡牌类型 {card_type!r} 不存在（游戏包里共 "
            f"{len(w.catalog.card_type_names())} 个）")
        return oc

    cards = w.table("cards.yml", [])
    if not isinstance(cards, list):
        oc.errors.append("根 cards.yml 结构异常")
        return oc
    if position is None:
        positions = [c.get("position") for c in cards
                     if isinstance(c, dict) and isinstance(c.get("position"), int)]
        position = (max(positions) + 1) if positions else 1
    if any(isinstance(c, dict) and c.get("position") == position for c in cards):
        oc.errors.append(f"槽位 {position} 已经被占了")
        return oc

    info = w.catalog.card_type(card_type) or {}
    if info.get("has_unit") and unit_id is None:
        oc.errors.append(f"卡牌 {card_type} 带单位，必须指定 unit_id")
        return oc
    if unit_id is not None:
        roster = w.save.roster_ids()
        if roster and unit_id not in roster:
            oc.errors.append(f"unit_id={unit_id} 不在战役名册里")
            return oc

    cards.append({"card_type": card_type,
                  "is_free": bool(e.params.get("is_free")),
                  "position": position,
                  "unit_id": unit_id,
                  "used": False})
    w.touch("cards.yml")
    oc.summary = f"加卡 {card_type}（槽位 {position}）"
    return oc


def _card_remove(w, e: Edit) -> Outcome:
    """删卡（根 `cards.yml`）。"""
    oc = Outcome()
    position = e.params.get("position")
    if not w.require(w.caps.can_edit_cards, "cards", "cards.yml"):
        return oc
    cards = w.table("cards.yml", [])
    if not isinstance(cards, list):
        oc.errors.append("根 cards.yml 结构异常")
        return oc
    target = next((c for c in cards
                   if isinstance(c, dict) and c.get("position") == position), None)
    if target is None:
        oc.errors.append(f"没有槽位号为 {position} 的卡")
        return oc
    cards.remove(target)
    w.touch("cards.yml")
    oc.summary = f"删卡 {target.get('card_type')}（槽位 {position}）"
    return oc


def _store_set(w, e: Edit) -> Outcome:
    """改商店条目的 price / quantity（根 `store.yml`）。"""
    oc = Outcome()
    front = e.params.get("front")
    index = e.params.get("index")
    field = e.params.get("field")
    value = e.params.get("value")
    if not w.require(w.caps.can_edit_store, "store", "store.yml"):
        return oc
    if field not in ("price", "quantity"):
        oc.errors.append(f"商店条目只能改 price / quantity，收到 {field!r}")
        return oc
    store = w.table("store.yml", {})
    if not isinstance(store, dict):
        oc.errors.append("根 store.yml 结构异常")
        return oc
    if front not in store:
        oc.errors.append(
            f"存档里没有战线 {front!r} —— 只能改存档已有的战线键，"
            "不要凭空新建（§10 第 12 条）")
        return oc
    entries = store.get(front)
    if not isinstance(entries, list) or not (0 <= index < len(entries)):
        oc.errors.append(f"战线 {front} 没有第 {index} 条商品")
        return oc
    entry = entries[index]
    if not isinstance(entry, dict):
        oc.errors.append(f"战线 {front} 第 {index} 条结构异常")
        return oc
    if field == "quantity":
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            oc.errors.append(
                f"quantity={value!r} 是非法值 —— 游戏没有「售罄」标记，"
                "下架商品请**删除该条目**（§4.6、§6.3）")
            return oc
    else:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            oc.errors.append(f"price={value!r} 必须是非负整数")
            return oc
    old = entry.get(field)
    entry[field] = value
    w.touch("store.yml")
    oc.summary = (f"商店 {front} 第 {index} 条"
                  f"（{entry.get('spec') or entry.get('equipment')}）"
                  f" 的 {field}：{old} → {value}")
    if field == "price" and value == 0:
        oc.warnings.append("price=0 表示**免费商品**，不是下架")
    return oc


def _store_remove(w, e: Edit) -> Outcome:
    """下架商品 —— 删条目（根 `store.yml`）。"""
    oc = Outcome()
    front = e.params.get("front")
    index = e.params.get("index")
    if not w.require(w.caps.can_edit_store, "store", "store.yml"):
        return oc
    store = w.table("store.yml", {})
    if not isinstance(store, dict):
        oc.errors.append("根 store.yml 结构异常")
        return oc
    if front not in store:
        oc.errors.append(f"存档里没有战线 {front!r}")
        return oc
    entries = store.get(front)
    if not isinstance(entries, list) or not (0 <= index < len(entries)):
        oc.errors.append(f"战线 {front} 没有第 {index} 条商品")
        return oc
    entry = entries[index]
    what = (entry.get("spec") or entry.get("equipment")) if isinstance(entry, dict) else "?"
    del entries[index]
    w.touch("store.yml")
    oc.summary = f"下架商店 {front} 第 {index} 条（{what}）"
    return oc


def _hand_restore(w, e: Edit) -> Outcome:
    """恢复上次会议的牌局（读 L2 的 `card_store` → 写 L1）。"""
    oc = Outcome()
    if not w.require(w.caps.can_restore_hand, "restore_hand", "main.yml"):
        return oc
    cp = w.table("last_conference/main.yml", {})
    if not isinstance(cp, dict):
        oc.errors.append("会议检查点 main.yml 结构异常")
        return oc
    hand = cp.get("card_store")
    if not isinstance(hand, list):
        oc.errors.append("会议检查点里没有 card_store（上次会议没有发牌？）")
        return oc
    main = w.table("main.yml", {})
    if not isinstance(main, dict):
        oc.errors.append("根 main.yml 结构异常")
        return oc
    old = main.get("card_store")
    main["card_store"] = hand
    w.touch("main.yml")
    n = len(hand)
    oc.summary = f"恢复上次会议的牌局（{n} 张牌，替换当前 {len(old) if isinstance(old, list) else 0} 张）"
    return oc


def _theater_asset(w, e: Edit) -> Outcome:
    """战区资产（唯一的 L3 写入白名单）。"""
    oc = Outcome()
    asset = e.params.get("asset")
    to_use = e.params.get("to_use")
    uses_total = e.params.get("uses_total")
    uses_turn = e.params.get("uses_turn")
    if not w.require(w.caps.can_edit_theater_assets, "theater_assets", "games/<场景>/main.yml"):
        return oc
    battle_dir = w.save.battle_dir()
    if battle_dir is None:
        oc.errors.append("当前存档没有进行中的战斗")
        return oc
    entry = f"{battle_dir}/main.yml"
    data = w.table(entry, {})
    if not isinstance(data, dict):
        oc.errors.append(f"{entry} 结构异常")
        return oc
    theater = data.get("theater_assets")
    if not isinstance(theater, list) or not theater or not isinstance(theater[0], list):
        oc.errors.append(f"{entry} 里没有 theater_assets")
        return oc
    items = theater[0]
    target = next((it for it in items
                   if isinstance(it, dict) and it.get("asset") == asset), None)
    if target is None:
        avail = ", ".join(str(it.get("asset")) for it in items if isinstance(it, dict))
        oc.errors.append(
            f"该场景没有战区资产 {asset!r}；本场景有：{avail or '（空）'}。"
            "修改器**不会凭空新增**资产条目（§6.2b）")
        return oc
    if not isinstance(to_use, int) or isinstance(to_use, bool) or to_use < 0:
        oc.errors.append(f"to_use={to_use!r} 必须是非负整数")
        return oc
    old = target.get("to_use")
    target["to_use"] = to_use
    if uses_total is not None:
        target["uses_total"] = uses_total
    target["uses_turn"] = uses_turn if uses_turn else target.get("uses_turn", 0)
    w.touch(entry)
    oc.summary = f"战区资产 {asset}：可用 {old} → {to_use} 次"
    oc.warnings.append(
        "战区资产**无法通过游戏内的『重置会议』撤销** —— 需要用修改器自己的撤销（§6.4）")
    return oc


# ---------------------------------------------------------------- 分发表

_HANDLERS = {
    "progress": _progress,
    "unit_field": _unit_field,
    "unit_spec_add": _unit_spec_add,
    "unit_spec_remove": _unit_spec_remove,
    "hq_force_pool": _hq_force_pool,
    "card_add": _card_add,
    "card_remove": _card_remove,
    "store_set": _store_set,
    "store_remove": _store_remove,
    "hand_restore": _hand_restore,
    "theater_asset": _theater_asset,
}


def apply_edit(w, e: Edit) -> Outcome:
    """把一条编辑应用到工作区，返回结果。"""
    handler = _HANDLERS.get(e.kind)
    if handler is None:
        return Outcome(errors=[f"未实现的编辑类型 {e.kind!r}"])
    try:
        return handler(w, e)
    except Exception as exc:                      # 绝不让一条坏编辑炸掉整个规划
        return Outcome(errors=[f"{e.kind} 处理失败：{exc}"])
