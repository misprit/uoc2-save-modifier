"""页面注册表。

**顺序 = Rail 上的顺序**（与《GUI设计规范.md》§2 的页面表一致）：

| # | 页 | 能力位 |
|---|---|---|
| 1 | 概览 | 恒可用 |
| 2 | 单位 | `can_edit_units`（**特种兵挂载并入本页**） |
| 3 | 总部 | `can_edit_hqs` |
| 4 | 卡牌 | `can_edit_hand` / `can_edit_shelf` |
| 5 | 商店 | `can_edit_store` |
| 6 | 战区资产 | `can_edit_theater_assets` |

> ⚠ 2026-11-18 用户拍板（U9）：原第 3 行「特种兵」**整页取消** ——
> 挂载 / 卸下是"某个单位的事"，跟单位放在一起才对。
> 详见《GUI设计规范.md》§2.3 / §7.3。
"""

from __future__ import annotations

from .base import Page, SimplePage
from .overview import OverviewPage
from .stubs import (CardsPage, HqPage, StorePage, TheaterPage, UnitsPage)

__all__ = ["PAGES", "Page", "OverviewPage", "UnitsPage",
           "HqPage", "CardsPage", "StorePage", "TheaterPage"]

#: 页面类列表（顺序即 Rail 顺序）
PAGES = [
    OverviewPage,
    UnitsPage,
    HqPage,
    CardsPage,
    StorePage,
    TheaterPage,
]
