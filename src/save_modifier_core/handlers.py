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

#: 手牌张数上限（`card_deck_limit`，按难度；`e158` 字节码实证）
CARD_DECK_LIMIT = {"easy": 5, "normal": 5, "classic": 4, "hard": 3}

#: 货架格数（`card_store_limit`，四个难度恒为 5；`e158` 实证）
CARD_STORE_LIMIT = {"easy": 5, "normal": 5, "classic": 5, "hard": 5}

#: 手牌里**允许改**的字段（§7.5.2）
CARD_FIELD_ALLOWED = {"is_free"}

#: 总部**允许改**的字段（§7.4）
HQ_FIELD_ALLOWED = {
    "xp", "xp_target", "cp", "max_cp", "supply",
    "trucks", "prisoners", "loss_count", "intels_revealed",
}

#: 总部的五个分支（§7.4）
HQ_BRANCHES = ("engineering", "force_pool", "intel", "logistics", "operations")

#: **CP 的合法区间**（游戏字节码坐实，U19 取证）
#:
#: `state/constants.pyc` 里两个模块级常量：
#:
#: ```python
#: hq_max_cp     = 9
#: hq_min_max_cp = 3
#: ```
#:
#: `state/entities/data_validation/hq.pyc` 的 voluptuous schema：
#:
#: | 字段 | schema | 合法范围 |
#: |---|---|---|
#: | `max_cp` | `All(int, Range(min=hq_min_max_cp, max=hq_max_cp))` | **3 – 9** |
#: | `cp`    | `All(int, Range(min=0,            max=hq_max_cp))`     | **0 – 9** |
#:
#: ⇒ **超出范围游戏读存档会直接报错**（voluptuous 校验失败），
#: 不是「显示异常」而是**存档打不开** ⇒ 必须硬拦。
HQ_CP_MIN, HQ_CP_MAX = 0, 9
HQ_MAX_CP_MIN, HQ_MAX_CP_MAX = 3, 9

#: 分支等级的**上限**（游戏 `BRANCH_MAX = 3`；`can_add_branch_level` 里
#: `current_level = level + suppressed`，`== 3` 就不许再加）
HQ_BRANCH_MAX = 3

#: 补给卡车数 → **总部补给作用范围**（游戏 `game.yml` → `supply_hubs_ranges` =
#: `[5, 8, 10, 11, 12]`，按 1-based 读：1 辆 → 5 格、2 辆 → 8、3 辆 → 10、
#: 4 辆 → 11、5 辆 → 12）。只作文案参考，**改卡车不动声望**。
TRUCK_RANGES = (5, 8, 10, 11, 12)

#: 卡车数的合法区间（0 不行 —— 总部至少要有一辆补给卡车）
TRUCK_MIN, TRUCK_MAX = 1, len(TRUCK_RANGES)

#: 商店的两个子商店（`store.yml` 是两层结构，`e154` 实证）
STORE_SUBS = ("store", "elite_store")


def _level_of(w) -> str:
    """存档难度（`main.yml.level`）；取不到就返回空串。"""
    main = w.table("main.yml", {})
    if isinstance(main, dict):
        lv = main.get("level")
        if isinstance(lv, str):
            return lv
    return ""


def _find_by_id(rows, obj_id):
    if not isinstance(rows, list):
        return None
    for r in rows:
        if isinstance(r, dict) and r.get("id") == obj_id:
            return r
    return None


# ---------------------------------------------------------------- 卡牌单位

def _reserved_unit_id(w, card_type: str) -> int | None:
    """这张卡在本战役登记的**可召唤单位 id**；没登记就是 None。

    来源：存档 `document/main.yml` 的 `card_type_units`（L5，只读）。

    ⚠️ 这才是 `unit_id` 的真实语义 —— **不是**"名册里任意一个单位"。
    实测 blitzkrieg 的 `tactical_para_german` → 718（名册里的 `ger_fsjg_40`），
    而 718 此刻还不在存档 `units.yml` 里（还没被召唤过）——
    所以"在名册里"那条只是碰巧成立，语义是错的（规范 §8.1）。
    """
    doc = w.save.read_yaml("document/main.yml", None)
    if not isinstance(doc, dict):
        return None
    for e in (doc.get("card_type_units") or []):
        if isinstance(e, dict) and e.get("card_type") == card_type:
            uid = e.get("unit_id")
            if isinstance(uid, int) and not isinstance(uid, bool):
                return uid
    return None


def _card_unit_id_in_hand(w, card_type: str) -> int | None:
    """手牌里那张卡的 `unit_id`（用于校验已存在的条目）。"""
    for c in w.save.root_cards():
        if isinstance(c, dict) and c.get("card_type") == card_type:
            uid = c.get("unit_id")
            if isinstance(uid, int) and not isinstance(uid, bool):
                return uid
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


