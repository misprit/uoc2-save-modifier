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
from typing import Any

from . import yamlio
from .capabilities import Capabilities
from .discovery import SaveInfo
from .paths import CorePaths

__all__ = ["Save", "View", "UnitView", "HqView", "CardView", "StoreEntryView"]

_TURN_RE = re.compile(r"^turn_(\d+)")


# ---------------------------------------------------------------- 只读视图


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
    losses: int | None = None
    retreated: bool | None = None
    #: 该单位是否出现在战役名册 `document/units.yml` 里
    in_roster: bool = True
    #: 类型的战力上限 —— S4 由 catalog 填；现在没有类型表就留 None
    max_st: int | None = None
    #: 类型的特种兵上限（`min(3, max_spec)`）
    max_spec: int | None = None

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
    uv: tuple[int, ...] | None = None
    xp: int | None = None
    xp_target: int | None = None
    branch_levels: dict | None = None
    persistent: bool | None = None
    overrun: bool | None = None
    turn_disbanded: bool | None = None

    @property
    def display_name(self) -> str:
        return self.name_brief or self.name_full or f"总部 {self.id}"


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
    """商店条目（`store.yml` 的一条）。"""

    front: str
    equipment: str | None = None
    spec: str | None = None
    nationality: str | None = None
    price: int = 0
    quantity: int = 0

    @property
    def what(self) -> str:
        return self.spec or self.equipment or "?"


@dataclass
class View:
    """给 GUI 用的只读投影（规范 §0.2 的 `save.view()`）。"""

    save: SaveInfo
    capabilities: Capabilities
    stage: str = ""
    prestige: int | None = None
    score: int | None = None
    units: list[UnitView] = field(default_factory=list)
    hqs: list[HqView] = field(default_factory=list)
    cards: list[CardView] = field(default_factory=list)
    hand: list[CardView] = field(default_factory=list)
    store: list[StoreEntryView] = field(default_factory=list)
    battle_turn: int | None = None
    warnings: list[str] = field(default_factory=list)


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
        self._yaml_cache: dict[str, Any] = {}
        self._overlay: dict[str, bytes] = {}
        self._battle_turn: int | None = None
        self._battle_turn_done = False

    # ---- 底层 ----

    def _zip(self) -> zipfile.ZipFile:
        if self._zf is None:
            self._zf = zipfile.ZipFile(self.info.path, "r")
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

    def battle_main(self) -> dict:
        """当前战斗的 `main.yml`（含 `theater_assets`）。"""
        d = self.battle_dir()
        if d is None:
            return {}
        data = self.read_yaml(f"{d}/main.yml", {})
        return data if isinstance(data, dict) else {}

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

    def view(self) -> View:
        """给 GUI 用的只读投影。"""
        caps = self.capabilities()
        main = self.root_main()
        roster = self.roster_ids() if caps.has_root_units else set()

        units = [
            UnitView(
                id=u.get("id"),
                type=u.get("type"),
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
                losses=u.get("losses"),
                retreated=u.get("retreated"),
                in_roster=u.get("id") in roster if roster else True,
            )
            for u in self.root_units()
            if isinstance(u.get("id"), int)
        ]

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
                uv=tuple(h["uv"]) if isinstance(h.get("uv"), list) else None,
                xp=h.get("xp"),
                xp_target=h.get("xp_target"),
                branch_levels=h.get("branch_levels"),
                persistent=h.get("persistent"),
                overrun=h.get("overrun"),
                turn_disbanded=h.get("turn_disbanded"),
            )
            for h in self.root_hqs()
            if isinstance(h.get("id"), int)
        ]

        cards = [CardView(
            card_type=c.get("card_type"),
            is_free=bool(c.get("is_free")),
            position=c.get("position"),
            unit_id=c.get("unit_id"),
            used=bool(c.get("used")),
        ) for c in self.root_cards()]

        hand = [CardView(
            card_type=c.get("card_type"),
            is_free=bool(c.get("is_free")),
            position=c.get("position"),
            unit_id=c.get("unit_id"),
            used=bool(c.get("used")),
        ) for c in (self.card_store() or []) if isinstance(c, dict)]

        store: list[StoreEntryView] = []
        for front, entries in self.root_store().items():
            if not isinstance(entries, list):
                continue
            for e in entries:
                if not isinstance(e, dict):
                    continue
                store.append(StoreEntryView(
                    front=front,
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
            cards=cards,
            hand=hand,
            store=store,
            battle_turn=self.battle_turn(),
            warnings=warnings,
        )

    # ---- 写回（S5 之后接上）----

    @property
    def path(self) -> Path:
        return self.info.path
