"""GUI 界面层 —— **本地 HTTP 桥 + Edge `--app` 独立窗口**（U26 技术路线）。

为什么不是 tkinter：视觉稿用的是 HTML/CSS，而 ttk 没有圆角 / 阴影 / flex /
`gap` / 过渡这些能力 ⇒ 用 tkinter 复刻一遍既慢又到不了同样的水准
（《GUI设计规范.md》§10.10）。这里让 **HTML/CSS 直接就是实现**
（实现文件 = `web/index.html`；`docs/GUI视觉稿.html` 已于 2026-11-19 冻结，
不再与实现比对，见 `docs/开发上下文.md` §5.1kk）。

跑法
----
```
python -m save_modifier_web.server          # 起服务 + 拉起 Edge 独立窗口
python -m save_modifier_web.server --serve  # 只起服务（自己开浏览器调试）
```

安全
----
* 只监听 **127.0.0.1**（不外网）；
* 每个会话带一个 **随机 token**，`/api/*` 必须带上（防本机其它进程/网页访问）；
* **本轮只提供只读接口** —— 写操作（plan / commit / undo）等 GUI 需求定稿后再加
  （交互方式会变，接口形状跟着变；核心库那边早就有 `plan_edit` / `commit` / `undo`）。
"""

from __future__ import annotations

import dataclasses
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO_SRC = Path(__file__).resolve().parents[1]
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

WEB_DIR = Path(__file__).resolve().parent / "web"

#: Edge 的常见安装位置（U26 实测：`--app=` 模式能给独立窗口、无地址栏）
EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge Beta\Application\msedge.exe",
)

#: Edge 自己的独立 profile（跟用户日常浏览隔开）。
#: ⚠️ 放在 **LOCALAPPDATA** 下，**不进源码树** —— 它是几百 MB 的浏览器缓存。
PROFILE_DIR = Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) \
    / ".uoc2" / "edge_profile"


# ---------------------------------------------------------------- 小工具