def _hq_field(w, e: Edit) -> Outcome:
    """总部的某个字段（经验 / CP / 补给 / 卡车 / 俘虏 …）。"""
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    field = e.params.get("field")
    value = e.params.get("value")
    if not w.require(w.caps.can_edit_hqs, "hqs", "hqs.yml"):
        return oc
    if field not in HQ_FIELD_ALLOWED:
        oc.errors.append(
            f"不允许改总部字段 {field!r}；可改：{', '.join(sorted(HQ_FIELD_ALLOWED))}")
        return oc
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        oc.errors.append(f"{field} 必须是非负整数，收到 {value!r}")
        return oc

    # ⚠️ CP 的合法区间比「非负整数」严 —— 游戏 schema 是硬范围（U19 字节码取证）
    if field == "max_cp" and not (HQ_MAX_CP_MIN <= value <= HQ_MAX_CP_MAX):
        oc.errors.append(
            f"max_cp 必须在 {HQ_MAX_CP_MIN}–{HQ_MAX_CP_MAX} 之间（游戏的硬范围），收到 {value}")
        return oc
    if field == "cp" and not (HQ_CP_MIN <= value <= HQ_CP_MAX):
        oc.errors.append(
            f"cp 必须在 {HQ_CP_MIN}–{HQ_CP_MAX} 之间（游戏的硬范围），收到 {value}")
        return oc

    hqs = w.table("hqs.yml", [])
    hq = _find_by_id(hqs, hq_id)
    if hq is None:
        oc.errors.append(f"存档里没有 id 为 {hq_id} 的总部")
        return oc

    old = hq.get(field)
    hq[field] = value
    w.touch("hqs.yml")
    oc.summary = f"总部 {hq_id} 的 {field}：{old} → {value}"

    if field == "cp" and isinstance(hq.get("max_cp"), int) and value > hq["max_cp"]:
        oc.warnings.append(
            f"CP {value} 超过该总部的上限 {hq['max_cp']} —— 游戏读档时按上限截断，"
            f"多出来的 CP 会白给")
    if field == "max_cp" and isinstance(hq.get("cp"), int) and hq["cp"] > value:
        oc.warnings.append(
            f"CP 上限降到 {value}，但当前 CP 是 {hq['cp']} —— 游戏读档时按上限截断")
    if field == "xp" and isinstance(old, int) and value < old:
        oc.warnings.append(
            "降低总部经验会让下属单位掉经验（游戏按『总部经验 - 单位经验』算欠账）")
    if field == "xp_target" and isinstance(old, int) and value < old:
        oc.warnings.append(
            "降低经验目标会让下属单位立刻算成欠账")
    if field in ("prisoners", "loss_count", "intels_revealed"):
        oc.warnings.append(
            f"{field} 是游戏自己累计的统计值，改了不会被重算，但界面可能对不上")
    if field == "trucks":
        oc.warnings.append(
            f"卡车数决定总部的补给作用范围（{TRUCK_MIN}–{TRUCK_MAX} 辆 → "
            f"{'/'.join(str(r) for r in TRUCK_RANGES)} 格）；改它**不扣声望**")
    return oc


def _hq_branch_level(w, e: Edit) -> Outcome:
    """总部的分支等级（总部"升级"= 五个分支各一个等级）。

    存档里 `branch_levels[分支] = {level, suppressed}`（`e166` 字节码坐实）：

    * `level` = **当前生效**的等级（技能能不能用，看它）；
    * `suppressed` = **被压制的等级数**（被扣住几级）——
      游戏内部「解锁到几级」= `level + suppressed`（`can_add_branch_level`）。

    ⚠️ `suppressed` 是**整数**（被压制的级数），**不是布尔开关**。
    """
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    branch = e.params.get("branch")
    level = e.params.get("level")
    suppressed = e.params.get("suppressed")
    if not w.require(w.caps.can_edit_hqs, "hqs", "hqs.yml"):
        return oc
    if branch not in HQ_BRANCHES:
        oc.errors.append(
            f"未知的分支 {branch!r}；合法取值：{', '.join(HQ_BRANCHES)}")
        return oc
    if not isinstance(level, int) or isinstance(level, bool) or level < 0:
        oc.errors.append(f"分支等级必须是非负整数，收到 {level!r}")
        return oc
    if level > HQ_BRANCH_MAX:
        oc.errors.append(f"分支等级不能超过 {HQ_BRANCH_MAX}，收到 {level!r}")
        return oc
    if suppressed is not None:
        if not isinstance(suppressed, int) or isinstance(suppressed, bool):
            oc.errors.append(
                f"suppressed 必须是整数（被压制的等级数，0–{HQ_BRANCH_MAX}），"
                f"收到 {suppressed!r}")
            return oc
        if suppressed < 0 or suppressed > HQ_BRANCH_MAX:
            oc.errors.append(
                f"被压制的等级数必须在 0–{HQ_BRANCH_MAX} 之间，收到 {suppressed!r}")
            return oc
        if level + suppressed > HQ_BRANCH_MAX:
            oc.errors.append(
                f"等级 {level} + 被压制 {suppressed} 超过上限 {HQ_BRANCH_MAX}"
                "（游戏内部「解锁到几级」= 等级 + 被压制）")
            return oc

    hqs = w.table("hqs.yml", [])
    hq = _find_by_id(hqs, hq_id)
    if hq is None:
        oc.errors.append(f"存档里没有 id 为 {hq_id} 的总部")
        return oc
    levels = hq.get("branch_levels")
    if not isinstance(levels, dict):
        oc.errors.append(f"总部 {hq_id} 没有 branch_levels 结构")
        return oc
    node = levels.get(branch)
    if not isinstance(node, dict):
        oc.errors.append(
            f"总部 {hq_id} 没有 {branch} 分支（存档里有：{', '.join(sorted(levels))}）")
        return oc

    old = node.get("level")
    old_supp = node.get("suppressed")
    if not isinstance(old_supp, int) or isinstance(old_supp, bool):
        old_supp = 0
    node["level"] = level
    if suppressed is not None:
        node["suppressed"] = suppressed
    w.touch("hqs.yml")
    oc.summary = f"总部 {hq_id} 的 {branch} 分支：等级 {old} → {level}"
    if suppressed is not None and suppressed != old_supp:
        oc.summary += f"，被压制 {old_supp} → {suppressed}"
    if isinstance(old, int) and level < old:
        oc.warnings.append(
            f"**降级**（{old} → {level}）—— 总部已经投过的点不会退回来，"
            "而且这个分支提供的加成/容量会立刻变小")
    return oc


