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

from .catalog import THEATER_ASSET_TYPES
from .container import ORDER_LISTS, theater_group_index, theater_side_cn
from .edits import UNSET, Edit

__all__ = ["Outcome", "apply_edit"]


@dataclass
class Outcome:
    """一次编辑的结果。"""

    summary: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 单位字段

#: **允许改**的单位字段。`type` 不在其中 —— 它是只读信息（§5.4、§7.5）。
#:
#: **`uv`（单位在地图上的坐标）也不在其中** —— 改坐标极易造出非法局面
#: （单位落到地图外 / 与别的单位同格）；游戏的 `uv_schema` 要求它是 `[int, int]`，
#: 写错**存档直接打不开**；界面本来也没有改坐标的入口 ⇒ 没把握就不给，宁可不写也不写坏。
UNIT_FIELD_ALLOWED = {
    "xp", "act_st", "sup_st", "name_brief", "name_full",
    "entr", "supply", "ap", "mp",
}

#: 字段的**中文名**（变更说明里用，别让玩家对着 `entr` 猜）。
#:
UNIT_FIELD_CN = {
    "entr": "工事等级",
    "ap": "行动力",
    "mp": "移动力",
    "supply": "补给",
}

#: 战斗外改会被场景预设覆盖的字段（§3.5.8 存活性矩阵）
UNIT_FIELD_RISKY = {"uv", "entr", "supply", "ap", "mp"}

#: 单位数值字段的取值范围（§5.2）
UNIT_FIELD_RANGE = {
    "xp": (0, 400),
    "entr": (0, 2),          # 游戏的 `unit_max_entr_level = 2`（U85 字节码实证）
    "supply": (0, 3),
    "ap": (0, 3),            # 游戏的 `ap_max_value = 3`（ap_none/conv/lock/full）
    "mp": (0, None),         # 上限 = 类型的基础移动力（`_type.move`），没法静态校验
    "act_st": (0, None),
    "sup_st": (0, None),
}

#: 手牌张数上限（`card_deck_limit`，按难度；`e158` 字节码实证）
CARD_DECK_LIMIT = {"easy": 5, "normal": 5, "classic": 4, "hard": 3}

#: 游戏的难度列表（`state/constants.pyc::play_levels`，字节码实证）
PLAY_LEVELS = ("easy", "normal", "classic", "hard")

#: 货架格数（`card_store_limit`，四个难度恒为 5；`e158` 实证）
CARD_STORE_LIMIT = {"easy": 5, "normal": 5, "classic": 5, "hard": 5}

#: 手牌里**允许改**的字段（§7.5.2）
CARD_FIELD_ALLOWED = {"is_free"}

#: 总部**允许改**的字段（§7.4）
#:
#: ⚠️ `name_brief` / `name_full` 是 U44 补上的 ——
#: 验收（F1）发现总部页 UI 上有「改名」按钮，但这里**没有**这两个字段
#: ⇒ 一点就报「不允许改总部字段」。
#: 取证：游戏的 `scenario_hq_schema` 里 `'name_brief': Or(str, None)`
#: ⇒ 名字字段本来就是字符串（或 None），写明文合法（与单位改名同一套口径）。
#: （游戏自己的改名走根 main.yml 的 `renamed_hqs` —— 那是 **id 重映射**，
#:  键和值都是正整数，不是名字表；它为空时游戏就显示 hqs.yml 里的 name_brief。）
HQ_FIELD_ALLOWED = {
    "cp", "max_cp", "supply",
    "trucks", "prisoners", "loss_count", "intels_revealed",
    "name_brief", "name_full",
}

#: 总部经验与经验目标不可改（游戏每次战役推进都重算，写了也白写）。
#:
#: 取证（游戏字节码）：`state/campaign/campaign.pyc::Campaign._set_hqs_xp_target`
#: —— 每次**战役推进**都会按「该总部在战役里的单位数 × 场景回合数 ×
#: `hq_xp_taget_fudge_factor`」**重算**每个总部的 `xp_target`。
#: ⇒ 静态写进去的值会被游戏下一次推进直接覆盖（功能基本无效），
#: 而把 `xp`（当前经验）改大会触发游戏自己的「可升级」连锁 ——
#: 升级我们本来就能直接改（分支等级 / 技能专精），没必要走这条有副作用的路。
HQ_XP_FIELDS = ("xp", "xp_target")

#: 总部里**是字符串**的字段（其余都是整数）
HQ_FIELD_TEXT = {"name_brief", "name_full"}

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

#: 总部的**补给数**合法范围 —— 游戏 schema 是硬范围（U25 字节码取证）：
#: `state/entities/data_validation/hq.pyc::_scenario_base_hq_schema`
#: ⇒ `Required('supply'): All(int, Range(min=0, max=3))`
#: ⇒ 写 4 以上**存档直接打不开**（voluptuous 校验失败）。
HQ_SUPPLY_MIN, HQ_SUPPLY_MAX = 0, 3

#: 战区资产三个字段的**合法范围**（U20 字节码取证 —— `lib/uoc2/` 反汇编）：
#:
#: | 字段 | 游戏里的含义 | 游戏的 voluptuous schema | 合法范围 |
#: |---|---|---|---|
#: | `to_use` | 当前剩余可用次数 | `All(int, Range(min=0))` | **0 – ∞** |
#: | `uses_total` | 本场景剩余总次数（`None` = 无限） | `Or(None, All(int, Range(min=0)))` | **0 – ∞ 或 None** |
#: | `uses_turn` | 每回合恢复次数 | `All(int, Range(min=1))` | **1 – ∞** |
#:
#: 依据：`state/scenario/scenario_data_validation.py`（`theater_asset_dict`）、
#: `state/game/game_data_validation.py`（`game_theater_asset_dict`）、
#: `tools/data_validation.py`（`nonnegative_int_schema` / `positive_int_schema`）。
#:
#: ⇒ 超范围不是「显示异常」，而是 **voluptuous 校验失败 ⇒ 存档直接打不开**。
THEATER_TO_USE_MIN = 0
THEATER_USES_TOTAL_MIN = 0
THEATER_USES_TURN_MIN = 1

#: 战区资产三个字段的中文名（变更清单 / GUI 用）
THEATER_FIELD_CN = {
    "to_use": "当前可用",
    "uses_total": "本场景剩余",
    "uses_turn": "每回合恢复",
}

#: 战区资产**全集** —— 唯一来源是 `catalog.THEATER_ASSET_TYPES`
#: （游戏常量 `uoc2.state.constants.theater_asset_types`，U45 字节码取证）。
#:
#: 游戏的 `scenario_data_validation.theater_asset_dict` 是
#: `Required('asset'): In(theater_asset_types)` ⇒ **存档里只认这 7 个**，
#: 写别的名字 voluptuous 校验失败 ⇒ **存档直接打不开**。

#: 运行时存档里战区资产一项的**字段全集**（U45 实测：730 个战斗文件、
#: 2320 个条目，字段组合 **100% 都是这 5 个**）。
#:
#: ⚠️ **场景定义**（游戏包 `scenarios/<id>/main.yml`）里只有 3 个字段
#: （`asset` / `uses_total` / `uses_turn`），**没有** `to_use` ——
#: 那两个是运行时字段（`Game.new` 载入时现算）。
THEATER_ITEM_FIELDS = ("asset", "to_use", "to_use_not_used",
                       "uses_total", "uses_turn")

