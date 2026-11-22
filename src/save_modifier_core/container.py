"""存档容器：打开一个 .usg，提供只读访问、能力位与 GUI 用的视图。

**这一层只读** —— 写入能力在 S5 之后逐步接上（plan / commit / undo）。

容器 = 一层 ZIP。存档里的每一层都是 ZIP 条目：

```
main.yml  units.yml  hqs.yml  cards.yml  store.yml   ← L1 根状态（唯一可写层）
last_conference/…  last_game/…                          ← L2 检查点（只读）
games/<场景>/…      game/…                              ← L3 战斗实时层（只读）
games/<场景>/archive                                   ← L4 回合历史（内层 ZIP，只读）
document/…                                             ← L5 战役文档（只读）
```

`games/<场景>/archive` 是**二层 ZIP**，里面还有 npz —— 读它时要先取出字节再开内层 ZIP。
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import yamlio
from .capabilities import Capabilities
from .discovery import SaveInfo
from .paths import CorePaths

if TYPE_CHECKING:                      # pragma: no cover
    from .catalog import Catalog
    from .commit import CommitResult
    from .plan import Plan
    from .undo import UndoResult

__all__ = ["Save", "SaveUnreadable", "View", "UnitView", "HqView", "CardView",
           "StoreEntryView"]

_TURN_RE = re.compile(r"^turn_(\d+)")


class SaveUnreadable(Exception):
    """存档**打不开**（文件损坏 / 不是 .usg / 读不出来）。

    ⚠️ **U141**：以前这里直接把 `zipfile.BadZipFile` 抛穿 ⇒ 服务端变成
    HTTP 500、界面只显示「BadZipFile: File is not a zip file」——
    玩家既看不懂，也**不知道下一步该干什么**（其实答案就摆着：
    修改器目录里 `bak` 文件夹中的 `_BACKUP.usg`）。
    """


def theater_assets_by_phase(ta: Any) -> list[dict[str, dict]]:
    """把 `theater_assets` 的**分组**拆成 `[{资产: {uses_total, uses_turn}}, …]`。

    ⚠️ **U143（更正 U141）**：这两组**不是"两个阶段"，而是「两个阵营各一组」**
    —— 战斗 `main.yml` 的 `factions` 第 i 项 = 第 i 组的拥有者，
    `phase` = 现在轮到哪一方（游戏读 `theater_assets[self.phase]`）。
    ⇒ `theater_assets_by_phase` 这个名字是历史包袱（公开 API，不改），
    但**返回的下标是阵营下标**。

    ⚠️ **U141**（仍然成立）：**同一种资产可能在两组里都出现、次数还不同**
    （实测 71 个存档里 **60 个**有这种场景）⇒
    **拍平**会让「后一组覆盖前一组」⇒ 显示的参照值可能是**另一方**的。
    ⇒ 保留分组，由调用方按**要改的那一方**取那一组
    （`theater_group_index()`）。
    """
    out: list[dict[str, dict]] = []
    if not isinstance(ta, list):
        return out
    for grp in ta:
        g: dict[str, dict] = {}
        if isinstance(grp, list):
            for it in grp:
                if isinstance(it, dict) and it.get("asset"):
                    g[str(it["asset"])] = {
                        "uses_total": it.get("uses_total"),
                        "uses_turn": it.get("uses_turn"),
                    }
        out.append(g)
    return out


def theater_assets_flat(groups: list[dict[str, dict]]) -> dict[str, dict]:
    """把分组**拍平**（兼容旧行为：**后一组覆盖前一组**）。"""
    out: dict[str, dict] = {}
    for g in groups:
        out.update(g)
    return out


def theater_sides(battle_data: Any) -> list[dict]:
    """这场战斗里 `theater_assets` 的**两组分别属于哪一方**（U143）。

    ⚠️ **U143（重要更正）**：这两组**不是"两个阶段"，而是「两个阵营各一组」**：

    * 战斗 `main.yml` 的 `factions` 是**有序字典**，第 i 项 = 第 i 组的拥有者，
      每项里 `player: local` / `player: ai` **直接标出哪一方是玩家**；
    * `phase` = **现在轮到哪一方**（游戏读 `theater_assets[self.phase]`）；
    * 字节码旁证：AI 代码 `is_ai = (self.phase != game.phase)`
      ⇒ **phase ⇔ 阵营**，不是时间上的阶段。

    返回 `[{"key": 阵营名, "index": 组下标, "is_player": bool,
    "is_current": bool}]`；`factions` 缺失（旧存档 / 夹具）⇒ 空列表。
    """
    out: list[dict] = []
    if not isinstance(battle_data, dict):
        return out
    fac = battle_data.get("factions")
    if not isinstance(fac, dict) or not fac:
        return out
    phase = battle_data.get("phase")
    for i, key in enumerate(fac.keys()):
        info = fac.get(key)
        info = info if isinstance(info, dict) else {}
        out.append({
            "key": str(key),
            "index": i,
            "is_player": info.get("player") == "local",
            "is_current": (phase == i),
        })
    return out


def theater_group_index(battle_data: Any, side: str = "player") -> int:
    """要改**哪一组**（组下标）。

    * `side="player"`（默认）⇒ **玩家那一方**（`player: local` 的下标）；
    * `side="opponent"` ⇒ **另一方**（不是玩家的那一组）；
    * `side="current"` ⇒ 当前行动方（`phase`）—— 旧语义，保留兼容；
    * `side="0"` / `side="1"`（**数字**）⇒ **直接就是组下标**（界面按组寻址用）；
    * `factions` 缺失（旧存档 / 合成夹具）⇒ 退回 `phase`（**不猜**）。

    ⚠️ **双 `player: local`（hotseat / 双人同机）**：两侧都是玩家 ⇒
    「不是玩家的那一侧」**根本不存在** ⇒ 旧写法会退回第 0 组
    ⇒ 两个页签都改第 0 组（**改错条目**），第二方那组永远改不到。
    ⇒ 现在改成取「玩家那一方**之外**的那一侧」。
    """
    sides = theater_sides(battle_data)
    if sides:
        # 数字 = **组下标**（界面按组寻址；越界 ⇒ 退回第 0 组，不猜）
        n_groups = len(sides)
        theater0 = (battle_data or {}).get("theater_assets")
        if isinstance(theater0, list):
            n_groups = len(theater0)
        if isinstance(side, bool):
            pass
        elif isinstance(side, int):
            return side if 0 <= side < n_groups else int(sides[0]["index"])
        elif isinstance(side, str) and side.strip().isdigit():
            n = int(side.strip())
            return n if 0 <= n < n_groups else int(sides[0]["index"])
        if side == "current":
            for sd in sides:
                if sd["is_current"]:
                    return int(sd["index"])
        # 玩家那一方 = 第一个 `player: local`（一个都没有 ⇒ 退第 0 组）
        player_idx = None
        for sd in sides:
            if sd["is_player"]:
                player_idx = int(sd["index"])
                break
        if player_idx is None:
            player_idx = int(sides[0]["index"])
        if side == "opponent":
            # 先找**不是玩家**的那一侧
            for sd in sides:
                if not sd["is_player"] and int(sd["index"]) != player_idx:
                    return int(sd["index"])
            # 两边都是玩家（hotseat）⇒ 玩家那一方**之外**的那一侧
            for sd in sides:
                if int(sd["index"]) != player_idx:
                    return int(sd["index"])
            return player_idx
        return player_idx
    theater = (battle_data or {}).get("theater_assets")
    phase = (battle_data or {}).get("phase")
    if isinstance(theater, list) and theater:
        if isinstance(phase, int) and not isinstance(phase, bool) \
                and 0 <= phase < len(theater):
            return phase
    return 0


# ---------------------------------------------------------------- 只读视图


#: 作战标记（HQ 技能的三种「命令」）⇒ 战斗层 `main.yml` 里的列表名。
#:
    #: 用户批准把**战斗层**列为可写（第二个 L3 例外，
#: 第一个是战区资产）。标记的官方名称来自游戏 locale：
#: `id_no_retreat`（不能撤退）/ `id_rearguard`（后卫部队）/ `id_elastic_defense`（反击）。
ORDER_LISTS = {
    "no_retreat": "no_retreat_units",
    "rearguard": "rearguard_units",
    "elastic_defense": "elastic_defense_units",
}

#: 标记的 locale 键（显示名）
ORDER_LOCALE_KEYS = {
    "no_retreat": "id_no_retreat",
    "rearguard": "id_rearguard",
    "elastic_defense": "id_elastic_defense",
}


def _effective_orders(keys) -> tuple[str, ...]:
    # 存档里一个单位可能同时在多个标记列表里 —— **只返回游戏会认的那个**。
    #
    # 依据（U102，字节码）：`Gamelike.get_defense_flag_string`
    # （`state/gamelike/gamelike.pyc:1470-1476`）按
    # **no_retreat → rearguard → elastic_defense** 的顺序**只返回一个**
    # ⇒ 存档里有冲突时，游戏只认第一个，其余静默忽略。
    for k in ORDER_LISTS:            # dict 的插入顺序 = 游戏的优先级顺序
        if k in keys:
            return (k,)
    return ()


@dataclass(frozen=True)
class UnitView:
    """单位（根 `units.yml` 的一条）。"""

    id: int
    type: str | None = None
    name_brief: str | None = None
    name_full: str | None = None
    hq_id: int | None = None
    xp: int | None = None
    act_st: int | None = None
    sup_st: int | None = None
    specs: tuple[dict, ...] = ()
    uv: tuple[int, ...] | None = None
    entr: int | None = None
    supply: int | None = None
    ap: int | None = None
    #: **移动力**（剩余的移动点）—— U85 补：视图里原来没有这个字段，
    #: 界面读不到、测试也读不到。游戏里它是**状态量**（`apply_mp_ap` 会按
    #: 类型的 `move` 重算），存档里存的是当前值。
    mp: int | None = None
    losses: int | None = None
    retreated: bool | None = None
    #: 该单位是否出现在战役名册 `document/units.yml` 里
    in_roster: bool = True
    #: 类型的战力上限 —— S4 由 catalog 填；现在没有类型表就留 None
    max_st: int | None = None
    #: 类型的特种兵上限（`min(3, max_spec)`）
    max_spec: int | None = None
    #: **作战标记**（HQ 技能的命令）—— `no_retreat` / `rearguard` /
    #: `elastic_defense`；只对当前战斗有效。
    #:
    #: ⚠️ 这三个标记互斥 —— 一个单位同时只能有一个。
    #: 游戏里下达命令是「先把该单位从三个列表全清掉、再加进其中一个」
    #: （`state/scenario/commands_unit.pyc::UnitSetFlags._set_flags:359-368`），
    #: 且三个 `can_make_*` 都要求「该单位没有其它标记」
    #: （`Gamelike.has_any_defense_flag`）⇒ 这里**只给生效的那一个**
    #:（按游戏优先级 no_retreat → rearguard → elastic_defense）。
    orders: tuple[str, ...] = ()
    #: 存档里这个单位**本来就**同时在多个列表里（游戏自己造不出这种状态，
    #: 可能是别的工具写的）⇒ 界面提示一句。只读，不改存档。
    orders_conflict: bool = False
    #: 是不是**装甲机动单位**（类型判定）——
    #: 游戏里「反击」只允许这种单位挂（`can_make_elastic_defense`）。
    armor_mobile: bool = False

    @property
    def total_st(self) -> int | None:
        a = self.act_st or 0
        s = self.sup_st or 0
        return a + s if (a or s) else None

    @property
    def display_name(self) -> str:
        return self.name_brief or self.name_full or f"单位 {self.id}"


@dataclass(frozen=True)
class HqView:
    """总部（根 `hqs.yml` 的一条）。"""

    id: int
    name_brief: str | None = None
    name_full: str | None = None
    general: int | None = None
    force_pool: tuple[dict, ...] = ()
    cp: int | None = None
    max_cp: int | None = None
    supply: int | None = None
    #: **补给卡车数**（`trucks`）—— U35 补：视图里原来没有这个字段，
    #: 导致界面读不到、测试也读不到（`_hq_trucks` 一直在写它）。
    trucks: int | None = None
    uv: tuple[int, ...] | None = None
    xp: int | None = None
    xp_target: int | None = None
    branch_levels: dict | None = None
    #: **技能树**（`branches`）：`{分支: [{action, cost, level, sp_avail, sp_used}]}`
    #: —— `level` 是该动作所在的级别（1/2/3 = 游戏 UI 矩阵的列），
    #: `sp_used` 是**已专精次数 = 技能等级**（`e165` 字节码坐实）
    branches: dict | None = None
    persistent: bool | None = None
    overrun: bool | None = None
    turn_disbanded: bool | None = None

    @property
    def display_name(self) -> str:
        return self.name_brief or self.name_full or f"总部 {self.id}"

    @property
    def branch_tiers(self) -> dict[str, dict[int, list[dict]]]:
        """技能树按 **分支 → 级别** 分好组 —— GUI 画「分支 × 级别」矩阵直接用。

        ```
        { "engineering": { 1: [{action, cost, level, sp_avail, sp_used}, ...],
                          2: [...], 3: [...] },
          ... }
        ```

        * 级别来自每条技能自己的 `level`（**不是**分支等级）；
        * 分支等级在 `branch_levels[分支]["level"]` —— 两者**不是一回事**：
          分支等级决定哪些级别已解锁（`tier <= 分支等级`）；
        * 存档里没有的分支**不出现**在结果里（不凭空造）。
        """
        out: dict[str, dict[int, list[dict]]] = {}
        for branch, items in (self.branches or {}).items():
            if not isinstance(items, list):
                continue
            tiers = out.setdefault(branch, {})
            for it in items:
                if not isinstance(it, dict):
                    continue
                tier = it.get("level")
                if not isinstance(tier, int) or isinstance(tier, bool):
                    continue
                tiers.setdefault(tier, []).append(it)
        return out


@dataclass(frozen=True)
class CardView:
    """卡牌（`cards.yml` 的一条，或手里的一张牌）。"""

    card_type: str | None = None
    is_free: bool = False
    position: int | None = None
    unit_id: int | None = None
    used: bool = False


@dataclass(frozen=True)
class StoreEntryView:
    """商店条目（`store.yml` 的一条）。

    ⚠️ `store.yml` 是**两层**的：`{战线: {store: [...], elite_store: [...]}}`
    —— 普通商店 + 精英商店（`e154` 实证）。所以条目要知道自己在哪个子商店里。
    """

    front: str
    sub: str = "store"
    equipment: str | None = None
    spec: str | None = None
    nationality: str | None = None
    price: int = 0
    quantity: int = 0

    @property
    def what(self) -> str:
        return self.spec or self.equipment or "?"

    @property
    def is_elite(self) -> bool:
        """是不是精英商店的条目。"""
        return self.sub == "elite_store"


@dataclass
class View:
    """给 GUI 用的只读投影（规范 §0.2 的 `save.view()`）。

    ⚠️ **两个卡牌集合别搞反**（`e157`/`e160` 实证）：

    | 字段 | 来源 | 是什么 |
    |---|---|---|
    | `hand` | 根 `cards.yml` | **手牌** —— 你手里已经拿到的牌 |
    | `shelf` | 根 `main.yml.card_store` | **货架** —— 会议里可以买的牌 |

    旁证：手牌张数上限 = `card_deck_limit`（classic = 4），
    货架格数 = `card_store_limit`（恒为 5）——
    实测存档手牌正好 4 张、货架正好 5 张。
    """

    save: SaveInfo
    capabilities: Capabilities
    stage: str = ""
    prestige: int | None = None
    score: int | None = None
    units: list[UnitView] = field(default_factory=list)
    hqs: list[HqView] = field(default_factory=list)
    #: 手牌（根 `cards.yml`）
    hand: list[CardView] = field(default_factory=list)
    #: 货架（根 `main.yml.card_store`）—— 只在会议阶段存在
    shelf: list[CardView] = field(default_factory=list)
    store: list[StoreEntryView] = field(default_factory=list)
    battle_turn: int | None = None
    #: 当前战斗里**已激活**的单位 id（`games/<场景>/units.yml`）—— 战斗中才有
    battle_unit_ids: tuple[int, ...] = ()
    warnings: list[str] = field(default_factory=list)

    @property
    def cards(self) -> list[CardView]:
        """手牌的旧名（`hand`）—— 保留是为了不打断已有调用方。"""
        return self.hand


# ---------------------------------------------------------------- 容器


class Save:
    """一个已打开的存档。

    生命周期：`open_save()` → 用 → `close()`。
    写回（S5 之后）走 `commit()`，它会先把内部 ZIP 句柄关掉再替换文件。
    """

    def __init__(self, info: SaveInfo, paths: CorePaths):
        self.info = info
        self.paths = paths
        self._zf: zipfile.ZipFile | None = None
        self._names: list[str] | None = None
        #: 当前战斗里已激活的单位 id（缓存一次就够 —— 战斗层只读）
        self._battle_unit_ids: tuple[int, ...] = ()
        self._battle_unit_ids_done = False
        self._yaml_cache: dict[str, Any] = {}
        self._overlay: dict[str, bytes] = {}
        self._battle_turn: int | None = None
        self._battle_turn_done = False

    # ---- 底层 ----

    def _zip(self) -> zipfile.ZipFile:
        if self._zf is None:
            try:
                self._zf = zipfile.ZipFile(self.info.path, "r")
            except (zipfile.BadZipFile, OSError) as exc:
                # ⚠️ 别把 `BadZipFile` 原样抛穿（玩家看不懂，
                # 也不知道下一步该干什么）⇒ 换成一句人话。
                raise SaveUnreadable(
                    "这个存档打不开（文件损坏，或它不是 .usg 存档）—— "
                    "试试把修改器目录里 bak 文件夹中的 _BACKUP.usg 复制回来"
                ) from exc
        return self._zf

    def close(self) -> None:
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    def __enter__(self) -> "Save":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def list_names(self) -> list[str]:
        """存档内全部条目名（ZIP 顺序）。"""
        if self._names is None:
            self._names = self._zip().namelist()
        return self._names

    def has(self, name: str) -> bool:
        return name in set(self.list_names())

    def read_bytes(self, name: str) -> bytes | None:
        """读一个条目；读不到返回 None（不抛异常）。"""
        if name in self._overlay:
            return self._overlay[name]
        try:
            return self._zip().read(name)
        except KeyError:
            return None

    def read_text(self, name: str) -> str | None:
        raw = self.read_bytes(name)
        if raw is None:
            return None
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")

    def read_yaml(self, name: str, default: Any = None) -> Any:
        """读一个 YAML 条目并解析。解析失败返回 default（不抛异常）。"""
        if name in self._yaml_cache:
            return self._yaml_cache[name]
        raw = self.read_bytes(name)
        value = default
        if raw is not None:
            try:
                value = yamlio.load(raw)
            except Exception:
                # 解析失败只当这个文件坏了，不能因此整个存档打不开
                value = default
            if value is None:
                value = default
        self._yaml_cache[name] = value
        return value

    # ---- 语义读取 ----

    def root_main(self) -> dict:
        data = self.read_yaml("main.yml", {})
        return data if isinstance(data, dict) else {}

    def root_units(self) -> list[dict]:
        data = self.read_yaml("units.yml", [])
        return [u for u in data if isinstance(u, dict)] if isinstance(data, list) else []

    def root_hqs(self) -> list[dict]:
        data = self.read_yaml("hqs.yml", [])
        return [h for h in data if isinstance(h, dict)] if isinstance(data, list) else []

    def root_cards(self) -> list[dict]:
        data = self.read_yaml("cards.yml", [])
        return [c for c in data if isinstance(c, dict)] if isinstance(data, list) else []

    def root_store(self) -> dict:
        """商店：{战线名: [条目, …]}。"""
        data = self.read_yaml("store.yml", {})
        return data if isinstance(data, dict) else {}

    def card_store(self) -> list | None:
        """当前会议发到手里的牌；不在会议界面为 None。"""
        cs = self.root_main().get("card_store")
        return cs if isinstance(cs, list) else None

    def in_state(self) -> dict:
        st = self.root_main().get("in_state")
        return st if isinstance(st, dict) else {}

    def current_scenario(self) -> str | None:
        """当前战斗的场景 id（战役用 `in_state.scenario`，独立场景用 `standalone_scenario`）。"""
        return self.in_state().get("scenario") or self.info.standalone_scenario or None

    def battle_dir(self) -> str | None:
        """当前战斗在 ZIP 里的目录。

        战役存档 → `games/<场景>/`；独立场景存档 → `game/`（单数目录）。
        不在战斗里返回 None。
        """
        scenario = self.current_scenario()
        if self.info.is_standalone:
            return "game" if self.has("game/main.yml") else None
        if not scenario:
            return None
        return f"games/{scenario}" if self.has(f"games/{scenario}/main.yml") else None

    def combat_orders(self) -> dict:
        """当前战斗里，**哪些单位被下了哪些作战标记**。

        数据源 = 当前战斗的 `main.yml` 里的三个**单位 id 列表**：

        * `no_retreat_units` —— 不能撤退（死守）
        * `rearguard_units` —— 后卫部队
        * `elastic_defense_units` —— 反击

        ⚠️ 这三个是 **HQ 技能下的「命令」**（`id_super_tooltip_hq_bar_*`），
        **敌方下一回合结束前有效** ⇒ 游戏回合开始会清掉（`Game.start_turn_clear`）。

        返回 `{单位id: [标记key, …]}`；不在战斗里（或没有这些列表）返回 {}。
        """
        try:
            data = self.battle_main()
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict = {}
        for key, list_key in ORDER_LISTS.items():
            ids = data.get(list_key)
            if not isinstance(ids, list):
                continue
            for uid in ids:
                if isinstance(uid, int) and not isinstance(uid, bool):
                    out.setdefault(uid, []).append(key)
        return out

    def document_theater_assets(self, phase: int | None = None) -> dict:
        """存档自带的**场景定义**里，这场战斗本来有哪些战区资产。

        数据源：战役存档里带着**整份战役的场景副本**
        （`document/scenarios/<场景>/main.yml`）—— 这是「这场战斗开打时的设计」。

        返回 `{asset: {"uses_total": …, "uses_turn": …}}`；找不到返回 `{}`
        （**不报错** —— 只是没有对照信息）。

        ⚠️ 场景定义里只有 **3 个字段**（`asset` / `uses_total` / `uses_turn`），
        **没有** `to_use` —— 那是运行时字段。

        ⚠️ **U143（更正 U141）**：`phase` 这个参数其实是**组下标 = 阵营下标**
        （历史命名，公开 API 不改）—— 场景定义里的资产是**按阵营分组**的，
        同名资产在不同阵营次数不同 ⇒ 不分组就会显示**另一方**的参照值。
        不给 `phase` ⇒ 拍平（**后一组覆盖前一组**，兼容旧行为）。
        """
        scen = self.current_scenario()
        if not scen:
            return {}
        variant = self.in_state().get("variant") or None
        cands = []
        if variant:
            cands.append("document/scenarios/%s/variants/%s/main.yml" % (scen, variant))
        cands.append("document/scenarios/%s/main.yml" % scen)
        for entry in cands:
            if not self.has(entry):
                continue
            data = self.read_yaml(entry, {})
            if not isinstance(data, dict):
                continue
            ta = data.get("theater_assets")
            if not isinstance(ta, list):
                continue
            groups = theater_assets_by_phase(ta)
            flat = theater_assets_flat(groups)
            if not flat:
                continue
            if phase is not None and 0 <= phase < len(groups):
                # ⚠️ **空组就是空组** —— 不退回拍平
                #    （拍平 = 后一组覆盖前一组 ⇒ 会把**另一方**的设计
                #      当成这一方的参照值 ⇒ 玩家照着错的数去调）
                return groups[phase]        # ← 当前阶段那一组
            return flat
        return {}

    def battle_main(self) -> dict:
        """当前战斗的 `main.yml`（含 `theater_assets`）。"""
        d = self.battle_dir()
        if d is None:
            return {}
        data = self.read_yaml(f"{d}/main.yml", {})
        return data if isinstance(data, dict) else {}

    def battle_unit_ids(self) -> tuple[int, ...]:
        """当前战斗里**已激活**的单位 id 名单。

        数据源 = `games/<场景>/units.yml`（独立场景是 `game/units.yml`）——
        那是个**扁平的 id 列表**（实测 `[2, 5, 7, 10, 11, 12]`），
        是规范 §7.2 单位页过滤器 #2「当前战斗激活的单位」的**唯一**来源。

        ⚠️ **只在战斗进行中才存在**（71 个存档里 15 个在战斗中）
        ⇒ 不在战斗里返回空元组（界面上那个过滤器要置灰 + 说明原因）。
        """
        if self._battle_unit_ids_done:
            return self._battle_unit_ids
        self._battle_unit_ids_done = True
        d = self.battle_dir()
        if d is None:
            self._battle_unit_ids = ()
            return self._battle_unit_ids
        data = self.read_yaml(f"{d}/units.yml", [])
        if not isinstance(data, list):
            self._battle_unit_ids = ()
            return self._battle_unit_ids
        self._battle_unit_ids = tuple(
            sorted(int(x) for x in data
                   if isinstance(x, int) and not isinstance(x, bool))
        )
        return self._battle_unit_ids

    def roster_ids(self) -> set[int]:
        """战役名册 `document/units.yml` 里的单位 id 集合。

        根表只装"已经登场过"的单位（规范 §3.4.3b），名册才是全部。
        """
        doc = self.read_yaml("document/units.yml", [])
        out: set[int] = set()
        if isinstance(doc, list):
            for u in doc:
                if isinstance(u, dict) and isinstance(u.get("id"), int):
                    out.add(u["id"])
        return out

    # ---- 能力位与阶段 ----

    def capabilities(self) -> Capabilities:
        """算出 8 个能力位（规范 §3.4.5.1）。"""
        names = set(self.list_names())
        main = self.root_main()
        cs = main.get("card_store")
        return Capabilities(
            has_root_units="units.yml" in names,
            has_root_hqs="hqs.yml" in names,
            has_root_cards="cards.yml" in names,
            has_root_store="store.yml" in names,
            has_card_store=isinstance(cs, list) and len(cs) > 0,
            cp_conference=any(n.startswith("last_conference/") for n in names),
            cp_game=any(n.startswith("last_game/") for n in names),
            # 独立场景存档的 in_state.scenario 恒为 null，但 game/main.yml 存在
            # ⇒ 用"当前战斗目录是否存在"判定，比单看字段准
            in_battle=self.battle_dir() is not None,
        )

    def battle_turn(self) -> int | None:
        """当前回合数。

        ⚠️ 不能看 `games/<场景>/main.yml` 的 `turn` —— 部署阶段时它也已经是 1。
        只能看内层 archive 里有没有 `turn_NN_*` 快照（规范 §10 第 17 条）。

        结果会缓存：读内层 archive 要把整个 ZIP 取进内存，代价不小。
        """
        if self._battle_turn_done:
            return self._battle_turn
        self._battle_turn_done = True
        d = self.battle_dir()
        if d is None:
            return None
        raw = self.read_bytes(f"{d}/archive")
        if raw is None:
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(raw), "r") as inner:
                names = inner.namelist()
        except (zipfile.BadZipFile, OSError):
            return None
        turns = []
        for n in names:
            m = _TURN_RE.match(n)
            if m:
                turns.append(int(m.group(1)))
        self._battle_turn = max(turns) if turns else None
        return self._battle_turn

    def stage(self) -> str:
        """当前阶段的**显示**文本（规范 §3.4.6）。

        ⚠️ 只用于界面显示，**不得**用来决定改哪张表 —— 那是能力位的活。
        """
        main = self.root_main()
        st = self.in_state()
        if self.info.standalone_scenario:
            return "独立场景"
        scenario = st.get("scenario")
        if scenario:
            turn = self.battle_turn()
            return f"战斗中（第 {turn} 回合）" if turn else "准备/部署阶段"
        if isinstance(main.get("card_store"), list) and main["card_store"]:
            return "会议界面（已发牌）"
        if st.get("completed"):
            return "战役已完成"
        if st.get("lost_scenario"):
            return "刚结束一场（失败）"
        if st.get("segment_finished"):
            return "本段场景已打完"
        return "战役地图"

    # ---- 视图 ----

    def view(self, catalog: "Catalog | None" = None) -> View:
        """给 GUI 用的只读投影。

        参数
        ----
        catalog : 类型目录。给了就把每个单位的 `max_st` / `max_spec` 填上
                  （战力上限在类型定义里，不在存档里 —— 规范 §5.3）。
                  不给就留空，GUI 只能显示存档里的值。
        """
        caps = self.capabilities()
        main = self.root_main()
        roster = self.roster_ids() if caps.has_root_units else set()

        # 作战标记（当前战斗层的一次读取）
        orders_map = self.combat_orders() if caps.in_battle else {}

        units = []
        for u in self.root_units():
            if not isinstance(u.get("id"), int):
                continue
            t = u.get("type")
            units.append(UnitView(
                id=u["id"],
                type=t,
                name_brief=u.get("name_brief"),
                name_full=u.get("name_full"),
                hq_id=u.get("hq_id"),
                xp=u.get("xp"),
                act_st=u.get("act_st"),
                sup_st=u.get("sup_st"),
                specs=tuple(s for s in (u.get("specs") or []) if isinstance(s, dict)),
                uv=tuple(u["uv"]) if isinstance(u.get("uv"), list) else None,
                entr=u.get("entr"),
                supply=u.get("supply"),
                ap=u.get("ap"),
                mp=u.get("mp"),
                losses=u.get("losses"),
                retreated=u.get("retreated"),
                # 三个标记互斥 ⇒ 只暴露**生效的那一个**（游戏优先级）
                orders=_effective_orders(orders_map.get(u["id"], ())),
                # 存档里本来就有冲突（同一单位在多个列表里）⇒ 标记出来
                orders_conflict=len(orders_map.get(u["id"], ())) > 1,
                # 类型级判定（有没有游戏包都安全 —— 没有就是 False）
                armor_mobile=bool(catalog.armor_mobile(t)) if (catalog and t) else False,
                in_roster=u["id"] in roster if roster else True,
                max_st=catalog.max_st(t) if (catalog and t) else None,
                max_spec=(catalog.spec_cap(t) if (catalog and t) else None),
            ))

        hqs = [
            HqView(
                id=h.get("id"),
                name_brief=h.get("name_brief"),
                name_full=h.get("name_full"),
                general=h.get("general"),
                force_pool=tuple(f for f in (h.get("force_pool") or []) if isinstance(f, dict)),
                cp=h.get("cp"),
                max_cp=h.get("max_cp"),
                supply=h.get("supply"),
                trucks=h.get("trucks"),
                uv=tuple(h["uv"]) if isinstance(h.get("uv"), list) else None,
                xp=h.get("xp"),
                xp_target=h.get("xp_target"),
                branch_levels=h.get("branch_levels"),
                branches=h.get("branches"),
                persistent=h.get("persistent"),
                overrun=h.get("overrun"),
                turn_disbanded=h.get("turn_disbanded"),
            )
            for h in self.root_hqs()
            if isinstance(h.get("id"), int)
        ]

        def _cards(rows) -> list[CardView]:
            return [CardView(
                card_type=c.get("card_type"),
                is_free=bool(c.get("is_free")),
                position=c.get("position"),
                unit_id=c.get("unit_id"),
                used=bool(c.get("used")),
            ) for c in rows if isinstance(c, dict)]

        # 手牌 = 根 cards.yml；货架 = 根 main.yml.card_store（别搞反，见 View 的说明）
        hand = _cards(self.root_cards())
        shelf = _cards(self.card_store() or [])

        store: list[StoreEntryView] = []
        for front, blob in self.root_store().items():
            # store.yml 是两层：{战线: {store: [...], elite_store: [...]}}
            if not isinstance(blob, dict):
                continue
            for sub, entries in blob.items():
                if not isinstance(entries, list):
                    continue
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    store.append(StoreEntryView(
                        front=front,
                        sub=sub,
                        equipment=e.get("equipment"),
                        spec=e.get("spec"),
                        nationality=e.get("nationality"),
                        price=e.get("price") if isinstance(e.get("price"), int) else 0,
                        quantity=e.get("quantity") if isinstance(e.get("quantity"), int) else 0,
                    ))

        warnings: list[str] = []
        if not caps.has_root_units:
            warnings.append("该存档没有根 units.yml —— 战役开局，单位功能已禁用")
        if not caps.has_root_store:
            warnings.append("该存档没有根 store.yml —— 商店功能已禁用")
        if not caps.has_root_cards:
            warnings.append("该存档没有根 cards.yml —— 卡牌功能已禁用")
        if not caps.can_undo_in_game:
            warnings.append("该存档没有游戏内回退点，无法在游戏里撤销修改")

        return View(
            save=self.info,
            capabilities=caps,
            stage=self.stage(),
            prestige=main.get("prestige"),
            score=main.get("score"),
            units=units,
            hqs=hqs,
            hand=hand,
            shelf=shelf,
            store=store,
            battle_turn=self.battle_turn(),
            battle_unit_ids=self.battle_unit_ids(),
            warnings=warnings,
        )

    # ---- 写回（S5 之后接上）----

    def plan_edit(self, edits, catalog: "Catalog | None" = None) -> "Plan":
        """规划一批编辑。**不碰磁盘。**"""
        from .plan import plan_edit
        return plan_edit(self, edits, catalog)

    def commit(self, plan: "Plan") -> "CommitResult":
        """把计划写回存档（备份 → 临时文件 → 校验 → 原子替换）。

        提交成功后会把本次改动**压进撤销栈**（§6.4.2）。
        """
        from .commit import commit
        # 必须先关掉 ZIP 句柄 —— Windows 上替换被打开的文件会失败
        self.close()
        res = commit(plan)
        if res.ok:
            self._invalidate()
        return res

    def undo(self) -> "UndoResult":
        """撤销上一次提交（修改器自己的撤销栈，§6.4.2）。

        撤销前会**校验基准**：如果存档在你改完之后又被动过（多半是在游戏里手动改的），
        就会**拒绝执行并说明原因**，不硬改。
        """
        from .undo import undo_save
        self.close()
        res = undo_save(self.info.path)
        if res.ok:
            self._invalidate()
        return res

    def campaign_position(self):
        """这个存档在战役里的位置（U18 · 只读）。

        返回 `campaigns.CampaignPosition` —— 战役名 / 会议 / 战线 /
        正在打的场景 / 这场会议的可选场景。
        """
        from . import campaigns as camp_mod
        return camp_mod.CampaignData(self.paths).position(self)

    def undo_available(self) -> bool:
        """撤销栈里有没有东西可撤（GUI 用来决定按钮是否可点）。"""
        from .undo import peek
        return peek(self.info.path) is not None

    def undo_peek(self) -> str | None:
        """看栈顶是什么（GUI 显示"可撤销：xxx"）；栈空返回 None。"""
        from .undo import peek
        rec = peek(self.info.path)
        if rec is None:
            return None
        if rec.summary:
            return rec.summary
        return f"改了 {len(rec.entries)} 个文件：{'、'.join(rec.entry_names)}"

    def undo_count(self) -> int:
        """撤销栈里有多少条记录（GUI 的 Rail 显示"撤销栈 N 条"）。"""
        from .undo import load_stack
        try:
            records, _ = load_stack(self.info.path)
        except Exception:
            return 0
        return len(records)

    def _invalidate(self) -> None:
        """写回之后，缓存的 YAML 解析结果与条目清单都过期了。"""
        self._yaml_cache.clear()
        self._names = None
        self._overlay.clear()
        self._battle_turn = None
        self._battle_turn_done = False

    @property
    def path(self) -> Path:
        return self.info.path
