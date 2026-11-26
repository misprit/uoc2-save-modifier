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
import re
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

    #: 存档打不开（文件损坏）时用这个异常 ⇒ 界面显示一句人话
from save_modifier_core import SaveUnreadable  # noqa: E402
#: 战区资产的组 = **阵营**（不是"阶段"）⇒ 按 side 定位
from save_modifier_core.container import (  # noqa: E402
    theater_group_index, theater_sides)

WEB_DIR = Path(__file__).resolve().parent / "web"

#: ⚠️ **预热导入核心库**（U74 踩到的坑）
#:
#: 浏览器会在**同一瞬间**并发请求 `/api/settings` 与 `/api/i18n`，
#: 两个线程若同时第一次 `import save_modifier_core` ⇒ importlib 的模块锁
#: **死锁**（`_DeadlockError: deadlock detected by _ModuleLock`）⇒ 两个请求都 500。
#: ⇒ 启动时先 import 一次，之后任何请求都不再触发导入。
try:
    import save_modifier_core  # noqa: F401
except Exception:            # pragma: no cover - 核心库不在时照样能起服务
    pass

#: Edge 的常见安装位置（U26 实测：`--app=` 模式能给独立窗口、无地址栏）
EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge Beta\Application\msedge.exe",
)

#: Edge profile 由 paths.py 统一定位；启动时动态取值以尊重环境变量覆盖。


# ---------------------------------------------------------------- 日志
#
# ⚠️ **外部测试者出问题时要能报告** —— 浏览器窗口一关，console 窗口也跟着关
# ⇒ 日志必须落到文件：`%LOCALAPPDATA%\.uoc2\modifier.log`
# （token **打码**；超过 1MB 轮转一次）。

_LOG_MAX = 1024 * 1024
_TOKEN_RE = re.compile(r"([?&]t=)[^&\s\"]+")


def _log_path():
    """日志文件路径（取不到就返回 None ⇒ 不写日志）。"""
    try:
        from save_modifier_core.paths import modifier_log_path
        return modifier_log_path()
    except Exception:
        return None


def _log(text):
    """追加一行日志（失败就算了，绝不影响主流程）。"""
    p = _log_path()
    if p is None:
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > _LOG_MAX:
            data = p.read_bytes()[-(_LOG_MAX // 3):]
            p.write_bytes(b"...[truncated]...\n" + data)
        with p.open("a", encoding="utf-8") as f:
            f.write(str(text).rstrip() + "\n")
    except Exception:
        pass


def _log_startup():
    """启动头：版本 / 解释器 / 游戏目录 / 存档目录（给测试者贴给开发者用）。"""
    import platform
    import sys
    __version__ = _version()
    try:
        from save_modifier_core.paths import CorePaths
        paths = CorePaths.discover()
        game_dir = str(paths.game_dir) if paths.game_dir else "(not found)"
        save_root = str(paths.save_root)
    except Exception:
        game_dir = save_root = "(unknown)"
    _log("=" * 60)
    _log("[start] %s | v%s | python %s (%s)"
         % (platform.platform(), __version__, sys.version.split()[0],
            platform.machine()))
    _log("[env] game dir = %s" % game_dir)
    _log("[env] save root = %s" % save_root)
    _log("[env] log = %s" % (_log_path(),))
    try:
        from save_modifier_web.version import AUTHOR
        _log("[author] %s" % AUTHOR)
    except Exception:
        pass


def _version() -> str:
    """成品版本号（`save_modifier_web/version.py` 是唯一来源）。"""
    try:
        from .version import __version__
        return __version__
    except Exception:
        try:
            from save_modifier_web.version import __version__
            return __version__
        except Exception:
            return "?"


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


#: 跟着界面语言的战役索引（按语言缓存）
_CAMP_INDEX: dict = {}


def _campaign_index(paths=None):
    """内置战役索引 —— **名字跟着界面语言**。

    ⚠️ 核心库的 `default_campaign_index()` 用的是**中文** locale
    ⇒ 战役名 / 会议名 / 场景名在英文界面下还是中文
    ⇒ 这里自己建一份（核心库不动）。
    """
    from save_modifier_core.campaigns import load_campaign_index
    from save_modifier_core.locale import TranslationStore
    from save_modifier_core.paths import CorePaths

    paths = paths or CorePaths.discover()
    lang = data_language()
    hit = _CAMP_INDEX.get(lang)
    if hit is None:
        hit = load_campaign_index(locale=_tr_store(lang))
        _CAMP_INDEX[lang] = hit
    return hit


def _campaign_data(paths=None):
    """战役包数据 —— **战线名跟着界面语言**。

    ⚠️ `CampaignData.locale` 默认是核心库的 `locale.default()`（**中文**）
    ⇒ 英文界面下战线名还是「高加索 / 南部」。
    ⇒ 这里在**显示层**把它换成跟着界面语言的那一份（核心库一个字不改）。
    """
    from save_modifier_core.campaigns import CampaignData
    from save_modifier_core.paths import CorePaths

    paths = paths or CorePaths.discover()
    cd = CampaignData(paths, _campaign_index(paths))
    cd.locale = _tr_store(data_language())
    return cd


def _localize_name(tr, cid, sid=None, pkg=None):
    """按**游戏 locale** 解析一个名字（找不到就返回空串）。"""
    if sid:
        for k in ("id_scenario_name_s_%s_c_%s_p_base" % (sid, cid),
                  "id_scenario_name_s_%s_p_base" % sid):
            v = tr.get(k)
            if v:
                return v
        return ""
    if pkg:
        v = tr.get("id_campaign_name_c_%s_p_%s" % (cid, pkg))
        return v or ""
    return ""


def _localize_position(cp, cid, paths):
    """战役位置里的**名字**跟着界面语言（战役 / 会议 / 战线 / 场景）。"""
    if not isinstance(cp, dict):
        return cp
    tr = _tr_store(data_language())
    # 战役名（包名从内置索引拿：dlc4 / base …）
    try:
        for pkg in (_campaign_index(paths).campaign_packages(cid) or []):
            v = _localize_name(tr, cid, pkg=pkg)
            if v:
                cp["campaign_name"] = v
                break
    except Exception:
        pass
    # 场景名（当前场景 + 可选场景列表）
    sid = str(cp.get("scenario_id") or "")
    if sid:
        v = _localize_name(tr, cid, sid=sid)
        if v:
            cp["scenario_name"] = v
    for s in (cp.get("available_scenes") or []):
        if isinstance(s, dict):
            v = _localize_name(tr, cid, sid=str(s.get("id") or ""))
            if v:
                s["name"] = v
    # 战线名
    front = str(cp.get("front") or "")
    if front:
        try:
            v = _campaign_data(paths).front_name(front, cid)
            if v:
                cp["front_name"] = v
        except Exception:
            pass
    # 会议名（第N次会议 ⇒ Meeting N）
    txt = str(cp.get("conference_text") or "")
    if txt:
        cp["conference_text"] = tr_error(txt)
    return cp


def _save_display(info) -> str:
    """存档的可读名（**跟着界面语言**）。

    ⚠️ 核心库的 `SaveInfo.display_name` 是**中文属性** ⇒ 英文界面下由这里另拼。
    """
    if ui_language() != "en":
        return info.display_name
    base = info.name
    if info.standalone_scenario:
        return "%s (Standalone scenario · %s)" % (base, info.standalone_scenario)
    if info.campaign_id:
        return "%s (Campaign · %s)" % (base, info.campaign_id)
    return base


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
            "display": _save_display(info),
            "campaign": info.campaign_name or info.campaign_id or "",
            "scenario": info.scenario or "",
            "kind": ("战役" if info.kind == "campaign" else "独立场景")
                     if ui_language() == "chi" else
                     ("Campaign" if info.kind == "campaign" else "Standalone scenario"),
            # 在**玩家自建的归档目录**里？（游戏只认 campaigns / games）
            "archived": bool(info.archived),
            "mtime": _mtime(info.mtime),
            "size": _size(info.size),
        })
    return {"saves": rows}


