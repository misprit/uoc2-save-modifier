"""目录：游戏包里的类型表与战线清单（**只读**）。

数据源
------
```
<包>/data/entity_types/unit_types/<类型名>.yml     627 个  → max_st / max_spec / equipment / equipment_q
<包>/data/entity_types/specialists/<类型名>.yml     375 个  → 攻防装甲火力 / 国籍 / 阵营 / flags
<包>/data/entity_types/cards/<类型名>.yml            39 个
<包>/data/entity_types/hq_types/<类型名>.yml        213 个
<包>/data/entity_types/generals/<类型名>.yml        304 个
<包>/data/entity_types/nationalities.yml             40 个  → faction / parent_nationality
<包>/data/entity_types/nationalities_2.yml           （mod 用的空模板，base 里是 {}）
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

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import yamlio
from .paths import CorePaths

__all__ = ["Catalog", "UnitType", "SpecialistType", "Nationality",
           "CardWhitelist", "TypeKind"]

#: 类型表的种类 → `entity_types/` 下的子目录名
TypeKind = str

ENTITY_DIRS = {
    "unit_types": "unit_types",
    "specialists": "specialists",
    "cards": "cards",
    "hq_types": "hq_types",
    "generals": "generals",
}

#: 国籍表是**文件**（不是目录）⇒ 不走 `ENTITY_DIRS` 那套目录索引
#: base 里 `nationalities.yml` 有 40 个；`nationalities_2.yml` 是给 mod 用的空模板
NATIONALITY_FILES = ("nationalities.yml", "nationalities_2.yml")

#: 抽卡的基础权重表（`card_types.pyc::card_meta_types_base_probabilities`，`e158` 实证）
#:
#: 15 分 = 常见；6 分 = 中等；3 分 = 稀有。
#: ⚠️ 这张表**不在游戏包的数据文件里**（在字节码常量里），所以只能写死一份，
#: 但它有字节码依据 —— 会议覆盖 / 前线缩放都是在这张表**之上**做的（`e158`）。
BASE_CARD_WEIGHTS: dict[str, float] = {
    "truck": 15, "air_attack": 15, "long_range_recon": 15,
    "air_supply": 6, "naval_bombardment": 6, "saturation_strike": 6,
    "espionage": 6, "flying_artillery": 6,
    "tactical_naval_assault": 3, "tactical_para": 3, "divisional_para": 3,
    "sabotage": 3, "store": 3, "precision_bombing": 3, "air_fleet": 3,
    "power_hq": 3, "arty_prep": 3, "air_hq": 3,
}

#: 商店的两个子商店（`store.yml` = `{战线: {store: [...], elite_store: [...]}}`）
STORE_SUBS = ("store", "elite_store")

#: 类型 yml **缺 `max_st` 字段**时的兜底值 —— 与游戏自己的 schema 默认值一致。
#:
#: 字节码实证（`state/entity_types/unit_types.pyc::_unit_type_schema`）：
#:     Required('max_st', default=7) : All(int, Range(min=1, max=7))
#: 游戏包 `_packages/base/entity_types/unit_types/`（`_packages/base/data/...`）
#: 的 627 个类型里，**178 个的 yml 没写 `max_st`** ⇒ 游戏按 **7** 处理。
#: 修改器若直接读 yml 拿到 None ⇒ 单位显示「上限 —」、血量条没有上限格
#: （实测 `Stalingrad.usg` 的 354 个单位里 **266 个** 受影响）。
UNIT_TYPE_MAX_ST_DEFAULT = 7

#: 战区资产**全集**（U45 字节码取证 —— `lib/uoc2/state/constants.pyc` 第 61 行）：
#:
#: ```python
#: theater_asset_types = ('air_supply', 'air_attack', 'saturation_strike',
#:                         'long_range_recon', 'naval_bombardment',
#:                         'flying_artillery', 'precision_bombing')
#: ```
#:
#: ⚠️ 这张表**不在游戏包的数据文件里**（在字节码常量里）⇒ 只能写死一份，
#: 但有字节码依据 —— 与 `BASE_CARD_WEIGHTS` 同一个做法。
#:
#: 游戏的 `scenario_data_validation.theater_asset_dict` 是
#: `Required('asset'): In(theater_asset_types)` ⇒ **存档里只认这 7 个**。
#:
#: ⚠️ **卡牌里的 `theater_asset` 是另一套名单**（`entity_types/card_types.pyc`
#: 的 `_theater_asset_types` = 10 个一次性能力 sabotage / espionage /
#: tactical_para / divisional_para / maquis / maskirovka / radio_silence /
#: clear_rubble / tactical_naval_assault / divisional_naval_assault
#: **并上**这 7 个）—— 那 10 个**不能**进战区资产列表（游戏 schema 会拒）。
THEATER_ASSET_TYPES = (
    "air_supply", "air_attack", "saturation_strike", "long_range_recon",
    "naval_bombardment", "flying_artillery", "precision_bombing",
)


@dataclass(frozen=True)
class UnitType:
    """一个单位类型的定义（来自 `unit_types/<名>.yml`）。"""

    name: str
    faction: str | None = None
    nationality: str | None = None
    movement: str | None = None
    #: **基础移动力**（类型表里的 `move`）—— U87：控制区锁定会把存档里的
    #: `mp` 清零，要恢复就得知道这个类型的满值是多少。
    #: ⚠️ 游戏界面显示的移动力是**每回合重算**的（`apply_mp_ap`：有补给就给满），
    #: 所以界面上"有 5 点移动力"而存档里 `mp` 可能是 0（被控制区清过）。
    move: int | None = None
    attack: int | None = None
    defense: int | None = None
    armor: int | None = None
    #: **防御装甲**（类型表里的 `armor_def`）—— U92：
    #: 步兵也有 `armor: 1`，但那是**被打时减伤**的防御装甲（`armor_def: true`），
    #: **不是**能反冲锋的机动装甲 ⇒ 决定「反击」能不能挂。
    armor_def: bool | None = None
    #: 战力上限 —— **上限在类型定义里，不在存档里**（规范 §5.3）
    #: ⚠️ U60：类型 yml **没写** `max_st` 时，游戏按 schema 默认 **7** 处理
    #: （`unit_types.pyc::_unit_type_schema`: `Required('max_st', default=7)`）
    #: ⇒ 这里也填 7，**不是 None**（None 只表示「这个类型根本查不到」）。
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

    @property
    def armor_mobile(self) -> bool:
        """这个类型是不是**装甲机动单位**（U92 · 字节码实证）。

        游戏原文（`state/entities_view/unit.py:45`）：

        ```python
        armor_mobile = property(lambda self: self.armor
                                         and not self.armor_def
                                         and self.movement == 'mobile')
        ```

        ⇒ **反击**（`elastic_defense`）只允许这种单位挂
        （`can_make_elastic_defense` 的**第一个条件**就是它，U92）；
        「死守」「后卫部队」**没有**这条约束。

        ⚠️ 步兵虽然有 `armor: 1`，但 `armor_def: true`（防御装甲）、
        且 `movement` 是 `infantry` ⇒ **不算**装甲机动单位。
        """
        return bool(self.armor) and not self.armor_def \
            and self.movement == "mobile"

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


@dataclass(frozen=True)
class SpecialistType:
    """一个特种兵类型的定义（来自 `specialists/<名>.yml`）。

    ⚠️ **数值只在游戏包里，不在存档里**（`e156` 实证）——
    存档 `units.yml` 的 `specs[]` 只有 `{active, captured, idx, type}`。
    ⇒ 改数值 = 改游戏包（mod 范畴）⇒ **本工具只读**。
    """

    name: str
    faction: str | None = None
    nationality: str | None = None
    name_brief: str | None = None
    name_full: str | None = None
    attack: int | None = None
    defense: int | None = None
    armor: int | None = None
    artillery: int | None = None
    att_idx: int | None = None
    dfe_idx: int | None = None
    #: 特殊类型旗标（`at` / `arty` / `towed` / `engineers` / `recon` / `ski` / `lci` / `special`）
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Nationality:
    """一个国籍的定义（来自 `nationalities.yml` / `nationalities_2.yml`）。"""

    name: str
    faction: str | None = None
    name_brief: str | None = None
    short: str | None = None
    #: 父国籍 —— 游戏判定「可挂特种兵」时会用到（`e162` 字节码实证）
    parent_nationality: str | None = None


@dataclass(frozen=True)
class CardWhitelist:
    """「本存档本会议，卡牌商店本来就能生成哪几张卡」。

    由 `Catalog.card_whitelist(save)` 算出 —— 逐条复刻游戏自己的
    `Campaign.get_cards_probabilities`（`e160` 实证）。

    **这是"当前存档 + 当前会议"的状态** —— 换战役、换会议、玩到下一场，
    白名单都会变 ⇒ **每次开卡牌页重算，不要缓存**（规范 §7.5.1）。
    """

    #: 可上架的卡牌类型名
    allowed: frozenset[str] = frozenset()
    #: 被屏蔽的卡牌 → **屏蔽原因**（中文，直接显示给玩家）
    blocked: Mapping[str, str] = field(default_factory=dict)
    #: 玩家阵营（存档 `document/main.yml`）
    player_faction: str | None = None
    #: 当前会议 id
    conference: str | None = None
    #: 当前战役 id
    campaign_id: str | None = None
    #: 本次会议的 meta_type 概率表（基础表 + 会议覆盖 + 前线缩放）
    probabilities: Mapping[str, float] = field(default_factory=dict)

    def is_allowed(self, card_type: str) -> bool:
        """这张卡能不能上架。"""
        return card_type in self.allowed

    def reason(self, card_type: str) -> str | None:
        """这张卡为什么被屏蔽；没被屏蔽返回 None。"""
        return self.blocked.get(card_type)

    def allowed_types(self) -> list[str]:
        """可上架的卡牌名（排序）。"""
        return sorted(self.allowed)

    def blocked_types(self) -> list[str]:
        """被屏蔽的卡牌名（排序）。"""
        return sorted(self.blocked)




class _PkgSource:
    """一个「包来源」：**目录** 或 **zip** 里的一个包（U73）。

    * `kind` —— `"dir"` / `"zip"`；
    * `path` —— 目录 或 zip 路径；
    * `prefix` —— **包内**路径前缀（`""` 表示包根就是容器本身）。

    创意工坊的 mod 有三种形态，这里统一成一套读法：
    裸文件（普通 mod）、`_packages/<包名>/`、压缩包。
    """

    __slots__ = ("kind", "path", "prefix")

    def __init__(self, kind: str, path, prefix: str = ""):
        self.kind = kind
        self.path = Path(path)
        self.prefix = prefix or ""

    def read_bytes(self, rel: str):
        """读包里一个文件（相对**包根**）⇒ 读不到返回 None。"""
        if self.kind == "dir":
            try:
                return (self.path / (self.prefix + rel)).read_bytes()
            except OSError:
                return None
        try:
            with zipfile.ZipFile(self.path, "r") as zf:
                return zf.read(self.prefix + rel)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None

    def names(self, sub: str) -> list:
        """包里某个子目录下的 `.yml` 文件名（不含目录部分）。"""
        pre = self.prefix + sub
        out: list = []
        if self.kind == "dir":
            base = self.path / (self.prefix + sub)
            try:
                for x in sorted(base.iterdir()):
                    if x.is_file() and x.name.endswith(".yml"):
                        out.append(x.name)
            except OSError:
                return out
            return out
        try:
            with zipfile.ZipFile(self.path, "r") as zf:
                for m in zf.namelist():
                    if m.startswith(pre) and m.endswith(".yml"):
                        rest = m[len(pre):]
                        if rest and "/" not in rest:
                            out.append(rest)
        except (OSError, zipfile.BadZipFile):
            return out
        return out


class _PkgFile:
    """包里的一个文件（目录或 zip）—— 接口和 `Path` 一样有 `read_bytes()`。"""

    __slots__ = ("src", "rel")

    def __init__(self, src: _PkgSource, rel: str):
        self.src = src
        self.rel = rel

    @property
    def name(self) -> str:
        return self.rel.rsplit("/", 1)[-1]

    def read_bytes(self):
        return self.src.read_bytes(self.rel)

    def __repr__(self) -> str:                      # pragma: no cover
        return "<pkg %s!%s>" % (self.src.path.name, self.rel)


def _pkg_type_members(src: _PkgSource, kind: str) -> dict:
    """包里的 `data/entity_types/<kind>/*.yml` ⇒ {类型名: 文件}。"""
    out: dict = {}
    sub = ENTITY_DIRS.get(kind)
    if not sub:
        return out
    rel_dir = "data/entity_types/%s/" % sub
    for name in src.names(rel_dir):
        if not name.endswith(".yml"):
            continue
        key = name[:-4]
        if key and key not in out:
            out[key] = _PkgFile(src, rel_dir + name)
    return out


def _pkg_nationality_members(src: _PkgSource) -> dict:
    """包里的国籍表（`nationalities.yml` / `nationalities_2.yml`）。"""
    out: dict = {}
    for fn in NATIONALITY_FILES:
        if fn in src.names("data/entity_types/"):
            out[fn] = _PkgFile(src, "data/entity_types/" + fn)
    return out

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
        self._ws_sources: list | None = None
        self._fronts: dict[str, list[str]] = {}
        self._nats: dict[str, dict] | None = None
        self._camp_pool: dict[str, set[str]] = {}

    # ---- 索引 ----

    @property
    def workshop_sources(self) -> list:
        """Steam 创意工坊里的 mod 包（**zip 里还没解压的也算**）—— U71。"""
        if self._ws_sources is None:
            try:
                self._ws_sources = [
                    _PkgSource(w.get("kind", "dir"), w["path"], w.get("prefix", ""))
                    for w in self.paths.workshop_packages()]
            except Exception:
                self._ws_sources = []
        return self._ws_sources

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
            # U71：**Steam 创意工坊里的 mod**（还没解压进游戏目录的也算）
            # ⇒ 它们的 `data/entity_types/…` 也要能读到。
            # ⚠️ 优先级排在磁盘包**之后** ⇒ 游戏真正在用的数据永远优先，
            #    创意工坊里没安装的 mod 只是「补充参考」。
            for src in self.workshop_sources:
                for name, member in _pkg_type_members(src, kind).items():
                    if name not in idx:
                        idx[name] = member
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
            move=_as_int(d.get("move")),
            attack=_as_int(d.get("attack")),
            defense=_as_int(d.get("defense")),
            armor=_as_int(d.get("armor")),
            armor_def=d.get("armor_def"),      # U92：防御装甲（决定能不能挂反击）
            # U60：缺 max_st 字段 ⇒ 用游戏 schema 的默认值 7（**不是 None**）
            max_st=(_as_int(d.get("max_st"))
                   if d.get("max_st") is not None else UNIT_TYPE_MAX_ST_DEFAULT),
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

    def armor_mobile(self, type_name: str) -> bool:
        """单位类型是不是**装甲机动单位**（「反击」的硬约束，U92）。

        类型查不到 ⇒ False（宁可不许挂反击，也不给非装甲单位开口子）。
        """
        t = self.unit_type(type_name)
        return bool(t and t.armor_mobile)

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

    # ---- 特种兵 / 国籍 ----

    def spec_type(self, name: str) -> SpecialistType | None:
        """查一个特种兵类型；查不到返回 None（**不是错误**）。"""
        if not name:
            return None
        d = self._load("specialists", name)
        if d is None:
            return None
        flags = d.get("flags") or []
        return SpecialistType(
            name=name,
            faction=d.get("faction"),
            nationality=d.get("nationality"),
            name_brief=d.get("name_brief"),
            name_full=d.get("name_full"),
            attack=_as_int(d.get("attack")),
            defense=_as_int(d.get("defense")),
            armor=_as_int(d.get("armor")),
            artillery=_as_int(d.get("artillery")),
            att_idx=_as_int(d.get("att_idx")),
            dfe_idx=_as_int(d.get("dfe_idx")),
            flags=tuple(str(f) for f in flags),
        )

    def _nationalities(self) -> dict[str, dict]:
        """国籍表（`nationalities.yml` + `nationalities_2.yml`）。

        ⚠️ **这两个是文件，不是目录** ⇒ 不走 `_index` 那套目录索引。
        用户包优先（与 `_index` 同样的「先到先得」语义）。
        base 里的 `nationalities_2.yml` 是**空模板**（`{}`），给 mod 用的。
        """
        if self._nats is not None:
            return self._nats
        out: dict[str, dict] = {}
        for pkg in self.paths.packages():
            d = pkg / "data" / "entity_types"
            for fn in NATIONALITY_FILES:
                p = d / fn
                if not p.is_file():
                    continue
                try:
                    data = yamlio.load(p.read_bytes())
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                for k, v in data.items():
                    if isinstance(v, dict) and k not in out:
                        out[k] = v
        # U71：创意工坊 mod（没解压进游戏目录的）里的国籍表也读进来
        for src in self.workshop_sources:
            for fn, member in _pkg_nationality_members(src).items():
                try:
                    data = yamlio.load(member.read_bytes())
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                for k, v in data.items():
                    if isinstance(v, dict) and k not in out:
                        out[k] = v
        self._nats = out
        return out

    def nationality(self, name: str) -> Nationality | None:
        """查一个国籍；查不到返回 None。"""
        if not name:
            return None
        d = self._nationalities().get(name)
        if d is None:
            return None
        return Nationality(
            name=name,
            faction=d.get("faction"),
            name_brief=d.get("name_brief"),
            short=d.get("short"),
            parent_nationality=d.get("parent_nationality"),
        )

    def nationality_names(self) -> list[str]:
        """全部国籍名（40 个）。"""
        return sorted(self._nationalities())

    def spec_can_attach(self, spec_name: str, unit_type_name: str,
                        captured: bool = False) -> bool:
        """这个特种兵能不能挂到这个单位类型上。

        **逐条复刻游戏自己的判定**（`uoc2/state/entities/unit.pyc::UnitState`
        的 `_can_add_specialist_no_len`，`e162` 字节码实证）：

        ```python
        if not specialist: return False
        if not captured:
            if self._type.faction != specialist.faction: return False
            if self._type.nationality != specialist.nationality:
                nat = nationality_types.get_type(self._type.nationality)
                if nat.parent_nationality != specialist.nationality: return False
        return True
        ```

        ⇒ 阵营必须相同；国籍相同，**或单位国籍的 `parent_nationality` == 特种兵国籍**。
        `captured=True`（被俘获的牌）**跳过**这两项检查。

        ⚠️ 槽位容量（`len(specs) < max_spec`）是**另一个**判定，不在这里。
        """
        spec = self.spec_type(spec_name)
        unit = self.unit_type(unit_type_name)
        if spec is None or unit is None:
            return False
        if captured:
            return True
        if unit.faction != spec.faction:
            return False
        if unit.nationality != spec.nationality:
            nat = self.nationality(unit.nationality or "")
            if nat is None or nat.parent_nationality != spec.nationality:
                return False
        return True

    def campaign_specialist_pool(self, campaign_id: str | None) -> set[str]:
        """该战役的「默认特种兵集合」。

        ```
        战役默认池 = { 该战役 所有战线 × 所有会议 的商店 spec 条目 }
                   ∪ { 该战役 所有场景 units.yml 里 specs[].type 出现过的 }
        ```

        **为什么是这个口径**（`e163` 实测，15 个战役全跑）：

        * 每个战役的商店**只卖玩家一方阵营**（allies / axis / soviet 各自纯净）⇒ 天然是「我方」；
        * 商店集合**年代自洽**（blitzkrieg 只有 `_39/_40/_42`，desert 只有 `_42`）;
        * **只用商店会漏 113 种**「游戏自己在该战役场景里挂过」的特种兵
          （`us_spec_42` / `ff_recon_42` / `ger_at_40` …）
          ⇒ 加上场景集合后**漏 0 种**（零假阴性）。

        ⚠️ **找不到战役包返回空集合**（不是错误）⇒ 调用方要自己走兜底（见
        `specialist_candidates`）。

        ⚠️ **实测耗时**：base/west 扫 19 个会议 + 44 个场景 units.yml ≈ **170 ms**
        （会议 20 ms + 场景 146 ms）⇒ **按战役缓存**，别在滚动路径上反复调。
        """
        if not campaign_id:
            return set()
        if campaign_id in self._camp_pool:
            return self._camp_pool[campaign_id]
        cdir = self.campaign_dir(campaign_id)
        pool: set[str] = set()
        if cdir is not None:
            # ① 商店：所有战线 × 所有会议的 store / elite_store
            for cf in sorted(cdir.rglob("conferences/*.yml")):
                try:
                    data = yamlio.load(cf.read_bytes())
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                for sub in STORE_SUBS:
                    for e in (data.get(sub) or []):
                        if isinstance(e, dict) and e.get("spec"):
                            pool.add(str(e["spec"]))
            # ② 场景：游戏自己在 units.yml 里挂过的 specs[].type
            for uf in sorted(cdir.rglob("scenarios/*/units.yml")):
                try:
                    data = yamlio.load(uf.read_bytes())
                except Exception:
                    continue
                if not isinstance(data, list):
                    continue
                for u in data:
                    if not isinstance(u, dict):
                        continue
                    for s in (u.get("specs") or []):
                        if isinstance(s, dict) and s.get("type"):
                            pool.add(str(s["type"]))
        self._camp_pool[campaign_id] = pool
        return pool

    def specialist_candidates(self, unit_type_name: str,
                              campaign_id: str | None = None,
                              captured: bool = False) -> tuple[list[str], str]:
        """某个单位类型能挂的特种兵候选 + 口径标签。

        **口径**（U10 拍板，2026-11-18）：

        ```
        最终候选 = 战役默认池 ∩ 游戏规则可挂集合
        ```

        **三层兜底**（用户拍板）：

        | 情形 | 结果 | 标签 |
        |---|---|---|
        | 正常 | 战役默认池 ∩ 规则 | `campaign` |
        | 找不到战役包 | 放宽成「仅规则」 | `no_campaign` |
        | 某个单位交集为空（敌国单位） | 放宽成「仅规则」 | `empty_intersection` |

        返回 `(候选类型名列表, 标签)`；标签给 GUI 决定怎么提示玩家。
        候选**按类型名排序**（GUI 再按中文名排）。
        """
        pool = self.campaign_specialist_pool(campaign_id)
        rule_ok = [n for n in self.spec_type_names()
                   if self.spec_can_attach(n, unit_type_name, captured)]
        if not pool:
            return rule_ok, "no_campaign"
        inter = [n for n in rule_ok if n in pool]
        if not inter:
            return rule_ok, "empty_intersection"
        return inter, "campaign"

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

    def store_sub_lists(self, campaign_id: str, front: str,
                        conference: str) -> dict[str, list[dict]]:
        """战役包默认商店的**两个子商店**（`store` / `elite_store`）。"""
        cdir = self.campaign_dir(campaign_id)
        if cdir is None:
            return {sub: [] for sub in STORE_SUBS}
        p = cdir / "fronts" / front / "conferences" / f"{conference}.yml"
        out: dict[str, list[dict]] = {sub: [] for sub in STORE_SUBS}
        if not p.is_file():
            return out
        try:
            data = yamlio.load(p.read_bytes())
        except Exception:
            return out
        if not isinstance(data, dict):
            return out
        for sub in STORE_SUBS:
            items = data.get(sub)
            if isinstance(items, list):
                out[sub] = [e for e in items if isinstance(e, dict)]
        return out

    def store_item_universe(self, campaign_id: str | None,
                            conference: str | None) -> dict[str, set[str]]:
        """这个战役/会议里，游戏自己会卖哪些**兵种 / 国籍 / 特种兵**。

        来源 = 战役包该会议**所有战线**的默认商店清单（`e154` 实证：
        489 条默认条目，`equipment` 只有 `infantry` / `armor`）。

        ⚠️ 这是**新上架商品**的校验依据 —— 游戏 schema 是枚举校验，
        填了游戏没有的东西会被游戏拒收（规范 §7.6）。
        特种兵另外用 `spec_type_names()` 兜底（375 个）。
        """
        equipments: set[str] = set()
        nationalities: set[str] = set()
        if campaign_id and conference:
            for front in self.fronts(campaign_id):
                for sub in STORE_SUBS:
                    for e in self.store_sub_lists(campaign_id, front, conference)[sub]:
                        if e.get("equipment"):
                            equipments.add(str(e["equipment"]))
                        if e.get("nationality"):
                            nationalities.add(str(e["nationality"]))
        specs = set(self.spec_type_names())
        return {"equipment": equipments, "nationality": nationalities,
                "spec": specs}

    # ---- 卡牌商店白名单 ----

    def card_probabilities(self, save, conference: str | None = None,
                           campaign_id: str | None = None) -> dict[str, float]:
        """本会议的 meta_type 概率表。

        权重链（`e158` 字节码实证）：

        1. **基础表** —— `BASE_CARD_WEIGHTS`（15 / 6 / 3 三档）；
        2. **会议覆盖** —— `document/conferences/<会议>.yml` 的 `card_probabilities`；
        3. **前线缩放** —— `document/fronts/<战线>/conferences/<会议>.yml`
           的 `card_probability_scales`（空 dict = 不覆盖）。

        ⚠️ **权威源是存档的 L5 文档**（游戏把 campaign_doc 从存档里加载），
        存档里没有才退回游戏包。
        """
        prob = dict(BASE_CARD_WEIGHTS)
        if not conference:
            return prob

        over: dict = {}
        scales: dict = {}
        for n in save.list_names():
            if not n.endswith(".yml"):
                continue
            if n == f"document/conferences/{conference}.yml":
                d = save.read_yaml(n, None)
                if isinstance(d, dict):
                    over = d.get("card_probabilities") or {}
            elif n.endswith(f"/conferences/{conference}.yml"):
                d = save.read_yaml(n, None)
                if isinstance(d, dict):
                    for c, v in (d.get("card_probability_scales") or {}).items():
                        scales.setdefault(c, v)
        if not over and not scales and campaign_id:
            cdir = self.campaign_dir(campaign_id)
            if cdir is not None and cdir.is_dir():
                for f in sorted(cdir.rglob(f"conferences/{conference}.yml")):
                    try:
                        d = yamlio.load(f.read_bytes())
                    except Exception:
                        continue
                    if not isinstance(d, dict):
                        continue
                    rel = f.relative_to(cdir).as_posix()
                    if rel == f"conferences/{conference}.yml":
                        over = d.get("card_probabilities") or {}
                    elif rel.endswith(f"/conferences/{conference}.yml"):
                        for c, v in (d.get("card_probability_scales") or {}).items():
                            scales.setdefault(c, v)
        prob.update(over)
        for c, v in scales.items():
            prob[c] = prob.get(c, 0) * v
        return prob

    def card_whitelist(self, save) -> CardWhitelist:
        """算出「本存档本会议，卡牌商店本来就能自然生成哪几张卡」。

        逐条复刻 `Campaign.get_cards_probabilities`（`e160` 实证）：

        ```
        可上架 = { ct : ∃ meta_type, p(meta_type) > 0,
                     ct.faction == 玩家阵营,
                     ct.meta_type == meta_type,
                     (¬ct.has_unit)                        ← 不召唤单位 ⇒ 无条件可上架
                     OR ( ct ∈ card_type_units            ← 本战役登记过 ⇒ 有单位可召唤
                          ∧ ct ∉ used_card_types_with_unit
                          ∧ ct ∉ 当前手牌
                          ∧ (预留单位不存在 OR 未阵亡) ) }
        ```

        ⚠️ **每次调用都重算** —— 白名单是"当前存档 + 当前会议"的状态（规范 §7.5.1）。
        """
        doc = save.read_yaml("document/main.yml", None)
        doc = doc if isinstance(doc, dict) else {}
        main_ = save.root_main()
        in_state = main_.get("in_state") or {}

        player_faction = doc.get("player_faction")
        ct_units = {}
        for e in (doc.get("card_type_units") or []):
            if isinstance(e, dict) and e.get("card_type"):
                ct_units[e["card_type"]] = e
        used = main_.get("used_card_types_with_unit") or {}
        campaign_id = main_.get("campaign_id")
        conference = in_state.get("conference")

        prob = self.card_probabilities(save, conference, campaign_id)

        hand_types = {c.get("card_type") for c in save.root_cards()}
        save_units = {u.get("id"): u for u in save.root_units()
                      if isinstance(u, dict)}

        allowed: set[str] = set()
        blocked: dict[str, str] = {}
        for name in self.card_type_names():
            d = self.card_type(name) or {}
            mt = d.get("meta_type")
            fac = d.get("faction")
            reasons: list[str] = []
            if fac != player_faction:
                reasons.append(f"阵营 {fac} ≠ 玩家 {player_faction}")
            elif prob.get(mt, 0) <= 0:
                reasons.append(f"本次会议抽不到（{mt} 概率 ≤ 0）")
            elif d.get("has_unit"):
                if name in used:
                    reasons.append("已召唤过（used_card_types_with_unit）")
                elif name in hand_types:
                    reasons.append("手牌里已有同类型")
                elif name not in ct_units:
                    reasons.append("本战役没有这张卡可召唤的单位")
                else:
                    unit_id = ct_units[name].get("unit_id")
                    unit = save_units.get(unit_id)
                    if unit is not None and unit.get("kia"):
                        reasons.append(f"预留单位 {unit_id} 已阵亡，名额用掉")
            if reasons:
                blocked[name] = "；".join(reasons)
            else:
                allowed.add(name)

        return CardWhitelist(
            allowed=frozenset(allowed),
            blocked=blocked,
            player_faction=player_faction,
            conference=conference,
            campaign_id=campaign_id,
            probabilities=prob,
        )

    # ---- 战区资产（U45）----

    def theater_asset_types(self) -> list[str]:
        """战区资产**候选全集**（7 种，顺序按游戏常量）。

        ⚠️ 这是**游戏自己的名单**（`constants.theater_asset_types`），
        不是修改器自己定的 ⇒ 存档里能写什么、界面就该列什么。
        """
        return list(THEATER_ASSET_TYPES)

    def theater_asset_has_texture(self, name: str) -> bool:
        """这个战区资产有没有游戏原贴图（`<asset>_neutral.png`）。

        游戏自己的 `TheaterCtrl._add_theater_asset` 拼的是
        `theater/<asset>_<阵营>_neutral`，找不到就退回 `<asset>_neutral`
        ⇒ 只要有 `_neutral.png` 就能显示。
        """
        for pkg in self.paths.packages():
            cand = Path(pkg) / "assets" / "surfaces" / "theater" / (name + "_neutral.png")
            try:
                if cand.is_file():
                    return True
            except OSError:
                continue
        return False

    def theater_asset_universe(self) -> list[dict]:
        """战区资产**候选全集** + 每项的贴图情况。

        返回 `[{"asset": 名字, "has_texture": bool}, …]`。
        """
        out = []
        for name in THEATER_ASSET_TYPES:
            out.append({"asset": name, "has_texture": self.theater_asset_has_texture(name)})
        return out

    def scenario_theater_assets(self, scenario_id: str,
                                campaign_id: str | None = None,
                                variant: str | None = None) -> dict:
        """**游戏包**里这个场景本来有哪些战区资产。

        返回 `{asset: {"uses_total": …, "uses_turn": …}}`；找不到返回 `{}`。

        ⚠️ 场景定义里只有 **3 个字段**（`asset` / `uses_total` / `uses_turn`），
        **没有** `to_use` —— 那是运行时字段（`Game.new` 载入时现算）。
        """
        for main in self._scenario_mains(scenario_id, campaign_id, variant):
            data = self._yaml(main)
            if not isinstance(data, dict):
                continue
            ta = data.get("theater_assets")
            if not isinstance(ta, list):
                continue
            out: dict[str, dict] = {}
            for grp in ta:
                if not isinstance(grp, list):
                    continue
                for it in grp:
                    if isinstance(it, dict) and it.get("asset"):
                        out[str(it["asset"])] = {
                            "uses_total": it.get("uses_total"),
                            "uses_turn": it.get("uses_turn"),
                        }
            if out:
                return out
        return {}

    def _scenario_mains(self, scenario_id: str, campaign_id: str | None,
                        variant: str | None) -> list[Path]:
        """场景 `main.yml` 的候选路径（用户包 → 游戏包，先到先得）。

        两种摆法：

        * **战役里的场景** —— `<包>/data/campaigns/<战役>.usc/scenarios/<场景>/main.yml`
          （独立场景存档也要靠这个找 —— 独立场景也是某个战役里的场景）；
        * **独立场景包** —— `<包>/data/scenarios/<场景>.usc/scenarios/<场景>/main.yml`。

        ⚠️ 不知道战役时（`campaign_id=None`）会把**所有战役包**都扫一遍
        （实测每个包最多 11 个战役目录，很便宜）。
        """
        rels = []
        if variant:
            rels.append("scenarios/%s/variants/%s/main.yml" % (scenario_id, variant))
        rels.append("scenarios/%s/main.yml" % scenario_id)
        out: list[Path] = []
        for pkg in self.paths.packages():
            data = pkg / "data"
            roots: list[Path] = []
            if campaign_id:
                roots.append(data / ("campaigns/%s.usc" % campaign_id))
            else:
                roots.append(data / ("scenarios/%s.usc" % scenario_id))
                camps = data / "campaigns"
                try:
                    roots.extend(sorted(camps.glob("*.usc")))
                except OSError:
                    pass
            for root in roots:
                for rel in rels:
                    cand = root / rel
                    try:
                        if cand.is_file():
                            out.append(cand)
                    except OSError:
                        continue
        return out

    @staticmethod
    def _yaml(path: Path):
        try:
            if not Path(path).is_file():
                return None
            return yamlio.load(Path(path).read_bytes())
        except (OSError, Exception):
            return None

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


def spec_type(name: str) -> SpecialistType | None:
    """一个特种兵类型的定义（攻防装甲火力 / 国籍 / 阵营 / flags）。"""
    return default().spec_type(name)


def nationality(name: str) -> Nationality | None:
    """一个国籍的定义（含 `parent_nationality`）。"""
    return default().nationality(name)


def campaign_specialist_pool(campaign_id: str | None) -> set[str]:
    """某战役的「默认特种兵集合」（商店 ∪ 场景，见 `e163`）。"""
    return default().campaign_specialist_pool(campaign_id)


def specialist_candidates(unit_type_name: str, campaign_id: str | None = None,
                          captured: bool = False) -> tuple[list[str], str]:
    """某单位类型能挂的特种兵候选 + 口径标签（见 `Catalog.specialist_candidates`）。"""
    return default().specialist_candidates(unit_type_name, campaign_id, captured)


def fronts(campaign_id: str) -> list[str]:
    """某战役包里的战线名。"""
    return default().fronts(campaign_id)


def store_defaults(campaign_id: str, front: str, conference: str) -> list[dict]:
    """战役包默认商店清单（**仅供参考**，不要拿它纠正存档）。"""
    return default().store_defaults(campaign_id, front, conference)


def card_whitelist(save) -> CardWhitelist:
    """卡牌商店白名单（见 `Catalog.card_whitelist`）。

    ⚠️ **每次调用都重算** —— 白名单是"当前存档 + 当前会议"的状态。
    """
    return default().card_whitelist(save)
