"""目录：游戏包里的类型表与战线清单（**只读**）。

数据源
------
```
<包>/data/entity_types/unit_types/<类型名>.yml     627 个  → max_st / max_spec / equipment / equipment_q
<包>/data/entity_types/specialists/<类型名>.yml     375 个
<包>/data/entity_types/cards/<类型名>.yml            39 个
<包>/data/entity_types/hq_types/<类型名>.yml        213 个
<包>/data/entity_types/generals/<类型名>.yml        304 个
<包>/data/campaigns/<战役>.usc/fronts/<战线>/         战线清单（**每个战役包各有一份**）
```

⚠️ **类型表只有 base 包有**（实测 11 个游戏包里只有 base 带 `entity_types/`，
dlc1..dlc10 的 `data/` 只有 `campaigns` / `scenarios`）。
⇒ **原版游戏的类型表永不变化**，适合做成内置静态快照；
新 DLC 带来的是战役/场景数据，不是新类型。

⚠️ **用户包优先**（mod 兼容）：游戏自己的 `paths.all_package_dirs()` 实测顺序是
`['%LOCALAPPDATA%\\.uoc2\\_packages', '<game>\\_packages']` ——
只扫游戏包会漏掉 mod 新增的类型与场景（规范 §9.1.5、§10 第 44/47 条）。

⚠️ **表只做候选，绝不做白名单**（规范 §9.1.3）：查不到某个类型时返回 None，
GUI 要**照样显示**存档里的未知 type，只提示不拦截。
否则内置表过期一次，玩家就完全改不了对应的单位。

性能
----
* **列目录**很便宜（实测 listdir 1.5 ms），**解析 YAML 很贵**
  （实测 `entity_types/` 全量解析 1072 ms）⇒ 本模块**按需单文件读取 + 缓存**，
  绝不启动时全量解析。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import yamlio
from .paths import CorePaths

__all__ = ["Catalog", "UnitType", "TypeKind"]

#: 类型表的种类 → `entity_types/` 下的子目录名
TypeKind = str

ENTITY_DIRS = {
    "unit_types": "unit_types",
    "specialists": "specialists",
    "cards": "cards",
    "hq_types": "hq_types",
    "generals": "generals",
}


@dataclass(frozen=True)
class UnitType:
    """一个单位类型的定义（来自 `unit_types/<名>.yml`）。"""

    name: str
    faction: str | None = None
    nationality: str | None = None
    movement: str | None = None
    attack: int | None = None
    defense: int | None = None
    armor: int | None = None
    #: 战力上限 —— **上限在类型定义里，不在存档里**（规范 §5.3）
    max_st: int | None = None
    #: 特种兵上限；None 表示该类型没有这个字段
    max_spec: int | None = None
    #: 装备类别（`null` = 无装备）；决定"战力阶梯"用哪张图
    equipment: str | None = None
    #: 装备档位（0 = 无装备；实测 base 包只有 1 / 2 两种）
    equipment_q: int | None = None
    name_brief: str | None = None

    @property
    def spec_cap(self) -> int:
        """能挂几个特种兵 = `min(3, max_spec or 3)`（规范 §5.3）。"""
        return min(3, self.max_spec if self.max_spec is not None else 3)

    def step_icon(self) -> str:
        """这个单位类型的"战力阶梯"图标文件名（不含目录、不含扩展名）。

        规则来自游戏自己的 `hq_ctrl.pyc::HQCtrl._fp_helper`（字节码实证）：

        ```python
        'steps/step{}'.format('_' + equipment + '_' + equipment_q if equipment else '')
        ```

        ⇒ 无装备 → `step`；有装备 → `step_<装备>_<档位>`。

        ⚠️ 游戏里是**先判 `equipment` 真假**，再看 `equipment_q`；
        `equipment` 为 null 时 `equipment_q` 恒为 0，不会拼出 `step__0`。

        兜底：拼不出来的组合一律回落到 `step`（GUI 侧不该因此崩）。
        """
        if self.equipment:
            return f"step_{self.equipment}_{self.equipment_q}"
        return "step"


def _as_int(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


class Catalog:
    """游戏包的只读目录。

    用法：
    ```python
    cat = Catalog()
    cat.unit_type("us_inf_42").max_st      # 6
    cat.unit_type_names()                   # 627 个名字（只列目录，不解析）
    cat.fronts("west")                      # ['france', 'italy']
    ```
    """

    def __init__(self, paths: CorePaths | None = None):
        self.paths = paths or CorePaths.discover()
        self._indexes: dict[str, dict[str, Path]] = {}
        self._types: dict[tuple[str, str], dict] = {}
        self._fronts: dict[str, list[str]] = {}

    # ---- 索引 ----

    def _index(self, kind: TypeKind) -> dict[str, Path]:
        """{类型名: 文件路径}，按「用户包 → 游戏包」优先级，先到先得。"""
        idx = self._indexes.get(kind)
        if idx is not None:
            return idx
        idx = {}
        sub = ENTITY_DIRS.get(kind)
        if sub:
            for pkg in self.paths.packages():
                d = pkg / "data" / "entity_types" / sub
                if not d.is_dir():
                    continue
                try:
                    names = list(d.glob("*.yml"))
                except OSError:
                    continue
                for p in names:
                    name = p.stem
                    if name not in idx:      # 先到先得 ⇒ 用户包优先
                        idx[name] = p
        self._indexes[kind] = idx
        return idx

    def _load(self, kind: TypeKind, name: str) -> dict | None:
        key = (kind, name)
        if key in self._types:
            return self._types[key]
        path = self._index(kind).get(name)
        data: dict | None = None
        if path is not None:
            try:
                loaded = yamlio.load(path.read_bytes())
                data = loaded if isinstance(loaded, dict) else None
            except Exception:
                data = None
        self._types[key] = data
        return data

    # ---- 类型查询 ----

    def unit_type(self, name: str) -> UnitType | None:
        """查一个单位类型；查不到返回 None（**不是错误**）。"""
        if not name:
            return None
        d = self._load("unit_types", name)
        if d is None:
            return None
        return UnitType(
            name=name,
            faction=d.get("faction"),
            nationality=d.get("nationality"),
            movement=d.get("movement"),
            attack=_as_int(d.get("attack")),
            defense=_as_int(d.get("defense")),
            armor=_as_int(d.get("armor")),
            max_st=_as_int(d.get("max_st")),
            max_spec=_as_int(d.get("max_spec")),
            equipment=d.get("equipment"),
            equipment_q=_as_int(d.get("equipment_q")),
            name_brief=d.get("name_brief"),
        )

    def max_st(self, type_name: str) -> int | None:
        """单位的战力上限；类型未知返回 None（**不要硬编码 6/7**）。"""
        t = self.unit_type(type_name)
        return t.max_st if t else None

    def spec_cap(self, type_name: str) -> int:
        """特种兵上限 = `min(3, max_spec or 3)`；类型未知按 3 处理。"""
        t = self.unit_type(type_name)
        return t.spec_cap if t else 3

    def step_icon(self, type_name: str) -> str:
        """单位的"战力阶梯"图标文件名（不含目录、不含扩展名）。

        类型未知回落到 `step`（GUI 侧不该因此崩）。
        """
        t = self.unit_type(type_name)
        return t.step_icon() if t else "step"

    def unit_type_names(self) -> list[str]:
        """全部单位类型名（只列目录，不解析 YAML）。"""
        return sorted(self._index("unit_types"))

    def spec_type_names(self) -> list[str]:
        """全部特种兵类型名。"""
        return sorted(self._index("specialists"))

    def card_type_names(self) -> list[str]:
        """全部卡牌类型名。"""
        return sorted(self._index("cards"))

    def hq_type_names(self) -> list[str]:
        """全部总部类型名。"""
        return sorted(self._index("hq_types"))

    def general_names(self) -> list[str]:
        """全部将领 id。"""
        return sorted(self._index("generals"))

    def has_unit_type(self, name: str) -> bool:
        return name in self._index("unit_types")

    def card_type(self, name: str) -> dict | None:
        """卡牌类型定义（`cost` / `has_unit` / `theater_asset` …）。"""
        return self._load("cards", name)

    def has_spec_type(self, name: str) -> bool:
        return name in self._index("specialists")

    def has_card_type(self, name: str) -> bool:
        return name in self._index("cards")

    # ---- 战役与战线 ----

    def campaign_ids(self) -> list[str]:
        """全部战役包 id（`west` / `blitzkrieg` / …）。"""
        out: list[str] = []
        for pkg in self.paths.packages():
            d = pkg / "data" / "campaigns"
            if not d.is_dir():
                continue
            try:
                entries = sorted(d.glob("*.usc"))
            except OSError:
                continue
            for p in entries:
                if p.stem not in out:
                    out.append(p.stem)
        return out

    def campaign_dir(self, campaign_id: str) -> Path | None:
        """战役包目录 `<包>/data/campaigns/<id>.usc`；用户包优先。"""
        for pkg in self.paths.packages():
            p = pkg / "data" / "campaigns" / f"{campaign_id}.usc"
            if p.is_dir():
                return p
        return None

    def fronts(self, campaign_id: str) -> list[str]:
        """该战役包里的战线名（`fronts/` 下的子目录）。

        ⚠️ **fronts 是每个战役包各有一份**，不是全局的。
        存档 `store.yml` 的顶层键必须是它的**子集**（当前已激活的战线），
        **不要凭空新建战线键**（规范 §10 第 12 条）。
        """
        if campaign_id in self._fronts:
            return self._fronts[campaign_id]
        out: list[str] = []
        cdir = self.campaign_dir(campaign_id)
        if cdir is not None:
            fdir = cdir / "fronts"
            if fdir.is_dir():
                try:
                    out = sorted(p.name for p in fdir.iterdir() if p.is_dir())
                except OSError:
                    out = []
        self._fronts[campaign_id] = out
        return out

    def store_defaults(self, campaign_id: str, front: str,
                       conference: str) -> list[dict]:
        """战役包默认商店清单 `fronts/<战线>/conferences/<会议>.yml`。

        ⚠️ **只是参考** —— 存档里的价格可能与包默认不同（实测 277 条），
        **不要拿它去"纠正"存档**（规范 §4.6.1、§10 第 37 条）。
        """
        cdir = self.campaign_dir(campaign_id)
        if cdir is None:
            return []
        p = cdir / "fronts" / front / "conferences" / f"{conference}.yml"
        if not p.is_file():
            return []
        try:
            data = yamlio.load(p.read_bytes())
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        store = data.get("store")
        return [e for e in store if isinstance(e, dict)] if isinstance(store, list) else []

    # ---- 批量预热 ----

    def warm(self, kind: TypeKind, names) -> int:
        """预先加载一批类型定义（GUI 一次要显示几十上百个单位时用）。

        返回实际加载成功的数量。加载不出来的（类型未知）**不报错**。
        """
        n = 0
        for name in names:
            if self._load(kind, name) is not None:
                n += 1
        return n


# ---------------------------------------------------------------- 模块级便捷函数
#
# 规范 §0.2 的接口形态是 `catalog.units()` / `catalog.card_types()` … ——
# 这里用一份**惰性创建的单例**支撑它。GUI 直接 `from save_modifier_core import catalog`。

_default: Catalog | None = None


def default() -> Catalog:
    """全局默认目录实例（第一次调用时创建）。"""
    global _default
    if _default is None:
        _default = Catalog()
    return _default


def units() -> list[str]:
    """全部单位类型名。"""
    return default().unit_type_names()


def hq_types() -> list[str]:
    """全部总部类型名。"""
    return default().hq_type_names()


def card_types() -> list[str]:
    """全部卡牌类型名。"""
    return default().card_type_names()


def spec_types() -> list[str]:
    """全部特种兵类型名。"""
    return default().spec_type_names()


def fronts(campaign_id: str) -> list[str]:
    """某战役包里的战线名。"""
    return default().fronts(campaign_id)


def store_defaults(campaign_id: str, front: str, conference: str) -> list[dict]:
    """战役包默认商店清单（**仅供参考**，不要拿它纠正存档）。"""
    return default().store_defaults(campaign_id, front, conference)
