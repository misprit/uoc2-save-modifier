"""测试公用工具：定位本机的真实存档。

真实存档不是仓库的一部分（`.gitignore` 排除 `*.usg`），
所以找不到就跳过相关测试，而不是让测试失败。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["save_root", "find_saves", "game_dir", "web_html", "pick_save"]


def save_root() -> Path:
    """游戏存档根目录 `<游戏数据目录>\\save`（默认 `%LOCALAPPDATA%\\.uoc2\\save`）。

    ⚠️ **必须和产品认的路径一致**（U166）：服务端按 **`UOC2_APPDATA`**
    核对存档有没有越界（`save_modifier_core.paths.appdata_dir` ⇒ U126 的安全修复），
    测试这边要是**认另一个根** ⇒ 干净环境自检
    （`release_check --clean` 把 `UOC2_APPDATA` 指到空目录）
    会找到**玩家真实存档**、而服务端又拒绝它 ⇒ 那个性能测试直接报错。

    ⇒ 优先级：`UOC2_SAVE_ROOT` > `UOC2_APPDATA/save` > `%LOCALAPPDATA%/.uoc2/save`
    （与核心库 `paths.appdata_dir()` 同口径）。
    """
    env = os.environ.get("UOC2_SAVE_ROOT")
    if env:
        return Path(env)
    appdata = os.environ.get("UOC2_APPDATA")
    if appdata:
        return Path(appdata) / "save"
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / ".uoc2" / "save"


def game_dir() -> Path | None:
    """游戏安装目录（探测不到返回 None）。"""
    env = os.environ.get("UOC2_GAME_DIR")
    if env:
        return Path(env)
    from save_modifier_core.paths import detect_game_dir
    return detect_game_dir()


def web_html() -> str:
    """前端的 `index.html` 全文。

    要断言"界面上的**静态说明**写了某条知识"时用
    （U146 起：软警告里的知识搬到了界面说明里）。
    """
    import io
    p = (Path(__file__).resolve().parent.parent / "src" / "save_modifier_web"
         / "web" / "index.html")
    return io.open(p, encoding="utf-8", newline="").read()


def find_saves(limit_per_dir: int = 2) -> list[Path]:
    """找出本机的真实存档（战役 / 独立场景 / 历史存档各取几个）。"""
    root = save_root()
    out: list[Path] = []
    for sub in ("campaigns", "games"):
        d = root / sub
        if d.is_dir():
            out.extend(sorted(d.glob("*.usg"))[:limit_per_dir])
    old = root / "Old Saves"
    if old.is_dir():
        out.extend(sorted(old.rglob("*.usg"))[:limit_per_dir])
    return out


def pick_save(predicate, *, reason="本机没有合适的存档"):
    """按**内容**挑一个存档 —— **不看 `list_saves()` 的顺序**。

    ⚠️ **为什么不能拿「第一个」当选择规则**：`list_saves()` 是按 **mtime 倒序**排的
    （`save_modifier_core/discovery.py`）⇒「第一个」= 玩家**最近动过**的那个存档
    ⇒ 玩家一开新档、玩一次，测试挑到的对象就换人 ⇒ 结果会莫名其妙地变红 / 变跳过。
    （实例：2026-11-24 玩家新开了 `fall_blau_2_fall_blau_2.usg`，
    `test_theater_to_use_edit` 与 `test_campaign_detail_has_route_roster_store` 当场变红。）

    ⇒ 这里先把全部存档按 **save_id 字典序**排好，再逐个交给 `predicate` 判，
    **第一个满足条件的**就是答案 ⇒ 选择只跟存档**内容**有关，
    与目录顺序、修改时间都无关 ⇒ 玩家玩不玩游戏都不影响测试结果。

    `predicate` 收到 `SaveInfo`，返回 True 表示可用；
    抛异常当作不可用（跳过该存档）⇒ 一个坏存档不会连累整轮。
    一个都不满足 ⇒ 抛 `unittest.SkipTest`（跳过，不是失败）。
    """
    import unittest

    for info in _all_saves():
        try:
            if predicate(info):
                return info
        except Exception:
            continue
    raise unittest.SkipTest(reason)


#: `list_saves()` 的结果缓存（键 = 游戏数据目录）。
#: ⚠️ `list_saves()` 要挨个打开存档读根 `main.yml`（本机 73 个存档 ≈ 2 秒），
#: 而 `setUp` 每个用例都要调一次 ⇒ 不缓存的话同一个存档列表会被扫几十遍。
#: 缓存键用**数据目录**，测试里切 `UOC2_APPDATA` 时自动换一份，不会串味。
_SAVE_CACHE: dict = {}


def _all_saves() -> list:
    """全部存档（按 **save_id 字典序**排好），按数据目录缓存。"""
    from save_modifier_core.paths import appdata_dir

    key = str(appdata_dir())
    if key not in _SAVE_CACHE:
        from save_modifier_core import list_saves
        _SAVE_CACHE[key] = sorted(list_saves(), key=lambda i: i.save_id)
    return _SAVE_CACHE[key]
