"""测试用的合成存档。

结构照着游戏真实的存档写（17 个键的根 `main.yml`、L2 检查点、L3 战斗层），
这样测试不用依赖玩家自己的存档，也能覆盖到各种边界。

用 `yaml.safe_dump` 写，保证与游戏/修改器的 YAML 风格一致。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import yaml

GAME_STAMP = (2026, 1, 2, 3, 4, 6)


def dump(obj) -> bytes:
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False).encode("utf-8")


def make_save(path: Path, *, main_overrides: dict | None = None,
              extra_entries: dict | None = None) -> Path:
    """造一个"像游戏"的 .usg。

    默认包含：根 5 张 L1 表、`last_conference/`、`last_game/`、
    以及一个进行中的战斗 `games/avalanche/`（含 theater_assets）。
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

    units = [
        {"id": 1, "type": "us_inf_42", "name_brief": "id_us_inf_42_brief",
         "name_full": None, "hq_id": 5, "xp": 10, "act_st": 4, "sup_st": 0,
         "losses": 0, "ap": 1, "mp": 3, "entr": 0, "supply": 3,
         "retreated": False, "hidden_defense": False,
         "specs": [{"active": True, "captured": False, "idx": 0,
                    "type": "ger_engineer"}],
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
         "trucks": 0, "fixed_movement": False, "fixed_range": False,
         "motor_pool_flag": False, "moved": False,
         "branch_levels": {"force_pool": {"level": 1, "suppressed": False},
                           "intel": {"level": 0, "suppressed": False},
                           "operations": {"level": 0, "suppressed": False},
                           "logistics": {"level": 0, "suppressed": False},
                           "engineering": {"level": 0, "suppressed": False}},
         "force_pool": [
             {"delay": 0, "nationality": "us", "quantity": 12,
              "equipment": "infantry"},
             {"delay": 0, "nationality": "german", "quantity": 3,
              "spec": "ger_engineer"},
         ]},
    ]
    cards = [
        {"card_type": "air_attack_allies", "is_free": True, "position": 1,
         "unit_id": None, "used": False},
    ]
    store = {
        "south": [
            {"equipment": "infantry", "nationality": "us", "price": 5,
             "quantity": 20},
            {"spec": "ger_engineer", "nationality": "german", "price": 8,
             "quantity": 4},
        ],
    }
    entries = {
        "main.yml": dump(main),
        "units.yml": dump(units),
        "hqs.yml": dump(hqs),
        "cards.yml": dump(cards),
        "store.yml": dump(store),
        "last_conference/main.yml": dump(main),
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
            "ar_ord": 190, "turn": 3, "turn_len": 1,
            "theater_assets": [[
                {"asset": "air_attack", "to_use": 1,
                 "to_use_not_used": None, "uses_total": 2, "uses_turn": 1},
                {"asset": "naval_bombardment", "to_use": 0,
                 "to_use_not_used": None, "uses_total": None, "uses_turn": 0},
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
        ]),
    }
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