def _hq_branch_suppressed(w, e: Edit) -> Outcome:
    """调**被压制的等级数**（`branch_levels[分支].suppressed`）。

    语义 = 游戏的 `branch_suppress`（`e166` 字节码）：压制 N 级 ⇒
    **生效等级 −N**、被压制数 **+N**，而「真实等级（`level + suppressed`）」不变。

    ⇒ 这里**自动重算 `level`**：

        新 level = (旧 level + 旧 suppressed) − 新 suppressed

    ⚠️ 压制只写在**战役进行中**的存档里才有意义 —— 游戏在一局结束时
    （`set_end_game` → `unsuppress_branch_levels`）会把压制全部还原。
    """
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    branch = e.params.get("branch")
    suppressed = e.params.get("suppressed")
    if not w.require(w.caps.can_edit_hqs, "hqs", "hqs.yml"):
        return oc
    if branch not in HQ_BRANCHES:
        oc.errors.append(
            f"未知的分支 {branch!r}；合法取值：{', '.join(HQ_BRANCHES)}")
        return oc
    if not isinstance(suppressed, int) or isinstance(suppressed, bool):
        oc.errors.append(
            f"被压制的等级数必须是整数（0–{HQ_BRANCH_MAX}），收到 {suppressed!r}")
        return oc
    if suppressed < 0 or suppressed > HQ_BRANCH_MAX:
        oc.errors.append(
            f"被压制的等级数必须在 0–{HQ_BRANCH_MAX} 之间，收到 {suppressed!r}")
        return oc

    hqs = w.table("hqs.yml", [])
    hq = _find_by_id(hqs, hq_id)
    if hq is None:
        oc.errors.append(f"存档里没有 id 为 {hq_id} 的总部")
        return oc
    levels = hq.get("branch_levels")
    if not isinstance(levels, dict):
        oc.errors.append(f"总部 {hq_id} 没有 branch_levels 结构")
        return oc
    node = levels.get(branch)
    if not isinstance(node, dict):
        oc.errors.append(
            f"总部 {hq_id} 没有 {branch} 分支（存档里有：{', '.join(sorted(levels))}）")
        return oc

    old_level = node.get("level")
    old_supp = node.get("suppressed")
    if not isinstance(old_level, int) or isinstance(old_level, bool):
        old_level = 0
    if not isinstance(old_supp, int) or isinstance(old_supp, bool):
        old_supp = 0
    real = old_level + old_supp            # 真实等级 = 解锁到几级
    if real > HQ_BRANCH_MAX:
        oc.errors.append(
            f"总部 {hq_id} 的 {branch} 分支等级 {old_level} + 被压制 {old_supp} "
            f"已经超过上限 {HQ_BRANCH_MAX}，先修正等级")
        return oc
    if suppressed > real:
        oc.errors.append(
            f"被压制 {suppressed} 级超过该分支的总等级 {real}（{branch} 分支）")
        return oc

    new_level = real - suppressed
    node["level"] = new_level
    node["suppressed"] = suppressed
    w.touch("hqs.yml")
    oc.summary = (f"总部 {hq_id} 的 {branch} 分支：被压制 {old_supp} → {suppressed}"
                  f"（生效等级 {old_level} → {new_level}，解锁到 {real} 级不变）")
    if suppressed > old_supp:
        oc.warnings.append(
            "压制期间，这个分支的**生效等级**会下降"
            f"（{old_level} → {new_level}）；游戏在一局结束时会把压制还原")
    elif suppressed < old_supp:
        oc.warnings.append(
            f"解除压制 —— 生效等级回到 {new_level}（解锁到 {real} 级不变）")
    return oc


def _hq_trucks(w, e: Edit) -> Outcome:
    """总部的**补给卡车数**（`hqs.yml` → `trucks`）。

    * 合法值 **1–5**（0 不行 —— 总部至少要有一辆补给卡车）；
    * 1–5 辆依次对应补给作用范围 **5 / 8 / 10 / 11 / 12** 格
      （游戏 `game.yml` → `supply_hubs_ranges`）；
    * **不涉及声望** —— 改卡车不动 `main.yml` 的任何数值。
    """
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    trucks = e.params.get("trucks")
    if not w.require(w.caps.can_edit_hqs, "hqs", "hqs.yml"):
        return oc
    if not isinstance(trucks, int) or isinstance(trucks, bool):
        oc.errors.append(f"卡车数必须是整数，收到 {trucks!r}")
        return oc
    if trucks < TRUCK_MIN or trucks > TRUCK_MAX:
        oc.errors.append(
            f"卡车数必须在 {TRUCK_MIN}–{TRUCK_MAX} 之间，收到 {trucks!r}"
            "（0 不行 —— 总部至少要有一辆补给卡车）")
        return oc

    hqs = w.table("hqs.yml", [])
    hq = _find_by_id(hqs, hq_id)
    if hq is None:
        oc.errors.append(f"存档里没有 id 为 {hq_id} 的总部")
        return oc

    old = hq.get("trucks")
    hq["trucks"] = trucks
    w.touch("hqs.yml")
    oc.summary = (f"总部 {hq_id} 的补给卡车：{old} → {trucks} 辆"
                  f"（补给作用范围 {TRUCK_RANGES[trucks - 1]} 格）")
    if isinstance(old, int) and trucks < old:
        oc.warnings.append(
            f"减少卡车会让总部的补给作用范围变小"
            f"（{TRUCK_RANGES[old - 1] if 1 <= old <= TRUCK_MAX else '?'} → "
            f"{TRUCK_RANGES[trucks - 1]} 格）")
    return oc