#: 新增战区资产时 `uses_total` 的**下限**。
#:
#: ⚠️ **0 不行** —— 游戏回合开始时按 `to_use = min(uses_turn, uses_total)`
#: 恢复（`Game.theater_assets_start_turn`），`uses_total=0` ⇒ `to_use` 恒为 0
#: ⇒ 这个资产**永远用不了**，却还在游戏里占一个按钮 —— 就是「000 残留」。
#: （存档里**已存在**的 `uses_total=0` 是正常的：那是「已经用完」的状态。）
THEATER_ADD_USES_TOTAL_MIN = 1

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

#: 游戏定义过的**兵种**（商店 / 兵库条目的 `equipment` 字段只能填这两个）。
#: 依据 = 游戏的存档 schema（`state/entities/data_validation/force_pool.pyc`，
#: U107 字节码实证）：
#: ```python
#: _all_eq = constants.unit_equipments + (constants.unit_equipment_none,)
#: _equipment_schema = In(_all_eq)        # = In(('armor', 'infantry'))
#: ```
#: ⚠️ 之前核心库拿「本次会议商店在售的兵种」当门 ⇒ **过严**
#: （某个会议只卖 infantry 时，写 armor 明明游戏能读却被拒）。
GAME_EQUIPMENTS = ("armor", "infantry")


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


def _level_cn(lv: str) -> str:
    """难度的中文名 —— **一律查游戏 locale**（`id_difficulty_<lv>`），
    查不到就退回原值（**绝不自己翻译**，§5.7）。"""
    try:
        from . import locale as _locale
        return _locale.default().get("id_difficulty_" + str(lv), "") or str(lv)
    except Exception:
        return str(lv)


def _level(w, e: Edit) -> Outcome:
    """难度（根 `main.yml` 的 `level`）。

    **难度决定手牌上限**（`card_deck_limit`：easy/normal 5、classic 4、hard 3）
    ⇒ 手里牌数超过新上限时**硬拦**：让玩家先删手牌。
    （改完难度，这个存档**以后开的新会议**才会按新难度生成：
      免费卡数 `card_store_free_cards`、折扣卡数 `discounted_cards_limit`、
      AI 强度、重置会议时重建的 HQ 卡车 / 工程兵 / 步兵阶梯 `_restat_d`。）
    """
    oc = Outcome()
    value = e.params.get("value")
    if value not in PLAY_LEVELS:
        oc.errors.append(
            f"难度只能是 {'、'.join(PLAY_LEVELS)}，收到 {value!r}")
        return oc
    main = w.table("main.yml", {})
    if not isinstance(main, dict):
        oc.errors.append("根 main.yml 结构异常")
        return oc
    old = main.get("level")
    if old == value:
        oc.summary = "难度没有变化"
        return oc

    limit = CARD_DECK_LIMIT[value]
    n_hand = len(w.save.root_cards())
    if n_hand > limit:
        oc.errors.append(
            f"手里有 {n_hand} 张牌，而「{_level_cn(value)}」最多只能放 {limit} 张 —— "
            f"请先删手牌再改难度（或者选一个手牌上限 ≥ {n_hand} 张的难度）")
        return oc

    main["level"] = value
    w.touch("main.yml")
    oc.summary = f"难度：{_level_cn(old) if old else '（空）'} → {_level_cn(value)}"
    return oc


#: **战役名册**（campaign_doc）里与根表同名的两张表 —— **U148**。
#:
#: 存档里有**两份**单位/总部表：
#:
#: | 表 | 内容 | 谁在显示 |
#: |---|---|---|
#: | 根 `units.yml` / `hqs.yml` | **已经登场过**的（实测 354 / 23 条） | **战斗中**（`game_world`） |
#: | `document/units.yml` / `document/hqs.yml` | **整场战役的全部**（实测 835 / 47 条） | **战役地图 / 主界面**（`main_screen`） |
#:
#: 两份表的 id 是**同一套编号**、同 id 的 `name_brief` **完全一致**
#: （实测 9 个存档 100% 一致）⇒ 改名按 id 同步即可。
#:
    # ⚠️ 改名要**两份都改** —— 战役地图显示的是**名册**那份。
ROSTER_ENTRY = {"units.yml": "document/units.yml",
                "hqs.yml": "document/hqs.yml"}


#: ⚠️ **游戏开着**时改盘 ⇒ 退出游戏时它会把**内存里的存档**写回去 ⇒ 你的改动被覆盖。
#:
                # ⚠️ 游戏开着时改盘 ⇒ 退出时它会把内存里的存档写回去 ⇒ 改名被覆盖。
#:
GAME_RUNNING_WARNING = (
    "⚠️ 游戏**开着**时改盘 ⇒ 退出游戏时它会把内存里的存档写回去 ⇒ "
    "你的改动会被覆盖 ⇒ **改之前先退出游戏**")


def _rename_fields(obj: dict, field: str, value) -> dict:
    """改名要**一并**改掉哪些字段。

    * `name_brief` —— 显示名（**必改**）；
    * `name_super_brief` —— 战役条上总部的简称标签（**只有总部有**）
      ⇒ **总是**一起改，否则战役地图顶上那个 HQ 标签是空的
      （游戏 `campaign_ctrl._hq_bar_button` 读的就是它）；
    * `name_full` —— 完整名：**原来不是 null 才改**
      （null = "没有另一个名字"，别凭空造一个）。

    ⚠️ 依据（字节码）：显示名的取值点几乎全是 `name_brief`
    （`unit_sheet.py:101` / `scalables.py:601` / `campaign_ctrl.py:1784`），
    但 `name_full` 会出现在 tooltip 里、`name_super_brief` 在战役条上
    ⇒ 只改 `name_brief` 会留下"有的地方还是旧名"。

    ⚠️ 根表与名册**各按自己的原值判断**（同一套规则、两个对象）。
    """
    out = {field: value}
    if field == "name_brief":
        for k in ("name_full", "name_super_brief"):
            if k == "name_full" and not isinstance(obj.get(k), str):
                continue
            if k in obj:
                out[k] = value
    return out