def find_edge() -> str | None:
    """找 Edge；找不到返回 `None`。"""
    for p in EDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def _jsonable(obj):
    """把 dataclass / 容器转成能 `json.dumps` 的东西。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _jsonable(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _mtime(ts) -> str:
    import datetime
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _size(n) -> str:
    try:
        n = float(n)
    except Exception:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024
    return ""


# ---------------------------------------------------------------- 只读 API


def api_saves() -> dict:
    """存档列表（启动页用）。"""
    from save_modifier_core import list_saves

    rows = []
    for info in list_saves():
        if not info.is_primary:
            continue
        rows.append({
            "save_id": info.save_id,
            "name": os.path.basename(str(info.path)),
            "display": info.display_name,
            "campaign": info.campaign_name or info.campaign_id or "",
            "scenario": info.scenario or "",
            "kind": "战役" if info.kind == "campaign" else "独立场景",
            "mtime": _mtime(info.mtime),
            "size": _size(info.size),
        })
    return {"saves": rows}


def api_view(save_id: str) -> dict:
    """某个存档的完整只读投影（概览页 / 各功能页用）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    catalog = Catalog(CorePaths.discover())
    with open_save(save_id) as save:
        view = save.view(catalog=catalog)
        caps = view.capabilities
        data = _jsonable(view)
        # 能力位体检：可用性用 `can_edit_*` 判断；`unavailable_reason()` 只是**原因文案表**
        # （永远返回字符串，不能拿它判可用性）。
        features = []
        for feat, attr in (("units", "can_edit_units"),
                           ("hqs", "can_edit_hqs"),
                           ("hand", "can_edit_hand"),
                           ("shelf", "can_edit_shelf"),
                           ("store", "can_edit_store"),
                           ("theater_assets", "can_edit_theater_assets"),
                           ("restore_hand", "can_restore_hand")):
            ok = bool(getattr(caps, attr, False))
            features.append({
                "name": feat,
                "ok": ok,
                "reason": "" if ok else caps.unavailable_reason(feat),
            })
        data["_features"] = features
        data["_save_id"] = save_id
        # U53：单位页过滤器 #2「当前场景激活的单位」的数据源
        # （`games/<场景>/units.yml` 的扁平 id 名单；**只在战斗中才有**）。
        data["battle_unit_ids"] = list(view.battle_unit_ids)
        data["in_battle"] = bool(caps.in_battle)
        # ⚠️ `SaveInfo.name` / `display_name` 是**属性**，不是 dataclass 字段
        # ⇒ `_jsonable` 不会输出它们 ⇒ 前端拿不到存档名（U42 实测 Header 显示「—」）。
        try:
            data["save"]["display_name"] = view.save.display_name
            data["save"]["file_name"] = view.save.name
        except Exception:
            pass

        # ---- 6 个功能页各自要的东西（U33 补齐）----
        # 战区资产：按当前 phase 取那一组（L3 例外的只读侧）
        data["theater_assets"] = _theater_assets_of(save)
        # 战区资产**全量候选**（U45）：7 种全集 + 每种在存档里的状态
        # + 「这场战斗本来有没有」的场景定义对照。
        data["theater_universe"], data["theater_meta"] = _theater_universe_of(save, catalog)
        # 战役位置（只读）
        try:
            pos = save.campaign_position()
            data["campaign_position"] = _jsonable(pos)
        except Exception as exc:
            data["campaign_position"] = {"error": str(exc)}
        # 单位 / 总部的 `name_brief` / `name_full` 存的是**本地化键**
        # （如 `id_unit_name_brief_97_dot__J_ger`）⇒ 这里查 locale 翻成中文。
        # ⚠️ 查不到就**原样返回**（玩家自己起的名字是明文，不是键）。
        # ⚠️ 中文一律来自游戏包 `localization/chi/strings.yml` —— 不自己翻译（§5.7）。
        _tr = None
        try:
            from save_modifier_core import locale as _locale
            _tr = _locale.default()
            for _u in (data.get("units") or []):
                _u["name_cn"] = _tr.get(_u.get("name_brief") or "", "") or (_u.get("name_brief") or "")
                _u["full_cn"] = _tr.get(_u.get("name_full") or "", "") or (_u.get("name_full") or "")
            for _h in (data.get("hqs") or []):
                _h["name_cn"] = _tr.get(_h.get("name_brief") or "", "") or (_h.get("name_brief") or "")
                _h["full_cn"] = _tr.get(_h.get("name_full") or "", "") or (_h.get("name_full") or "")
        except Exception as exc:
            data["_name_error"] = str(exc)

        # ---- 技能 / 将领 / 装备的中文名（U35）----
        # 技能：locale 键 = `id_tooltip_hq_bar_<action>`（20 个动作**全覆盖**，
        #   如 id_tooltip_hq_bar_bridge_repair → 修复桥梁）
        #   —— `id_<action>` 只有 15 个命中（deploy / reorg / entrenchment /
        #      security_unit / transfer 查不到），所以以 tooltip 键为主。
        # 将领：locale 键 = `id_<general>_brief` / `_full`
        # 装备：locale 键 = `id_equipment_type_<equipment>`（步兵 / 装甲兵）
        # ⚠️ 查不到就**退回内部 id** —— 绝不自己翻译（规范 §5.7）。
        skills, generals = {}, {}
        for _h in (data.get("hqs") or []):
            for _br, _items in (_h.get("branches") or {}).items():
                for _it in (_items or []):
                    if isinstance(_it, dict) and _it.get("action"):
                        _a = str(_it["action"])
                        if _a not in skills:
                            skills[_a] = ((_tr.get("id_tooltip_hq_bar_" + _a, "")
                                           or _tr.get("id_" + _a, "")) if _tr else "") or _a
            if _h.get("general"):
                _g = str(_h["general"])
                if _g not in generals:
                    generals[_g] = {
                        "cn": (_tr.get("id_" + _g + "_brief", "") if _tr else "") or _g,
                        "full": (_tr.get("id_" + _g + "_full", "") if _tr else "") or "",
                    }
        data["skills"] = skills
        data["generals"] = generals
        # 战区资产的中文名 = locale `id_<asset>_view`（如 id_air_supply_view → 空中补给）
        # ⚠️ **全集 7 种都要有名字**（U45）—— 界面要列没在存档里的那些候选。
        _t_assets = [str(a.get("asset")) for a in (data.get("theater_assets") or [])
                     if isinstance(a, dict)]
        _t_assets += [str(u.get("asset")) for u in (data.get("theater_universe") or [])
                      if isinstance(u, dict)]
        data["theater_cn"] = {
            a: (((_tr.get("id_" + a + "_view", "") if _tr else "") or a))
            for a in _t_assets
        }
        data["equipment_cn"] = {
            e: ((_tr.get("id_equipment_type_" + e, "") if _tr else "") or e)
            for e in ("infantry", "armor")
        }

        # 战线中文名（§5.7）—— 商店页的 tab 原来直接显示 id（caucasus / south）
        try:
            from save_modifier_core.campaigns import (CampaignData,
                                                     default_campaign_index)
            _cd = CampaignData(CorePaths.discover(), default_campaign_index())
            _cid = save.info.campaign_id
            _fs: dict[str, str] = {}
            for _e in (data.get("store") or []):
                _f = str(_e.get("front") or "")
                if _f and _f not in _fs:
                    _fs[_f] = _cd.front_name(_f, _cid) or _f
            data["front_names"] = _fs
        except Exception:
            data["front_names"] = {}

        # 手牌 / 货架的**格数上限跟难度走**（e158 字节码实证）：
        #   手牌 card_deck_limit  = easy 5 / normal 5 / classic 4 / hard 3
        #   货架 card_store_limit = 四个难度恒为 5
        # ⚠️ 界面找空槽位必须按这个上限找 —— classic 只有 4 个槽位。
        try:
            from save_modifier_core.handlers import CARD_DECK_LIMIT, CARD_STORE_LIMIT
            _lv = str((save.root_main() or {}).get("level") or "")
            data["hand_limit"] = CARD_DECK_LIMIT.get(_lv, 5)
            data["shelf_limit"] = CARD_STORE_LIMIT.get(_lv, 5)
            data["level"] = _lv
        except Exception:
            data["hand_limit"] = 5
            data["shelf_limit"] = 5
            data["level"] = ""

        # 卡牌白名单 —— **本存档 + 本会议**的状态，每次重算（规范 §7.5.1）
        try:
            wl = catalog.card_whitelist(save)
            data["card_whitelist"] = {
                "allowed": wl.allowed_types(),
                "blocked": dict(wl.blocked),
                "conference": wl.conference,
                "campaign_id": wl.campaign_id,
                "player_faction": wl.player_faction,
            }
        except Exception:
            data["card_whitelist"] = {"allowed": [], "blocked": {}}
        return data


