"""能力位 —— 整个修改器的核心设计原则（规范 §3.4.5）。

**按能力实现，不按状态实现。**

70 个存档只是样本，真实玩家会遇到样本里没有的组合（比如"会议发牌后立刻存档"）。
如果按"状态枚举 + switch 分支"实现，遇到没见过的组合就会出错；
按下面的 8 个能力位实现，任何组合都会自然落进正确的行为 ——
**新增状态不需要改任何代码**。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Capabilities"]


@dataclass(frozen=True)
class Capabilities:
    """一个存档的 8 个能力位。

    全部来自**只读观察**，不需要加载游戏本体。
    """

    #: 根 `units.yml` 存在？—— 有没有战役名册可以改单位（实测 67/70）
    has_root_units: bool = False
    #: 根 `hqs.yml` 存在？—— 有没有总部可以改（实测 70/70，恒存在）
    has_root_hqs: bool = False
    #: 根 `cards.yml` 存在？—— 有没有卡牌库存可改（实测 63/70）
    has_root_cards: bool = False
    #: 根 `store.yml` 存在？—— 有没有商店可改（实测 67/70）
    has_root_store: bool = False
    #: 根 `main.yml` 的 `card_store` 非空？—— 玩家是否正停在会议界面（已发牌）
    has_card_store: bool = False
    #: `last_conference/` 存在？—— 有没有会议回退基线（只读，不参与写入决策）
    cp_conference: bool = False
    #: `last_game/` 存在？—— 有没有战斗回退基线（只读，不参与写入决策）
    cp_game: bool = False
    #: `in_state.scenario` 非空？—— 是否在战斗里
    in_battle: bool = False

    # ---- 编辑能力（规范 §3.4.5.2 的能力矩阵）----

    @property
    def can_edit_progress(self) -> bool:
        """声望 / 分数：根 `main.yml` 恒可用（实测 70/70 都有）。"""
        return True

    @property
    def can_edit_units(self) -> bool:
        return self.has_root_units

    @property
    def can_edit_hqs(self) -> bool:
        return self.has_root_hqs

    @property
    def can_edit_force_pool(self) -> bool:
        """总部兵库（`force_pool[].quantity`）—— 存在 HQ 表即可。"""
        return self.has_root_hqs

    @property
    def can_edit_cards(self) -> bool:
        """手牌（根 `cards.yml`）。"""
        return self.has_root_cards

    @property
    def can_edit_store(self) -> bool:
        """商店（`store.yml`）。"""
        return self.has_root_store

    @property
    def can_edit_hand(self) -> bool:
        """手牌（根 `cards.yml`）—— 和 `can_edit_cards` 是一回事。

        ⚠️ **别和货架搞反**：手牌是 `cards.yml`，货架是 `main.yml.card_store`
        （`e157`/`e160` 实证：手牌张数上限 = `card_deck_limit`，货架格数 = `card_store_limit`）。
        """
        return self.has_root_cards

    @property
    def can_edit_shelf(self) -> bool:
        """卡牌商店货架（`main.yml` 的 `card_store`）—— 正停在会议界面时。"""
        return self.has_card_store

    @property
    def can_restore_hand(self) -> bool:
        """恢复上次会议的牌局（读 L2 的 `card_store` → 写 L1）。"""
        return self.cp_conference

    @property
    def can_edit_theater_assets(self) -> bool:
        """战区资产（L3 白名单例外）—— 只在**当前进行中的战斗**里可用。"""
        return self.in_battle

    @property
    def can_undo_in_game(self) -> bool:
        """游戏内有没有回退点（「重置会议」/「重打上一场」）。"""
        return self.cp_conference or self.cp_game

    def unavailable_reason(self, feature: str) -> str:
        """给 GUI 用的禁用原因（中文，直接显示给玩家）。"""
        reasons = {
            "units": "该存档还没有可编辑的单位（战役开局尚未生成名册）",
            "hqs": "该存档没有总部数据",
            "force_pool": "该存档没有总部数据",
            "cards": "该存档没有手牌数据（cards.yml）",
            "store": "该存档没有商店数据",
            "hand": "该存档没有手牌数据（cards.yml）",
            "shelf": "当前不在会议界面，没有卡牌商店货架",
            "restore_hand": "该存档没有会议检查点，无法恢复牌局",
            "theater_assets": "当前不在战斗中，战区资产由场景在开打时计算",
            "ruins": "当前存档正在战斗中 —— 游戏会在存档时从内存重写"
                     "当前战斗目录与根 main.yml，改了会被覆盖回去；"
                     "请先打完这场战斗再修复废墟",
        }
        return reasons.get(feature, "该存档不支持此功能")
