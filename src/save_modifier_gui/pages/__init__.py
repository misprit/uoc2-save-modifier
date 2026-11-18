"""页面注册表。

**顺序 = Rail 上的顺序**（与《GUI设计规范.md》§2 的页面表一致）：

| # | 页 | 能力位 |
|---|---|---|
| 1 | 概览 | 恒可用 |
| 2 | 单位 | `can_edit_units` |
| 3 | 特种兵 | `can_edit_units` |
| 4 | 总部 | `can_edit_hqs` |
| 5 | 卡牌 | `can_edit_hand` / `can_edit_shelf` |
| 6 | 商店 | `can_edit_store` |
| 7 | 战区资产 | `can_edit_theater_assets` |
"""

from __future__ import annotations

from .base import Page, SimplePage
from .overview import OverviewPage
from .stubs import (CardsPage, HqPage, SpecialistsPage, StorePage,
                    TheaterPage, UnitsPage)

__all__ = ["PAGES", "Page", "OverviewPage", "UnitsPage", "SpecialistsPage",
           "HqPage", "CardsPage", "StorePage", "TheaterPage"]

#: 页面类列表（顺序即 Rail 顺序）
PAGES = [
    OverviewPage,
    UnitsPage,
    SpecialistsPage,
    HqPage,
    CardsPage,
    StorePage,
    TheaterPage,
]