# ---------------------------------------------------------------- 目录 / 选择器
#
# 「中文名从哪来」：**只**来自游戏包 `localization/chi/strings.yml`（规范 §5.7）。
# 目录里的类型定义（`entity_types/*.yml`）只给**键**（`name_brief`），
# 中文要拿键去 locale 查 —— 查不到就退回内部 id，**绝不自己翻译**。

#: 游戏包目录的进程内缓存 —— 装好游戏后不会变，别每次请求都重扫 600 多个 YAML。
_CATALOG_CACHE: dict | None = None


def _catalog_payload() -> dict:
    """游戏包目录：单位类型 / 特种兵 / 卡牌 / 国籍 + 中文名。"""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE

    from save_modifier_core import Catalog, CorePaths, locale

    paths = CorePaths.discover()
    catalog = Catalog(paths)
    tr = locale.default()

    def cn(key, fallback: str = "") -> str:
        """查一条中文；查不到退回 `fallback`（一般是内部 id）。"""
        if not key:
            return fallback
        return tr.get(key, "") or fallback

    #: 难度列表（游戏常量 `play_levels`）—— 中文名查 locale，
    #: `deck_limit` = 该难度的**手牌上限**（`card_deck_limit`，改难度时用来判冲突）。
    from save_modifier_core.handlers import CARD_DECK_LIMIT, PLAY_LEVELS
    levels = [
        {"id": lv, "cn": cn("id_difficulty_" + lv, lv),
         "deck_limit": CARD_DECK_LIMIT.get(lv, 5)}
        for lv in PLAY_LEVELS
    ]

    unit_types: dict = {}
    for name in catalog.unit_type_names():
        t = catalog.unit_type(name)
        if t is None:
            continue
        unit_types[name] = {
            "cn": cn(t.name_brief, name),
            "faction": t.faction,
            "nationality": t.nationality,
            "movement": t.movement,
            "attack": t.attack,
            "defense": t.defense,
            "armor": t.armor,
            "max_st": t.max_st,
            "max_spec": t.max_spec,
            "step_icon": t.step_icon(),
            "equipment": t.equipment,
        }

    spec_types: dict = {}
    #: 特种兵「特性」的中文名（locale 键 `id_sheet_spec_flag_<flag>`）——
    #: 查不到就**退回英文 flag**（**绝不自己翻译**，§5.7）。
    spec_flags: dict[str, str] = {}
    for name in catalog.spec_type_names():
        s = catalog.spec_type(name)
        if s is None:
            continue
        for _f in (s.flags or []):
            spec_flags.setdefault(_f, cn("id_sheet_spec_flag_" + _f, _f))
        spec_types[name] = {
            "cn": cn(s.name_brief, name),
            "full": cn(s.name_full, ""),
            "faction": s.faction,
            "nationality": s.nationality,
            "attack": s.attack,
            "defense": s.defense,
            "armor": s.armor,
            "artillery": s.artillery,
            "flags": list(s.flags),
        }

    card_types: dict = {}
    for name in catalog.card_type_names():
        d = catalog.card_type(name) or {}
        card_types[name] = {
            "cn": cn(d.get("title"), name),
            "subtitle": cn(d.get("subtitle"), ""),
            "description": cn(d.get("description"), ""),
            "cost": d.get("cost"),
            "faction": d.get("faction"),
            "has_unit": bool(d.get("has_unit")),
            "image": d.get("image"),
            "meta_type": d.get("meta_type"),
            "theater_asset": d.get("theater_asset"),
            "image_resolved": _resolve_card_image(name, d),
        }

    nationalities: dict = {}
    for name in catalog.nationality_names():
        n = catalog.nationality(name)
        nationalities[name] = {
            "cn": cn(n.name_brief if n else None, name),
            "short": cn(n.short if n else None, ""),
            "faction": n.faction if n else None,
            "parent": n.parent_nationality if n else None,
        }

    _CATALOG_CACHE = {
        "levels": levels,
        "unit_types": unit_types,
        "spec_types": spec_types,
        "card_types": card_types,
        "nationalities": nationalities,
        "spec_flags": spec_flags,
    }
    return _CATALOG_CACHE


