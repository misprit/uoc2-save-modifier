"""编辑请求 —— 核心库对外的结构化"改什么"。

⚠️ **不要接受 YAML 文本。** 用户不写 YAML，工具也不该让用户写（规范 §0.2）。
一次编辑 = 一个 `Edit` 对象，字段是结构化的。

每种 `kind` 对应：

* 一个**目标条目**（ZIP 里的哪个文件）—— 绝大多数是 L1 根目录的 5 个 YAML；
* 一个**能力位要求** —— 不满足就报错，不静默忽略；
* 一段**应用逻辑**（`handlers.py`）与**校验逻辑**（`plan.py`）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["Edit", "EDIT_KINDS"]


#: 全部合法的 kind —— 写错会直接报错，不会静默忽略
EDIT_KINDS = (
    "progress",            # 声望 / 分数（根 main.yml）
    "unit_field",          # 单位的某个字段（根 units.yml）
    "unit_spec_add",       # 加特种（根 units.yml）
    "unit_spec_remove",    # 卸特种（根 units.yml）
    "hq_force_pool",       # 总部兵库数量（根 hqs.yml）
    "hq_field",            # 总部的某个字段（根 hqs.yml）
    "hq_branch_level",     # 总部分支等级（根 hqs.yml）
    "hq_force_pool_add",   # 总部兵库加一条（根 hqs.yml）
    "hq_force_pool_remove",  # 总部兵库删一条（根 hqs.yml）
    "card_add",            # 加卡到手牌（根 cards.yml）
    "card_remove",         # 删手牌（根 cards.yml）
    "card_set",            # 改手牌某个字段（根 cards.yml）
    "store_set",           # 改商店条目字段（根 store.yml）
    "store_remove",        # 下架商店条目 —— 删条目，不是把 quantity 设 0
    "store_add",           # 上架新商品（根 store.yml）
    "card_store_set",      # 改货架上的卡（根 main.yml → card_store）
    "card_store_remove",   # 下架一张卡（根 main.yml → card_store）
    "card_store_add",      # 上架一张卡（根 main.yml → card_store）
    "hand_restore",        # 恢复上次会议的牌局（读 L2 → 写 L1）
    "theater_asset",       # 战区资产（唯一的 L3 例外）
)

#: 商店的两个子商店（`store.yml` = `{战线: {store: [...], elite_store: [...]}}`）
STORE_SUBS = ("store", "elite_store")


@dataclass(frozen=True)
class Edit:
    """一次结构化编辑请求。"""

    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in EDIT_KINDS:
            raise ValueError(
                f"未知的编辑类型 {self.kind!r}；合法取值：{', '.join(EDIT_KINDS)}")

    # ---------------------------------------------------------------- 工厂

    @staticmethod
    def progress(field: str, value: int) -> "Edit":
        """改声望（`prestige`）或分数（`score`）。"""
        return Edit("progress", {"field": field, "value": value})

    @staticmethod
    def unit_field(unit_id: int, field: str, value: Any) -> "Edit":
        """改单位的某个字段：`xp` / `act_st` / `sup_st` / `name_brief` / `name_full`。"""
        return Edit("unit_field",
                    {"unit_id": unit_id, "field": field, "value": value})

    @staticmethod
    def unit_spec_add(unit_id: int, spec_type: str) -> "Edit":
        """给单位挂一个特种。"""
        return Edit("unit_spec_add",
                    {"unit_id": unit_id, "spec_type": spec_type})

    @staticmethod
    def unit_spec_remove(unit_id: int, spec_type: str,
                         idx: int | None = None) -> "Edit":
        """卸一个特种；同名有多个时卸一条（给 `idx` 指定卸哪一条）。"""
        return Edit("unit_spec_remove",
                    {"unit_id": unit_id, "spec_type": spec_type, "idx": idx})

    @staticmethod
    def hq_force_pool(hq_id: int, index: int, quantity: int) -> "Edit":
        """改总部兵库某条目的存量。"""
        return Edit("hq_force_pool",
                    {"hq_id": hq_id, "index": index, "quantity": quantity})

    @staticmethod
    def hq_field(hq_id: int, field: str, value: Any) -> "Edit":
        """改总部的某个字段（经验 / CP / 补给 / 卡车 / 俘虏 …）。"""
        return Edit("hq_field", {"hq_id": hq_id, "field": field, "value": value})

    @staticmethod
    def hq_branch_level(hq_id: int, branch: str, level: int,
                        suppressed: bool | None = None) -> "Edit":
        """改总部的**分支等级**（总部"升级"= 五个分支各一个等级）。"""
        return Edit("hq_branch_level", {"hq_id": hq_id, "branch": branch,
                                        "level": level, "suppressed": suppressed})

    @staticmethod
    def hq_force_pool_add(hq_id: int, entry: Mapping[str, Any],
                          index: int | None = None) -> "Edit":
        """往总部兵库**加一条**（`{delay, nationality, quantity, spec?|equipment?}`）。

        `index` 给了就插在那个位置，不给就追加到末尾。
        """
        return Edit("hq_force_pool_add",
                    {"hq_id": hq_id, "entry": dict(entry), "index": index})

    @staticmethod
    def hq_force_pool_remove(hq_id: int, index: int) -> "Edit":
        """从总部兵库**删一条**。"""
        return Edit("hq_force_pool_remove", {"hq_id": hq_id, "index": index})

    @staticmethod
    def card_add(card_type: str, *, is_free: bool = False,
                 position: int | None = None, unit_id: int | None = None) -> "Edit":
        """加一张卡到手牌。"""
        return Edit("card_add", {
            "card_type": card_type, "is_free": is_free,
            "position": position, "unit_id": unit_id,
        })

    @staticmethod
    def card_remove(position: int) -> "Edit":
        """按槽位号删一张手牌。"""
        return Edit("card_remove", {"position": position})

    @staticmethod
    def card_set(position: int, field: str, value: Any) -> "Edit":
        """改手牌某一张的某个字段（目前只有 `is_free`）。

        ⚠️ 手牌的 `is_free` **没有玩法影响** —— 只改 tooltip 文案与卡背贴图。
        货架上的 `is_free` 才是真价格（`Edit.card_store_set`）。
        """
        return Edit("card_set", {"position": position, "field": field,
                                 "value": value})

    @staticmethod
    def store_set(front: str, sub: str, index: int, field: str,
                  value: Any) -> "Edit":
        """改商店某战线条目的 `price` 或 `quantity`。

        ⚠️ `sub` 是**子商店**（`store` 普通 / `elite_store` 精英）——
        `store.yml` 是两层结构，不带 `sub` 会改错列表（规范 §7.6、§8.1）。
        """
        return Edit("store_set", {"front": front, "sub": sub, "index": index,
                                  "field": field, "value": value})

    @staticmethod
    def store_remove(front: str, sub: str, index: int) -> "Edit":
        """下架商品 —— **删条目**（`quantity: 0` 是非法值，§4.6）。"""
        return Edit("store_remove", {"front": front, "sub": sub, "index": index})

    @staticmethod
    def store_add(front: str, sub: str, entry: Mapping[str, Any]) -> "Edit":
        """上架新商品。

        `entry` = `{spec XOR equipment, nationality, price, quantity}`。
        商品本身（特种兵 / 兵种 / 国籍）必须是游戏定义过的（规范 §7.6）。
        """
        return Edit("store_add", {"front": front, "sub": sub,
                                  "entry": dict(entry)})

    @staticmethod
    def card_store_set(position: int, card_type: str | None = None,
                       is_free: bool | None = None) -> "Edit":
        """改卡牌商店**货架**上的某一张（换牌 / 改成免费 / 改成收费）。

        ⚠️ `card_type` 必须在**白名单**里（规范 §7.5.1）——
        登陆 / 空降卡会召唤单位，战役里没有就崩。
        货架上的 `is_free` = **真实价格**（True ⇒ 0 声望）。
        """
        return Edit("card_store_set", {"position": position,
                                       "card_type": card_type,
                                       "is_free": is_free})

    @staticmethod
    def card_store_remove(position: int) -> "Edit":
        """下架货架上的一张卡。"""
        return Edit("card_store_remove", {"position": position})

    @staticmethod
    def card_store_add(position: int, card_type: str,
                       is_free: bool = False) -> "Edit":
        """上架一张卡到货架（`card_type` 同样要在白名单里）。"""
        return Edit("card_store_add", {"position": position,
                                       "card_type": card_type,
                                       "is_free": is_free})

    @staticmethod
    def hand_restore() -> "Edit":
        """把上次会议发到手里的牌恢复到当前会议（读 L2 → 写 L1）。"""
        return Edit("hand_restore", {})

    @staticmethod
    def theater_asset(asset: str, *, to_use: int,
                      uses_total: int | None = None,
                      uses_turn: int = 0) -> "Edit":
        """改战区资产（**只在当前进行中的战斗里有效**，L3 唯一白名单）。"""
        return Edit("theater_asset", {
            "asset": asset, "to_use": to_use,
            "uses_total": uses_total, "uses_turn": uses_turn,
        })

    # ---------------------------------------------------------------- 描述

    def describe(self) -> str:
        """一句话说明这次要改什么（给 GUI 的变更清单用）。"""
        p = self.params
        k = self.kind
        if k == "progress":
            return f"战役进度 {p.get('field')}：{p.get('value')}"
        if k == "unit_field":
            return f"单位 {p.get('unit_id')} 的 {p.get('field')}：{p.get('value')}"
        if k == "unit_spec_add":
            return f"单位 {p.get('unit_id')} 加特种 {p.get('spec_type')}"
        if k == "unit_spec_remove":
            return f"单位 {p.get('unit_id')} 卸特种 {p.get('spec_type')}"
        if k == "hq_force_pool":
            return (f"总部 {p.get('hq_id')} 兵库第 {p.get('index')} 条"
                    f"：{p.get('quantity')}")
        if k == "hq_field":
            return f"总部 {p.get('hq_id')} 的 {p.get('field')}：{p.get('value')}"
        if k == "hq_branch_level":
            return (f"总部 {p.get('hq_id')} 的 {p.get('branch')} 分支："
                    f"等级 {p.get('level')}")
        if k == "hq_force_pool_add":
            entry = p.get("entry") or {}
            return (f"总部 {p.get('hq_id')} 兵库加一条"
                    f"（{entry.get('spec') or entry.get('equipment')} ×"
                    f" {entry.get('quantity')}）")
        if k == "hq_force_pool_remove":
            return f"总部 {p.get('hq_id')} 兵库删第 {p.get('index')} 条"
        if k == "card_add":
            return f"加卡 {p.get('card_type')}"
        if k == "card_remove":
            return f"删手牌（槽位 {p.get('position')}）"
        if k == "card_set":
            return (f"手牌槽位 {p.get('position')} 的 {p.get('field')}："
                    f"{p.get('value')}")
        if k == "store_set":
            return (f"商店 {p.get('front')}/{p.get('sub')} 第 {p.get('index')} 条的 "
                    f"{p.get('field')}：{p.get('value')}")
        if k == "store_remove":
            return f"下架商店 {p.get('front')}/{p.get('sub')} 第 {p.get('index')} 条"
        if k == "store_add":
            entry = p.get("entry") or {}
            return (f"上架商品 {entry.get('spec') or entry.get('equipment')}"
                    f"（{p.get('front')}/{p.get('sub')}）")
        if k == "card_store_set":
            bits = []
            if p.get("card_type"):
                bits.append(f"换成 {p.get('card_type')}")
            if p.get("is_free") is not None:
                bits.append("改成免费" if p.get("is_free") else "改成收费")
            return f"货架槽位 {p.get('position')}：" + "、".join(bits)
        if k == "card_store_remove":
            return f"下架货架槽位 {p.get('position')}"
        if k == "card_store_add":
            return f"上架卡 {p.get('card_type')}（槽位 {p.get('position')}）"
        if k == "hand_restore":
            return "恢复上次会议的牌局"
        if k == "theater_asset":
            return (f"战区资产 {p.get('asset')}："
                    f"可用 {p.get('to_use')} 次")
        return k