def _sync_rename_to_roster(w, entry: str, obj_id, field: str, value) -> bool:
    """把改名**同步**到战役名册（`document/` 那份）。返回是否真的改了。

    ⚠️ 名册可能**没有这个 id**（这个单位还没登场）或**整个文件不存在**
    （独立场景存档没有 `document/`）⇒ 静默跳过、**不报错**
    （那不是错误，只是没有第二份要改）。
    """
    doc_entry = ROSTER_ENTRY.get(entry)
    if not doc_entry:
        return False
    roster = w.table(doc_entry, [])
    if not isinstance(roster, list):
        return False
    item = _find_by_id(roster, obj_id)
    if item is None:
        return False
    changed = False
    for k, v in _rename_fields(item, field, value).items():
        if k in item and item.get(k) != v:
            item[k] = v
            changed = True
    if changed:
        w.touch(doc_entry)
    return changed


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
    # ⚠️ 改名要**两份都改** —— 战役地图显示的是**名册**那份
    # （`document/units.yml`），只改根表 ⇒ 玩家在战役地图上看不到变化。
    if field in ("name_brief", "name_full"):
        for k, v in _rename_fields(unit, field, value).items():
            if k in unit and unit.get(k) != v:
                unit[k] = v
        _sync_rename_to_roster(w, "units.yml", unit_id, field, value)
        # ⚠️ 游戏开着 ⇒ 退出时它把内存里的存档写回去 ⇒ 改名被覆盖。
        oc.warnings.append(GAME_RUNNING_WARNING)

    # 写入时**自动配平**「普通部队」（活跃 + 被压制）。
    #
    # 背景：上限 `max_st` 约束的是**普通部队**（游戏读档时也只查这两项：
    # `UnitState.check_data_consistency`），**特种兵不占名额**
    # （特种兵另占「总战力」，而总战力超上限游戏是允许的 —— 真实存档里
    #   就有 166 个这样的单位 ⇒ 7 兵 + 2 特种兵是合法的）。
    #
    # 为什么必须在这里配平：前端滚轮会**同时**改 act_st 与 sup_st，但两条编辑依次执行 ⇒ 先改 act_st 时 sup_st 还是旧值 ⇒ 会**误报**超上限。
    #
    # 配平口径与前端夹取、与游戏读档修复（`UnitState._repair_data`）一致：
    # 先从**压制**里扣，不够再截**活跃**。
    if field in ("act_st", "sup_st") and w.catalog is not None:
        limit = w.catalog.max_st(unit.get("type"))
        if limit is not None:
            a = int(unit.get("act_st") or 0)
            s = int(unit.get("sup_st") or 0)
            if a + s > limit:
                s_old, a_old = s, a
                need = a + s - limit
                if s >= need:
                    s -= need
                else:
                    s = 0
                    a = limit
                unit["sup_st"] = s
                unit["act_st"] = a
                if field == "act_st":
                    value = a                # 变更说明要显示**实际写入**的值
                if s != s_old:
                    oc.warnings.append(
                        f"该单位普通部队合计（活跃 + 被压制）不能超过类型上限 "
                        f"{limit}（{unit.get('type')} 的 max_st）—— "
                        f"已把被压制兵力从 {s_old} 调到 {s}")
                else:
                    oc.warnings.append(
                        f"该单位普通部队合计（活跃 + 被压制）不能超过类型上限 "
                        f"{limit}（{unit.get('type')} 的 max_st）—— "
                        f"活跃兵力已按上限截断（{a_old} → {a}）")
    if field == "entr":
        oc.summary = f"单位 {unit_id} 的工事等级（entr）：{old!r} → {value!r}"
    elif field == "ap":
        oc.summary = f"单位 {unit_id} 的行动力（ap）：{old!r} → {value!r}"
    elif field == "mp":
        oc.summary = f"单位 {unit_id} 的移动力（mp）：{old!r} → {value!r}"
    elif field == "supply":
        oc.summary = f"单位 {unit_id} 的补给（supply）：{old!r} → {value!r}"
    else:
        oc.summary = f"单位 {unit_id} 的 {field}：{old!r} → {value!r}"
    if field in UNIT_FIELD_RISKY:
        if field == "entr":
            oc.warnings.append(
                f"单位 {unit_id} 的工事等级在战斗外改，"
                "下一次开打时可能被场景预设覆盖（§3.5.8）")
        elif field == "ap":
            oc.warnings.append(
                f"单位 {unit_id} 的行动力在战斗外改，"
                "下一次开打时可能被场景预设覆盖（§3.5.8）")
        elif field == "mp":
            oc.warnings.append(
                f"单位 {unit_id} 的移动力在战斗外改，"
                "下一次开打时可能被场景预设覆盖（§3.5.8）")
        else:
            oc.warnings.append(
                f"单位 {unit_id} 的 {field} 在战斗外改，"
                "下一次开打时可能被场景预设覆盖（§3.5.8）")
    if field == "xp":
        oc.warnings.append(
            "登陆单位被补兵后 XP 会被重算掉一部分（§3.5.6）")
    if field in ("name_brief", "name_full") and isinstance(value, str):
        if value.startswith("id_") or value.startswith("idp_"):
            oc.warnings.append(
                f"{value!r} 看起来是本地化 id，游戏会去本地化表里查它；"
                "想显示固定文字请直接写明文（§5.5）")
    # 上面已经**自动配平**过了 ⇒ 这里只兜底（类型上限拿不到时）说清后果：游戏读档修复（`UnitState._repair_data`）会把超出的部分**截回上限**。
    if field in ("act_st", "sup_st") and w.catalog is not None:
        limit = w.catalog.max_st(unit.get("type"))
        if limit is not None:
            total = int(unit.get("act_st") or 0) + int(unit.get("sup_st") or 0)
            if total > limit:
                oc.warnings.append(
                    f"该单位普通部队合计 {total}（活跃 + 被压制）超过该类型的上限 "
                    f"{limit}（{unit.get('type')} 的 max_st）—— 特种兵不占这个名额；"
                    f"游戏读档时会把超出的部分截回 {limit}，这部分会白改")
    return oc


def _unit_spec_add(w, e: Edit) -> Outcome:
    """加特种（根 `units.yml`）。"""
    oc = Outcome()
    unit_id = e.params.get("unit_id")
    spec_type = e.params.get("spec_type")
    # 新挂的特种兵可以**一上来就是被压制的**（`active=False`）——游戏里「被压制」就是 `active=False`（没有独立的 suppressed 字段）⇒ 与「先挂再压制」写出来的存档**完全一样**。
    active = e.params.get("active", True)
    if not isinstance(active, bool):
        oc.errors.append(
            f"active 必须是布尔值（True = 活跃 / False = 被压制），收到 {active!r}")
        return oc
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

    # **挂载合法性硬拦** —— 照抄游戏自己的 `_can_add_specialist_no_len`：阵营必须相同；国籍相同，或**单位国籍的 parent_nationality == 特种兵国籍**（**单向**）。
    unit_type = unit.get("type")
    # 存档 `units.yml` 顶层实测**没有** captured 字段（只有 `specs[].captured`）
    # ⇒ 实测恒为 False；有的话按游戏逻辑（captured 跳过阵营/国籍检查）处理。
    captured = bool(unit.get("captured"))
    if not w.catalog.spec_can_attach(spec_type, unit_type, captured=captured):
        sp = w.catalog.spec_type(spec_type)
        ut = w.catalog.unit_type(unit_type)
        if ut is None:
            reason = f"单位类型 {unit_type!r} 不在游戏包的 unit_types 里"
        elif sp is not None and ut.faction != sp.faction:
            reason = (f"阵营不同（单位 {ut.faction!r} / 特种兵 {sp.faction!r}）")
        else:
            nat = w.catalog.nationality(ut.nationality or "")
            parent = nat.parent_nationality if nat is not None else None
            sp_nat = sp.nationality if sp is not None else None
            if parent:
                reason = (f"单位国籍 {ut.nationality!r} 的父国籍是 {parent!r}，"
                          f"只能挂同国籍或父国籍的特种兵（当前是 {sp_nat!r}）")
            else:
                reason = (f"单位国籍 {ut.nationality!r} 没有父国籍，"
                          f"只能挂同国籍的特种兵（当前是 {sp_nat!r}）")
        oc.errors.append(
            f"特种兵 {spec_type!r} 不能挂到 {unit_type!r} 上：{reason}"
            "（规则见规范 §7.3.2：阵营相同 + 国籍相同或单位国籍的 parent_nationality 匹配）")
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
    specs.append({"active": active, "captured": False,
                  "idx": free, "type": spec_type})
    w.touch("units.yml")
    if active:
        oc.summary = f"单位 {unit_id} 加特种 {spec_type}（槽位 {free}）"
    else:
        oc.summary = (f"单位 {unit_id} 加特种 {spec_type}"
                      f"（槽位 {free}，新增即被压制）")
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