def _hq_branch_sp(w, e: Edit) -> Outcome:
    """总部分支里**某个技能的专精次数**（`branches` → `sp_used`）。

    **专精 = 该技能发动时的 CP 消耗 −1**（`e165` 字节码：`a.cost = max(0, a.cost - 1)`）。

    ⚠️ 存档里 `cost` 存的是**已经扣减过的** CP ⇒ 原始 CP = `cost + sp_used`。
    所以本函数**同时**改 `sp_used` 和 `cost`（两边一起动，存档才自洽）。

    * `sp_used` 必须落在 `[0, sp_avail]`；`sp_avail` 是存档里给的权威上限；
    * `sp_avail` 为 `null` 的技能（`force_pool` 分支的四个动作 + `motor_pool`）
      **没有技能点** ⇒ 报错，不静默忽略。
    """
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    branch = e.params.get("branch")
    action = e.params.get("action")
    sp_used = e.params.get("sp_used")
    if not w.require(w.caps.can_edit_hqs, "hqs", "hqs.yml"):
        return oc
    if branch not in HQ_BRANCHES:
        oc.errors.append(
            f"未知的分支 {branch!r}；合法取值：{', '.join(HQ_BRANCHES)}")
        return oc
    if not isinstance(action, str) or not action:
        oc.errors.append(f"必须指定技能（action），收到 {action!r}")
        return oc
    if not isinstance(sp_used, int) or isinstance(sp_used, bool) or sp_used < 0:
        oc.errors.append(f"专精次数必须是非负整数，收到 {sp_used!r}")
        return oc

    hqs = w.table("hqs.yml", [])
    hq = _find_by_id(hqs, hq_id)
    if hq is None:
        oc.errors.append(f"存档里没有 id 为 {hq_id} 的总部")
        return oc
    branches = hq.get("branches")
    if not isinstance(branches, dict):
        oc.errors.append(f"总部 {hq_id} 没有 branches（技能树）结构")
        return oc
    items = branches.get(branch)
    if not isinstance(items, list):
        oc.errors.append(
            f"总部 {hq_id} 的 {branch} 分支没有技能列表"
            f"（存档里有：{', '.join(sorted(branches))}）")
        return oc
    node = None
    for it in items:
        if isinstance(it, dict) and it.get("action") == action:
            node = it
            break
    if node is None:
        have = ", ".join(str(i.get("action")) for i in items if isinstance(i, dict))
        oc.errors.append(
            f"总部 {hq_id} 的 {branch} 分支里没有技能 {action!r}（有：{have}）")
        return oc

    sp_avail = node.get("sp_avail")
    if sp_avail is None:
        oc.errors.append(
            f"技能 {action!r} 没有技能点（sp_avail 为空）—— "
            "兵库分支的动作与车辆调度场不能专精")
        return oc
    if not isinstance(sp_avail, int) or isinstance(sp_avail, bool) or sp_avail < 0:
        oc.errors.append(f"技能 {action!r} 的 sp_avail 非法：{sp_avail!r}")
        return oc
    if sp_used > sp_avail:
        oc.errors.append(
            f"技能 {action!r} 最多能专精 {sp_avail} 次，请求 {sp_used} 次")
        return oc

    old_used = node.get("sp_used")
    if not isinstance(old_used, int) or isinstance(old_used, bool):
        old_used = 0
    old_cost = node.get("cost")
    if not isinstance(old_cost, int) or isinstance(old_cost, bool):
        old_cost = 0
    base_cost = old_cost + old_used          # 原始 CP 消耗（扣减前的）
    new_cost = base_cost - sp_used          # 专精 sp_used 次之后的 CP 消耗
    if new_cost < 0:
        oc.errors.append(
            f"技能 {action!r} 专精 {sp_used} 次会让 CP 消耗变成 {new_cost}（负数）")
        return oc

    node["sp_used"] = sp_used
    node["cost"] = new_cost
    w.touch("hqs.yml")
    oc.summary = (f"总部 {hq_id} 的 {branch} 分支 · {action}："
                  f"专精 {old_used} → {sp_used}（CP 消耗 {old_cost} → {new_cost}）")
    if sp_used < old_used:
        oc.warnings.append(
            f"**取消专精**（{old_used} → {sp_used}）—— "
            "该技能发动时的 CP 消耗会涨回去")
    if sp_used > old_used:
        oc.warnings.append(
            f"专精会让 **{action}** 发动时的 CP 消耗从 {old_cost} 降到 {new_cost}")
    return oc


