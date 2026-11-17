"""存档内单位 (units.yml) 的访问封装。

存档根目录 units.yml 是一个“当前进行中战斗的单位列表”：
每个单位一条记录，常见字段见下。本模块提供按 id 读取/修改单位、
以及高频字段（xp / 战力 / type / 特种）的语义操作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .savefile import dump_yaml, load_yaml

# 常见字段（供帮助与 find 显示使用）
KNOWN_FIELDS = [
    "id", "type", "name_brief", "name_full", "hq_id", "xp",
    "act_st", "sup_st", "losses", "ap", "mp", "entr", "supply",
    "retreated", "hidden_defense", "specs", "supplied_by", "uv",
]

# ⚠️ **不再有硬编码的战力上限。**
# 以前这里写死 `AXIS_STEP_CAP = 7`（"轴心 7 / 盟军 6"），那是粗糙近似：
# 真实上限在**类型定义**里（`entity_types/unit_types/<type>.yml` 的 `max_st`），
# 实测 627 个类型的 max_st 分布是 {3:4, 4:9, 5:83, 6:108, 7:245, 无:178}。
# 现在从类型目录取（`Catalog`）；类型查不到时**不提示上限，也不拦截**
# —— 类型表只做候选，绝不做白名单（规范 §9.1.3、§5.3、§10 第 8 条）。
SPEC_HARD_LIMIT = 3          # 存档 schema 的硬上限（§5.2：长度 0..3）


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class UnitList:
    """对工作目录中 units.yml 的读访问与写回封装。

    设计：所有读操作访问 self.units（内存快照）；所有修改通过 self.set_*，
    内部立即写回 work_dir 的 units.yml；session.commit() 只把整个工作目录
    打包回 .usg。
    """

    def __init__(self, session, path: Optional[Path] = None, catalog=None):
        self.session = session
        self.path = path or session.work_dir / "units.yml"
        self.catalog = catalog
        self.units: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            data = load_yaml(self.path)
            self.units = data if isinstance(data, list) else []
        else:
            self.units = []

    def _find(self, unit_id: int) -> Optional[dict[str, Any]]:
        return next((u for u in self.units if u.get("id") == unit_id), None)

    def get(self, unit_id: int) -> Optional[dict[str, Any]]:
        return self._find(unit_id)

    def find_by_name(self, keyword: str, translations=None) -> list[dict[str, Any]]:
        """按中文名或本地化 id 或 type 模糊匹配单位（供 find 命令）。"""
        kw = keyword.strip().lower()
        out = []
        for u in self.units:
            brief = str(u.get("name_brief", ""))
            name = ""
            if translations:
                name = translations.get(brief, "")
            type_ = str(u.get("type", ""))
            haystack = f"{brief} {name} {type_}".lower()
            if kw in haystack:
                out.append(u)
        return out

    def set_field(self, unit_id: int, field: str, value) -> bool:
        """通用字段设置：set <id> <field> <value>。

        value 原样写入；整数与字符串的区分由调用方（REPL 的 set 命令）
        完成，本方法不再次转换。
        """
        unit = self._find(unit_id)
        if unit is None:
            print(f"未找到单位 id {unit_id}")
            return False
        if field not in KNOWN_FIELDS:
            print(f"警告：字段 '{field}' 不在已知字段列表中，仍将写入。")
        unit[field] = value
        self.persist()
        print(f"单位 {unit_id}.{field} = {value}")
        return True

    # ---- 高频字段语义操作 ----

    def set_xp(self, unit_id: int, xp: int) -> bool:
        return self.set_field(unit_id, "xp", xp)

    def set_strength(self, unit_id: int, active: Optional[int] = None,
                     suppressed: Optional[int] = None) -> bool:
        """战力设置：可设活跃战力 (act_st) 与压制战力 (sup_st)。

        战力上限来自**类型定义**的 `max_st`（`entity_types/unit_types/`），
        不是硬编码的"轴心 7 / 盟军 6"。类型查不到时**只提示不拦截** ——
        类型表只做候选，绝不做白名单（规范 §5.3、§9.1.3）。
        """
        unit = self._find(unit_id)
        if unit is None:
            print(f"未找到单位 id {unit_id}")
            return False
        if active is not None:
            unit["act_st"] = active
        if suppressed is not None:
            unit["sup_st"] = suppressed
        self.persist()
        total = int(unit.get("act_st", 0)) + int(unit.get("sup_st", 0))
        print(f"单位 {unit_id} 战力: act_st={unit.get('act_st')} "
              f"sup_st={unit.get('sup_st')} 合计={total}")
        limit = self._max_st(unit)
        if limit is not None and total > limit:
            print(f"提示：合计 {total} 超过该单位的战力上限 {limit}"
                  f"（来自类型 {unit.get('type')} 的 max_st）。")
        return True

    def _max_st(self, unit: dict[str, Any]) -> Optional[int]:
        """该单位的战力上限；类型未知返回 None（不提示、不拦截）。"""
        if self.catalog is None:
            return None
        type_name = unit.get("type")
        if not type_name:
            return None
        return self.catalog.max_st(type_name)

    def _spec_cap(self, unit: dict[str, Any]) -> int:
        """该单位能挂几个特种兵 = `min(3, max_spec or 3)`（规范 §5.3）。"""
        if self.catalog is None:
            return SPEC_HARD_LIMIT
        type_name = unit.get("type")
        if not type_name:
            return SPEC_HARD_LIMIT
        return self.catalog.spec_cap(type_name)

    def set_type(self, unit_id: int, type_name: str) -> bool:
        return self.set_field(unit_id, "type", type_name)

    def add_spec(self, unit_id: int, spec_type: str) -> bool:
        """给单位挂载一个特种（specs 追加）。

        同名特种允许重复挂载（例如两个工兵），每条各占一个槽位与 idx。
        上限是该单位**类型**的 `min(3, max_spec or 3)`（规范 §5.3），
        不是写死的 3；类型查不到时按存档 schema 的硬上限 3 处理。
        """
        unit = self._find(unit_id)
        if unit is None:
            print(f"未找到单位 id {unit_id}")
            return False
        specs = unit.setdefault("specs", [])
        cap = self._spec_cap(unit)
        if len(specs) >= cap:
            print(f"特种已满（{cap}），无法自动添加。")
            return False
        used_idx = {s.get("idx") for s in specs}
        free_idx = next(i for i in (0, 1, 2) if i not in used_idx)
        specs.append({"active": True, "captured": False,
                      "idx": free_idx, "type": spec_type})
        self.persist()
        print(f"单位 {unit_id} 已添加特种 {spec_type} (idx={free_idx})")
        return True

    def remove_spec(self, unit_id: int, spec_type: str,
                    idx: Optional[int] = None) -> bool:
        """移除一个特种；同名特种有多条时只移除一条，其余保留。

        默认移除该类型的第一条（列表顺序，通常即 idx 最小者）；给出 idx 时
        只移除 type 与 idx 同时匹配的那一条。这样“两个工兵”可以只卸一个。
        """
        unit = self._find(unit_id)
        if unit is None:
            print(f"未找到单位 id {unit_id}")
            return False
        specs = unit.get("specs", [])
        target = next(
            (s for s in specs
             if s.get("type") == spec_type
             and (idx is None or s.get("idx") == idx)),
            None,
        )
        if target is None:
            suffix = f" (idx={idx})" if idx is not None else ""
            print(f"单位 {unit_id} 没有特种 {spec_type}{suffix}")
            return False
        specs.remove(target)
        unit["specs"] = specs
        self.persist()
        remaining = sum(1 for s in specs if s.get("type") == spec_type)
        print(f"单位 {unit_id} 已移除特种 {spec_type} (idx={target.get('idx')})"
              + (f"，同类还剩 {remaining} 条" if remaining else ""))
        return True

    def persist(self) -> None:
        """把内存中的单位列表写回工作目录的 units.yml。

        每次字段修改都会调用；session.commit() 只负责打包工作目录，落盘必须
        在这里完成。
        """
        dump_yaml(self.path, self.units)
