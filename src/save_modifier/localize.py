"""本地化文本写入。

brief/full/troopName 命令的本质是往 temp mod 的中文本地化文件写入
{文本id: 中文}，并把实体/单位的 name 字段指向该文本 id。

本地化文件位置：<temp_mod>/localization/chi/<存档名>_strings.yml
（游戏加载 mod 时会读取 chi 本地化并显示中文名。）
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .savefile import dump_yaml, load_yaml

if TYPE_CHECKING:
    from .entities import Entity


def _strings_path(session, create: bool = False) -> Path:
    mod = session.config.temp_mod_dir_for(session.name)
    path = mod / "localization" / session.config.locale / f"{session.name}_strings.yml"
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def set_localization_text(session, text_id: str, text: str) -> bool:
    """写入 {text_id: text} 到该存档 temp mod 的本地化文件。"""
    path = _strings_path(session, create=True)
    data = load_yaml(path) if path.exists() else {}
    data[text_id] = text
    dump_yaml(path, data)
    print(f"本地化写入: {text_id} = {text}")
    return True


def localize_entity_text(
    session,
    entity: "Entity",
    text: str,
    field: str = "brief",
    verbose: bool = False,
) -> bool:
    """把实体的 name_brief/name_full 指到默认文本 id 并写入翻译。

    实体必须已存在于 temp mod。写回实体 type_data 并更新 mod 文件。
    """
    from .entities import Entity

    if not isinstance(entity, Entity):
        print("内部错误：localize_entity_text 需要 Entity 实例。")
        return False
    if field not in ("brief", "full"):
        print(f"未知文本类型: {field}")
        return False
    name_key = f"name_{field}"
    default_id = entity.default_name_id(field)
    entity.set_type_field(name_key, default_id)
    entity.update_in_mod(verbose=verbose)
    ok = set_localization_text(session, default_id, text)
    return ok


def localize_unit_name_brief(session, unit: dict, unit_id: int, text: str) -> bool:
    """troopName：改单位 name_brief 为 <原名>_custom 并写入本地化。

    该方式不改实体，只让“这一个单位”显示自定义名。
    """
    brief = unit.get("name_brief") or f"id_unit_{unit_id}_brief"
    if not brief.endswith("_custom"):
        brief = f"{brief}_custom"
    unit["name_brief"] = brief
    ok = set_localization_text(session, brief, text)
    print(f"单位 {unit_id} 名称设为: {text} ({brief})")
    return ok