def _hq_force_pool_add(w, e: Edit) -> Outcome:
    """总部兵库加一条。"""
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    entry = e.params.get("entry")
    index = e.params.get("index")
    if not w.require(w.caps.can_edit_force_pool, "force_pool", "hqs.yml"):
        return oc
    if not isinstance(entry, dict):
        oc.errors.append("兵库条目必须是字典")
        return oc
    if not isinstance(entry.get("quantity"), int) or isinstance(entry.get("quantity"), bool) \
            or entry.get("quantity") < 0:
        oc.errors.append(f"quantity 必须是非负整数，收到 {entry.get('quantity')!r}")
        return oc
    has_spec = bool(entry.get("spec"))
    has_equipment = bool(entry.get("equipment"))
    if has_spec and has_equipment:
        oc.errors.append("兵库条目同时有 spec 与 equipment（二选一），不能安全修改")
        return oc
    if not has_spec and not has_equipment:
        oc.errors.append("兵库条目必须给 spec（特种兵）或 equipment（兵种）之一")
        return oc

    hqs = w.table("hqs.yml", [])
    hq = _find_by_id(hqs, hq_id)
    if hq is None:
        oc.errors.append(f"存档里没有 id 为 {hq_id} 的总部")
        return oc
    pool = hq.get("force_pool")
    if not isinstance(pool, list):
        oc.errors.append(f"总部 {hq_id} 没有 force_pool 列表")
        return oc
    if index is None:
        index = len(pool)
    if not isinstance(index, int) or isinstance(index, bool) \
            or not (0 <= index <= len(pool)):
        oc.errors.append(f"总部 {hq_id} 的兵库没有第 {index} 条")
        return oc

    # 条目字段补齐：游戏自己写的是 {delay, nationality, quantity, spec?|equipment?}
    new = dict(entry)
    new.setdefault("delay", 0)
    new.setdefault("nationality", "")
    pool.insert(index, new)
    hq["force_pool"] = pool
    w.touch("hqs.yml")
    oc.summary = (f"总部 {hq_id} 兵库加一条"
                  f"（{new.get('spec') or new.get('equipment')} × {new.get('quantity')}）")
    oc.warnings.append(
        "兵库条目的**国籍**要填国籍 id（uk / us / german …），不是阵营"
        "（allies / axis）—— 填错游戏读不出来")
    return oc


def _hq_force_pool_remove(w, e: Edit) -> Outcome:
    """总部兵库删一条。"""
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    index = e.params.get("index")
    if not w.require(w.caps.can_edit_force_pool, "force_pool", "hqs.yml"):
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
    what = (entry.get("spec") or entry.get("equipment")) if isinstance(entry, dict) else "?"
    del pool[index]
    hq["force_pool"] = pool
    w.touch("hqs.yml")
    oc.summary = f"总部 {hq_id} 兵库删第 {index} 条（{what}）"
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
    if info.get("has_unit"):
        # ⚠️ unit_id 的真实语义 = 本战役为这张卡登记的**预留 id**（§8.1）
        reserved = _reserved_unit_id(w, card_type)
        if reserved is None:
            oc.errors.append(
                f"卡牌 {card_type} 会召唤单位，但本战役没有为它登记可召唤的单位"
                "（document/main.yml.card_type_units）—— 硬写进去用卡时游戏会崩"
                "（§7.5.1）")
            return oc
        if unit_id is None:
            unit_id = reserved
        elif unit_id != reserved:
            oc.errors.append(
                f"卡牌 {card_type} 预留的单位是 {reserved}，不能填 {unit_id}"
                "（填错会召唤出**错误的单位**）")
            return oc
    elif unit_id is not None:
        oc.errors.append(f"卡牌 {card_type} 不召唤单位，unit_id 必须是 None")
        return oc

    cards.append({"card_type": card_type,
                  "is_free": bool(e.params.get("is_free")),
                  "position": position,
                  "unit_id": unit_id,
                  "used": False})
    w.touch("cards.yml")
    oc.summary = f"加卡 {card_type}（槽位 {position}）"
    limit = CARD_DECK_LIMIT.get(_level_of(w))
    if limit is not None and len(cards) > limit:
        oc.warnings.append(
            f"手牌已经有 {len(cards)} 张，超过本难度（{_level_of(w)}）的"
            f"上限 {limit} —— 游戏可能只发前 {limit} 张")
    return oc


def _card_set(w, e: Edit) -> Outcome:
    """改手牌某一张的某个字段（目前只有 `is_free`）。"""
    oc = Outcome()
    position = e.params.get("position")
    field = e.params.get("field")
    value = e.params.get("value")
    if not w.require(w.caps.can_edit_hand, "hand", "cards.yml"):
        return oc
    if field not in CARD_FIELD_ALLOWED:
        oc.errors.append(
            f"不允许改手牌字段 {field!r}；可改：{', '.join(sorted(CARD_FIELD_ALLOWED))}")
        return oc
    if not isinstance(value, bool):
        oc.errors.append(f"{field} 必须是 True / False，收到 {value!r}")
        return oc

    cards = w.table("cards.yml", [])
    if not isinstance(cards, list):
        oc.errors.append("根 cards.yml 结构异常")
        return oc
    target = next((c for c in cards
                   if isinstance(c, dict) and c.get("position") == position), None)
    if target is None:
        oc.errors.append(f"手牌里没有槽位号为 {position} 的卡")
        return oc

    old = target.get(field)
    target[field] = value
    w.touch("cards.yml")
    oc.summary = f"手牌槽位 {position} 的 {field}：{old} → {value}"
    oc.warnings.append(
        "手牌上的 is_free **没有玩法影响** —— 只改 tooltip 文案与卡背贴图；"
        "想改价格要改货架上的卡（§7.5.2）")
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


