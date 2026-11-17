"""存档根级数据访问：声望（prestige）与战区资产（theater_assets）。

声望在根 main.yml；战区资产在“当前战斗的 main.yml”——战役为
games/<场景>/main.yml，独立场景为 game/main.yml（见 _game_main_path）。
"""

from __future__ import annotations

from pathlib import Path

from .savefile import dump_yaml, load_yaml


def _find_scenario(session) -> str | None:
    """定位“当前战斗”的名字。

    战役：根 main.yml 的 in_state.scenario；
    独立场景：根 main.yml 的 standalone_scenario（单局存档，无 in_state）。
    """
    main = load_yaml(session.work_dir / "main.yml")
    standalone = main.get("standalone_scenario")
    if standalone:
        return standalone
    try:
        return main["in_state"]["scenario"]
    except (KeyError, TypeError):
        return None


def _game_main_path(session) -> Path | None:
    """定位“当前战斗的 main.yml”（含 theater_assets 等运行时数据）。

    布局差异：战役存于 games/<场景>/main.yml；独立场景是单局，数据直接
    放在根级 game/main.yml（单数目录），没有 games/<场景>/ 子层。
    """
    main = load_yaml(session.work_dir / "main.yml")
    if main.get("standalone_scenario"):
        cand = session.work_dir / "game" / "main.yml"
        return cand if cand.exists() else None
    try:
        scenario = main["in_state"]["scenario"]
    except (KeyError, TypeError):
        scenario = None
    if scenario:
        cand = session.work_dir / "games" / scenario / "main.yml"
        if cand.exists():
            return cand
    return None


def get_prestige(session) -> int | None:
    data = load_yaml(session.work_dir / "main.yml")
    return data.get("prestige")


def set_prestige(session, value: int) -> bool:
    path = session.work_dir / "main.yml"
    data = load_yaml(path)
    data["prestige"] = value
    dump_yaml(path, data)
    print(f"声望已设为 {value}")
    return True


# 战区资产：命令别名 -> 存档内 asset 名
ASSET_MAPPING = {
    "air": "air_attack",
    "airArt": "flying_artillery",
    "airRec": "long_range_recon",
    "pb": "precision_bombing",
    "supply": "air_supply",
    "ss": "saturation_strike",
    "nb": "naval_bombardment",
}


def set_theater_asset(session, asset_alias: str, to_use: int,
                      uses_total: int, uses_turn: int) -> bool:
    """设置战区资产次数。

    目标文件是“当前战斗的 main.yml”：战役在 games/<scenario>/main.yml，
    独立场景在根 game/main.yml；其 theater_assets[0] 是当前可用的资产列表
    （元素形如 {asset, to_use, to_use_not_used, uses_total, uses_turn}）。
    uses_total=0 时视为不限（存 null）。
    """
    scenario = _find_scenario(session)
    path = _game_main_path(session)
    if scenario is None or path is None:
        print("无法确定当前场景文件（根 main.yml 缺 standalone_scenario/"
              "in_state.scenario，或对应 main.yml 不存在）。")
        return False
    asset = ASSET_MAPPING.get(asset_alias)
    if asset is None:
        print(f"未定义战区资产: {asset_alias}（可用: {', '.join(ASSET_MAPPING)}）")
        return False
    data = load_yaml(path)
    theater = data.get("theater_assets")
    if not theater:
        print("场景文件中没有 theater_assets 字段。")
        return False
    entry = {"asset": asset, "to_use": to_use, "to_use_not_used": None,
             "uses_total": uses_total if uses_total else None,
             "uses_turn": uses_turn}
    items = theater[0]
    replaced = False
    for i, item in enumerate(items):
        if item.get("asset") == asset:
            items[i] = entry
            replaced = True
            break
    if not replaced:
        items.append(entry)
    dump_yaml(path, data)
    print(f"战区资产 {asset} 已设置 (to_use={to_use}, total={uses_total or '∞'}, "
          f"turn={uses_turn})")
    return True