def _save_id_checked(save_id: str) -> str:
    """游戏数据目录保持原边界；程序目录只允许导入根内的 .usg 副本。"""
    from save_modifier_core import paths as core_paths

    raw = (save_id or "").strip()
    if not raw:
        raise ValueError("没有指定存档")
    appdata = Path(core_paths.appdata_dir()).resolve()
    root = (appdata / "save").resolve()
    try:
        # 相对路径按存档根拼；绝对路径直接用（下面统一再核对边界）
        cand = Path(raw) if Path(raw).is_absolute() else (root / Path(*raw.split("/")))
        real = cand.resolve()
    except OSError as exc:
        raise ValueError("存档路径打不开：%s" % exc)
    try:
        rel = real.relative_to(root)
    except ValueError:
        if real.is_relative_to(appdata) or (real.suffix.lower() == ".usg" and
                any(real.is_relative_to(p.absolute()) for p in core_paths.import_roots())):
            return str(real)
        raise ValueError("存档不在允许的数据目录里（拒绝越界访问）：%s" % raw)
    if str(rel) == ".":
        raise ValueError("这不是一个存档文件：%s" % raw)
    return rel.as_posix()


def api_view(save_id: str) -> dict:
    """某个存档的完整只读投影（概览页 / 各功能页用）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    catalog = Catalog(CorePaths.discover())
    with open_save(_save_id_checked(save_id)) as save:
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
        # 单位页过滤器 #2「当前场景激活的单位」的数据源
        # （`games/<场景>/units.yml` 的扁平 id 名单；**只在战斗中才有**）。
        data["battle_unit_ids"] = list(view.battle_unit_ids)
        data["in_battle"] = bool(caps.in_battle)
        # ⚠️ `SaveInfo.name` / `display_name` 是**属性**，不是 dataclass 字段
        # ⇒ `_jsonable` 不会输出它们 ⇒ 前端拿不到存档名（U42 实测 Header 显示「—」）。
        try:
            # `display_name` 是核心库的**中文属性** ⇒ 英文界面下走 `_save_display()`
            data["save"]["display_name"] = _save_display(view.save)
            data["save"]["file_name"] = view.save.name
        except Exception:
            pass

        # ---- 6 个功能页各自要的东西（U33 补齐）----
        # 战区资产：**玩家那一方**（L3 例外的只读侧；U143：组 = 阵营）
        data["theater_assets"] = _theater_assets_of(save, "player")
        # 对手那一方（敌方也有战区资产 —— 存档里就在另一组）
        data["theater_assets_opponent"] = _theater_assets_of(save, "opponent")
        # 战区资产**全量候选**（U45）：7 种全集 + 每种在存档里的状态
        # + 「这场战斗本来有没有」的场景定义对照。
        data["theater_universe"], data["theater_meta"] = _theater_universe_of(save, catalog)
        # 战役位置（只读）
        try:
            pos = save.campaign_position()
            data["campaign_position"] = _jsonable(pos)
            # 战役位置里的**名字**跟着界面语言
            try:
                _cp = data.get("campaign_position")
                if isinstance(_cp, dict):
                    _cid2 = _cp.get("campaign_id") or save.info.campaign_id
                    if _cid2:
                        _localize_position(_cp, _cid2, CorePaths.discover())
            except Exception:
                pass
        except Exception as exc:
            data["campaign_position"] = {"error": str(exc)}
        # 单位 / 总部的 `name_brief` / `name_full` 存的是**本地化键**
        # （如 `id_unit_name_brief_97_dot__J_ger`）⇒ 这里查 locale 翻成中文。
        # ⚠️ 查不到就**原样返回**（玩家自己起的名字是明文，不是键）。
        # ⚠️ 中文一律来自游戏包 `localization/chi/strings.yml` —— 不自己翻译（§5.7）。
        _tr = None
        try:
            _tr = _tr_store(data_language())
            #: 名字回退链 = **当前语言 → 英文 → 内部 id**
            _pick = _name_lookup(data_language())
            for _u in (data.get("units") or []):
                _u["name_cn"] = _pick(_u.get("name_brief") or "", _u.get("name_brief") or "")
                _u["full_cn"] = _pick(_u.get("name_full") or "", _u.get("name_full") or "")
            for _h in (data.get("hqs") or []):
                _h["name_cn"] = _pick(_h.get("name_brief") or "", _h.get("name_brief") or "")
                _h["full_cn"] = _pick(_h.get("name_full") or "", _h.get("name_full") or "")
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
        # 作战标记（HQ 技能的三种命令）—— 显示名跟着界面语言
        try:
            from save_modifier_core.container import ORDER_LISTS, ORDER_LOCALE_KEYS
            data["orders_meta"] = {
                k: {"key": k,
                    "name": ((_tr.get(ORDER_LOCALE_KEYS[k], "") if _tr else "")
                             or k),
                    "icon": "sheet/special_defense_%s.png" % k}
                for k in ORDER_LISTS
            }
            data["orders_available"] = bool(save.battle_dir())
        except Exception:
            data["orders_meta"] = {}
            data["orders_available"] = False
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

        # 商店的**结构**（战线 → 子商店）—— ⚠️ 要**独立于条目**取（B-11）：
        #   下架全部 / 买空之后 store.yml **仍然存在**，只是列表空了
        #   ⇒ 前端要能区分「文件不存在」与「文件存在但为空」
        #   ⇒ 只靠条目推战线的话，一清空就误判成「没有商店数据」。
        try:
            _rs = save.root_store()
            data["store_structure"] = {
                str(_f): [str(_s) for _s in (_v or {})]
                for _f, _v in _rs.items() if isinstance(_v, dict)
            }
        except Exception:
            data["store_structure"] = {}

        # 战线中文名（§5.7）—— 商店页的 tab 原来直接显示 id（caucasus / south）
        # ⚠️ 同样**从结构取**：商店清空后战线名不能跟着丢。
        try:
            _cd = _campaign_data()
            _cid = save.info.campaign_id
            _fs: dict[str, str] = {}
            for _f in (data.get("store_structure") or {}):
                _fs[str(_f)] = _cd.front_name(str(_f), _cid) or str(_f)
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

    from save_modifier_core import Catalog, CorePaths

    paths = CorePaths.discover()
    catalog = Catalog(paths)
    #: 显示名回退链 = **当前语言 → 英文 → 内部 id**（U83）
    cn = _name_lookup(data_language())

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
            "move": t.move,
            "attack": t.attack,
            "defense": t.defense,
            "armor": t.armor,
            # 防御装甲 + 「装甲机动单位」判定（「反击」的硬约束）
            "armor_def": t.armor_def,
            "armor_mobile": t.armor_mobile,
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


def api_pickers(save_id: str, unit_type: str = "",
                unit_types: str = "") -> dict:
    """`GET /api/pickers` —— 各页选择器的候选。

    * `specialists_for_unit` —— 某个单位类型能挂的特种兵（战役池 ∩ 游戏规则）
    * `campaign_pool`      —— 该战役的特种兵池（总部兵库 / 商店上架用）
    * `store_universe`     —— 游戏自己在该战役该会议会卖的东西（**上架的校验依据**）
    * `cards`              —— 本存档本会议的卡牌白名单（**每次开卡牌页重算，不缓存**）

    **U104**：传 `unit_types=a,b,c`（逗号分隔）⇒ 额外返回
    `specialists_by_unit = {类型: {candidates, scope}}` ——
    一次开存档、一次算战役池，把**所有单位类型**的候选池一次算完
    （前端进单位页时拉一次 ⇒ 之后切单位是即时的；单次请求 370 ms，
    逐个拉 13 种类型要 13 次往返）。
    """
    from save_modifier_core import Catalog, CorePaths, open_save

    catalog = Catalog(CorePaths.discover())
    with open_save(_save_id_checked(save_id)) as save:
        info = save.info
        campaign_id = info.campaign_id

        names: list[str] = []
        scope = "none"
        if unit_type:
            names, scope = catalog.specialist_candidates(
                unit_type, campaign_id=campaign_id)
        pool = sorted(catalog.campaign_specialist_pool(campaign_id))
        # 批量 —— 一次算齐所有单位类型的候选池
        by_unit: dict[str, dict] = {}
        for t in [x for x in (unit_types or "").split(",") if x]:
            if t in by_unit:
                continue
            try:
                n2, s2 = catalog.specialist_candidates(t, campaign_id=campaign_id)
            except Exception:
                continue
            by_unit[t] = {"candidates": list(n2), "scope": s2}

        conference = None
        try:
            pos = save.campaign_position()
            conference = getattr(pos, "conference_id", None)
        except Exception:
            conference = None

        universe = catalog.store_item_universe(campaign_id, conference)
        wl = catalog.card_whitelist(save)
        # 玩家「挂得上的」特种兵 —— 与**单位页挂载特种兵**同一个函数
        # （`specialist_candidates`）：玩家**自己阵营**的每个单位类型的候选池取并集。
        # ⚠️ 存档里**也有 AI 的单位**（west 存档 45 个单位里有德国 / 意大利的）
        # ⇒ 必须按 `player_faction` 过滤，否则会把敌方的也带进来。
        # ⚠️ 只收 scope == "campaign" 的 —— 「仅规则」的兜底会把敌方的也带进来。
        player_faction = wl.player_faction
        player_specs: set[str] = set()
        try:
            unit_types = {u.get("type") for u in save.root_units()
                          if isinstance(u, dict) and u.get("type")}
        except Exception:
            unit_types = set()
        for ut in sorted(x for x in unit_types if x):
            if player_faction:
                ut_obj = catalog.unit_type(ut)
                if ut_obj is not None and ut_obj.faction \
                        and ut_obj.faction != player_faction:
                    continue
            try:
                names, scope = catalog.specialist_candidates(ut, campaign_id=campaign_id)
            except Exception:
                continue
            if scope != "campaign":
                continue
            player_specs.update(names)
        return {
            "unit_type": unit_type,
            # 玩家阵营 + 「挂得上的」特种兵（商店上架 / 兵库加条目用）
            "player_faction": player_faction,
            "player_specs": sorted(player_specs),
            "specialists_for_unit": {"candidates": list(names), "scope": scope},
            # 批量拿到的「每种单位类型的候选池」
            "specialists_by_unit": by_unit,
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


def _theater_assets_of(save, side: str = "player") -> list:
    """某一方的**战区资产**（按**阵营**取那一组）。

    ⚠️ `theater_assets` 是**按阵营分组**的（组下标 = 阵营下标，U143 更正）
    ⇒ 只给 `side` 指的那一组，别把另一方的混进来。

    ⚠️ `side="opponent"` 在**双 `player: local`**（hotseat）时
    取「玩家那一方之外的那一侧」⇒ 两组不重合（U153）。
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
    # ⚠️ 组 = **阵营**（不是"阶段"）⇒ 按 side 定位
    idx = theater_group_index(data, side)
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
        scenario_uses_total, scenario_uses_turn, added,
        opponent_scenario, opponent_scenario_uses_total,
        opponent_scenario_uses_turn}`
      * `in_current` —— **玩家那一方**那组里有没有它（历史别名，语义已是「两方」）；
      * `in_other`  —— **另一方**那组里有没有它；
      * `scenario` —— **玩家那一方**的场景定义里有没有它；
      * `opponent_scenario*` —— **另一方**的场景定义（**各自一份**，别混）；
      * `added`     —— 场景本来没有、现在有了 ⇒ **「无中生有」的那一项**。
    * `meta` —— `{editable, reason, phase, phase_count, groups, sides,
      player_index, opponent_index, scenario_source, scenario_found}`。
      * `sides` —— 两个阵营（`{key, index, is_player, is_current}`）；
      * `player_index` / `opponent_index` —— 两方各对应**哪一组**
        （前端按它对齐阵营页签 ⇒ 不用 `is_player` 布尔，U153）。

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
    # ⚠️ 组 = **阵营**（不是"阶段"）⇒
    #   `current` = **玩家那一方**（`factions` 里 `player: local` 的下标），
    #   `other`   = **对手那一方**。
    #   以前按 `phase`（当前行动方）⇒ 轮到 AI 时会把**敌方那组当成自己的**。
    player_idx = theater_group_index(data, "player")
    opponent_idx = theater_group_index(data, "opponent")
    current = groups[player_idx] if groups else []
    opponent = groups[opponent_idx] if groups else []

    other: dict[str, int] = {}
    for it in opponent:
        a = it.get("asset")
        if isinstance(a, str):
            other[a] = other.get(a, 0) + 1

    # 场景定义：这场战斗**本来**有哪些战区资产
    # ⚠️ **U141 + U143**：场景定义里的资产**也是两组 = 两个阵营各一组**
    # ⇒ 参照值必须取**玩家那一方**（不是"当前行动方"那一组，
    #    否则轮到 AI 行动时给的是**敌方那方的设计**）。
    player_idx = theater_group_index(data, "player")
    opponent_idx = theater_group_index(data, "opponent")

    def _scenario_of(idx: int) -> dict:
        """某一方的**场景设计**（存档自带的副本优先，其次游戏包）。"""
        out: dict = {}
        try:
            out = save.document_theater_assets(idx) or {}
        except Exception:
            out = {}
        if not out:
            try:
                scen = save.current_scenario()
                if scen:
                    cid = getattr(save.info, "campaign_id", None) or None
                    out = catalog.scenario_theater_assets(scen, cid,
                                                         phase=idx) or {}
            except Exception:
                out = {}
        return out

    scenario = _scenario_of(player_idx)          # 玩家那一方
    scenario_opp = _scenario_of(opponent_idx)    # 对手那一方

    universe = []
    for it in catalog.theater_asset_universe():
        name = str(it.get("asset"))
        cur = next((x for x in current if x.get("asset") == name), None)
        defn = scenario.get(name)
        universe.append({
            "asset": name,
            "has_texture": bool(it.get("has_texture")),
            # **玩家那一方 / 对手那一方**（旧的 in_current / in_other
            #        保留为别名，语义同步改成"两方"）
            "in_player": cur is not None,
            "in_opponent": name in other,
            "in_current": cur is not None,
            "in_other": name in other,
            "other_count": other.get(name, 0),
            "scenario": defn is not None,
            "scenario_uses_total": (defn or {}).get("uses_total"),
            "scenario_uses_turn": (defn or {}).get("uses_turn"),
            # **对手那一方**的设计（各自的参照值，别混）
            "opponent_scenario": (scenario_opp.get(name) is not None),
            "opponent_scenario_uses_total":
                (scenario_opp.get(name) or {}).get("uses_total"),
            "opponent_scenario_uses_turn":
                (scenario_opp.get(name) or {}).get("uses_turn"),
            "added": defn is None and cur is not None,
        })

    meta = {
        "editable": editable,
        "reason": reason,
        "phase": idx,
        "phase_count": len(groups),
        # ⚠️ 两组分别属于哪一方（`player: local` / `player: ai`）
        "sides": theater_sides(data),
        "player_index": player_idx,
        "opponent_index": opponent_idx,
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

    ⚠️ **U120：路径穿越防护** —— `rel` 直接来自 HTTP 请求路径
    （`do_GET` 里有 `unquote(u.path)` ⇒ `%2e%2e%2f` 会变成 `../`），
    **绝不能**让它逃出 `assets/surfaces/`：

    * `Path("C:/Windows/win.ini")` 在 Windows 上是**绝对路径** ⇒
      `Path(pkg) / "assets" / "surfaces" / rel` 会把前半段**整个替换掉**
      ⇒ 等于「任意文件读取」（外部审阅报告 P0-1）；
    * `..` 段同理。

    ⇒ **三道闸**：① 逐段白名单校验（空段 / `.` / `..` / 带冒号的一律拒）；
    ② 解析（`resolve`）后必须**仍在 `assets/surfaces/` 里面**；
    ③ 才看它是不是文件。
    """
    from save_modifier_core import CorePaths

    rel = (rel or "").replace("\\", "/")
    if not rel:
        return None
    parts = rel.split("/")
    # ① 逐段校验
    for p in parts:
        if p in ("", ".", "..") or ":" in p:
            return None
    paths = CorePaths.discover()
    for pkg in paths.packages():
        try:
            base = (Path(pkg) / "assets" / "surfaces").resolve()
            cand = (base / Path(*parts)).resolve()
        except (OSError, ValueError, RuntimeError):
            continue
        # ② 必须仍在 surfaces 目录**里面**（防盘符 / 防符号链接）
        if cand == base or base not in cand.parents:
            continue
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


# ---------------------------------------------------------------- 文件浏览 / 另存为


def _fs_roots(paths) -> list:
    """文件浏览器的快捷入口（游戏存档目录 / 桌面 / 文档 / 各盘根）。"""
    out = []
    home = Path.home()
    for label, p in (("游戏存档目录", paths.save_root),
                     ("桌面", home / "Desktop"),
                     ("文档", home / "Documents"),
                     ("下载", home / "Downloads")):
        try:
            if p.is_dir():
                out.append({"label": label, "path": str(p)})
        except OSError:
            continue
    if os.name == "nt":
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            try:
                root = Path(ch + ":\\")
                if root.is_dir():
                    out.append({"label": ch + ":\\", "path": str(root)})
            except OSError:
                continue
    return out


def api_fs_list(dir_path: str) -> dict:
    """列一个目录 —— **内置文件浏览器**用（U67）。

    ⚠️ 这是**用户主动**打开的本地文件浏览器（界面里点「打开其他位置的存档」），
    和「静态文件服务」不是一回事 —— 后者有目录穿越防护，前者本来就是给人翻盘的。
    """
    from save_modifier_core import CorePaths

    paths = CorePaths.discover()
    raw = (dir_path or "").strip()
    try:
        d = Path(raw).expanduser().resolve() if raw else paths.save_root.resolve()
    except OSError as exc:
        return {"ok": False, "error": "路径无效：%s" % exc}
    if not d.is_dir():
        return {"ok": False, "error": "不是目录：%s" % d, "dir": str(d)}
    dirs, files = [], []
    try:
        for p in sorted(d.iterdir(), key=lambda x: x.name.lower()):
            try:
                if p.is_dir():
                    dirs.append({"name": p.name, "path": str(p)})
                elif p.is_file() and p.suffix.lower() == ".usg":
                    st = p.stat()
                    files.append({"name": p.name, "path": str(p),
                                  "size": _size(st.st_size), "bytes": st.st_size})
            except OSError:
                continue
    except OSError as exc:
        return {"ok": False, "error": "读目录失败：%s" % exc, "dir": str(d)}
    parent = str(d.parent) if d.parent != d else ""
    return {"ok": True, "dir": str(d), "parent": parent,
            "dirs": dirs, "files": files, "roots": _fs_roots(paths)}


def api_import_save(payload) -> dict:
    """拖进来的存档 —— 存成**副本**放到修改器自己的导入目录。

    ⚠️ **浏览器拿不到拖入文件的完整路径**（File API 只给 name / size / 内容）
    ⇒ 只能收字节 ⇒ 落成副本；**改动只作用在副本上**，原文件一个字节都不动。
    想直接改原文件 ⇒ 用「打开其他位置的存档…」（那条路走的是文件浏览器，能拿到路径）。
    """
    import base64

    from save_modifier_core import CorePaths

    paths = CorePaths.discover()
    raw_name = ((payload or {}).get("name") or "").strip()
    # 只取文件名 —— 不要路径
    name = raw_name.replace("\\", "/").split("/")[-1] or "imported.usg"
    if not name.lower().endswith(".usg"):
        name += ".usg"
    b64 = (payload or {}).get("data") or ""
    try:
        data = base64.b64decode(b64, validate=True)
    except Exception as exc:
        return {"ok": False, "errors": ["数据不是合法的 base64：%s" % exc]}
    if not data:
        return {"ok": False, "errors": ["文件是空的"]}
    if not data.startswith(b"PK"):
        return {"ok": False, "errors": ["这不像存档文件（.usg 应该是 zip 包）"]}
    from save_modifier_core.paths import modifier_imports_dir
    imp = modifier_imports_dir()
    try:
        imp.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "errors": ["建不了导入目录：%s" % exc]}
    target = imp / name
    n = 2
    while target.exists():
        target = imp / ("%s_%d%s" % (Path(name).stem, n, Path(name).suffix))
        n += 1
    try:
        target.write_bytes(data)
    except OSError as exc:
        return {"ok": False, "errors": ["写文件失败：%s" % exc]}
    return {"ok": True, "path": str(target), "save_id": str(target),
            "bytes": len(data), "summary": "已导入副本 %s" % target.name}


def api_settings() -> dict:
    """当前设置：**游戏本体目录** + 包列表 + 探测候选（界面要能告诉玩家找过哪儿）。"""
    from save_modifier_core import CorePaths
    from save_modifier_core import paths as core_paths

    paths = CorePaths.discover()
    disabled = core_paths.disabled_packages(paths.uoc2_appdata, paths.game_dir)
    return {
        "game_dir": str(paths.game_dir) if paths.game_dir else "",
        "found": bool(paths.game_dir),
        "packages": [str(p) for p in paths.packages()],
        # 被游戏**整包禁用**的 mod（not_moddable 规则命中）⇒ 修改器也不读
        "disabled_packages": [{"path": k, "rule": v} for k, v in disabled.items()],
        # 界面语言（用户选的 / 跟随游戏）与数据名字的语言
        "ui_language": ui_language(),
        "game_language": _game_language(),
        "data_language": data_language(),
        "available_languages": list(UI_LANGUAGES),
        # Steam 创意工坊里的 mod 包（zip 里还没解压的也算 ⇒ 已并入参考数据）
        "workshop_packages": [
            {"kind": w["kind"], "pkg": w["pkg"], "item": w["item"],
             "path": str(w["path"])}
            for w in core_paths.workshop_package_sources()],
        "candidates": core_paths.game_dir_candidates(),
        "config_path": str(core_paths.config_path()),
        # 版本号（测试者要能说清自己用的哪版）+ 日志文件（出问题贴给开发者）
        "version": _version(),
        "log_file": str(_log_path() or ""),
    }


def api_settings_set(payload) -> dict:
    """设置**游戏本体目录**（写设置文件）。

    ⚠️ 只记一个路径 —— **不移动任何文件**；
    ⚠️ 目录不像游戏本体（没有 `_packages` / `lib/uoc2`）⇒ 直接拒绝。
    """
    from save_modifier_core import CorePaths
    from save_modifier_core import paths as core_paths

    gd = ((payload or {}).get("game_dir") or "").strip()
    if not gd:
        return {"ok": False, "errors": ["没有指定目录"]}
    try:
        p = core_paths.set_game_dir(gd)
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)]}
    except OSError as exc:
        return {"ok": False, "errors": ["写设置失败：%s" % exc]}
    paths = CorePaths.discover()
    return {"ok": True, "game_dir": str(p),
            "packages": [str(x) for x in paths.packages()],
            "summary": "游戏本体目录已设为 %s" % p}


def api_save_as(payload) -> dict:
    """「另存为」—— 把存档（**可含待应用改动**）写成一个新的 .usg 文件。

    ⚠️ 三条硬规矩：
    1. **绝不覆盖已存在的文件** —— 宁可让用户换个名字；
    2. **原存档一个字节都不动**（另存为只是复制一份出来）；
    3. 带改动时，先复制到临时目录 → 在副本上走完整的
       「plan → 备份 → 写回 → 校验」管线 → 再复制到目标位置
       ⇒ 目标文件一定是**合法的存档**，不是一个半成品。
    """
    import shutil
    import tempfile

    from save_modifier_core import Catalog, CorePaths, open_save

    save_id = (payload or {}).get("save_id") or ""
    dest_raw = ((payload or {}).get("dest") or "").strip()
    edits = (payload or {}).get("edits") or []
    if not save_id:
        return {"ok": False, "errors": ["没有指定存档"]}
    if not dest_raw:
        return {"ok": False, "errors": ["没有指定保存位置"]}
    dest = Path(dest_raw).expanduser()
    if dest.suffix.lower() != ".usg":
        dest = dest.with_name(dest.name + ".usg")
    if dest.exists():
        return {"ok": False,
                "errors": ["目标文件已存在：%s（不会覆盖，换个名字）" % dest.name]}
    if not dest.parent.is_dir():
        return {"ok": False, "errors": ["目录不存在：%s" % dest.parent]}
    try:
        with open_save(_save_id_checked(save_id)) as save:
            src = Path(save.info.path)
    except Exception as exc:
        return {"ok": False, "errors": ["读不到原存档：%s" % exc]}
    if not src.is_file():
        return {"ok": False, "errors": ["原存档不在了：%s" % src]}

    tmpdir = None
    try:
        if edits:
            tmpdir = Path(tempfile.mkdtemp(prefix="uoc2_saveas_"))
            work = tmpdir / dest.name
            shutil.copy2(src, work)
            catalog = Catalog(CorePaths.discover())
            with open_save(str(work)) as wsave:
                # ⚠️ 前端传的是 `[{kind, params}]` ⇒ 要先转成核心库的 Edit 对象
                #    （与 api_commit 走同一条 `_edits_from`）
                plan = wsave.plan_edit(_edits_from({"edits": edits}),
                                           catalog=catalog)
                if not plan.ok:
                    return {"ok": False, "errors": list(plan.errors),
                            "warnings": list(plan.warnings)}
                res = wsave.commit(plan)
                if not res.ok:
                    return {"ok": False, "errors": list(res.errors)}
            shutil.copy2(work, dest)
        else:
            shutil.copy2(src, dest)
    except Exception as exc:
        return {"ok": False, "errors": ["写入失败：%s" % exc]}
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        size = dest.stat().st_size
    except OSError:
        size = 0
    return {"ok": True, "path": str(dest), "bytes": size,
            "with_edits": bool(edits),
            "summary": "已另存为 %s" % dest.name}


# ---------------------------------------------------------------- 界面语言（U74）

#: 修改器**界面**支持的语言（用户拍板：只做英语）
UI_LANGUAGES = ("chi", "en")

#: 界面语言 ↔ 游戏本地化目录名
LANG_DIR = {"chi": "chi", "en": "eng"}

_I18N_CACHE = None      # (mtime, 词表)


def _i18n_table() -> dict:
    """词表（`web/i18n.json`）—— 界面文案 + 报错文案。

    ⚠️ **按 mtime 失效** —— 改了词表不用重启服务。
    """
    global _I18N_CACHE
    p = WEB_DIR / "i18n.json"
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _I18N_CACHE is not None and _I18N_CACHE[0] == mtime:
        return _I18N_CACHE[1]
    try:
        import json as _json
        data = _json.loads(p.read_text(encoding="utf-8"))
        table = data if isinstance(data, dict) else {}
    except Exception:
        table = {}
    _I18N_CACHE = (mtime, table)
    return table


def _game_language() -> str:
    r"""**游戏自己**的语言设置（`%LOCALAPPDATA%\.uoc2\settings.yml` 的 `language`）。"""
    try:
        import re as _re
        from save_modifier_core.paths import CorePaths
        p = CorePaths.discover().uoc2_appdata / "settings.yml"
        m = _re.search(r"^language:\s*(\S+)", p.read_text(encoding="utf-8",
                                                             errors="ignore"),
                       _re.M)
        if m:
            return m.group(1).strip().strip("\"'")
    except Exception:
        pass
    return ""


#: `ui_language()` 的缓存：(设置文件 mtime, 游戏设置 mtime, 语言)
_UI_LANG_CACHE: tuple | None = None


#: 游戏 `settings.yml` 的路径（**缓存** —— `ui_language()` 每次被问都要用，
#: 而 `CorePaths.discover()` 会去扫游戏目录 ⇒ 放在热路径上就是灾难，U81 踩过）
_GAME_SETTINGS: list = []


def _game_settings_path():
    """游戏自己的 `settings.yml` 路径（只查一次）。"""
    if not _GAME_SETTINGS:
        try:
            from save_modifier_core.paths import CorePaths
            _GAME_SETTINGS.append(
                CorePaths.discover().uoc2_appdata / "settings.yml")
        except Exception:
            _GAME_SETTINGS.append(None)
    return _GAME_SETTINGS[0]


def ui_language() -> str:
    """**界面语言**：用户自己选的 > 游戏设置 > 中文。

    ⚠️ 游戏设置里的语言目录名（`chi`/`eng`/`ger`/`rus`）与界面语言不是一回事：
    界面只做中/英 ⇒ 游戏是德语时界面仍是中文，玩家可以用按钮自己切。

    ⚠️ **按 mtime 缓存** —— 翻译每条报错都要问一次语言，
    不能每条都去读两个设置文件。
    ⚠️ **U81**：游戏 settings.yml 的路径也缓存住（别每次 `discover()`）——
    这个函数在热路径上（每个响应节点都会问一次语言）。
    """
    global _UI_LANG_CACHE
    from save_modifier_core.paths import config_path, read_config
    try:
        cfg_mtime = config_path().stat().st_mtime
    except OSError:
        cfg_mtime = 0.0
    gs_path = _game_settings_path()
    try:
        gs_mtime = gs_path.stat().st_mtime if gs_path else 0.0
    except OSError:
        gs_mtime = 0.0
    if _UI_LANG_CACHE is not None and _UI_LANG_CACHE[:2] == (cfg_mtime, gs_mtime):
        return _UI_LANG_CACHE[2]
    picked = (read_config().get("ui_language") or "").strip()
    if picked in UI_LANGUAGES:
        lang = picked
    elif _game_language() == "eng":
        lang = "en"
    else:
        lang = "chi"
    _UI_LANG_CACHE = (cfg_mtime, gs_mtime, lang)
    return lang


#: 按语言的本地化 store（**进程内缓存**）
#:
#: ⚠️ 每次新建 `TranslationStore` 都要重读 11 个包 × 40 个 yml（实测 0.07 s/次）
#:    ⇒ 一个请求里建好几次就是几秒 ⇒ U81 起一律走缓存。
_TR_STORES: dict = {}


def _tr_store(locale: str):
    """按语言的本地化 store（进程内缓存）。"""
    st = _TR_STORES.get(locale)
    if st is None:
        from save_modifier_core.locale import TranslationStore
        from save_modifier_core.paths import CorePaths
        st = TranslationStore(CorePaths.discover(), locale=locale)
        _TR_STORES[locale] = st
    return st


def _name_lookup(data_lang: str):
    """返回一个「查显示名」的闭包：**当前语言 → 英文 → 内部 id**。

    U83（2026-11-20 · 朋友反馈）：mod 常常**只做英文翻译**
    （游戏底层本来就是英文）⇒ 中文界面下查不到中文名时，
    直接退到**英文**，别退到文件名 / 内部 id
    （游戏里显示的是他改的文件名，修改器不该显示得更难看）。

    ⚠️ **只加一级、且只在"查不到"时生效** ——
    游戏自带资源 chi / eng **100% 覆盖**（实测各 16776 键，差集为 0）
    ⇒ 现有显示**一个字符都不会变**。
    ⚠️ **绝不自己翻译**（规范 §5.7）—— 英文也是游戏自己的资源。
    """
    tr = _tr_store(data_lang)
    #: 英文表只在「当前语言不是英文」时才用得上（英文界面下 `tr` 已经是它）
    tr_en = _tr_store("eng") if data_lang != "eng" else None

    def pick(key, fallback: str = "") -> str:
        if not key:
            return fallback
        v = tr.get(key, "")
        if v:
            return v
        if tr_en is not None:
            v = tr_en.get(key, "")
            if v:
                return v
        return fallback

    return pick


def data_language() -> str:
    """**数据名字的语言**（单位/特种兵/卡牌/战役的名字）—— 跟**界面语言**一致。

    ⇒ 界面切到 English，单位/特种兵的名字也从游戏的 `eng` 资源里取
    （键与中文 100% 覆盖 ⇒ 名字一定取得到）。
    """
    return LANG_DIR.get(ui_language(), "chi")


def api_i18n() -> dict:
    """词表 + 当前语言（前端启动时一次拿全）。"""
    table = _i18n_table()
    return {
        "ui": table.get("ui") or {},
        "errors": table.get("errors") or {},
        "language": ui_language(),
        "data_language": data_language(),
        "available": list(UI_LANGUAGES),
    }


def api_language_set(payload) -> dict:
    """设置界面语言（写修改器自己的设置文件；**不动存档**）。"""
    from save_modifier_core.paths import read_config, write_config

    lang = ((payload or {}).get("lang") or "").strip()
    if lang == "auto":
        cfg = read_config()
        cfg.pop("ui_language", None)
        write_config(cfg)
        return {"ok": True, "language": ui_language()}
    if lang not in UI_LANGUAGES:
        return {"ok": False, "errors": ["不支持的语言：%s（只有 %s）"
                                        % (lang, " / ".join(UI_LANGUAGES))]}
    cfg = read_config()
    cfg["ui_language"] = lang
    write_config(cfg)
    return {"ok": True, "language": lang}


#: 词表里「带占位符的模板」编译成的正则（长的在前 ⇒ 更具体的先替）
_ERR_RX_CACHE: tuple | None = None

#: 模板里的占位符 `{name}`
_ERR_PH = re.compile(r"\{([^{}]*)\}")

#: 中文检测（只翻有中文的串）
_CJK = re.compile(r"[\u4e00-\u9fff]")

#: 响应里这些键下的字符串是**给玩家看的文案** ⇒ 逐条翻译
_TR_KEYS = ("error", "errors", "warnings", "notes", "summary", "detail", "reason")


def _err_table() -> dict:
    """报错/警告/摘要的译文表（`i18n.json` 的 `errors` 段）。"""
    return _i18n_table().get("errors") or {}


def _err_values() -> dict:
    """**占位符级别**的值翻译（`i18n.json` 的 `values` 段）。

    例：核心库内部把难度名写死成中文（`普通`），它作为占位符的值出现 ⇒
    按**占位符名字**精确替换，不影响别的上下文。
    """
    return _i18n_table().get("values") or {}


def _compile_err_templates(table: dict):
    """把「带占位符的模板」编译成正则（长的在前）。

    ⇒ 连同**字面量替换表**一起缓存（U81：原来每条报错都要重排一次 266 条）。
    """
    global _ERR_RX_CACHE
    if _ERR_RX_CACHE is not None and _ERR_RX_CACHE[0] is table:
        return _ERR_RX_CACHE[1]
    pats = []
    for tpl, en in table.items():
        if "{" not in tpl:
            continue
        parts, pairs, last, lit = [], [], 0, 0
        for m in _ERR_PH.finditer(tpl):
            chunk = tpl[last:m.start()]
            parts.append(re.escape(chunk))
            lit += len(chunk)
            raw = m.group(1)
            gname = "g%d" % len(pairs)
            pairs.append((raw, gname))
            # ⚠️ **不跨 `；`** —— 核心库用 `；` 把几条错误拼成一串，
            # 一条模板不该把两句话连着吃。
            parts.append("(?P<%s>[^；]*?)" % gname)
            last = m.end()
        tail = tpl[last:]
        parts.append(re.escape(tail))
        lit += len(tail)
        try:
            rx = re.compile("".join(parts), re.S)
        except re.error:                       # 模板写坏了就跳过它
            continue
        pats.append((lit, len(tpl), rx, en, pairs))
    # 字面量多的（更具体的）先替
    pats.sort(key=lambda x: (-x[0], -x[1]))
    out = [(rx, en, pairs) for _, _, rx, en, pairs in pats]
    lits = sorted(((k, v) for k, v in table.items()
                   if "{" not in k and isinstance(v, str)),
                  key=lambda kv: -len(kv[0]))
    _ERR_RX_CACHE = (table, out, lits)
    return out


def _err_literals(table: dict) -> list:
    """字面量替换表（长的在前）—— 随编译缓存一起缓存（U81）。"""
    _compile_err_templates(table)
    return _ERR_RX_CACHE[2]


def _fill_template(en_tpl: str, groups: dict, pairs: list, values: dict,
                   depth: int = 0) -> str:
    """把捕获到的值填进英文模板（值本身也可能要翻译）。

    ⚠️ **值里可能还套着中文** —— 核心库的摘要常常是拼出来的
    （「改了 1 个文件：单位 3 加特种 xxx（槽位 0）」）⇒ 值也要再翻一层。
    """
    out = en_tpl
    for raw, gname in pairs:
        val = groups.get(gname, "")
        if depth < 3 and isinstance(val, str) and _CJK.search(val):
            val = tr_error(val, depth + 1)
        vmap = values.get(raw)
        if vmap:
            for zh, en in vmap.items():
                val = val.replace(zh, en)
        out = out.replace("{%s}" % raw, val)
    return out


def tr_error(text, depth: int = 0, lang: str | None = None) -> str:
    """把**一条**中文报错/警告/摘要翻成英文（**只在显示层**，核心库一个字不改）。

    ① 整条精确匹配；
    ② **模板**匹配 —— 报错里带着真值（`单位 U1 的 xp=900 越界（必须 0..399）`），
       整条匹配不上 ⇒ 把词表里的 `{name}` 占位符编译成正则再匹配；
    ③ 兜底：整串里能认出来的中文片段换掉（核心库把几条错误拼成一串时用）。

    ⚠️ **U81**：`lang` 由调用方传进来（**别在热路径上问语言**）——
    一次响应几十万节点，每个节点问一次语言 ⇒ 每次请求 23 秒。
    """
    if not isinstance(text, str) or not text or not _CJK.search(text):
        return text
    if lang is None:
        lang = ui_language()
    if lang != "en":
        return text
    table = _err_table()
    if not table:
        return text
    exact = table.get(text)
    if isinstance(exact, str):
        return exact
    values = _err_values()
    pats = _compile_err_templates(table)
    out = text
    for rx, en, pairs in pats:                    # ② 整条模板匹配
        m = rx.fullmatch(text)
        if m:
            got = m.groupdict()
            # 捕获到的值里含 `，`/`；` ⇒ 它把后面的分句一起吞了
            # （摘要常常是「……等级 3 → 2，被压制 1 → 0」这种拼出来的）
            # ⇒ 不算整条匹配，交给下面的片段替换。
            if any(("，" in v or "；" in v) for v in got.values()):
                continue
            out = _fill_template(en, got, pairs, values, depth)
            break
    else:
        out = text                               # ③ 片段替换（字面量多的先替）
        for rx, en, pairs in pats:
            def _sub(m, en=en, pairs=pairs):
                return _fill_template(en, m.groupdict(), pairs, values, depth)
            out = rx.sub(_sub, out)
    lits = _err_literals(table)
    for zh, en in lits:
        if zh in out:
            out = out.replace(zh, en)
    # 中文分隔符 → 英文（正文已经翻完了，这两个符号还留着）
    for zh, en in (("；", "; "), ("、", ", ")):
        out = out.replace(zh, en)
    return out


def tr_errors(items, lang: str | None = None) -> list:
    """一批报错/警告逐条翻译。"""
    return [tr_error(x, lang=lang) for x in (items or [])]


def _tr_payload(obj, lang: str | None = None):
    """把响应里**给玩家看的文案**翻成英文（数据本身一个字不动）。

    ⚠️ **U81：语言只算一次**（`lang`）—— 原来每个节点都问一次 `ui_language()`，
    而它要扫游戏目录 ⇒ 一次请求 23 秒（英文模式；中文模式第一行就 return 所以看不出来）。
    """
    if lang is None:
        lang = ui_language()
    if lang != "en":
        return obj
    if isinstance(obj, dict):
        return {k: (_tr_value(v, lang) if k in _TR_KEYS else _tr_payload(v, lang))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_tr_payload(x, lang) for x in obj]
    return obj


def _tr_value(v, lang: str | None = None):
    """一个「文案值」：字符串 ⇒ 翻译；列表/字典 ⇒ 递归。"""
    if isinstance(v, str):
        return tr_error(v, lang=lang)
    if isinstance(v, list):
        return [tr_error(x, lang=lang) if isinstance(x, str)
                else _tr_payload(x, lang) for x in v]
    if isinstance(v, dict):
        return _tr_payload(v, lang)
    return v


# ---------------------------------------------------------------- 战役页 / 撤销栈


def api_campaign_detail(save_id: str) -> dict:
    """战役页的三块：**路线图** / **场景名册** / **这场会议的商店**。

    ⚠️ 名册与会议商店来自**游戏包**（战役包默认配置），**不是玩家存档** ——
    单位不一定存活 / 一定继承 / 一定登场（§7.8）。
    """
    from save_modifier_core import CorePaths, open_save

    paths = CorePaths.discover()
    with open_save(_save_id_checked(save_id)) as save:
        try:
            pos = save.campaign_position()
        except Exception as exc:
            return {"error": str(exc)}
        cid = pos.campaign_id or save.info.campaign_id
        if not cid:
            return {"error": "这个存档没有战役信息（独立场景？）"}
        data = _campaign_data(paths)

        # 路线图：按**关卡**挑线路（U66）——
        #   ① 关卡在**历史线**里有 ⇒ 走历史线；
        #   ② 历史线里没有 ⇒ 去别的线路找这个关卡，用**找到的第一个**。
        # ⚠️ 以前是「按会议找 + 路线按 sorted 遍历」⇒ `"fantasy" < "historical"`
        #    ⇒ **幻想线永远先命中** ⇒ 走历史线的存档显示的是幻想线的关卡。
        cur = pos.conference_id
        chosen_route = data.index.pick_route(cid, cur, pos.scenario_id)
        confs = data.index.conferences(cid, chosen_route)
        cur_idx = next((i for i, c in enumerate(confs) if c.id == cur), -1)

        # 场景名跟着界面语言（内置索引里是**写死的中文**）
        _tr2 = None
        try:
            _tr2 = _tr_store(data_language())
        except Exception:
            _tr2 = None
        route = []
        for i, c in enumerate(confs):
            _scenes = []
            for s in c.scenes:
                _nm = s.name
                if _tr2 is not None:
                    _v = _localize_name(_tr2, cid, sid=str(s.id))
                    if _v:
                        _nm = _v
                _scenes.append({"id": s.id, "name": _nm, "variant": s.variant})
            route.append({
                "id": c.id, "text": tr_error(c.text),
                "scenes": _scenes,
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
                    #: 名字回退链 = **当前语言 → 英文 → 内部 id**
                    _pick2 = _name_lookup(data_language())
                    for _u in (roster.get("units") or []):
                        _u["name_cn"] = _pick2(str(_u.get("name_brief") or ""),
                                               str(_u.get("name_brief") or ""))
                    for _h in (roster.get("hqs") or []):
                        _h["name_cn"] = _pick2(str(_h.get("name_brief") or ""),
                                               str(_h.get("name_brief") or ""))
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

        # 废墟（被摧毁的城市）—— 只读清单（规范 §6.5）
        ruins = save.ruined_cities()

        return {
            "campaign_id": cid,
            "route_name": chosen_route,
            "route": route,
            "roster": roster,
            "store": store,
            "position": _jsonable(pos),
            "front_names": front_names,
            "active_front_names": active_front_names,
            "ruins": _jsonable(ruins),
        }


from save_modifier_web.backup_cleanup import BackupCleanup

_backup_cleanup = BackupCleanup()


def api_backup_preview(save_id: str) -> dict:
    from save_modifier_core import open_save
    with open_save(_save_id_checked(save_id)) as save:
        return {"backups": _backup_cleanup.preview(save.path)}


def api_backup_recycle(payload) -> dict:
    """严格校验后按预览顺序逐件回收备份；失败项及其后续项不冒充成功。"""
    from save_modifier_core import open_save
    if not isinstance(payload, dict) or set(payload) != {"save_id", "ids"}:
        raise ValueError("请求体必须严格包含 save_id 和 ids")
    save_id = payload["save_id"]
    ids = payload["ids"]
    if not isinstance(save_id, str) or not save_id.strip():
        raise ValueError("save_id 必须是非空字符串")
    if not isinstance(ids, list) or not ids:
        raise ValueError("ids 必须是非空列表")
    if any(not isinstance(item, str) for item in ids):
        raise ValueError("ids 只能包含字符串")
    if len(set(ids)) != len(ids):
        raise ValueError("ids 不能重复")
    if any(not re.fullmatch(r"[0-9]{1,16}[.][0-9a-f]{64}", item)
           for item in ids):
        raise ValueError("备份标识无效")

    # 先验证存档边界和存在性，再允许任何回收动作。
    with open_save(_save_id_checked(save_id)) as save:
        completed = []
        for index, item_id in enumerate(ids):
            try:
                _backup_cleanup.recycle_one(save.path, item_id)
            except Exception as exc:
                return {"ok": False, "completed": completed, "failed": item_id,
                        "remaining": ids[index + 1:], "errors": [str(exc)]}
            completed.append(item_id)
    return {"ok": True, "completed": completed, "failed": None,
            "remaining": [], "errors": []}


def api_undo_stack(save_id: str) -> dict:
    """撤销栈 + 备份文件列表（概览页的「备份与撤销栈」面板）。"""
    from save_modifier_core import open_save
    from save_modifier_core.undo import load_stack

    with open_save(_save_id_checked(save_id)) as save:
        path = Path(save.path)
        records, _ = load_stack(path)
        stack = [{"id": r.id, "time": r.time, "summary": r.summary,
                  "entries": [e.entry for e in r.entries]} for r in reversed(records)]
        # ⚠️ 栈顶可能**撤不了**（存档后来又被改过）
        # ⇒ 如实告诉界面「从栈顶往下还有几条真的能撤」，
        #   界面据此禁用撤销按钮、标出「已过期」的记录
        #   （玩家就不会反复点一个注定失败的按钮）。
        undoable = 0
        try:
            from save_modifier_core.undo import baseline_ok
            for rec in reversed(records):
                if not baseline_ok(path, rec):
                    break
                undoable += 1
        except Exception:
            undoable = len(records)
        # 备份文件：U109 起放在 `<修改器目录>/bak/`（游戏看不到、存档目录也干净）；
        # **老位置**（存档旁边）留下的备份也一并列出来（升级前生成的）。
        backups = []
        try:
            from save_modifier_core.paths import backup_dir, fallback_backup_dir
            folders = (backup_dir(), fallback_backup_dir(), path.parent)
        except Exception:
            folders = (path.parent,)
        seen = set()
        for folder in dict.fromkeys(folders):
            try:
                for p in sorted(folder.glob(path.stem + "_BACKUP*.usg")):
                    key = str(p)
                    if key in seen:
                        continue
                    seen.add(key)
                    backups.append({"name": p.name, "path": key,
                                    "size": p.stat().st_size,
                                    "mtime": _mtime(p.stat().st_mtime)})
            except OSError:
                pass
        # 新的在前（备份列表按时间倒序 ⇒ 一眼看到最近那次）
        backups.sort(key=lambda b: b.get("mtime") or "", reverse=True)
        return {"stack": stack, "backups": backups,
                "undo_available": bool(records) and undoable > 0,
                "undoable": undoable,
                "count": len(records)}


def api_plan(payload) -> dict:
    """规划一批编辑（**不碰磁盘**）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    save_id = (payload or {}).get("save_id") or ""
    catalog = Catalog(CorePaths.discover())
    with open_save(_save_id_checked(save_id)) as save:
        plan = save.plan_edit(_edits_from(payload), catalog=catalog)
        # 备份文件**在哪里**提前算出来给确认框显示（写盘前就能告诉玩家）
        try:
            from save_modifier_core.writer import backup_path_for
            bp = backup_path_for(Path(save.path))
            try:
                from save_modifier_core.paths import modifier_home
                backup = str(bp.relative_to(modifier_home()))
            except Exception:
                backup = str(bp)
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
    with open_save(_save_id_checked(save_id)) as save:
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
    with open_save(_save_id_checked(save_id)) as save:
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

    def log_message(self, fmt, *args):     # 不往 console 刷，落到文件
        try:
            line = fmt % args
        except Exception:
            line = str(fmt)
        _log("[http] " + _TOKEN_RE.sub(r"\1***", line))

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
        # ⚠️ **显示层翻译**（U74）：界面是英文时，把报错/警告/摘要翻成英文
        # ⚠️ 语言**只问一次**（整包一个）—— 别每个节点问一遍。
        obj = _tr_payload(obj, lang=ui_language())
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
                    # 批量（一次算齐所有单位类型的候选池）
                    uts = (q.get("unit_types") or [""])[0]
                    self._json(api_pickers(sid, ut, uts))
                elif path == "/api/campaign-detail":
                    q = parse_qs(urlparse(self.path).query)
                    sid = (q.get("save_id") or [""])[0]
                    self._json(api_campaign_detail(sid))
                elif path == "/api/backups/preview":
                    sid = (parse_qs(u.query).get("save_id") or [""])[0]
                    try:
                        self._json(api_backup_preview(sid))
                    except (ValueError, OSError) as exc:
                        self._json({"error": str(exc)}, 400)
                elif path == "/api/undo-stack":
                    q = parse_qs(urlparse(self.path).query)
                    sid = (q.get("save_id") or [""])[0]
                    self._json(api_undo_stack(sid))
                elif path == "/api/fs/list":
                    q = parse_qs(urlparse(self.path).query)
                    self._json(api_fs_list((q.get("dir") or [""])[0]))
                elif path == "/api/settings":
                    self._json(api_settings())
                elif path == "/api/i18n":
                    self._json(api_i18n())
                else:
                    self._json({"error": "未知接口"}, 404)
            except SaveUnreadable as exc:
                # ⚠️ 存档**打不开**（文件坏了）⇒ 这是用户的文件坏了，
                # 不是服务器出错 ⇒ 400 + 一句人话（别甩 BadZipFile 给他看）。
                self._json({"error": str(exc)}, 400)
            except Exception as exc:                     # 绝不让一条坏请求炸掉服务
                import traceback
                _log("[500] %s: %s" % (type(exc).__name__, exc))
                _log(traceback.format_exc())
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
            elif path == "/api/backups/recycle":
                self._json(_jsonable(api_backup_recycle(payload)))
            elif path == "/api/save-as":
                self._json(_jsonable(api_save_as(payload)))
            elif path == "/api/import-save":
                self._json(_jsonable(api_import_save(payload)))
            elif path == "/api/settings":
                self._json(_jsonable(api_settings_set(payload)))
            elif path == "/api/settings/lang":
                self._json(_jsonable(api_language_set(payload)))
            else:
                self._json({"ok": False, "errors": ["未知接口"]}, 404)
        except SaveUnreadable as exc:
            # ⚠️ 存档**打不开**（文件坏了）⇒ 400 + 一句人话
            self._json({"ok": False, "errors": [str(exc)]}, 400)
        except ValueError as exc:
            # 请求体不合法（非法 kind / params 不是字典 …）⇒ 400，不是 500
            if path == "/api/backups/recycle":
                self._json({"ok": False, "completed": [], "failed": None,
                            "remaining": [], "errors": [str(exc)]}, 400)
            else:
                self._json({"ok": False, "errors": [str(exc)]}, 400)
        except Exception as exc:
            import traceback
            _log("[500] %s: %s" % (type(exc).__name__, exc))
            _log(traceback.format_exc())
            self._json({"ok": False, "errors": ["%s: %s" % (type(exc).__name__, exc)]}, 500)


# ---------------------------------------------------------------- 启动


def _serve_forever(httpd):
    httpd.serve_forever(poll_interval=0.3)


def run(serve_only: bool = False, no_window: bool = False,
        no_browser: bool = False) -> int:
    """起服务 + 拉起 Edge 独立窗口；窗口关掉 ⇒ 服务一起退。"""
    token = secrets.token_urlsafe(16)
    _Handler.token = token

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=_serve_forever, args=(httpd,), daemon=True).start()
    url = "http://127.0.0.1:%d/?t=%s" % (port, token)
    print("[OK ] GUI 服务已启动：%s" % url)
    try:
        _log_startup()
    except Exception:
        pass

    if no_window:
        print("（--no-window：只起服务，不拉窗口）")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()
        return 0

    if serve_only:
        if no_browser:
            # 启动器 exe 会自己开浏览器（能管 Edge --app / 默认浏览器，
            # 也能实现「关窗即退」与单实例）⇒ 服务端**不要**碰浏览器。
            print("（--no-browser：只起服务，浏览器交给启动器）")
        else:
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

    from save_modifier_core.paths import modifier_profile_dir
    profile_dir = modifier_profile_dir()
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print("[NG ] 无法创建 Edge profile：%s（%s）。请将程序放在可写目录。" % (profile_dir, exc))
        httpd.shutdown()
        httpd.server_close()
        return 1
    proc = subprocess.Popen(
        [edge, "--app=" + url, "--user-data-dir=" + str(profile_dir),
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
    return run(serve_only="--serve" in argv, no_window="--no-window" in argv,
               no_browser="--no-browser" in argv)


if __name__ == "__main__":
    sys.exit(main())