def _unit_spec_active(w, e: Edit) -> Outcome:
    """特种兵的「被压制」状态（根 `units.yml`）。

    ⚠️ 存档里特种兵条目只有 `type` / `active` / `captured` / `idx` 四个字段
    —— **没有独立的 suppressed 字段**；`active=False` 就是被压制
    （U84 的字节码实证）。
    这里**只改 `active` 这一个键**，`type` / `captured` / `idx` 原样保留。
    """
    oc = Outcome()
    unit_id = e.params.get("unit_id")
    spec_type = e.params.get("spec_type")
    idx = e.params.get("idx")
    active = e.params.get("value")
    if not w.require(w.caps.can_edit_units, "units", "units.yml"):
        return oc
    if not isinstance(active, bool):
        oc.errors.append(
            f"active 必须是布尔值（True = 活跃 / False = 被压制），收到 {active!r}")
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
    old = bool(target.get("active", True))
    if old == active:
        return oc                       # 没变 ⇒ 什么都不写
    target["active"] = active
    unit["specs"] = specs
    w.touch("units.yml")
    oc.summary = (f"单位 {unit_id} 的特种 {spec_type}"
                  + (f"（槽位 {target.get('idx')}）" if target.get("idx") is not None else "")
                  + ("：设为被压制" if not active else "：恢复活跃"))
    return oc


def _elastic_defense_allowed(w, unit_id):
    """这个单位能不能挂「反击」？（U92 · 游戏硬约束）

    **取证**（游戏字节码）：
    * `state/entities_view/unit.py:45`

      ```python
      armor_mobile = property(lambda self: self.armor
                                           and not self.armor_def
                                           and self.movement == 'mobile')
      ```

    * `state/entities_view/unit.py:98` `can_make_elastic_defense` 的
      **第一个条件**就是 `self.armor_mobile`
      ⇒ **非装甲机动单位挂不了「反击」**；
      而 `can_make_no_retreat` / `can_make_rearguard` **没有**这条约束。

    **实证**（用户的 `west.usg`）：
    `elastic_defense_units = [87, 104]`（87 = 突击炮、104 = 坦克）
    两个都是 `movement=mobile` ⇒ 装甲机动；
    同存档里的死守 / 后卫部队单位则是**步兵** ⇒ 印证只有反击有这条限制。

    返回 `(ok, 原因)`；`原因` 为空表示没意见。
    """
    units = w.table("units.yml", [])
    unit = next((u for u in units
                 if isinstance(u, dict) and u.get("id") == unit_id), None)
    if unit is None:
        return True, ""            # 找不到单位 ⇒ 交给别的校验去报错
    type_name = unit.get("type")
    if w.catalog is None:
        return True, ""            # 没有游戏包 ⇒ 判不了（下面会加一条警告）
    if not type_name:
        return True, ""
    t = w.catalog.unit_type(type_name)
    if t is None:
        return True, ""            # 类型查不到（类型表可能缺）⇒ 不拦
    if t.armor_mobile:
        return True, ""
    return False, (
        "单位 %d（类型 %s）**不能挂「反击」** —— 游戏里的硬约束是"
        "「反击只能挂**装甲机动单位**」"
        "（要有装甲值 armor、不是防御装甲 armor_def、且 movement = mobile）；"
        "这个单位是 movement=%s / armor=%s / armor_def=%s ⇒ 不是装甲机动单位。"
        % (unit_id, type_name, t.movement, t.armor, t.armor_def))


def _unit_orders(w, e: Edit) -> Outcome:
    """给单位**下 / 撤**作战标记（HQ 技能的三种「命令」，U89）。

    ⚠️ 写的是**战斗层** `games/<场景>/main.yml`（独立场景是 `game/main.yml`）——
    这是本仓库的**第二个 L3 例外**（第一个是战区资产），用户 2026-11-20 批准。

    三个列表：`no_retreat_units`（不能撤退）/ `rearguard_units`（后卫部队）
    / `elastic_defense_units`（反击）。

    ⚠️ 这些是**命令**，**敌方下一回合结束前有效** ⇒ 游戏回合开始会清
    （`Game.start_turn_clear`）⇒ 改完只对**当前回合**有效。
    """
    oc = Outcome()
    unit_id = e.params.get("unit_id")
    orders = e.params.get("orders")
    if not isinstance(unit_id, int) or isinstance(unit_id, bool):
        oc.errors.append(f"单位 id 必须是整数，收到 {unit_id!r}")
        return oc
    if not isinstance(orders, list):
        oc.errors.append(f"orders 必须是列表，收到 {orders!r}")
        return oc
    bad = [o for o in orders if o not in ORDER_LISTS]
    if bad:
        oc.errors.append(
            "未知的作战标记 %s；游戏只认这三种：%s"
            % (bad, "、".join(ORDER_LISTS)))
        return oc
    orders = [o for o in ORDER_LISTS if o in orders]     # 去重 + 按固定顺序

    # 游戏里这三个标记**互斥** —— 一个单位同时只能有一个。
    #   字节码依据（三条独立路径共同维持）：
    #   ① `Gamelike.has_any_defense_flag`（gamelike.pyc:1452-1455）
    #      = 该单位在三个列表**任意一个**里；
    #   ② 三个 `can_make_*`（entities_view/unit.pyc:84/91/98）的最后一个条件
    #      都是 `not has_any_defense_flag(self.id)`；
    #   ③ `UnitSetFlags._set_flags`（scenario/commands_unit.pyc:359-368）
    #      = 先从三个列表全 discard，再 add 进**其中一个**。
    if len(orders) > 1:
        oc.errors.append(
            "一个单位**只能有一个**作战标记（死守 / 后卫部队 / 反击三者互斥）—— "
            "游戏里下达命令是「先把该单位从三个列表全清掉、再加进其中一个」"
            "（`UnitSetFlags._set_flags`），而且三个 `can_make_*` 都要求"
            "「该单位没有别的标记」（`has_any_defense_flag`）；"
            "存档里有冲突时游戏只认第一个（%s）"
            % "、".join(orders))
        return oc

    # 游戏硬约束 —— **「反击」只允许装甲机动单位**
    # （`can_make_elastic_defense` 的第一个条件就是 `armor_mobile`）。
    # ⚠️ 只拦**新增**；撤除已有标记不受影响（存档里原本就有的也不主动清理）。
    if "elastic_defense" in orders:
        ok, why = _elastic_defense_allowed(w, unit_id)
        if not ok:
            oc.errors.append(why)
            return oc
        if w.catalog is None:
            oc.warnings.append(
                "没有游戏包目录 ⇒ 没能校验「反击只能挂装甲机动单位」这条游戏硬约束")

    battle_dir = w.save.battle_dir()
    if battle_dir is None:
        oc.errors.append("当前存档没有进行中的战斗 —— 作战标记是战斗里的命令")
        return oc
    in_battle = w.save.battle_unit_ids()
    if in_battle and unit_id not in in_battle:
        oc.errors.append(f"单位 {unit_id} 不在这场战斗里（当前战斗的单位 id 名单）")
        return oc

    entry = f"{battle_dir}/main.yml"
    data = w.table(entry, {})
    if not isinstance(data, dict):
        oc.errors.append(f"{entry} 结构异常")
        return oc

    # 先把这个单位从三个列表里**全部**摘掉，再按新的 orders 放回去
    for list_key in ORDER_LISTS.values():
        ids = data.get(list_key)
        if not isinstance(ids, list):
            continue
        data[list_key] = [x for x in ids if x != unit_id]
    for key in orders:
        list_key = ORDER_LISTS[key]
        ids = data.get(list_key)
        if not isinstance(ids, list):
            ids = []
            data[list_key] = ids
        if unit_id not in ids:
            ids.append(unit_id)
    w.touch(entry)

    oc.summary = ("单位 %d 的作战标记：%s"
                  % (unit_id, "、".join(orders) if orders else "（全撤）"))
    oc.warnings.append(
        "作战标记是**命令**：敌方下一回合结束前有效 —— "
        "游戏回合开始会把它清掉（`Game.start_turn_clear`）")
    oc.warnings.append(
        "⚠️ 游戏**开着**时改盘 ⇒ 退出时的自动保存会覆盖你的改动 ⇒ "
        "改之前先退出游戏")
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