def _resolve_card_image(card_type: str, info: dict) -> str:
    """卡牌贴图 —— `image` 字段**不总是**等于文件名。

    实测：`image='cards/generic_para'` 的文件其实是
    `logo_divisional_para_allies_1.png` ⇒ 直接按 image 拼路径会 404。

    ⇒ 按候选链找**第一个真实存在**的相对路径（找不到就退回 image 猜测值，
    前端会显示占位块，§5.6）。
    """
    rel = str(info.get("image") or ("cards/" + card_type)).replace("\\", "/")
    base = rel.split("/")[-1]
    b2 = base
    for suf in ("_allies", "_axis", "_soviet"):
        if b2.endswith(suf):
            b2 = b2[: -len(suf)]
            break
    cands = []
    for p in ("bgt_", "bgmf_", "bgm_", "logo_"):
        cands.append(p + base + ".png")
    cands.append(base + ".png")
    for p in ("bgt_", "bgmf_", "bgm_", "logo_"):
        cands.append(p + b2 + ".png")
    cands.append(b2 + ".png")
    cands.append("logo_" + card_type + ".png")
    cands.append("bgt_" + card_type + ".png")
    for c in cands:
        if find_surface("cards/" + c) is not None:
            return "cards/" + c
    return rel + ".png"


def api_catalog() -> dict:
    """`GET /api/catalog` —— 游戏包目录（静态，进程内缓存）。"""
    return _catalog_payload()


def api_pickers(save_id: str, unit_type: str = "") -> dict:
    """`GET /api/pickers` —— 各页选择器的候选。

    * `specialists_for_unit` —— 某个单位类型能挂的特种兵（战役池 ∩ 游戏规则）
    * `campaign_pool`      —— 该战役的特种兵池（总部兵库 / 商店上架用）
    * `store_universe`     —— 游戏自己在该战役该会议会卖的东西（**上架的校验依据**）
    * `cards`              —— 本存档本会议的卡牌白名单（**每次开卡牌页重算，不缓存**）
    """
    from save_modifier_core import Catalog, CorePaths, open_save

    catalog = Catalog(CorePaths.discover())
    with open_save(save_id) as save:
        info = save.info
        campaign_id = info.campaign_id

        names: list[str] = []
        scope = "none"
        if unit_type:
            names, scope = catalog.specialist_candidates(
                unit_type, campaign_id=campaign_id)
        pool = sorted(catalog.campaign_specialist_pool(campaign_id))

        conference = None
        try:
            pos = save.campaign_position()
            conference = getattr(pos, "conference_id", None)
        except Exception:
            conference = None

        universe = catalog.store_item_universe(campaign_id, conference)
        wl = catalog.card_whitelist(save)
        return {
            "unit_type": unit_type,
            "specialists_for_unit": {"candidates": list(names), "scope": scope},
            "campaign_pool": pool,
            # ⚠️ `store_item_universe()` 的键是**单数**（equipment / nationality / spec）
            "store_universe": {
                "equipment": sorted(universe.get("equipment") or []),
                "nationality": sorted(universe.get("nationality") or []),
                "spec": sorted(universe.get("spec") or []),
            },
            "cards": {
                "allowed": wl.allowed_types(),
                "blocked": dict(wl.blocked),
                "conference": wl.conference,
                "campaign_id": wl.campaign_id,
                "player_faction": wl.player_faction,
            },
        }


def _theater_assets_of(save) -> list:
    """当前战斗的**战区资产**（按 `phase` 取当前那一组）。

    ⚠️ `theater_assets` 是按 phase 分组的（U20 实测）⇒ 只给当前 phase 那组，
    别把别的阶段的混进来。
    """
    try:
        data = save.battle_main()
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    theater = data.get("theater_assets")
    if not isinstance(theater, list) or not theater:
        return []
    phase = data.get("phase")
    idx = (phase if isinstance(phase, int) and not isinstance(phase, bool)
           and 0 <= phase < len(theater) else 0)
    items = theater[idx]
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append({
            "asset": it.get("asset"),
            "to_use": it.get("to_use"),
            "uses_total": it.get("uses_total"),
            "uses_turn": it.get("uses_turn"),
        })
    return out