def _store_list(w, front, sub):
    """取 `{战线: {sub: [...]}}` 里的那个列表。

    `store.yml` 是**两层**的：`{战线: {store: [...], elite_store: [...]}}`
    （`e154` 实证）—— 不带 `sub` 会改错列表（规范 §8.1）。

    返回 `(entries, None)` 或 `(None, 错误说明)`。
    """
    store = w.table("store.yml", {})
    if not isinstance(store, dict):
        return None, "根 store.yml 结构异常"
    if front not in store:
        return None, (f"存档里没有战线 {front!r} —— 只能改存档已有的战线键，"
                      "不要凭空新建（§10 第 12 条）")
    blob = store.get(front)
    if not isinstance(blob, dict):
        return None, (f"战线 {front} 的商店结构异常"
                      "（应是 {store: [...], elite_store: [...]}）")
    entries = blob.get(sub)
    if entries is None:
        label = "普通商店" if sub == "store" else "精英商店"
        return None, f"战线 {front} 本次会议没有启用{label}（{sub} 是空的）"
    if not isinstance(entries, list):
        return None, f"战线 {front} 的 {sub} 结构异常"
    return entries, None


def _validate_store_entry(entry) -> list[str]:
    """校验一条要上架的商品（schema 来自游戏的 `store_schema`，`e154` 实证）。

    * `price` 必填、非负整数；
    * `quantity` 必填、正整数；
    * `spec` 与 `equipment` **Exclusive（二选一，不能都给）**。
    """
    errs: list[str] = []
    if not isinstance(entry, dict):
        return ["商品条目必须是字典"]
    has_spec = entry.get("spec") is not None
    has_eq = entry.get("equipment") is not None
    if has_spec and has_eq:
        errs.append("spec 与 equipment 二选一，不能都给")
    if not has_spec and not has_eq:
        errs.append("必须给 spec（特种兵）或 equipment（兵种）之一")
    price = entry.get("price")
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        errs.append(f"price={price!r} 必须是非负整数")
    qty = entry.get("quantity")
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        errs.append(f"quantity={qty!r} 必须是正整数 —— 游戏没有「售罄」标记，"
                    "下架请**删除该条目**（§4.6、§6.3）")
    nat = entry.get("nationality")
    if not isinstance(nat, str) or not nat:
        errs.append("nationality 必须是国籍 id（uk / us / german …），不是阵营")
    return errs


def _check_store_universe(w, entry) -> list[str]:
    """商品本身必须是**游戏定义过的**（schema 是枚举校验）。

    依据 = 战役包该会议所有战线的默认商店 + 存档自己的商店 + 游戏包的特种兵表。
    拿不到游戏包就不查（只提示，不拦）。
    """
    if w.catalog is None:
        return []
    main = w.table("main.yml", {})
    in_state = (main.get("in_state") or {}) if isinstance(main, dict) else {}
    campaign_id = main.get("campaign_id") if isinstance(main, dict) else None
    universe = w.catalog.store_item_universe(campaign_id, in_state.get("conference"))

    save_equip: set[str] = set()
    save_nat: set[str] = set()
    for blob in w.save.root_store().values():
        if not isinstance(blob, dict):
            continue
        for items in blob.values():
            if not isinstance(items, list):
                continue
            for e in items:
                if not isinstance(e, dict):
                    continue
                if e.get("equipment"):
                    save_equip.add(str(e["equipment"]))
                if e.get("nationality"):
                    save_nat.add(str(e["nationality"]))
    equips = universe["equipment"] | save_equip
    nats = universe["nationality"] | save_nat

    errs: list[str] = []
    spec = entry.get("spec")
    if spec and universe["spec"] and spec not in universe["spec"]:
        errs.append(f"特种兵 {spec!r} 游戏里没有 —— 不能凭空新增种类")
    eq = entry.get("equipment")
    if eq and equips and eq not in equips:
        errs.append(f"兵种 {eq!r} 游戏里没有（可选：{', '.join(sorted(equips))}）")
    nat = entry.get("nationality")
    if nat and nats and nat not in nats:
        errs.append(f"国籍 {nat!r} 游戏里没有（可选：{', '.join(sorted(nats)[:12])} …）")
    return errs


def _shelf_of(w):
    """根 `main.yml` 的 `card_store`（货架）；不在会议阶段返回 None。"""
    main = w.table("main.yml", {})
    if not isinstance(main, dict):
        return None
    shelf = main.get("card_store")
    return shelf if isinstance(shelf, list) else None


