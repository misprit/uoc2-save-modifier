"""实体创建与单位类型绑定服务：克隆原型类型、解析模型 meta、维护绑定文件。

设计要点：
- 两步显式分离：
  * create-type <原型> [新类型名] —— 从原型克隆一个新单位/特种类型实体到
    temp mod，不绑定任何单位；
  * bind <单位id> <类型> —— 把单位指向某类型（写入绑定文件并应用到 units.yml）。
- 绑定文件 = <存档隔离>/unit_type_modifier.yml，记录 {单位id: 类型}；
  每次进入会话/执行 reu 时强制应用（应对战役段脚本把单位 type 覆写回默认）。
- 绑定目标可以是自定义类型，也可以是原版类型（多单位共享）。
- 原型默认只搜原版包（base + 战役包），另支持 config.mod_search_paths 扩展。
- 模型 meta（assets/models/<名>_meta.yml）可用 create-type 的 --model-from 指定
  来源：包名（base/dlc1/...）或路径（包目录 / 直接的 meta 文件）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from . import entities
from .package_map import package_for_campaign


class BindingStore:
    """每存档隔离的单位类型绑定文件。"""

    def __init__(self, base_dir: Path):
        self.path = base_dir / "unit_type_modifier.yml"
        self.data: dict[int, str] = {}
        self.load()

    def load(self) -> None:
        self.data = {}
        if self.path.exists():
            from .savefile import load_yaml
            raw = load_yaml(self.path)
            if isinstance(raw, dict):
                self.data = {int(k): str(v) for k, v in raw.items()}

    def save(self) -> None:
        from .savefile import dump_yaml
        dump_yaml(self.path, self.data)

    def get(self, unit_id: int) -> Optional[str]:
        return self.data.get(unit_id)

    def set(self, unit_id: int, type_name: str) -> None:
        self.data[unit_id] = type_name
        self.save()

    def unset(self, unit_id: int) -> bool:
        if unit_id in self.data:
            del self.data[unit_id]
            self.save()
            return True
        return False

    def items(self):
        return self.data.items()

    def contains_type(self, type_name: str) -> bool:
        return type_name in self.data.values()


def apply_bindings(session, unit_list, bindings: BindingStore,
                   verbose: bool = False) -> int:
    """把绑定文件应用到当前 units.yml。

    对每个有绑定的单位：若其当前 type 与绑定目标不一致，则改成目标。
    返回改动数量。单位此时不在 units.yml 时跳过。
    """
    changed = 0
    for uid, type_name in bindings.items():
        unit = unit_list.get(uid)
        if unit is None:
            if verbose:
                print(f"单位 {uid} 当前不在 units.yml，跳过（可能在第0回合/未上场）。")
            continue
        if unit.get("type") != type_name:
            unit["type"] = type_name
            changed += 1
            if verbose:
                print(f"单位 {uid}: type => {type_name}")
    if changed:
        unit_list.persist()
    return changed


def _first_existing(search_roots: list[Path], rel: Path) -> Optional[Path]:
    for root in search_roots:
        cand = root / rel
        if cand.exists():
            return cand
    return None


def _looks_like_package_name(value: str) -> bool:
    """base / dlc1 / dlc10 这类纯包名（不含路径分隔符）。"""
    return bool(value) and all(
        ch.isalnum() or ch in "_-."
        for ch in value
    ) and "/" not in value and "\\" not in value


def _resolve_model_meta(
    orig: Path,
    default_roots: list[Path],
    meta_rel: Path,
    model_from: Optional[str],
    verbose: bool = False,
) -> tuple[Optional[Path], bool]:
    """定位模型 meta 文件，返回 (路径, 是否由调用方显式指定来源)。

    未指定 model_from 时沿用默认搜索根（战役包 → base）。
    显式指定时只在该来源中查找：
      * 包名（base/dlc1/...）：<orig>/<包名>/assets/models/<名>_meta.yml
      * 路径：若为文件则直接作为 meta；若为目录则按 <目录>/assets/models/... 查
    """
    if not model_from or not model_from.strip():
        return _first_existing(default_roots, meta_rel), False

    raw = model_from.strip()
    if _looks_like_package_name(raw):
        pkg_dir = orig / raw
        if not pkg_dir.is_dir():
            print(f"指定的模型来源包不存在: {pkg_dir}")
            return None, True
        if verbose:
            print(f"模型来源包: {pkg_dir}")
        return _first_existing([pkg_dir], meta_rel), True

    src = Path(os.path.expandvars(os.path.expanduser(raw)))
    if src.is_file():
        if verbose:
            print(f"模型 meta 来源文件: {src}")
        return src, True
    if src.is_dir():
        if verbose:
            print(f"模型来源目录: {src}")
        return _first_existing([src], meta_rel), True
    print(f"指定的模型来源路径不存在: {src}")
    return None, True


def resolve_unit_prototype(
    config,
    campaign_name: str,
    type_name: str,
    kind: str,
    model_from: Optional[str] = None,
    verbose: bool = False,
) -> entities.Entity | None:
    """按名称在原版包（+扩展搜索路径）中定位原型实体。

    model_from: 仅对 unit 生效，指定模型 meta 的来源——包名（base/dlc1/...）
    或路径（包目录 / 直接的 *_meta.yml）。None 时沿用默认搜索根
    （扩展路径 → 战役包 → base）。

    返回一个以“来源包为 mod_path”的 Entity（尚未写入 temp mod）。
    """
    # 组装搜索根：扩展搜索路径（若有）+ 战役包 + base
    orig = config.orig_packages
    if orig is None:
        print("未配置原版包路径 (uoc2_orig_packages_path)，无法以原版为原型。")
        return None
    roots: list[Path] = []
    for p in config.mod_search_paths:
        if p.is_dir():
            roots.append(p)
    pkg = package_for_campaign(campaign_name)
    roots.append(orig / pkg)
    roots.append(orig / "base")

    if kind == "unit":
        type_rel = Path("data/entity_types/unit_types") / f"{type_name}.yml"
        surf_rel = Path("assets/surfaces/unit") / type_name
        meta_rel = Path("assets/models") / f"{type_name}_meta.yml"
    else:
        type_rel = Path("data/entity_types/specialists") / f"{type_name}.yml"
        surf_rel = Path("assets/surfaces/specialist") / type_name
        meta_rel = None

    type_file = _first_existing(roots, type_rel)
    surf_dir = _first_existing(roots, surf_rel)
    meta_file = None
    explicit_meta = False
    if meta_rel is not None:
        meta_file, explicit_meta = _resolve_model_meta(
            orig, roots, meta_rel, model_from, verbose=verbose)
    if type_file is None or surf_dir is None:
        if verbose:
            print(f"未找到原型 '{type_name}'（{kind}）的 type/surfaces。")
        return None
    if explicit_meta and meta_file is None:
        print(f"指定的模型来源中未找到 '{type_name}' 的 model_meta，创建失败。")
        return None
    if kind == "unit" and meta_file is None:
        if verbose:
            print(f"未找到原型 '{type_name}' 的 model_meta，仍继续（可能缺）。")
    # 加载 type_data
    from .savefile import load_yaml
    type_data = load_yaml(type_file) if type_file.exists() else {}
    meta_data = load_yaml(meta_file) if meta_file and meta_file.exists() else {}
    ent = entities.Entity(
        name=type_name,
        mod_path=orig,  # 仅占位；surfaces_path 用解析出的目录
        kind=kind,
        type_data=type_data,
        meta_data=meta_data,
        surfaces_path=surf_dir,
    )
    if verbose:
        print(f"原型定位成功: {type_file}")
        if meta_file:
            print(f"模型 meta: {meta_file}")
    return ent


def create_type_from_prototype(
    config,
    session,
    campaign_name: str,
    prototype_type: str,
    new_name: Optional[str] = None,
    kind: str = "unit",
    model_from: Optional[str] = None,
    verbose: bool = False,
) -> Optional[str]:
    """create-type 命令核心：从原型克隆新类型到 temp mod。

    model_from 见 resolve_unit_prototype（仅 unit 生效）。
    返回新建的实体名；失败返回 None。
    """
    proto = resolve_unit_prototype(config, campaign_name, prototype_type, kind,
                                   model_from=model_from, verbose=verbose)
    if proto is None:
        print(f"以 {prototype_type} 为原型创建失败：原版包中未找到。")
        return None
    new_name = new_name or f"{prototype_type}_custom"
    target_mod = session.config.temp_mod_dir_for(session.name)
    target_mod.mkdir(parents=True, exist_ok=True)
    created = entities.clone_entity_from_template(
        template=proto,
        new_name=new_name,
        target_mod=target_mod,
        orig_default_prefix=prototype_type,
        copy_surfaces=True,
        verbose=verbose,
    )
    print(f"已创建{('单位' if kind == 'unit' else '特种')}类型实体: {new_name}")
    print(f"位置: {target_mod / created.files.type_rel}")
    if kind == "unit" and created.meta_data:
        print(f"模型 meta 已写入: {target_mod / created.files.meta_rel}")
    print("提示：创建/修改 temp mod 实体后需重启游戏（重载 mod）才生效。")
    print("可用 bind <单位id> <类型名> 将单位指向该类型。")
    return new_name


def bind_unit_to_type(session, unit_list, bindings: BindingStore,
                      unit_id: int, type_name: str) -> bool:
    """bind 命令核心：写入绑定并应用。"""
    unit = unit_list.get(unit_id)
    if unit is None:
        print(f"单位 {unit_id} 当前不在 units.yml 中，仅记录绑定；"
              f"该单位上场后将自动应用。")
    bindings.set(unit_id, type_name)
    # 应用（若单位在场）
    if unit is not None:
        unit["type"] = type_name
        unit_list.persist()
        print(f"单位 {unit_id} type => {type_name}")
    else:
        print(f"已记录绑定: {unit_id} => {type_name}")
    return True