def _theater_universe_of(save, catalog) -> tuple[list, dict]:
    """战区资产的**全量候选**（U45）。

    返回 `(universe, meta)`：

    * `universe` —— 游戏那 **7 种**候选，每项：
      `{asset, has_texture, in_current, in_other, other_count, scenario,
        scenario_uses_total, scenario_uses_turn, added}`
      * `in_current` —— **当前 phase** 那一组里有没有它；
      * `in_other`  —— 别的 phase 组里有没有它（那些组不生效，只是留着）；
      * `scenario` —— **这场战斗本来有没有**它（场景定义）；
      * `added`     —— 场景本来没有、现在有了 ⇒ **「无中生有」的那一项**。
    * `meta` —— `{editable, reason, phase, phase_count, groups, scenario_source,
      scenario_found}`。

    ⚠️ `scenario_source` 的数据源优先级：
    **存档自带**的 `document/scenarios/<场景>/main.yml` → **游戏包**里的场景定义。
    （前者是「这份存档这场战斗开打时的设计」，后者是「游戏现在怎么定义的」。）
    """
    caps = save.capabilities()
    editable = bool(getattr(caps, "can_edit_theater_assets", False))
    reason = "" if editable else caps.unavailable_reason("theater_assets")

    try:
        data = save.battle_main()
    except Exception:
        data = {}
    theater = data.get("theater_assets") if isinstance(data, dict) else None
    phase = data.get("phase") if isinstance(data, dict) else None

    groups: list[list] = []
    if isinstance(theater, list):
        for grp in theater:
            groups.append([it for it in grp if isinstance(it, dict)]
                          if isinstance(grp, list) else [])
    idx = (phase if isinstance(phase, int) and not isinstance(phase, bool)
           and 0 <= phase < len(groups) else 0)
    current = groups[idx] if groups else []

    other: dict[str, int] = {}
    for i, grp in enumerate(groups):
        if i == idx:
            continue
        for it in grp:
            a = it.get("asset")
            if isinstance(a, str):
                other[a] = other.get(a, 0) + 1

    # 场景定义：这场战斗**本来**有哪些战区资产
    scenario: dict = {}
    try:
        scenario = save.document_theater_assets() or {}
    except Exception:
        scenario = {}
    if not scenario:
        try:
            scen = save.current_scenario()
            if scen:
                cid = getattr(save.info, "campaign_id", None) or None
                scenario = catalog.scenario_theater_assets(scen, cid) or {}
        except Exception:
            scenario = {}

    universe = []
    for it in catalog.theater_asset_universe():
        name = str(it.get("asset"))
        cur = next((x for x in current if x.get("asset") == name), None)
        defn = scenario.get(name)
        universe.append({
            "asset": name,
            "has_texture": bool(it.get("has_texture")),
            "in_current": cur is not None,
            "in_other": name in other,
            "other_count": other.get(name, 0),
            "scenario": defn is not None,
            "scenario_uses_total": (defn or {}).get("uses_total"),
            "scenario_uses_turn": (defn or {}).get("uses_turn"),
            "added": defn is None and cur is not None,
        })

    meta = {
        "editable": editable,
        "reason": reason,
        "phase": idx,
        "phase_count": len(groups),
        "groups": groups,
        "scenario_source": scenario,
        "scenario_found": bool(scenario),
    }
    return universe, meta


def _summary_of(obj) -> str:
    """`summary` 在不同结果类上**有的方法是属性** —— 两种都要认。"""
    v = getattr(obj, "summary", "")
    if callable(v):
        try:
            v = v()
        except Exception:
            v = ""
    return str(v or "")


def _edits_from(payload):
    """把前端传来的 `[{kind, params}]` 转成核心库的 `Edit` 列表。

    ⚠️ `Edit.__post_init__` 会校验 `kind` 必须在 `EDIT_KINDS` 里 —— 非法 kind 直接抛。
    """
    from save_modifier_core.edits import Edit

    out = []
    for item in (payload or {}).get("edits") or []:
        if not isinstance(item, dict):
            raise ValueError("每条编辑必须是 {kind, params} 字典")
        kind = item.get("kind")
        params = item.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("params 必须是字典")
        out.append(Edit(kind, params))
    return out