def _card_store_set(w, e: Edit) -> Outcome:
    """改卡牌商店货架上的某一张（换牌 / 改成免费 / 改成收费）。"""
    oc = Outcome()
    position = e.params.get("position")
    card_type = e.params.get("card_type")
    is_free = e.params.get("is_free")
    if not w.require(w.caps.can_edit_shelf, "shelf", "main.yml"):
        return oc
    if card_type is None and is_free is None:
        oc.errors.append("card_store_set 至少要改一个字段（card_type / is_free）")
        return oc
    if is_free is not None and not isinstance(is_free, bool):
        oc.errors.append(f"is_free 必须是 True / False，收到 {is_free!r}")
        return oc

    main = w.table("main.yml", {})
    if not isinstance(main, dict):
        oc.errors.append("根 main.yml 结构异常")
        return oc
    shelf = main.get("card_store")
    if not isinstance(shelf, list):
        oc.errors.append(
            "当前不在会议界面 —— 根 main.yml 里没有 card_store（货架不存在）")
        return oc
    target = next((c for c in shelf
                   if isinstance(c, dict) and c.get("position") == position), None)
    if target is None:
        oc.errors.append(f"货架上没有槽位号为 {position} 的卡")
        return oc

    if card_type is not None:
        if w.catalog is None:
            oc.errors.append("没有游戏包目录，无法校验卡牌能不能上架")
            return oc
        wl = w.catalog.card_whitelist(w.save)
        if not wl.is_allowed(card_type):
            reason = wl.reason(card_type) or "不在本战役商店的可上架清单里"
            oc.errors.append(f"卡牌 {card_type} 不能上架：{reason}")
            return oc
        info = w.catalog.card_type(card_type) or {}
        if info.get("has_unit"):
            uid = _reserved_unit_id(w, card_type)
            if uid is None:
                oc.errors.append(
                    f"卡牌 {card_type} 会召唤单位，但本战役没有为它登记可召唤的单位")
                return oc
            target["unit_id"] = uid
        else:
            target["unit_id"] = None
        old_type = target.get("card_type")
        target["card_type"] = card_type
        oc.summary = f"货架槽位 {position} 的牌：{old_type} → {card_type}"

    if is_free is not None:
        old_free = target.get("is_free")
        target["is_free"] = is_free
        if oc.summary:
            oc.summary += f"；{'改成免费' if is_free else '改成收费'}"
        else:
            oc.summary = (f"货架槽位 {position}：{'改成免费' if is_free else '改成收费'}"
                          f"（原来 {old_free}）")

    w.touch("main.yml")
    if is_free:
        oc.warnings.append(
            "货架上的 is_free=True = **价格 0**（不扣声望）—— 这是白嫖（§7.5.2）")
    oc.warnings.append(
        "货架只管**这一场会议** —— 进入新会议时游戏会按权重重掷（§7.5）")
    return oc


def _card_store_remove(w, e: Edit) -> Outcome:
    """下架货架上的一张卡。"""
    oc = Outcome()
    position = e.params.get("position")
    if not w.require(w.caps.can_edit_shelf, "shelf", "main.yml"):
        return oc
    main = w.table("main.yml", {})
    if not isinstance(main, dict):
        oc.errors.append("根 main.yml 结构异常")
        return oc
    shelf = main.get("card_store")
    if not isinstance(shelf, list):
        oc.errors.append(
            "当前不在会议界面 —— 根 main.yml 里没有 card_store（货架不存在）")
        return oc
    target = next((c for c in shelf
                   if isinstance(c, dict) and c.get("position") == position), None)
    if target is None:
        oc.errors.append(f"货架上没有槽位号为 {position} 的卡")
        return oc
    shelf.remove(target)
    w.touch("main.yml")
    oc.summary = f"下架货架槽位 {position}（{target.get('card_type')}）"
    return oc


def _card_store_add(w, e: Edit) -> Outcome:
    """上架一张卡到货架。"""
    oc = Outcome()
    position = e.params.get("position")
    card_type = e.params.get("card_type")
    is_free = bool(e.params.get("is_free"))
    if not w.require(w.caps.can_edit_shelf, "shelf", "main.yml"):
        return oc
    if not isinstance(position, int) or isinstance(position, bool) or position < 1:
        oc.errors.append(f"槽位号必须是 ≥ 1 的整数，收到 {position!r}")
        return oc
    if w.catalog is None:
        oc.errors.append("没有游戏包目录，无法校验卡牌能不能上架")
        return oc

    main = w.table("main.yml", {})
    if not isinstance(main, dict):
        oc.errors.append("根 main.yml 结构异常")
        return oc
    shelf = main.get("card_store")
    if not isinstance(shelf, list):
        oc.errors.append(
            "当前不在会议界面 —— 根 main.yml 里没有 card_store（货架不存在）")
        return oc

    limit = CARD_STORE_LIMIT.get(_level_of(w), 5)
    if position > limit:
        oc.errors.append(f"货架只有 {limit} 格（第 {position} 格不存在）")
        return oc
    if any(isinstance(c, dict) and c.get("position") == position for c in shelf):
        oc.errors.append(f"槽位 {position} 已经被占了")
        return oc

    wl = w.catalog.card_whitelist(w.save)
    if not wl.is_allowed(card_type):
        reason = wl.reason(card_type) or "不在本战役商店的可上架清单里"
        oc.errors.append(f"卡牌 {card_type} 不能上架：{reason}")
        return oc

    unit_id = None
    info = w.catalog.card_type(card_type) or {}
    if info.get("has_unit"):
        unit_id = _reserved_unit_id(w, card_type)
        if unit_id is None:
            oc.errors.append(
                f"卡牌 {card_type} 会召唤单位，但本战役没有为它登记可召唤的单位")
            return oc

    shelf.append({"card_type": card_type, "is_free": is_free,
                  "position": position, "unit_id": unit_id, "used": False})
    w.touch("main.yml")
    oc.summary = f"上架卡 {card_type}（槽位 {position}）"
    if is_free:
        oc.warnings.append("is_free=True = **价格 0**（不扣声望）—— 这是白嫖")
    oc.warnings.append(
        "货架只管**这一场会议** —— 进入新会议时游戏会按权重重掷（§7.5）")
    return oc


