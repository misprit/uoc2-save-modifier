"""单位类型实体（UnitEntity）与特种实体（SpecEntity）的配置管理。

一个“实体”在磁盘上由若干配置文件组成：
- Unit 实体三件套：unit_type 配置、model_meta 配置、surfaces 贴图目录
  <mod>/data/entity_types/unit_types/<名>.yml
  <mod>/assets/models/<名>_meta.yml
  <mod>/assets/surfaces/unit/<名>/
- Spec 实体两件套：specialist 配置 + surfaces 贴图目录
  <mod>/data/entity_types/specialists/<名>.yml
  <mod>/assets/surfaces/specialist/<名>/

本模块职责：
1. 从“来源包”（原版包 base/战役包，可加扩展搜索路径）按原型加载实体；
2. 以原型为模板创建新实体（复制三/两件套 + 改写 name 引用到新实体默认 id）；
3. 把实体写入目标 temp mod；
4. 重命名/删除实体时同步改名关联文件与文本 id。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

import yaml

from .savefile import dump_yaml, load_yaml


class EntityFiles:
    """一个实体的磁盘文件布局描述（相对 mod 根）。"""

    def __init__(self, entity_type: str, kind: str):
        # kind: "unit" 或 "specialist"
        self.kind = kind
        if kind == "unit":
            self.type_rel = Path("data/entity_types/unit_types") / f"{entity_type}.yml"
            self.surf_rel = Path("assets/surfaces/unit") / entity_type
            self.meta_rel = Path("assets/models") / f"{entity_type}_meta.yml"
        else:
            self.type_rel = Path("data/entity_types/specialists") / f"{entity_type}.yml"
            self.surf_rel = Path("assets/surfaces/specialist") / entity_type
            self.meta_rel = None  # spec 无 meta

    @property
    def has_meta(self) -> bool:
        return self.meta_rel is not None


class Entity:
    """在某个 mod 中一个实体的数据视图（unit 或 specialist 通用）。"""

    def __init__(self, name: str, mod_path: Path, kind: str,
                 type_data: Optional[dict] = None,
                 meta_data: Optional[dict] = None,
                 surfaces_path: Optional[Path] = None):
        self.name = name
        self.kind = kind
        self.mod_path = Path(mod_path)
        self.files = EntityFiles(name, kind)
        self.type_data = type_data if type_data is not None else {}
        self.meta_data = meta_data if meta_data is not None else {}
        self.surfaces_path = Path(surfaces_path) if surfaces_path else (
            self.mod_path / self.files.surf_rel)

    # ---- 路径 ----
    @property
    def type_file(self) -> Path:
        return self.mod_path / self.files.type_rel

    @property
    def meta_file(self) -> Optional[Path]:
        return self.mod_path / self.files.meta_rel if self.files.meta_rel else None

    # ---- 命名 id ----
    def default_name_id(self, field: str) -> str:
        """实体“默认文本 id”：id_<实体名>_<brief|full>。"""
        return f"id_{self.name}_{field}"

    # ---- 加载 ----
    @classmethod
    def from_mod(cls, name: str, mod_path: Path, kind: str,
                 verbose: bool = False) -> "Entity":
        """从已配置 mod 加载实体，缺失必需文件抛 FileNotFoundError。"""
        inst = cls(name, mod_path, kind)
        missing = []
        if not inst.type_file.exists():
            missing.append(str(inst.type_file))
        if not inst.surfaces_path.exists():
            missing.append(str(inst.surfaces_path))
        if inst.meta_file and not inst.meta_file.exists():
            missing.append(str(inst.meta_file))
        if missing:
            raise FileNotFoundError(
                f"实体 '{name}' ({kind}) 缺少文件：\n" + "\n".join(missing))
        inst.type_data = load_yaml(inst.type_file)
        if inst.meta_file:
            inst.meta_data = load_yaml(inst.meta_file) or {}
        if verbose:
            print(f"已从 {mod_path} 加载实体 {name}")
        return inst

    # ---- 写入 / 复制 ----
    def write_to_mod(self, target_mod: Path, copy_surfaces: bool = True,
                     verbose: bool = False) -> None:
        """把实体写入 target_mod（覆写）。"""
        target_mod = Path(target_mod)
        # type_data
        tf = target_mod / self.files.type_rel
        tf.parent.mkdir(parents=True, exist_ok=True)
        if self.type_data:
            dump_yaml(tf, self.type_data)
        # meta（仅 unit 有）
        meta_rel = self.files.meta_rel
        if self.meta_data and meta_rel is not None:
            mf = target_mod / meta_rel
            mf.parent.mkdir(parents=True, exist_ok=True)
            dump_yaml(mf, self.meta_data)
        # surfaces
        if copy_surfaces and self.surfaces_path.exists():
            tgt_surf = target_mod / self.files.surf_rel
            tgt_surf.mkdir(parents=True, exist_ok=True)
            for item in self.surfaces_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, tgt_surf / item.name)
        if verbose:
            print(f"实体已写入 {target_mod}")

    def rename_entity(self, new_name: str, verbose: bool = False) -> bool:
        """重命名实体：同步改名关联文件（type/meta/surfaces）并更新 name id。

        若实体引用了自定义 name id（非本实体默认），则保留该 id（由调用方
        决定是否通过本地化命令改写）。返回成功与否。
        """
        old_name = self.name
        if old_name == new_name:
            print("新旧名称相同，无需重命名。")
            return False
        old_files = EntityFiles(old_name, self.kind)
        new_files = EntityFiles(new_name, self.kind)
        # 1. type 文件
        if self.type_file.exists():
            self.type_file.rename(self.mod_path / new_files.type_rel)
        # 2. meta 文件（unit 有）
        old_meta_rel = old_files.meta_rel
        new_meta_rel = new_files.meta_rel
        if old_meta_rel is not None and new_meta_rel is not None:
            old_meta = self.mod_path / old_meta_rel
            if old_meta.exists():
                old_meta.rename(self.mod_path / new_meta_rel)
        # 3. surfaces 目录
        old_surf = self.mod_path / old_files.surf_rel
        if old_surf.exists():
            old_surf.rename(self.mod_path / new_files.surf_rel)
        # 4. 更新内存中的 name id（旧默认 id -> 新默认 id；自定义 id 保留）
        for field, key in (("brief", "name_brief"), ("full", "name_full")):
            cur = self.type_data.get(key)
            if isinstance(cur, str) and cur == f"id_{old_name}_{field}":
                self.type_data[key] = f"id_{new_name}_{field}"
        # 5. 更新对象自身路径与名称
        self.name = new_name
        self.files = new_files
        self.surfaces_path = self.mod_path / new_files.surf_rel
        # 6. 写回改名后的 type 数据
        if self.type_data:
            dump_yaml(self.type_file, self.type_data)
        if verbose:
            print(f"实体已重命名: {old_name} -> {new_name}")
        return True

    # ---- 修改 type_data ----
    def set_type_field(self, key: str, value: Any) -> None:
        self.type_data[key] = value

    def update_in_mod(self, target_mod: Optional[Path] = None,
                      verbose: bool = False) -> None:
        target_mod = Path(target_mod) if target_mod else self.mod_path
        self.write_to_mod(target_mod, copy_surfaces=False, verbose=verbose)


# 由于 unit 与 specialist 主要差异只是 kind/目录，上面用统一 Entity 表示。
# 提供两个工厂方便调用方语义清晰。

def load_entity(mod_path: Path, name: str, kind: str,
                verbose: bool = False) -> Entity:
    return Entity.from_mod(name, mod_path, kind, verbose)


def clone_entity_from_template(
    *,
    template: Entity,
    new_name: str,
    target_mod: Path,
    orig_default_prefix: str,
    copy_surfaces: bool = True,
    verbose: bool = False,
) -> Entity:
    """以 template 为原型创建名为 new_name 的新实体（写入 target_mod）。

    orig_default_prefix: 原型的原名（用于把旧默认 id id_<原名>_brief 改写为
    id_<new_name>_brief）。若原型用的是自定义 id，则保留原 id（inherit 语义）。
    """
    type_data = dict(template.type_data) if template.type_data else {}
    # 改写 name 引用：若当前为原型默认 id -> 新默认 id
    for field, key in (("brief", "name_brief"), ("full", "name_full")):
        cur = type_data.get(key)
        if isinstance(cur, str):
            old_default = f"id_{orig_default_prefix}_{field}"
            if cur == old_default:
                type_data[key] = f"id_{new_name}_{field}"
    meta_data = dict(template.meta_data) if template.meta_data else {}
    ent = Entity(name=new_name, mod_path=target_mod, kind=template.kind,
                 type_data=type_data, meta_data=meta_data,
                 surfaces_path=template.surfaces_path)
    ent.write_to_mod(target_mod, copy_surfaces=copy_surfaces, verbose=verbose)
    return ent