def find_surface(rel: str):
    """在游戏包里找 `assets/surfaces/<rel>` —— **用户包优先**（mod 覆盖）。

    返回 `Path` 或 `None`。找不到**不报错**（界面退化成占位方块，§5.6）。
    ⚠️ `package_roots()` 是**容器**目录（`_packages`）；真正的包在它下面
    （`base` / `dlc1` … / 用户 mod）⇒ 要用 `packages()`。
    """
    from save_modifier_core import CorePaths

    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    paths = CorePaths.discover()
    for pkg in paths.packages():
        cand = Path(pkg) / "assets" / "surfaces" / rel
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


# ---------------------------------------------------------------- 战役页 / 撤销栈


def api_campaign_detail(save_id: str) -> dict:
    """战役页的三块：**路线图** / **场景名册** / **这场会议的商店**。

    ⚠️ 名册与会议商店来自**游戏包**（战役包默认配置），**不是玩家存档** ——
    单位不一定存活 / 一定继承 / 一定登场（§7.8）。
    """
    from save_modifier_core import CorePaths, open_save
    from save_modifier_core.campaigns import CampaignData, default_campaign_index

    paths = CorePaths.discover()
    with open_save(save_id) as save:
        try:
            pos = save.campaign_position()
        except Exception as exc:
            return {"error": str(exc)}
        cid = pos.campaign_id or save.info.campaign_id
        if not cid:
            return {"error": "这个存档没有战役信息（独立场景？）"}
        index = default_campaign_index()
        data = CampaignData(paths, index)

        # 路线图：挑**包含当前会议**的那条路线
        cur = pos.conference_id
        routes = list(index.routes(cid))
        chosen_route, confs = None, ()
        for r in routes:
            cs = index.conferences(cid, r)
            if any(c.id == cur for c in cs):
                chosen_route, confs = r, cs
                break
        if chosen_route is None:
            chosen_route = routes[0] if routes else "historical"
            confs = index.conferences(cid, chosen_route)
        cur_idx = next((i for i, c in enumerate(confs) if c.id == cur), -1)

        route = []
        for i, c in enumerate(confs):
            route.append({
                "id": c.id, "text": c.text,
                "scenes": [{"id": s.id, "name": s.name, "variant": s.variant}
                           for s in c.scenes],
                "done": i < cur_idx,
                "now": i == cur_idx,
            })

        roster = None
        if pos.scenario_id:
            r = data.roster(cid, pos.scenario_id)
            if r is not None:
                roster = _jsonable(r)
                # 名册单位的 name_brief 是**本地化键** ⇒ 翻成中文（§5.7）
                try:
                    from save_modifier_core import locale as _locale2
                    _tr2 = _locale2.default()
                    for _u in (roster.get("units") or []):
                        _u["name_cn"] = (_tr2.get(str(_u.get("name_brief") or ""), "")
                                          or str(_u.get("name_brief") or ""))
                    for _h in (roster.get("hqs") or []):
                        _h["name_cn"] = (_tr2.get(str(_h.get("name_brief") or ""), "")
                                         or str(_h.get("name_brief") or ""))
                except Exception:
                    pass

        store = None
        if pos.front and cur:
            sl = data.store(cid, pos.front, cur)
            if sl is not None:
                store = _jsonable(sl)

        # 战线中文名（§5.7）—— 「已激活战线」原来直接显示 id
        front_names: dict[str, str] = {}
        try:
            for _f in data.fronts(cid):
                front_names[_f] = data.front_name(_f, cid) or _f
        except Exception:
            front_names = {}
        active_fronts = [str(f) for f in (getattr(pos, "fronts", None) or [])]
        active_front_names = [front_names.get(f, f) for f in active_fronts]

        return {
            "campaign_id": cid,
            "route_name": chosen_route,
            "route": route,
            "roster": roster,
            "store": store,
            "position": _jsonable(pos),
            "front_names": front_names,
            "active_front_names": active_front_names,
        }


def api_undo_stack(save_id: str) -> dict:
    """撤销栈 + 备份文件列表（概览页的「备份与撤销栈」面板）。"""
    from save_modifier_core import open_save
    from save_modifier_core.undo import load_stack

    with open_save(save_id) as save:
        path = Path(save.path)
        records, _ = load_stack(path)
        stack = [{"id": r.id, "time": r.time, "summary": r.summary,
                  "entries": [e.entry for e in r.entries]} for r in reversed(records)]
        # 备份文件：存档旁边的 <名字>_BACKUP.usg / _BACKUP_2.usg …
        backups = []
        try:
            for p in sorted(path.parent.glob(path.stem + "_BACKUP*.usg")):
                backups.append({"name": p.name, "size": p.stat().st_size,
                                "mtime": _mtime(p.stat().st_mtime)})
        except OSError:
            pass
        return {"stack": stack, "backups": backups,
                "undo_available": bool(records),
                "count": len(records)}