def _store_set(w, e: Edit) -> Outcome:
    """改商店条目的 price / quantity（根 `store.yml`）。"""
    oc = Outcome()
    front = e.params.get("front")
    sub = e.params.get("sub")
    index = e.params.get("index")
    field = e.params.get("field")
    value = e.params.get("value")
    if not w.require(w.caps.can_edit_store, "store", "store.yml"):
        return oc
    if sub not in STORE_SUBS:
        oc.errors.append(
            f"未知的子商店 {sub!r}；合法取值：{', '.join(STORE_SUBS)}"
            "（store.yml 是两层结构，普通商店 / 精英商店）")
        return oc
    if field not in ("price", "quantity"):
        oc.errors.append(f"商店条目只能改 price / quantity，收到 {field!r}")
        return oc
    entries, err = _store_list(w, front, sub)
    if err:
        oc.errors.append(err)
        return oc
    if not isinstance(index, int) or isinstance(index, bool) \
            or not (0 <= index < len(entries)):
        oc.errors.append(f"战线 {front} 的 {sub} 没有第 {index} 条商品")
        return oc
    entry = entries[index]
    if not isinstance(entry, dict):
        oc.errors.append(f"战线 {front} 的 {sub} 第 {index} 条结构异常")
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
    oc.summary = (f"商店 {front}/{sub} 第 {index} 条"
                  f"（{entry.get('spec') or entry.get('equipment')}）"
                  f" 的 {field}：{old} → {value}")
    if field == "price" and value == 0:
        oc.warnings.append("price=0 表示**免费商品**，不是下架")
    nat = entry.get("nationality")
    if isinstance(nat, str) and nat.lower() in ("allies", "axis"):
        oc.warnings.append(
            f"nationality={nat!r} 看着像阵营 —— 它要填**国籍 id**"
            "（uk / us / german / …），不是 allies / axis（§10 第 15 条）")
    return oc


def _store_remove(w, e: Edit) -> Outcome:
    """下架商品 —— 删条目（根 `store.yml`）。"""
    oc = Outcome()
    front = e.params.get("front")
    sub = e.params.get("sub")
    index = e.params.get("index")
    if not w.require(w.caps.can_edit_store, "store", "store.yml"):
        return oc
    if sub not in STORE_SUBS:
        oc.errors.append(
            f"未知的子商店 {sub!r}；合法取值：{', '.join(STORE_SUBS)}")
        return oc
    entries, err = _store_list(w, front, sub)
    if err:
        oc.errors.append(err)
        return oc
    if not isinstance(index, int) or isinstance(index, bool) \
            or not (0 <= index < len(entries)):
        oc.errors.append(f"战线 {front} 的 {sub} 没有第 {index} 条商品")
        return oc
    entry = entries[index]
    what = (entry.get("spec") or entry.get("equipment")) if isinstance(entry, dict) else "?"
    del entries[index]
    w.touch("store.yml")
    oc.summary = f"下架商店 {front}/{sub} 第 {index} 条（{what}）"
    return oc


def _store_add(w, e: Edit) -> Outcome:
    """上架新商品（根 `store.yml`）。"""
    oc = Outcome()
    front = e.params.get("front")
    sub = e.params.get("sub")
    entry = e.params.get("entry")
    if not w.require(w.caps.can_edit_store, "store", "store.yml"):
        return oc
    if sub not in STORE_SUBS:
        oc.errors.append(
            f"未知的子商店 {sub!r}；合法取值：{', '.join(STORE_SUBS)}")
        return oc
    errs = _validate_store_entry(entry)
    if errs:
        oc.errors.extend(errs)
        return oc
    errs = _check_store_universe(w, entry)
    if errs:
        oc.errors.extend(errs)
        return oc

    entries, err = _store_list(w, front, sub)
    if err:
        oc.errors.append(err)
        return oc

    new = {"equipment": entry.get("equipment"), "spec": entry.get("spec"),
           "nationality": entry.get("nationality"),
           "price": entry.get("price"), "quantity": entry.get("quantity")}
    # 只留真正填了的那个 —— 游戏自己不会两个都写
    if new["spec"] is None:
        new.pop("spec")
    if new["equipment"] is None:
        new.pop("equipment")
    entries.append(new)
    w.touch("store.yml")
    oc.summary = (f"上架商品 {new.get('spec') or new.get('equipment')}"
                  f"（{front}/{sub}，价格 {new.get('price')}，库存 {new.get('quantity')}）")
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
    "hq_field": _hq_field,
    "hq_trucks": _hq_trucks,
    "hq_branch_level": _hq_branch_level,
    "hq_branch_suppressed": _hq_branch_suppressed,
    "hq_branch_sp": _hq_branch_sp,
    "hq_force_pool_add": _hq_force_pool_add,
    "hq_force_pool_remove": _hq_force_pool_remove,
    "card_add": _card_add,
    "card_remove": _card_remove,
    "card_set": _card_set,
    "store_set": _store_set,
    "store_remove": _store_remove,
    "store_add": _store_add,
    "card_store_set": _card_store_set,
    "card_store_remove": _card_store_remove,
    "card_store_add": _card_store_add,
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
