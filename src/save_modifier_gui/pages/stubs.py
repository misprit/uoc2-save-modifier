"""其余 5 页的占位实现（G1 阶段）。

**每个页面在它自己的阶段被填实**（G2–G5）：
G2 单位头像 / G3 单位页完整 / G4 待应用面板 / G5 其余各页。

到那时这个文件会被逐个替换成独立模块（`pages/units.py` 等），
`pages/__init__.py` 的注册表指向谁，页面就换谁 —— 界面结构不用动。
"""

from __future__ import annotations

from .base import SimplePage

__all__ = ["UnitsPage", "HqPage", "CardsPage", "StorePage", "TheaterPage"]


class UnitsPage(SimplePage):
    key = "units"
    icon = "▥"
    title = "单位"
    caption = "战力 · 特种兵 · 改名"
    capability = "units"

    def build(self) -> None:
        super().build()
        self.placeholder(
            "单位页（G2–G3）：左侧名册列表（头像 / 兵力段格条），"
            "右侧详情（抬头精简、兵力与经验并排、特种兵挂载区、改名）。\n\n"
            "数值上限在游戏包里 —— 改不了上限，只能改当前值。\n"
            "特种兵挂载**并入本页**（2026-11-18 用户拍板）："
            "点备选图标挂到第一个空槽位，点已挂图标卸下。")


class HqPage(SimplePage):
    key = "hq"
    icon = "▧"
    title = "总部"
    caption = "分支 · 兵库 · CP"
    capability = "hqs"

    def build(self) -> None:
        super().build()
        self.placeholder(
            "总部页：总部列表（经验条 / 分支等级）+ 详情（分支升级、兵库增删、CP）。\n\n"
            "分支降级要二次确认 —— 已投的点不会退回来。")


class CardsPage(SimplePage):
    key = "cards"
    icon = "▨"
    title = "卡牌"
    caption = "手牌 + 商店货架 + 图鉴"
    capability = "cards"

    def build(self) -> None:
        super().build()
        self.placeholder(
            "卡牌页三段式：**手牌**（`cards.yml`）、**货架**（`main.yml.card_store`，"
            "只在会议阶段存在）、**图鉴**（39 种，只读）。\n\n"
            "换牌只允许改成「商店本来就能自然生成」的卡（白名单），"
            "图鉴里被屏蔽的置灰并给出原因。")


class StorePage(SimplePage):
    key = "store"
    icon = "▩"
    title = "商店"
    caption = "普通店 / 精英店"
    capability = "store"

    def build(self) -> None:
        super().build()
        self.placeholder(
            "商店页：按战线分组，**普通店 / 精英店**两个 tab，"
            "可改价、改库存、下架（删条目）、上架新商品。\n\n"
            "库存不能为 0 —— 游戏没有「售罄」标记，要下架请删条目。")


class TheaterPage(SimplePage):
    key = "theater"
    icon = "▪"
    title = "战区资产"
    caption = "只在战斗中"
    capability = "theater_assets"

    def build(self) -> None:
        super().build()
        self.placeholder(
            "战区资产页：当前战斗场景里可用的战区资产（空袭、炮舰轰炸……）"
            "的**可用次数**。\n\n"
            "只在**当前进行中的战斗**里可用；战斗外会被场景重算覆盖。"
            "这是唯一允许写 L3 的地方。")