def api_plan(payload) -> dict:
    """规划一批编辑（**不碰磁盘**）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    save_id = (payload or {}).get("save_id") or ""
    catalog = Catalog(CorePaths.discover())
    with open_save(save_id) as save:
        plan = save.plan_edit(_edits_from(payload), catalog=catalog)
        # 备份文件名提前算出来给确认框显示（写盘前就能告诉玩家备份叫什么）
        try:
            from save_modifier_core.writer import backup_path_for
            backup = backup_path_for(Path(save.path)).name
        except Exception:
            backup = ""
        return {
            "ok": plan.ok,
            "errors": list(plan.errors),
            "warnings": list(plan.warnings),
            "notes": list(plan.notes),
            "backup": backup,
            "save_name": Path(save.path).name,
            "changes": [{"entry": c.entry, "notes": list(c.notes),
                         "diff": c.diff, "layer": c.layer,
                         "is_l3_exception": c.is_l3_exception}
                        for c in plan.changes],
        }


def api_commit(payload) -> dict:
    """提交一批编辑（备份 → 写回 → 压撤销栈）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    save_id = (payload or {}).get("save_id") or ""
    catalog = Catalog(CorePaths.discover())
    with open_save(save_id) as save:
        plan = save.plan_edit(_edits_from(payload), catalog=catalog)
        if not plan.ok:
            return {"ok": False, "errors": list(plan.errors),
                    "warnings": list(plan.warnings), "changes": []}
        res = save.commit(plan)
        return {"ok": res.ok or res.nothing_to_do,
                "nothing_to_do": bool(res.nothing_to_do),
                "errors": list(res.errors),
                "warnings": list(res.warnings),
                "changed": list(res.changed),
                "backup": str(res.backup) if res.backup else "",
                "summary": _summary_of(res)}


def api_undo(payload) -> dict:
    """撤销上一次提交（核心库自己的撤销栈）。"""
    from save_modifier_core import open_save

    save_id = (payload or {}).get("save_id") or ""
    with open_save(save_id) as save:
        if not save.undo_available():
            return {"ok": False, "errors": ["没有可撤销的改动"], "summary": ""}
        r = save.undo()
        return {"ok": bool(getattr(r, "ok", True)),
                "errors": list(getattr(r, "errors", []) or []),
                "summary": _summary_of(r)}


# ---------------------------------------------------------------- HTTP


class _Handler(BaseHTTPRequestHandler):
    server_version = "UOC2Web/1.0"

    # 路由里放 token
    token = ""

    def log_message(self, fmt, *args):     # 安静点
        pass

    # ---- 工具 ----
    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _check_token(self) -> bool:
        got = self.headers.get("X-Token") or ""
        if not got:
            q = parse_qs(urlparse(self.path).query)
            got = (q.get("t") or [""])[0]
        if not got or not secrets.compare_digest(got, self.token):
            self._json({"error": "token 无效"}, 403)
            return False
        return True

    # ---- GET ----
    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)

        if path.startswith("/api/"):
            if not self._check_token():
                return
            try:
                if path == "/api/saves":
                    self._json(api_saves())
                elif path.startswith("/api/view/"):
                    sid = path[len("/api/view/"):]
                    self._json(api_view(sid))
                elif path == "/api/catalog":
                    self._json(api_catalog())
                elif path == "/api/pickers":
                    q = parse_qs(urlparse(self.path).query)
                    sid = (q.get("save_id") or [""])[0]
                    ut = (q.get("unit_type") or [""])[0]
                    self._json(api_pickers(sid, ut))
                elif path == "/api/campaign-detail":
                    q = parse_qs(urlparse(self.path).query)
                    sid = (q.get("save_id") or [""])[0]
                    self._json(api_campaign_detail(sid))
                elif path == "/api/undo-stack":
                    q = parse_qs(urlparse(self.path).query)
                    sid = (q.get("save_id") or [""])[0]
                    self._json(api_undo_stack(sid))
                else:
                    self._json({"error": "未知接口"}, 404)
            except Exception as exc:                     # 绝不让一条坏请求炸掉服务
                self._json({"error": "%s: %s" % (type(exc).__name__, exc)}, 500)
            return

        # ---- 游戏贴图（代理；http 页面不能直接读 file://）----
        if path.startswith("/surfaces/"):
            if not self._check_token():
                return
            target = find_surface(path[len("/surfaces/"):])
            if target is None:
                self._send(404, b"surface not found", "text/plain; charset=utf-8")
                return
            ctype = mimetypes.guess_type(str(target))[0] or "image/png"
            try:
                self._send(200, target.read_bytes(), ctype)
            except OSError:
                self._send(404, b"surface unreadable", "text/plain; charset=utf-8")
            return

        # ---- 静态文件 ----
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError:
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        if not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        if not path.startswith("/api/"):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        if not self._check_token():
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            self._json({"ok": False, "errors": ["请求体不是合法 JSON：%s" % exc]}, 400)
            return
        try:
            if path == "/api/plan":
                self._json(_jsonable(api_plan(payload)))
            elif path == "/api/commit":
                self._json(_jsonable(api_commit(payload)))
            elif path == "/api/undo":
                self._json(_jsonable(api_undo(payload)))
            else:
                self._json({"ok": False, "errors": ["未知接口"]}, 404)
        except ValueError as exc:
            # 请求体不合法（非法 kind / params 不是字典 …）⇒ 400，不是 500
            self._json({"ok": False, "errors": [str(exc)]}, 400)
        except Exception as exc:
            self._json({"ok": False, "errors": ["%s: %s" % (type(exc).__name__, exc)]}, 500)


