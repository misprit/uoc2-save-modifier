"""测试用的合成存档。

结构照着游戏真实的存档写（17 个键的根 `main.yml`、L2 检查点、L3 战斗层），
这样测试不用依赖玩家自己的存档，也能覆盖到各种边界。

用 `yaml.safe_dump` 写，保证与游戏/修改器的 YAML 风格一致。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import copy

import yaml

GAME_STAMP = (2026, 1, 2, 3, 4, 6)


def dump(obj) -> bytes:
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False).encode("utf-8")


def make_save(path: Path, *, main_overrides: dict | None = None,
              battle_overrides: dict | None = None,
              store_overrides: dict | None = None,
              cards_override: list | None = None,
              extra_entries: dict | None = None) -> Path:
    """造一个"像游戏"的 .usg。

    默认包含：根 5 张 L1 表、`last_conference/`、`last_game/`、
    以及一个进行中的战斗 `games/avalanche/`（含 theater_assets）。

    `battle_overrides` 用来覆盖**战斗** `games/avalanche/main.yml` 的内容
    （比如换 `phase`、换 theater_assets 分组）—— 根 `main.yml` 用 `main_overrides`；
    `store_overrides` 用来覆盖根 `store.yml`（比如加一条战线）。
    """
    main = {
        "campaign_id": "west",
        "campaign_name": "id_campaign_name_c_west_p_base",
        "level": "hard",
        "prestige": 320,
        "score": 2980,
        "milestones": ["masters_of_the_north_african_shores", "fascist_regime"],
        "num_buyed_turns": 0,
        "card_store": None,
        "conference_start_state": None,
        "destroyed_cities": [[203, 252]],
        "renamed_hqs": {5: 14},
        "reverted_games": [],
        "standalone_scenario": None,
        "tokens": [["avalanche", "coast"]],
        "tokens_map": [["avalanche", "ortona", "A", "id_objective_name_brief_Ortona"]],
        "used_card_types_with_unit": {"tactical_naval_assault_us": [570]},
        "in_state": {
            "completed": False,
            "conference": "c_43_09",
            "front": "south",
            "scenario": "avalanche",
            "variant": None,
            "segment_finished": True,
            "lost_scenario": None,
            "fronts": {
                "south": {"approved_plan": None, "played_segments": [],
                          "segment": "s_43_09_south", "situation_idx": 2,
                          "supply_value": [100, 100], "tmp_approved_plan": None},
            },
        },
    }
    if main_overrides:
        main.update(main_overrides)

    # 上次会议检查点：那时**发了牌**，所以 card_store 非空（§6.3「恢复牌局」的来源）
    conference_main = dict(main)
    conference_main["card_store"] = [
        {"card_type": "air_attack_allies", "is_free": True, "position": 1,
         "unit_id": None, "used": False},
        {"card_type": "air_supply_allies", "is_free": False, "position": 2,
         "unit_id": None, "used": False},
    ]

    units = [
        {"id": 1, "type": "us_inf_42", "name_brief": "id_us_inf_42_brief",
         "name_full": "第 1 步兵连", "hq_id": 5, "xp": 10, "act_st": 4, "sup_st": 0,
         "losses": 0, "ap": 1, "mp": 3, "entr": 0, "supply": 3,
         "retreated": False, "hidden_defense": False,
         "specs": [{"active": True, "captured": False, "idx": 0,
                    "type": "ger_arty_40"}],
         "supplied_by": 0, "uv": [12, 34]},
        {"id": 2, "type": "ger_inf_39", "name_brief": "我的警卫队",
         "name_full": None, "hq_id": 5, "xp": 50, "act_st": 6, "sup_st": 1,
         "losses": 2, "ap": 2, "mp": 2, "entr": 1, "supply": 2,
         "retreated": False, "hidden_defense": False,
         "specs": [], "supplied_by": 1, "uv": [13, 35]},
    ]
    hqs = [
        {"id": 5, "name_brief": "id_hq_5_brief", "name_full": None,
         "name_super_brief": None, "general": None, "cp": 4, "max_cp": 5,
         "supply": 3, "uv": [10, 20], "xp": 0, "xp_target": 100,
         "persistent": True, "overrun": False, "turn_disbanded": False,
         "loss_count": 0, "intels_revealed": 0, "prisoners": 0,
         "trucks": 3, "fixed_movement": False, "fixed_range": False,
         "motor_pool_flag": False, "moved": False,
         # **被压制的等级数是整数**（不是布尔开关）—— `e166` 字节码：
         # `branch_suppress` → level −= n; suppressed += n；
         # `unsuppress_branch_levels` → level += suppressed; suppressed = 0。
         # 游戏内部「解锁到几级」= level + suppressed（`can_add_branch_level`）。
         "branch_levels": {"force_pool": {"level": 1, "suppressed": 0},
                           "intel": {"level": 0, "suppressed": 0},
                           "operations": {"level": 2, "suppressed": 0},
                           "logistics": {"level": 2, "suppressed": 0},
                           "engineering": {"level": 1, "suppressed": 0}},
         # **技能树**（`e165`）：分支 → 技能列表；每条 = {action, cost, level,
         # sp_avail, sp_used}。`level` 是**级别 tier**（矩阵的列），**不是**分支等级；
         # `sp_used` = 已专精次数 = 技能等级；`sp_avail` = 还能再专精几次（≤2）。
         # `force_pool` 的四个动作与 `motor_pool` 没有技能点 ⇒ sp_avail/sp_used = null。
         # 这里是照真实存档（截图里那个「A集团军群」）抄的形状。
         "branches": {
             "engineering": [
                 {"action": "bridge_repair", "cost": 2, "level": 1,
                  "sp_avail": 2, "sp_used": 1},
                 {"action": "bridge_destroy", "cost": 2, "level": 2,
                  "sp_avail": 1, "sp_used": 0},
                 {"action": "bridge_create", "cost": 3, "level": 3,
                  "sp_avail": 2, "sp_used": 0},
                 {"action": "river_crossing", "cost": 1, "level": 1,
                  "sp_avail": 1, "sp_used": 1},
                 {"action": "assault_crossing", "cost": 3, "level": 2,
                  "sp_avail": 2, "sp_used": 0},
                 {"action": "entrenchment", "cost": 1, "level": 1,
                  "sp_avail": 1, "sp_used": 1},
             ],
             "force_pool": [
                 {"action": "deploy", "cost": 0, "level": 1,
                  "sp_avail": None, "sp_used": None},
                 {"action": "reorg", "cost": 1, "level": 1,
                  "sp_avail": None, "sp_used": None},
                 {"action": "transfer", "cost": 2, "level": 1,
                  "sp_avail": None, "sp_used": None},
                 {"action": "security_unit", "cost": 2, "level": 2,
                  "sp_avail": None, "sp_used": None},
             ],
             "intel": [],
             "logistics": [
                 {"action": "supply_emergency", "cost": 2, "level": 1,
                  "sp_avail": 2, "sp_used": 1},
                 {"action": "supply_dump", "cost": 2, "level": 2,
                  "sp_avail": 2, "sp_used": 1},
                 {"action": "motor_pool", "cost": 2, "level": 2,
                  "sp_avail": None, "sp_used": None},
             ],
             "operations": [
                 {"action": "no_retreat", "cost": 1, "level": 1,
                  "sp_avail": 1, "sp_used": 1},
                 {"action": "pindown", "cost": 3, "level": 2,
                  "sp_avail": 2, "sp_used": 0},
                 {"action": "set_piece_attack", "cost": 1, "level": 1,
                  "sp_avail": 1, "sp_used": 1},
                 {"action": "suppressive_fire", "cost": 2, "level": 2,
                  "sp_avail": 2, "sp_used": 1},
                 {"action": "rearguard", "cost": 3, "level": 3,
                  "sp_avail": 2, "sp_used": 0},
                 {"action": "elastic_defense", "cost": 4, "level": 3,
                  "sp_avail": 2, "sp_used": 0},
                 {"action": "recon_in_force", "cost": 4, "level": 3,
                  "sp_avail": 2, "sp_used": 0},
             ],
         },
         "force_pool": [
             {"delay": 0, "nationality": "us", "quantity": 12,
              "equipment": "infantry"},
             {"delay": 0, "nationality": "german", "quantity": 3,
              "spec": "ger_arty_40"},
         ]},
    ]
    # U23：**每个总部的兵库独立** ⇒ 判重范围 = 单个 hq。
    # 加第二个总部，用来验证「同一条特种兵在另一个总部可以再加」。
    _hq6 = copy.deepcopy(hqs[0])
    _hq6["id"] = 6
    _hq6["name_brief"] = "id_hq_6_brief"
    _hq6["uv"] = [11, 21]
    _hq6["force_pool"] = []          # 空兵库 —— 加什么都行
    hqs.append(_hq6)
    cards = [
        {"card_type": "air_attack_allies", "is_free": True, "position": 1,
         "unit_id": None, "used": False},
    ]
    # U64：`cards_override` 用来改**手牌张数**（测难度与手牌上限的冲突）
    if cards_override is not None:
        cards = list(cards_override)
    # ⚠️ store.yml 是**两层**的：`{战线: {store: [...], elite_store: [...]}}`
    # （`e154` 实证：全部 68 个存档都是这个结构，`elite_store` 恒为 null）
    store = {
        "south": {
            "store": [
                {"equipment": "infantry", "nationality": "us", "price": 5,
                 "quantity": 20},
                {"spec": "ger_arty_40", "nationality": "german", "price": 8,
                 "quantity": 4},
            ],
            "elite_store": None,
        },
    }
    # 战役文档（L5，只读）—— 白名单要靠它知道玩家阵营与卡→单位登记表
    document_main = {
        "player_faction": "axis",
        "card_type_units": [
            {"card_type": "tactical_para_german", "unit_id": 718},
        ],
    }
    entries = {
        "main.yml": dump(main),
        "units.yml": dump(units),
        "hqs.yml": dump(hqs),
        "cards.yml": dump(cards),
        "store.yml": dump(store),
        "last_conference/main.yml": dump(conference_main),
        "last_conference/units.yml": dump(units),
        "last_conference/hqs.yml": dump(hqs),
        "last_conference/cards.yml": dump(cards),
        "last_conference/store.yml": dump(store),
        "last_game/main.yml": dump(main),
        "last_game/units.yml": dump(units),
        "last_game/hqs.yml": dump(hqs),
        "last_game/cards.yml": dump(cards),
        "last_game/store.yml": dump(store),
        "games/avalanche/main.yml": dump({
            "ar_ord": 190, "turn": 3, "turn_len": 1, "phase": 0,
            # 三个字段都取**游戏里的合法值**（U20 字节码取证）：
            #   to_use ≥ 0 / uses_total ≥ 0 或 None / uses_turn ≥ 1
            "theater_assets": [[
                {"asset": "air_attack", "to_use": 1,
                 "to_use_not_used": None, "uses_total": None, "uses_turn": 1},
                {"asset": "naval_bombardment", "to_use": 0,
                 "to_use_not_used": None, "uses_total": None, "uses_turn": 1},
                {"asset": "long_range_recon", "to_use": 1,
                 "to_use_not_used": 0, "uses_total": 2, "uses_turn": 1},
            ], []],
            "scores": {"casualties": 0},
        }),
        "games/avalanche/ar_list.yml": dump([]),
        "games/avalanche/units.yml": dump([1, 2]),
        "document/units.yml": dump([
            {"id": 1, "type": "us_inf_42", "name_brief": "id_us_inf_42_brief",
             "name_full": None},
            {"id": 2, "type": "ger_inf_39", "name_brief": "我的警卫队",
             "name_full": None},
            {"id": 718, "type": "ger_fsjg_40", "name_brief": "id_ger_fsjg_40_brief",
             "name_full": None},
        ]),
        "document/main.yml": dump(document_main),
    }
    if battle_overrides:
        _bm = yaml.safe_load(entries["games/avalanche/main.yml"])
        _bm.update(battle_overrides)
        entries["games/avalanche/main.yml"] = dump(_bm)
    if store_overrides:
        _sm = yaml.safe_load(entries["store.yml"])
        _sm.update(store_overrides)
        entries["store.yml"] = dump(_sm)
    if extra_entries:
        entries.update(extra_entries)

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zi = zipfile.ZipInfo(name, date_time=GAME_STAMP)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zi.create_system = 0
            zf.writestr(zi, data)
    return path