def _batch_final_hq_field(w, hq_id, field):
    """这一批编辑**全部执行完**后，这个总部的该字段会是什么值。

    U97：同一批编辑是**依次执行**的 ⇒ handler 执行到某条时，
    别的字段可能还没改（中间态）⇒ 用它判定会**误报**。
    例：玩家同时把 CP 调到 9、把 CP 上限也调到 9 ——
    先执行 CP 那条时上限还是 6 ⇒ 误报「CP 9 超过上限 6」。

    没有同批的编辑 ⇒ 返回 None（调用方回退到存档里的当前值）。
    """
    final = None
    for ed in (getattr(w, "batch_edits", None) or []):
        p = getattr(ed, "params", None) or {}
        if p.get("hq_id") == hq_id and p.get("field") == field:
            final = p.get("value")
    return final


def _hq_field(w, e: Edit) -> Outcome:
    """总部的某个字段（经验 / CP / 补给 / 卡车 / 俘虏 …）。"""
    oc = Outcome()
    hq_id = e.params.get("hq_id")
    field = e.params.get("field")
    value = e.params.get("value")
    if not w.require(w.caps.can_edit_hqs, "hqs", "hqs.yml"):
        return oc
    if field in HQ_XP_FIELDS:
        # 经验 / 经验目标**不能手改**（游戏会重算，写了也白写）。
        oc.errors.append(
            "总部经验（xp）与经验目标（xp_target）**不能手改** —— "
            "经验目标是游戏按战役规模动态重算的"
            "（`campaign._set_hqs_xp_target`：该总部的单位数 × 场景回合数 × "
            "hq_xp_taget_fudge_factor），下次战役推进就会覆盖；"
            "想升级请直接改**分支等级 / 技能专精**。")
        return oc
    if field not in HQ_FIELD_ALLOWED:
        oc.errors.append(
            f"不允许改总部字段 {field!r}；可改：{', '.join(sorted(HQ_FIELD_ALLOWED))}")
        return oc
    if field in HQ_FIELD_TEXT:
        # 名字字段：字符串或 None（游戏的 `Or(str, None)`）
        if value is not None and not isinstance(value, str):
            oc.errors.append(f"{field} 必须是字符串或 null，收到 {value!r}")
            return oc
        if isinstance(value, str) and not value.strip():
            oc.errors.append(f"{field} 不能是空字符串")
            return oc
    elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
        oc.errors.append(f"{field} 必须是非负整数，收到 {value!r}")
        return oc

    # ⚠️ 合法区间比「非负整数」严 —— 游戏 schema 是硬范围（字节码取证）；
    #    超范围**不是显示异常，是 voluptuous 校验失败 ⇒ 存档直接打不开**。
    if field == "max_cp" and not (HQ_MAX_CP_MIN <= value <= HQ_MAX_CP_MAX):
        oc.errors.append(
            f"max_cp 必须在 {HQ_MAX_CP_MIN}–{HQ_MAX_CP_MAX} 之间（游戏的硬范围），收到 {value}")
        return oc
    if field == "cp" and not (HQ_CP_MIN <= value <= HQ_CP_MAX):
        oc.errors.append(
            f"cp 必须在 {HQ_CP_MIN}–{HQ_CP_MAX} 之间（游戏的硬范围），收到 {value}")
        return oc
    # ⚠️ trucks / supply 也是**硬范围**（游戏 schema 限制，不是我们的选择）——
    #    越界写出来的存档**打不开**，所以两个入口用同一套规则。
    if field == "trucks" and not (TRUCK_MIN <= value <= TRUCK_MAX):
        oc.errors.append(
            f"trucks 必须在 {TRUCK_MIN}–{TRUCK_MAX} 之间（游戏的硬范围），收到 {value}")
        return oc
    if field == "supply" and not (HQ_SUPPLY_MIN <= value <= HQ_SUPPLY_MAX):
        oc.errors.append(
            f"supply 必须在 {HQ_SUPPLY_MIN}–{HQ_SUPPLY_MAX} 之间（游戏的硬范围），收到 {value}")
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
    # ⚠️ 同单位 —— 战役地图显示的是**名册**那份（`document/hqs.yml`）。
    if field in ("name_brief", "name_full"):
        for k, v in _rename_fields(hq, field, value).items():
            if k in hq and hq.get(k) != v:
                hq[k] = v
        _sync_rename_to_roster(w, "hqs.yml", hq_id, field, value)
        # ⚠️ 同上（游戏开着 ⇒ 退出时覆盖）。
        oc.warnings.append(GAME_RUNNING_WARNING)

    # ⚠️ 判定要看**这一批改完之后**的值，不能看中间态。
    #（同一批编辑依次执行 ⇒ 先改 CP 时上限可能还没改 ⇒ 误报）。
    _cp_final = _batch_final_hq_field(w, hq_id, "cp")
    _maxcp_final = _batch_final_hq_field(w, hq_id, "max_cp")
    _cp_now = _cp_final if _cp_final is not None else hq.get("cp")
    _maxcp_now = _maxcp_final if _maxcp_final is not None else hq.get("max_cp")
    if field == "cp" and isinstance(_maxcp_now, int) and value > _maxcp_now:
        oc.warnings.append(
            f"CP {value} 超过该总部的上限 {_maxcp_now} —— 游戏读档时按上限截断"
            f"（`HQState._repair_data`），多出来的 CP 会白给")
    if field == "max_cp" and isinstance(_cp_now, int) and _cp_now > value:
        oc.warnings.append(
            f"CP 上限降到 {value}，但当前 CP 是 {_cp_now} —— 游戏读档时按上限截断"
            f"（`HQState._repair_data`）")
    if field in ("prisoners", "loss_count", "intels_revealed"):
        oc.warnings.append(
            f"{field} 是游戏自己累计的统计值，改了不会被重算，但界面可能对不上")
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
    # ⚠️ **不管有没有传 suppressed**，都要检查「等级 + 被压制 ≤ 3」
    #（游戏内部「解锁到几级」= 等级 + 被压制；超了**游戏读档会失败**）。
    #   以前只在传了 suppressed 时才查 ⇒ 界面那条「只改等级」的路绕过了
    #   ⇒ 能写出「等级 3 + 被压制 1」这种**打不开的存档**。
    eff_supp = old_supp if suppressed is None else suppressed
    if level + eff_supp > HQ_BRANCH_MAX:
        oc.errors.append(
            f"等级 {level} + 被压制 {eff_supp} 超过上限 {HQ_BRANCH_MAX}"
            "（游戏内部「解锁到几级」= 等级 + 被压制）")
        return oc
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
    # ⚠️ 游戏的 `force_pool_schema` 里 `delay` 是**非负整数**
    #   （`state/entities/data_validation/force_pool.pyc`）⇒ 写负数**存档打不开**。
    _delay = new.get("delay")
    if not isinstance(_delay, int) or isinstance(_delay, bool) or _delay < 0:
        oc.errors.append(
            "delay 必须是非负整数（游戏的硬范围），收到 %r" % (_delay,))
        return oc
    if not new.get("nationality"):
        # 实测：真实存档里 商店 1043 条 + 兵库 1747 条 spec 条目，
        # 国籍 **100% 等于该特种兵类型自身的 nationality**，0 条例外
        # ⇒ 给了 spec 就自动把国籍填成类型国籍。
        nat = _spec_nationality(w, new.get("spec"))
        if nat:
            new["nationality"] = nat
        else:
            new.setdefault("nationality", "")
    # ★ 同身份 + **同延迟**不许并存。
    ident = _entry_identity(new)
    delay = new.get("delay", 0)
    others = []
    for i, e in enumerate(pool):
        if not isinstance(e, dict):
            continue
        if _entry_identity(e) != ident:
            continue
        if e.get("delay", 0) != delay:
            others.append((i + 1, e.get("delay", 0), e.get("quantity")))
            continue
        oc.errors.append(
            f"总部 {hq_id} 的兵库已经有「{_entry_label(new)}」了"
            f"（第 {i + 1} 条，延迟 {e.get('delay', 0)} 回合，数量 {e.get('quantity')}）—— "
            f"**同一个总部里不能有两条延迟同为 {delay} 的同样条目**；"
            "延迟不同的可以共存")
        return oc

    pool.insert(index, new)
    hq["force_pool"] = pool
    w.touch("hqs.yml")
    oc.summary = (f"总部 {hq_id} 兵库加一条"
                  f"（{new.get('spec') or new.get('equipment')} × {new.get('quantity')}）")
    spec_nat = _spec_nationality(w, new.get("spec"))
    if spec_nat and new.get("nationality") != spec_nat:
        oc.warnings.append(
            f"国籍填的是 {new.get('nationality')!r}，但这个特种兵自己的国籍是 "
            f"{spec_nat!r} —— 游戏自己的数据全部跟着特种兵类型走，"
            "建议让国籍跟着类型自动填")
    elif not new.get("nationality"):
        oc.warnings.append(
            "兵库条目的**国籍**要填国籍 id（uk / us / german …），不是阵营"
            "（allies / axis）—— 填错游戏读不出来")
    return oc


