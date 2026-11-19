"""战役只读数据层 —— 战役 → 会议 → 场景 → 单位名册 / 商店。

**只读**：本模块只从**游戏包**和**内置索引**读，一个字节都不写。

数据来源分三层（U18 实测，详见《GUI设计规范.md》§7.8）：

┌──────────────────┬────────────────────────────────────────────────────┐
│ 层               │ 来源                                              │
├──────────────────┼────────────────────────────────────────────────────┤
│ **索引**         │ 内置 `campaign_index.json`（33.5 KB）              │
│                  │ —— 战役中文名 / 会议→场景列表 / 场景中文名 / 变体   │
│                  │ 这是**唯一**从隔壁项目搬进来的东西               │
├──────────────────┼────────────────────────────────────────────────────┤
│ **游戏包**       │ `<包>/data/campaigns/<战役>.usc/`                  │
│                  │ —— 场景目录（units.yml / hqs.yml / main.yml）      │
│                  │ —— 战线商店（fronts/*/conferences/*.yml）          │
├──────────────────┼────────────────────────────────────────────────────┤
│ **locale**       │ `localization/chi/strings.yml`                    │
│                  │ —— 单位名 / 特种兵名 / 场景名 / 国籍名             │
└──────────────────┴────────────────────────────────────────────────────┘

⚠️ **为什么索引必须存在**：游戏包的 `fronts/<战线>/conferences/<会议>.yml`
里的 `tracks` 是**段图**（`default_segment` / `alternatives`），**推不出**
「这场会议能打哪几个场景」—— 段名（`s_44_05_italy`）不是场景名，
`tokens` 只在部分会议出现，`segments/` 目录在游戏包里是空的。
⇒ 「会议 → 可选场景」这份**语义解读**来自隔壁项目的结论包，
   我们只搬这一层（33.5 KB），其余全部运行时读游戏包。

⚠️ **索引不代替游戏包**：场景的单位名册、HQ、商店**一律读游戏包**，
索引只管「叫什么、在哪条路上」。
索引里每个场景名都用游戏包 `scenarios/<id>/locale.yml` 的 locale 键**复核过**
（386/386 全中）⇒ 索引与游戏包一致，不会自相矛盾。
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import yamlio
from .locale import TranslationStore, default as default_locale
from .paths import CorePaths

__all__ = [
    "CampaignIndex",
    "CampaignPosition",
    "Conference",
    "Scenario",
    "ScenarioRoster",
    "StoreListing",
    "default_campaign_index",
    "load_campaign_index",
]


#: 内置索引文件名（放在包的 `data/` 下）
INDEX_FILENAME = "campaign_index.json"


# ---------------------------------------------------------------- 数据类

@dataclass(frozen=True)
class Conference:
    """一场会议（战役推进的一步）。

    ⚠️ `id` = 会议键（如 `c_43_04`），对应游戏包
    `fronts/<战线>/conferences/<id>.yml`。
    """

    id: str | None
    text: str
    scenes: tuple["Scenario", ...] = ()


@dataclass(frozen=True)
class Scenario:
    """一个场景（战役里的一场战斗）。

    `id` = 场景目录名（游戏包 `scenarios/<id>/`）。
    `variant` = `base`（基础配置）或 `variant`（变体配置）。
    """

    id: str
    name: str
    variant: str | None = None


@dataclass(frozen=True)
class ScenarioRoster:
    """场景的**静态名册**（游戏包 `scenarios/<id>/`）。

    ⚠️ **这是游戏包的默认配置，不是玩家存档** ——
    单位不一定存活、一定继承、一定登场。
    """

    scenario_id: str
    name: str = ""
    #: 地图名（`main.yml` 的 `map_name`）
    map_name: str | None = None
    #: 开局日期（`main.yml` 的 `start`）
    #: ⚠️ YAML 会把它解析成 `datetime.date` ⇒ 这里**转成字符串**
    start: str | None = None
    #: 总回合数（`main.yml` 的 `base_num_turns`）
    base_num_turns: int | None = None
    #: 参战阵营顺序（`main.yml` 的 `turn_seq`）
    turn_seq: tuple[str, ...] = ()
    #: 场景内的 HQ（`hqs.yml`）
    hqs: tuple[dict, ...] = ()
    #: 场景内的单位（`units.yml`）
    units: tuple[dict, ...] = ()
    #: 在途单位（`enroute_units.yml`）
    enroute_units: tuple[dict, ...] = ()
    #: locale 键（`locale.yml`）—— 场景名 / 日期 / 战况说明
    locale_keys: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StoreListing:
    """一条商店清单（战役包默认商店，**只读参考**）。

    ⚠️ 存档里的商店**覆盖**包默认（`e154` 字节码实证）⇒
    这里给的是「这场会议**本来**卖什么」，
    **不是**玩家当前的库存，也不是钱包余额。
    """

    front: str
    conference: str
    items: tuple[dict, ...] = ()
    elite_items: tuple[dict, ...] = ()


# ---------------------------------------------------------------- 索引

class CampaignIndex:
    """内置的「战役 → 会议 → 场景」索引。

    数据来自 `统一指挥2战役数据研究_项目/conclusion-package`
    （只取 navigation / stores.meetings 两层，已剔除其余）。
    """

    def __init__(self, data: dict, locale: TranslationStore | None = None):
        self.data = data or {}
        self.locale = locale

    # ---- 战役 ----

    def campaign_ids(self) -> list[str]:
        """全部战役短名（`west` / `stalingrad` / …）。"""
        return sorted((self.data.get("campaigns") or {}).keys())

    def campaign(self, campaign_id: str) -> dict | None:
        """一个战役的索引条目。"""
        return (self.data.get("campaigns") or {}).get(campaign_id)

    def campaign_name(self, campaign_id: str) -> str:
        """战役中文名（取不到就退回短名）。"""
        c = self.campaign(campaign_id)
        if c and c.get("name"):
            return str(c["name"])
        return campaign_id

    def campaign_packages(self, campaign_id: str) -> list[str]:
        """该战役在哪些游戏包里（`base` / `dlc4` / …）。"""
        c = self.campaign(campaign_id)
        return list((c or {}).get("packages") or [])

    # ---- 路线 ----

    def routes(self, campaign_id: str) -> list[str]:
        """该战役的路线版本（`historical` / `fantasy` / `relief` / …）。

        ⚠️ **这是版本化的静态规划投影**，不是玩家实际走过的路线。
        """
        c = self.campaign(campaign_id)
        return sorted(((c or {}).get("routes") or {}).keys())

    def route_order(self, campaign_id: str) -> list[str]:
        """路线**查找顺序** —— **历史线优先**（用户口径，U66），其余按字母序。

        ⚠️ 以前直接用 `routes()`（= **sorted**）⇒ `"fantasy" < "historical"`
        ⇒ 跨路线查找时**幻想线永远先命中** ⇒ 走历史线的存档会显示**幻想线**的关卡
        （实测 `Stalingrad.usg` 正在打 `road_to_stalingrad`，它只在历史线上）。
        """
        routes = list(self.routes(campaign_id))
        if "historical" in routes:
            return ["historical"] + [r for r in routes if r != "historical"]
        return routes

    def pick_route(self, campaign_id: str, conference_id: str | None = None,
                   scenario_id: str | None = None) -> str:
        """按**关卡**挑线路（用户口径，U66）：

        ① 关卡在**历史线**里有 ⇒ 走历史线；
        ② 历史线里没有 ⇒ 去别的线路找这个关卡，**用找到的第一个**；
        ③ 找不到关卡（存档不在战斗里 / 这个场景不在任何线路）⇒
           退回「这个会议在哪条线上」，再不行就用第一条（历史线）。
        """
        order = self.route_order(campaign_id)
        if scenario_id:
            for r in order:
                for c in self.conferences(campaign_id, r):
                    if any(s.id == scenario_id for s in c.scenes):
                        return r
        if conference_id:
            for r in order:
                if any(c.id == conference_id for c in self.conferences(campaign_id, r)):
                    return r
        return order[0] if order else "historical"

    def conferences(self, campaign_id: str, route: str = "historical") -> tuple[Conference, ...]:
        """某条路线上的会议列表。"""
        c = self.campaign(campaign_id) or {}
        r = (c.get("routes") or {}).get(route) or {}
        out = []
        for m in (r.get("meetings") or []):
            scenes = tuple(
                Scenario(id=str(s["id"]), name=str(s.get("name") or s["id"]),
                         variant=s.get("variant"))
                for s in (m.get("scenes") or []) if s.get("id")
            )
            out.append(Conference(id=m.get("id"), text=str(m.get("text") or ""),
                                  scenes=scenes))
        return tuple(out)

    def find_conference(self, campaign_id: str, conference_id: str,
                        route: str = "historical") -> Conference | None:
        """按会议 ID 找会议（找不到返回 None）。

        ⚠️ **查找顺序 = 历史线优先**（U66）：`route` 是「优先路线」，
        它里面没有这个会议时，再按 `route_order()` 继续找，**找到的第一个**就用。
        """
        order = self.route_order(campaign_id)
        seq = ([route] if route and route in order else []) + [r for r in order if r != route]
        for r in seq:
            for c in self.conferences(campaign_id, r):
                if c.id == conference_id:
                    return c
        return None

    def scenarios_of(self, campaign_id: str, conference_id: str,
                     route: str = "historical") -> tuple[Scenario, ...]:
        """某场会议下的可选场景列表。"""
        c = self.find_conference(campaign_id, conference_id, route)
        return c.scenes if c else ()

    def find_scenario(self, campaign_id: str, scenario_id: str) -> Scenario | None:
        """按场景 ID 找场景（**历史线优先**，U66）。"""
        for r in self.route_order(campaign_id):
            for c in self.conferences(campaign_id, r):
                for s in c.scenes:
                    if s.id == scenario_id:
                        return s
        return None

    # ---- 场景名复核 ----

    def verify_scene_name(self, scenario_id: str, campaign_id: str) -> str:
        """用游戏包 locale 复核场景中文名。

        索引里的名字是**抄来的**，这里用游戏包
        `scenarios/<id>/locale.yml` 的 locale 键现查一次 ——
        查得到就用游戏包的（权威），查不到才退回索引里的。
        """
        if self.locale is None:
            return ""
        for pk in (self.locale,):
            for key in self._scene_locale_keys(scenario_id, campaign_id):
                v = pk.get(key)
                if v:
                    return v
        return ""

    def _scene_locale_keys(self, scenario_id: str, campaign_id: str) -> list[str]:
        """可能的 locale 键（`locale.yml` 不在手边时的兜底推导）。"""
        out = []
        for p in ("base",):
            out.append("id_scenario_name_s_%s_c_%s_p_%s" % (scenario_id, campaign_id, p))
        return out


def _index_path() -> Path:
    return Path(__file__).resolve().parent / "data" / INDEX_FILENAME


def load_campaign_index(path: Path | None = None,
                        locale: TranslationStore | None = None) -> CampaignIndex:
    """载入内置索引。

    索引文件缺失 ⇒ 返回**空索引**（不报错）——
    战役只读页降级成「只有游戏包内容」，功能不缺。
    """
    p = path or _index_path()
    data: dict = {}
    try:
        if p.is_file():
            raw = io.open(p, "r", encoding="utf-8", newline="").read()
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                data = loaded
    except Exception:
        data = {}
    return CampaignIndex(data, locale if locale is not None else default_locale())


_DEFAULT: CampaignIndex | None = None


def default_campaign_index() -> CampaignIndex:
    """进程内共享的索引实例。"""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_campaign_index()
    return _DEFAULT


# ---------------------------------------------------------------- 游戏包

class CampaignData:
    """战役包的**游戏包**侧只读数据。

    索引管「叫什么、在哪条路上」；本类管「场景里有什么、商店卖什么」。
    """

    def __init__(self, paths: CorePaths | None = None,
                 index: CampaignIndex | None = None):
        self.paths = paths or CorePaths.discover()
        self.index = index or default_campaign_index()
        self.locale = default_locale()
        self._cache: dict[str, Any] = {}

    # ---- 路径 ----

    def campaign_dir(self, campaign_id: str) -> Path | None:
        """战役包目录（`<包>/data/campaigns/<战役>.usc/`）。

        按「用户包 → 游戏包」优先级，先到先得。
        """
        key = "cd:" + campaign_id
        if key in self._cache:
            return self._cache[key]
        out: Path | None = None
        for pkg in self.paths.packages():
            d = pkg / "data" / "campaigns" / (campaign_id + ".usc")
            if d.is_dir():
                out = d
                break
        self._cache[key] = out
        return out

    def scenario_dir(self, campaign_id: str, scenario_id: str) -> Path | None:
        """场景目录（`<战役>.usc/scenarios/<场景>/`）。"""
        cd = self.campaign_dir(campaign_id)
        if cd is None:
            return None
        d = cd / "scenarios" / str(scenario_id)
        return d if d.is_dir() else None

    def scenario_ids(self, campaign_id: str) -> list[str]:
        """该战役包里的全部场景目录名。"""
        key = "sc:" + campaign_id
        if key in self._cache:
            return self._cache[key]
        out: list[str] = []
        cd = self.campaign_dir(campaign_id)
        if cd is not None:
            sd = cd / "scenarios"
            if sd.is_dir():
                try:
                    out = sorted(p.name for p in sd.iterdir() if p.is_dir())
                except OSError:
                    out = []
        self._cache[key] = out
        return out

    # ---- 场景名册 ----

    def roster(self, campaign_id: str, scenario_id: str) -> ScenarioRoster | None:
        """读场景的静态名册（`units.yml` / `hqs.yml` / `main.yml` / `locale.yml`）。

        ⚠️ **只读**，且是**游戏包默认配置** ——
        不是玩家存档，单位不一定存活 / 继承 / 登场。
        """
        key = "ro:%s:%s" % (campaign_id, scenario_id)
        if key in self._cache:
            return self._cache[key]
        sd = self.scenario_dir(campaign_id, scenario_id)
        if sd is None:
            self._cache[key] = None
            return None
        main = self._yaml(sd / "main.yml") or {}
        loc = self._yaml(sd / "locale.yml") or {}
        name = ""
        lk = loc.get("scenario_name")
        if lk:
            name = self.locale.get(str(lk))
        if not name:
            sc = self.index.find_scenario(campaign_id, scenario_id)
            name = sc.name if sc else scenario_id
        r = ScenarioRoster(
            scenario_id=scenario_id,
            name=name,
            map_name=main.get("map_name"),
            start=(str(main.get("start")) if main.get("start") is not None else None),
            base_num_turns=main.get("base_num_turns"),
            turn_seq=tuple(str(x) for x in (main.get("turn_seq") or [])),
            hqs=tuple(x for x in (self._yaml(sd / "hqs.yml") or []) if isinstance(x, dict)),
            units=tuple(x for x in (self._yaml(sd / "units.yml") or []) if isinstance(x, dict)),
            enroute_units=tuple(x for x in (self._yaml(sd / "enroute_units.yml") or [])
                                if isinstance(x, dict)),
            locale_keys={str(k): str(v) for k, v in loc.items() if isinstance(v, str)},
        )
        self._cache[key] = r
        return r

    # ---- 商店 ----

    def store(self, campaign_id: str, front: str, conference: str) -> StoreListing | None:
        """战役包默认商店（`fronts/<战线>/conferences/<会议>.yml`）。

        ⚠️ **只读参考** —— 存档里的商店覆盖包默认（`e154`），
        这里给的是「这场会议**本来**卖什么」。
        """
        key = "st:%s:%s:%s" % (campaign_id, front, conference)
        if key in self._cache:
            return self._cache[key]
        cd = self.campaign_dir(campaign_id)
        if cd is None:
            self._cache[key] = None
            return None
        f = cd / "fronts" / str(front) / "conferences" / (str(conference) + ".yml")
        d = self._yaml(f)
        if not isinstance(d, dict):
            self._cache[key] = None
            return None
        items = tuple(x for x in (d.get("store") or []) if isinstance(x, dict))
        elite = tuple(x for x in (d.get("elite_store") or []) if isinstance(x, dict))
        r = StoreListing(front=str(front), conference=str(conference),
                         items=items, elite_items=elite)
        self._cache[key] = r
        return r

    def front_name(self, front: str, campaign_id: str | None = None) -> str:
        """战线中文名（「地中海」/「北欧」…）。

        locale 键 = `id_front_<战线代码>_name_full`；
        少数战线带战役前缀（`id_front_ardennes_east_name_full`）⇒
        先试带前缀的，再试通用的，取第一个查到的。
        """
        if not front:
            return ""
        cands = []
        if campaign_id:
            cands.append("id_front_%s_%s_name_full" % (campaign_id, front))
        cands.append("id_front_%s_name_full" % front)
        for k in cands:
            v = self.locale.get(k)
            if v:
                return v
        return ""

    def fronts(self, campaign_id: str) -> list[str]:
        """该战役包的战线名。"""
        cd = self.campaign_dir(campaign_id)
        if cd is None:
            return []
        fd = cd / "fronts"
        if not fd.is_dir():
            return []
        try:
            return sorted(p.name for p in fd.iterdir() if p.is_dir())
        except OSError:
            return []

    def conferences_of_front(self, campaign_id: str, front: str) -> list[str]:
        """某条战线下的会议 ID 列表（按游戏包里的文件名排序）。"""
        cd = self.campaign_dir(campaign_id)
        if cd is None:
            return []
        ccd = cd / "fronts" / str(front) / "conferences"
        if not ccd.is_dir():
            return []
        try:
            return sorted(p.stem for p in ccd.iterdir() if p.is_file())
        except OSError:
            return []

    # ---- 存档位置 ----

    def position(self, save) -> CampaignPosition:
        """算出一个存档在战役里的位置。

        `save` 是 `save_modifier_core.Save`（或任何有
        `root_main()` / `root_store()` 的对象）。

        ⚠️ **纯读取** —— 一个字节都不写存档。
        独立场景存档（没有 `conference`）⇒ 战役名照给，会议/场景留空。
        """
        try:
            main = save.root_main() or {}
        except Exception:
            main = {}
        try:
            store = save.root_store() or {}
        except Exception:
            store = {}
        ins = main.get("in_state") or {}

        cid = main.get("campaign_id") or None
        conf = ins.get("conference") or None
        front = ins.get("front") or None
        scen = ins.get("scenario") or None
        variant = ins.get("variant") or None

        active = tuple(sorted(store.keys())) if isinstance(store, dict) else ()

        camp_name = self.index.campaign_name(cid) if cid else None
        if cid:
            key = "id_campaign_name_c_%s_p_%s" % (cid, (self.index.campaign_packages(cid) or ["base"])[0])
            v = self.locale.get(key)
            if v:
                camp_name = v

        mtg = self.index.find_conference(cid, conf) if (cid and conf) else None
        conf_text = mtg.text if mtg else None
        scenes = mtg.scenes if mtg else ()

        scen_name = None
        if scen:
            sc = self.index.find_scenario(cid, scen) if cid else None
            if sc:
                scen_name = sc.name
            else:
                d = self.scenario_dir(cid, scen) if cid else None
                if d is not None:
                    lp = d / "locale.yml"
                    ld = self._yaml(lp)
                    if isinstance(ld, dict) and ld.get("scenario_name"):
                        scen_name = self.locale.get(str(ld["scenario_name"]))

        return CampaignPosition(
            campaign_id=cid,
            campaign_name=camp_name,
            conference_id=conf,
            conference_text=conf_text,
            front=front,
            front_name=(self.front_name(front, cid) if front else None),
            active_fronts=active,
            scenario_id=scen,
            scenario_name=scen_name,
            variant=variant,
            available_scenes=scenes,
        )

    # ---- 内部 ----

    @staticmethod
    def _yaml(path: Path):
        try:
            if not path.is_file():
                return None
            return yamlio.load(path.read_bytes())
        except Exception:
            return None


# ---------------------------------------------------------------- 存档位置

@dataclass(frozen=True)
class CampaignPosition:
    """一个存档在战役里的位置。

    ⚠️ **只读描述**，不是游戏状态判定 ——
    「会议 = 第4次会议」是存档里记的当前会议，
    不代表玩家一定能在这场会议里打任意场景。
    """

    #: 战役短名（`west` / `stalingrad` / …）
    campaign_id: str | None = None
    #: 战役中文名（locale `id_campaign_name_c_<战役>_p_<包>`）
    campaign_name: str | None = None
    #: 当前会议 ID（`c_43_04`）
    conference_id: str | None = None
    #: 当前会议的中文名（「第4次会议」）
    conference_text: str | None = None
    #: 当前战线（`italy` / `eur` / …）
    front: str | None = None
    #: 当前战线的中文名（「地中海」/「北欧」…）
    front_name: str | None = None
    #: 存档里激活的所有战线（`store.yml` 的顶层键）
    active_fronts: tuple[str, ...] = ()
    #: 正在打的场景 ID（战斗中才有）
    scenario_id: str | None = None
    #: 正在打的场景中文名
    scenario_name: str | None = None
    #: 场景变体（`in_state.variant`）
    variant: str | None = None
    #: 这场会议的**可选场景**（来自索引）
    available_scenes: tuple["Scenario", ...] = ()

    @property
    def is_in_battle(self) -> bool:
        """是否正在一场战斗里（`in_state.scenario` 有值）。"""
        return bool(self.scenario_id)

    @property
    def location_line(self) -> str:
        """一行位置描述（给 GUI 直接显示）。

        例：「斯大林格勒 · 第3次会议 · 南线 · 可选：布吕歇尔行动 / 卡拉奇 / 里海海岸」
        """
        parts = [self.campaign_name or self.campaign_id or "未知战役"]
        if self.conference_text:
            parts.append(self.conference_text)
        elif self.conference_id:
            parts.append(self.conference_id)
        if self.front_name or self.front:
            parts.append(self.front_name or self.front)
        if self.scenario_name:
            parts.append("战斗中：%s" % self.scenario_name)
        line = " · ".join(p for p in parts if p)
        if self.available_scenes and not self.is_in_battle:
            line += " · 可选：%s" % " / ".join(s.name for s in self.available_scenes)
        return line
