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

# 战力上限中最大的一个（轴心 7；盟军 6，美军战斗指挥部 4）。units.yml 不含
# 阵营与编制信息，无法逐单位判定上限，故只按此值提示，不做硬性校验。
AXIS_STEP_CAP = 7


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

    def __init__(self, session, path: Optional[Path] = None):
        self.session = session
        self.path = path or session.work_dir / "units.yml"
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

        游戏单位战力由 act_st（活跃）+ sup_st（被压制）构成，上限依阵营与
        编制而定（轴心 7、盟军 6、美军战斗指挥部 4）。存档里没有阵营信息，
        因此只在合计超过 AXIS_STEP_CAP 时提示，不拦截写入。
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
        if total > AXIS_STEP_CAP:
            print(f"提示：合计 {total} 超过 {AXIS_STEP_CAP}（轴心上限，盟军为 6），"
                  "游戏读取时可能出错。")
        return True

    def set_type(self, unit_id: int, type_name: str) -> bool:
        return self.set_field(unit_id, "type", type_name)

    def add_spec(self, unit_id: int, spec_type: str) -> bool:
        """给单位挂载一个特种（specs 追加）。

        同名特种允许重复挂载（例如两个工兵），每条各占一个槽位与 idx。
        游戏规则盟军最多 3 个、轴心依战役而定（通常更少）；本方法按 3 校验
        并提示，若需突破可手改 YAML。
        """
        unit = self._find(unit_id)
        if unit is None:
            print(f"未找到单位 id {unit_id}")
            return False
        specs = unit.setdefault("specs", [])
        if len(specs) >= 3:
            print("特种已满（3），无法自动添加；可手改 YAML 突破。")
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