def _spec_nationality(w, spec) -> str | None:
    """特种兵类型自己的国籍（查不到返回 `None`）。

    数据源：游戏包 `entity_types/specialists/<type>.yml` 的 `nationality` 字段
    （实测 375/375 都有）。拿不到游戏包就返回 `None` —— **不猜**。
    """
    if not spec or w.catalog is None:
        return None
    try:
        st = w.catalog.spec_type(spec)
    except Exception:
        return None
    return getattr(st, "nationality", None) if st is not None else None


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


def _as_bool(v):
    """把外部传来的值读成**布尔**（只认明确的值，不做「看着像」的强转）。

    ⚠️ **U131**：原来写的是 `bool(v)` ⇒ **字符串 `"false"` 会被当成 True**
    （`bool("false")` 是 True！）⇒ 「改成收费」会变成「**改成免费**」。

    ⇒ 这里只认：真正的 `bool` / `0`-`1` 整数 / 明确写着 true-false 的字符串；
    认不出来返回 `None`（由调用方报错，**不许**默默当成 False）。
    """
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, int):
        return bool(v) if v in (0, 1) else None
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("true", "1", "yes", "y", "on"):
            return True
        if t in ("false", "0", "no", "n", "off", ""):
            return False
        return None
    return None


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
    # 手牌槽位有上限（`card_deck_limit[难度]`），超限的槽位**游戏读不到**
    #（游戏的 card schema 里压根没有 position 字段，是按槽位索引读的）
    # ⇒ 写进去不会让存档打不开，但那张卡等于白写 ⇒ 必须拦。
    limit = CARD_DECK_LIMIT.get(_level_of(w), 5)
    if position is None:
        used = {c.get("position") for c in cards
                if isinstance(c, dict) and isinstance(c.get("position"), int)}
        position = next((p for p in range(1, limit + 1) if p not in used), None)
        if position is None:
            oc.errors.append(
                f"手牌已满（本难度「{_level_of(w)}」的上限是 {limit} 张）—— 先删一张再添加")
            return oc
    else:
        if not isinstance(position, int) or isinstance(position, bool) or position < 1:
            oc.errors.append(f"槽位号必须是 ≥ 1 的整数，收到 {position!r}")
            return oc
        if position > limit:
            oc.errors.append(
                f"槽位 {position} 超过本难度（{_level_of(w)}）的手牌上限 {limit} —— "
                "游戏按槽位索引读手牌，超限的槽位**读不到**（白写）")
            return oc
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

    # ⚠️ 别用 `bool(...)` 强转（`"false"` 会被当成 True）。
    is_free = e.params.get("is_free")
    flag = _as_bool(is_free)
    if flag is None:
        oc.errors.append(f"is_free 必须是 True / False，收到 {is_free!r}")
        return oc
    cards.append({"card_type": card_type,
                  "is_free": flag,
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


def _entry_identity(entry) -> tuple:
    """一条商品 / 兵库条目的**身份**。

    * 特种兵（`spec`）⇒ `("spec", 类型名, 国籍)`
    * 装备（`equipment`）⇒ `("equipment", 类别, 国籍)`
    * 两者都没有 ⇒ `("?", None, 国籍)`

    国籍**算进身份** —— 同样是「德国步兵」，`german` 和 `uk` 是两样东西。
    """
    if not isinstance(entry, dict):
        return ("?", None, None)
    if entry.get("spec"):
        return ("spec", entry["spec"], entry.get("nationality"))
    if entry.get("equipment"):
        return ("equipment", entry["equipment"], entry.get("nationality"))
    return ("?", None, entry.get("nationality"))


def _entry_label(entry) -> str:
    """条目的人话名字（给报错文案用）。"""
    if not isinstance(entry, dict):
        return "?"
    if entry.get("spec"):
        return f"特种兵 {entry['spec']}"
    if entry.get("equipment"):
        return f"装备 {entry['equipment']}（{entry.get('nationality') or '无国籍'}）"
    return "?"


def _check_store_universe(w, entry) -> list[str]:
    """商品本身必须是**游戏定义过的**（schema 是枚举校验）。

    依据 = 游戏的存档 schema（`state/entities/data_validation/force_pool.pyc`，
    U107 字节码实证）：

    | 字段 | 游戏怎么校验 | 合法范围 |
    |---|---|---|
    | `spec` | `Exclusive('spec','t')` + `specialist_types.id_validation_schema` | **全部** 375 个特种兵类型 |
    | `equipment` | `Exclusive('equipment','t')` + `In(constants.unit_equipments + (unit_equipment_none,))` | **全部** `('armor','infantry')` |
    | `nationality` | `Required('nationality')` + `nationality_types.id_validation_schema` | **全部** 40 个国籍 id |

    ⚠️ **U107：之前这里拿「本次会议商店在售的兵种 / 国籍」当门 ⇒ 过严** ——
    west 存档里 free_french 的 3 个特种兵游戏明明能读，却被核心库拒了
    ⇒ 玩家「部分无法正常上架」。现在按**游戏定义过的**判（与游戏 schema 一致）。
    拿不到游戏包就不查（只提示，不拦）。
    """
    if w.catalog is None:
        return []
    errs: list[str] = []
    spec = entry.get("spec")
    if spec and not w.catalog.has_spec_type(spec):
        errs.append(f"特种兵 {spec!r} 游戏里没有 —— 不能凭空新增种类")
    eq = entry.get("equipment")
    if eq and eq not in GAME_EQUIPMENTS:
        errs.append(f"兵种 {eq!r} 游戏里没有（可选：{', '.join(GAME_EQUIPMENTS)}）")
    nat = entry.get("nationality")
    if nat and w.catalog.nationality(str(nat)) is None:
        errs.append(f"国籍 {nat!r} 游戏里没有（可选：{', '.join(w.catalog.nationality_names()[:12])} …）")
    return errs


def _player_faction(w) -> str | None:
    """玩家阵营（存档 `document/main.yml` 的 `player_faction`，L5 只读）。

    拿不到就返回 None（不猜）。
    """
    try:
        doc = w.save.read_yaml("document/main.yml", None)
    except Exception:
        doc = None
    if isinstance(doc, dict):
        pf = doc.get("player_faction")
        if pf:
            return str(pf)
    return None


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
    # ⚠️ 别用 `bool(...)` 强转（`"false"` 会被当成 True）。
    is_free = e.params.get("is_free")
    flag = _as_bool(is_free)
    if flag is None:
        oc.errors.append(f"is_free 必须是 True / False，收到 {is_free!r}")
        return oc
    is_free = flag
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

    # ★ 同一个 (战线, 子商店) 里**不允许重复条目**。
    ident = _entry_identity(new)
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        if _entry_identity(e) != ident:
            continue
        oc.errors.append(
            f"{front}/{sub} 里已经有「{_entry_label(new)}」了"
            f"（第 {i + 1} 条，价格 {e.get('price')}，库存 {e.get('quantity')}）—— "
            "**同一个商店不能出现重复条目**；要改它就直接改那一条，别再上一份")
        return oc

    entries.append(new)
    w.touch("store.yml")
    oc.summary = (f"上架商品 {new.get('spec') or new.get('equipment')}"
                  f"（{front}/{sub}，价格 {new.get('price')}，库存 {new.get('quantity')}）")
    # **软警告** —— 游戏允许上架敌方阵营的特种兵（存档能读），
    pf = _player_faction(w)
    spec = new.get("spec")
    if pf and spec and w.catalog is not None:
        st = w.catalog.spec_type(spec)
        fac = st.faction if st is not None else None
        if fac and fac != pf:
            oc.warnings.append(
                f"这个特种兵是 {fac} 阵营的（玩家是 {pf}）—— "
                "游戏能读，但买回来**挂不到自己的单位上**（U107）")
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


def _is_int(v):
    """是不是一个**真整数**（`bool` 是 `int` 的子类，要排除）。"""
    return isinstance(v, int) and not isinstance(v, bool)


def _theater_group(w, side: str = "player"):
    """定位要改的那一**组**战区资产。

    返回 `(entry, data, idx, items)`；定位不到就返回 `None`
    （原因已经写进 `w.outcomes`）。

    ⚠️ **U143（重要更正）**：组 = **阵营**，不是"阶段"：
    * `side="player"`（默认）⇒ **玩家那一方**（`factions` 里 `player: local`）；
    * `side="opponent"` ⇒ **对手那一方**；
    * `side="current"` ⇒ 当前行动方（`phase`）—— 旧语义，保留兼容。

    ⚠️ 以前按 `phase`（**当前行动方**）定位 ⇒ **轮到 AI 行动时，
    修改器会显示/编辑敌方那组**（当成自己的）⇒ 已修（U143）。
    ⚠️ **组数恒为 2**（U45 实测 730/730 个战斗文件）⇒ 增删**只动组内项**，
    绝不新增或删除组（改组数会让游戏的 `phase` 索引错位）。
    """
    if not w.require(w.caps.can_edit_theater_assets, "theater_assets",
                     "games/<场景>/main.yml"):
        return None
    battle_dir = w.save.battle_dir()
    if battle_dir is None:
        w.outcomes.append(Outcome(errors=["当前存档没有进行中的战斗"]))
        return None
    entry = f"{battle_dir}/main.yml"
    data = w.table(entry, {})
    if not isinstance(data, dict):
        w.outcomes.append(Outcome(errors=[f"{entry} 结构异常"]))
        return None
    theater = data.get("theater_assets")
    if not isinstance(theater, list) or not theater or not isinstance(theater[0], list):
        w.outcomes.append(Outcome(errors=[f"{entry} 里没有 theater_assets"]))
        return None
    idx = theater_group_index(data, side)
    items = theater[idx]
    if not isinstance(items, list):
        w.outcomes.append(Outcome(
            errors=[f"{entry} 里 theater_assets 第 {idx} 组不是列表"]))
        return None
    return entry, data, idx, items


def _theater_asset(w, e: Edit) -> Outcome:
    """战区资产（唯一的 L3 写入白名单）。

    **三个字段都能单独改**（U20 字节码取证，见 `THEATER_*` 常量的注释）：

    | 字段 | 游戏里的含义 | 合法范围 |
    |---|---|---|
    | `to_use` | 当前剩余可用次数 | 0 – ∞ |
    | `uses_total` | 本场景剩余总次数（`None` = 无限） | 0 – ∞ 或 `None` |
    | `uses_turn` | 每回合恢复次数 | 1 – ∞ |

    **跨字段不变式**：`to_use ≤ uses_total`（`uses_total` 有限时）。
    游戏每用一次资产就让 `uses_total` 减 1（`Game.spend_theater_asset`），
    减到负数会让存档校验失败 ⇒ 硬拦。
    """
    oc = Outcome()
    asset = e.params.get("asset")
    side = e.params.get("side") or "player"
    want = {f: e.params.get(f) for f in ("to_use", "uses_total", "uses_turn")}
    ctx = _theater_group(w, side)
    if ctx is None:
        return oc
    entry, _data, idx, items = ctx
    target = next((it for it in items
                   if isinstance(it, dict) and it.get("asset") == asset), None)
    if target is None:
        avail = ", ".join(str(it.get("asset")) for it in items if isinstance(it, dict))
        oc.errors.append(
            f"该场景没有战区资产 {asset!r}；本场景有：{avail or '（空）'}。"
            "修改器**不会凭空新增**资产条目（§6.2b）"
            "—— 要新增请用「添加战区资产」操作")
        return oc

    # 改后值：没传的字段（UNSET）沿用存档里的原值
    after = {f: (target.get(f) if want[f] is UNSET else want[f])
             for f in ("to_use", "uses_total", "uses_turn")}

    if not _is_int(after["to_use"]) or after["to_use"] < THEATER_TO_USE_MIN:
        oc.errors.append(
            f"to_use={after['to_use']!r} 必须是不小于 {THEATER_TO_USE_MIN} 的整数")
        return oc
    total = after["uses_total"]
    if total is not None and (not _is_int(total) or total < THEATER_USES_TOTAL_MIN):
        oc.errors.append(
            f"uses_total={total!r} 必须是不小于 {THEATER_USES_TOTAL_MIN} 的整数"
            "，或 None（无限）")
        return oc
    if not _is_int(after["uses_turn"]) or after["uses_turn"] < THEATER_USES_TURN_MIN:
        oc.errors.append(
            f"uses_turn={after['uses_turn']!r} 必须是不小于 {THEATER_USES_TURN_MIN} 的整数")
        return oc
    # 不变式：当前可用次数不得超过本场景剩余总次数
    if total is not None and after["to_use"] > total:
        oc.errors.append(
            f"to_use={after['to_use']} 不能大于 uses_total={total}："
            "游戏每用一次资产就让 uses_total 减 1，减成负数会让存档校验失败（打不开）")
        return oc

    changed = []
    for f in ("to_use", "uses_total", "uses_turn"):
        if want[f] is UNSET:
            continue
        old = target.get(f)
        if old == want[f]:
            continue
        target[f] = want[f]
        changed.append((f, old, want[f]))
    if not changed:
        side_cn = theater_side_cn(_data, idx)
        oc.summary = f"战区资产 {asset}（{side_cn}）：没有需要改的字段"
        return oc
    w.touch(entry)
    oc.summary = "战区资产 %s（%s）：%s" % (
        asset, theater_side_cn(_data, idx),
        "、".join("%s %s → %s" % (THEATER_FIELD_CN[f], _theater_val(f, o),
                                _theater_val(f, n))
                  for f, o, n in changed))
    # 回合开始后的**有效可用次数**（`Game.theater_assets_start_turn`）：
    #   uses_total 为 None -> to_use = uses_turn
    #   否则              -> to_use = min(uses_turn, uses_total)
    eff = (after["uses_turn"] if total is None
           else min(after["uses_turn"], total))
    if total is not None and after["uses_turn"] > total:
        oc.warnings.append(
            f"每回合恢复 {after['uses_turn']} 次 大于 本场景剩余 {total} 次："
            "回合开始时游戏按 min(每回合恢复, 本场景剩余) 恢复，"
            f"实际每回合只能用 {total} 次")
    if after["to_use"] > eff:
        oc.warnings.append(
            f"当前可用 {after['to_use']} 次 大于 回合开始后的有效值 {eff} 次："
            f"回合开始时游戏会把当前可用次数重置为 {eff} 次")
    return oc


def _theater_asset_add(w, e: Edit) -> Outcome:
    """**新增**一项战区资产到**指定那一方**（阵营）的那一组（U45）。

    「无中生有」的安全边界（全部有依据）：

    | 检查 | 依据 |
    |---|---|
    | `asset` 必须在 7 种全集里 | `theater_asset_dict` = `Required('asset'): In(theater_asset_types)` |
    | 同组内不能有同名 | 游戏按名字取**第一个**匹配（`Game.get_theater_asset_uses`） |
    | **组数不变** | 实测 730/730 个战斗文件恒为 2 组 |
    | `uses_total` 不能是 0 | 回合开始按 `to_use = min(uses_turn, uses_total)` 恢复 ⇒ 0 = 永远用不了 |
    | `uses_turn ≥ 1` | `positive_int_schema` |
    | 写全 5 个字段且自洽 | 运行时项字段组合实测 2320/2320 一致 |

    ⚠️ 新加的资产**只对这一方（阵营）生效**；游戏载入战斗时 `Game.new`
    会把 `to_use` 重置成 `uses_turn`、`to_use_not_used` 重置成 `None`
    （我们写的是「存档里的样子」，不保证游戏里立刻是这个数）。
    """
    oc = Outcome()
    asset = e.params.get("asset")
    uses_total = e.params.get("uses_total")
    uses_turn = e.params.get("uses_turn")
    side = e.params.get("side") or "player"
    ctx = _theater_group(w, side)
    if ctx is None:
        return oc
    entry, _data, idx, items = ctx
    side_cn = theater_side_cn(_data, idx)

    if not isinstance(asset, str) or asset not in THEATER_ASSET_TYPES:
        oc.errors.append(
            f"{asset!r} 不是游戏的战区资产；游戏只认这 7 种："
            + "、".join(THEATER_ASSET_TYPES)
            + "（写别的名字存档直接打不开）")
        return oc
    if any(isinstance(it, dict) and it.get("asset") == asset for it in items):
        oc.errors.append(
            f"这一方（{side_cn}）已经有战区资产 {asset!r} —— "
            "同一个组里不能有同名（游戏按名字取第一个匹配）")
        return oc
    if not _is_int(uses_turn) or uses_turn < THEATER_USES_TURN_MIN:
        oc.errors.append(
            f"uses_turn={uses_turn!r} 必须是不小于 {THEATER_USES_TURN_MIN} 的整数")
        return oc
    if uses_total is not None and (not _is_int(uses_total)
                                   or uses_total < THEATER_ADD_USES_TOTAL_MIN):
        oc.errors.append(
            f"uses_total={uses_total!r} 必须是不小于 {THEATER_ADD_USES_TOTAL_MIN}"
            " 的整数，或 None（无限）"
            " —— 0 会让这个资产永远用不了"
            "（回合开始时按 min(每回合恢复, 本场景剩余) 恢复）")
        return oc

    # 自洽地算出 to_use / to_use_not_used（游戏回合开始时的口径）：
    #   uses_total 为 None -> to_use = uses_turn
    #   否则              -> to_use = min(uses_turn, uses_total)
    #   to_use_not_used    = uses_turn - to_use
    eff = uses_turn if uses_total is None else min(uses_turn, uses_total)
    items.append({
        "asset": asset,
        "to_use": eff,
        "to_use_not_used": uses_turn - eff,
        "uses_total": uses_total,
        "uses_turn": uses_turn,
    })
    w.touch(entry)
    oc.summary = ("加战区资产 %s（%s；每回合恢复 %d，本场景剩余 %s）"
                  % (asset, side_cn, uses_turn,
                     "无限" if uses_total is None else uses_total))
    oc.warnings.append(
        "新加的战区资产**只对这一方（阵营）生效** —— "
        "场景自己的定义（存档里的 document/scenarios/…）不动，"
        "下一场战斗会按它重新初始化")
    oc.warnings.append(
        "游戏载入战斗时会把「当前可用」重置成「每回合恢复」"
        "（本场景剩余有限时取两者较小值）")
    return oc


def _theater_asset_remove(w, e: Edit) -> Outcome:
    """从**指定那一方**（阵营）的那一组里**删掉**一项战区资产（U45）。

    删的是**整项**，不是把次数清零 —— 这才是「清理干净」：
    清零会留下一个永远用不了的死条目，游戏里还白占一个按钮。

    ⚠️ 只删**指定那一方**（阵营）那一组里的那一个；另一方不动。
    """
    oc = Outcome()
    asset = e.params.get("asset")
    side = e.params.get("side") or "player"
    ctx = _theater_group(w, side)
    if ctx is None:
        return oc
    entry, _data, idx, items = ctx
    side_cn = theater_side_cn(_data, idx)
    pos = next((i for i, it in enumerate(items)
                if isinstance(it, dict) and it.get("asset") == asset), None)
    if pos is None:
        avail = ", ".join(str(it.get("asset")) for it in items if isinstance(it, dict))
        oc.errors.append(
            f"这一方（{side_cn}）没有战区资产 {asset!r}；本组有："
            f"{avail or '（空）'}")
        return oc
    target = items[pos]
    items.pop(pos)
    w.touch(entry)
    oc.summary = "删战区资产 %s（%s）" % (asset, side_cn)

    total = target.get("uses_total")
    if isinstance(total, int) and not isinstance(total, bool) and total > 0:
        oc.warnings.append(
            f"这个资产本场景还剩 {total} 次可用 —— 删掉就没有了"
            "（想保留次数就改数值，不要删）")
    to_use = target.get("to_use")
    if isinstance(to_use, int) and not isinstance(to_use, bool) and to_use > 0:
        oc.warnings.append(f"当前还有 {to_use} 次没用 —— 删掉等于放弃")
    if not items:
        oc.warnings.append(
            f"这一方（{side_cn}）删完是空的 —— "
            "游戏里这一方就没有战区资产了")
    return oc


def _theater_val(field: str, value) -> str:
    """战区资产字段的中文展示值（`uses_total=None` = 无限）。"""
    if field == "uses_total" and value is None:
        return "无限"
    return str(value)


# ---------------------------------------------------------------- 分发表

_HANDLERS = {
    "progress": _progress,
    "level": _level,
    "unit_field": _unit_field,
    "unit_spec_add": _unit_spec_add,
    "unit_spec_remove": _unit_spec_remove,
    "unit_orders": _unit_orders,
    "unit_spec_active": _unit_spec_active,
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
    "theater_asset_add": _theater_asset_add,
    "theater_asset_remove": _theater_asset_remove,
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