# ---------------------------------------------------------------- 启动


def _serve_forever(httpd):
    httpd.serve_forever(poll_interval=0.3)


def run(serve_only: bool = False, no_window: bool = False) -> int:
    """起服务 + 拉起 Edge 独立窗口；窗口关掉 ⇒ 服务一起退。"""
    token = secrets.token_urlsafe(16)
    _Handler.token = token

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=_serve_forever, args=(httpd,), daemon=True).start()
    url = "http://127.0.0.1:%d/?t=%s" % (port, token)
    print("[OK ] GUI 服务已启动：%s" % url)

    if no_window:
        print("（--no-window：只起服务，不拉窗口）")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()
        return 0

    if serve_only:
        print("（--serve：自己开浏览器）")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()
        return 0

    edge = find_edge()
    if not edge:
        print("[NG ] 找不到 Edge —— 请装 Edge，或用 --serve 模式自己开浏览器。")
        httpd.shutdown()
        return 1

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [edge, "--app=" + url, "--user-data-dir=" + str(PROFILE_DIR),
         "--no-first-run", "--no-default-browser-check",
         # ⚠️ **强制缩放系数 = 1**（U34 实测踩坑）：
         #   Windows 有 150% 缩放时，Edge 的 CSS 视口 ≈ 物理像素 / 1.5
         #   ⇒ 1690 物理像素的窗口只有 ~1050 CSS 像素 ⇒ 视觉稿的两栏布局
         #   会被窄屏规则折叠成一栏。锁成 1 之后 **CSS px == 物理 px**，
         #   窗口多大就是多少 CSS 像素，和视觉稿（1440×900）对得上。
         "--force-device-scale-factor=1",
         "--window-size=1500,940",
         "--disable-features=Translate,msEdgeSidebarV2,msEdgeShoppingAssistant"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[OK ] Edge 独立窗口已启动（pid=%d）—— 关掉窗口即退出。" % proc.pid)
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        httpd.shutdown()
    return 0


def check() -> int:
    """自检（不弹窗）：起服务 → 探接口 → 探贴图 → 退出。

    用来回答「装好了没 / 能不能跑」：游戏目录、存档列表、贴图代理、
    Edge 在不在，一项一项报出来。
    """
    import urllib.request

    ok = True
    token = secrets.token_urlsafe(16)
    _Handler.token = token
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=_serve_forever, args=(httpd,), daemon=True).start()
    base = "http://127.0.0.1:%d" % port

    def get(path):
        req = urllib.request.Request(base + path)
        req.add_header("X-Token", token)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()

    try:
        st, _, body = get("/api/saves")
        n = len(json.loads(body.decode("utf-8")).get("saves") or [])
        print("[OK ] 存档列表接口正常 —— %d 个存档" % n)
    except Exception as exc:
        print("[NG ] 存档列表接口失败：%s" % exc)
        ok = False

    try:
        st, ct, body = get("/surfaces/unit/ger_inf_42/sheet_L.png")
        good = body[:4] == b"\x89PNG"
        print("[%s ] 贴图代理：%s（%d 字节）"
              % ("OK" if good else "NG", ct, len(body)))
        ok = ok and good
    except Exception as exc:
        print("[NG ] 贴图代理失败：%s" % exc)
        ok = False

    edge = find_edge()
    if edge:
        print("[OK ] Edge：%s" % edge)
    else:
        print("[NG ] 找不到 Edge —— 装 Edge，或用 run_web.bat --serve 自己开浏览器")
        ok = False

    httpd.shutdown()
    print("自检" + ("通过" if ok else "失败"))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return check()
    return run(serve_only="--serve" in argv, no_window="--no-window" in argv)


if __name__ == "__main__":
    sys.exit(main())
