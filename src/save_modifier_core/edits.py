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

__all__ = ["Edit", "EDIT_KINDS", "UNSET"]


#: 全部合法的 kind —— 写错会直接报错，不会静默忽略
EDIT_KINDS = (
    "progress",            # 声望 / 分数（根 main.yml）
    "level",               # 难度（根 main.yml；决定手牌上限）
    "unit_field",          # 单位的某个字段（根 units.yml）
    "unit_spec_add",       # 加特种（根 units.yml）
    "unit_spec_remove",    # 卸特种（根 units.yml）
    "unit_orders",         # 作战标记（战斗层 games/<场景>/main.yml）
    "unit_spec_active",    # 特种兵的「被压制」状态（根 units.yml）
    "hq_force_pool",       # 总部兵库数量（根 hqs.yml）
    "hq_field",            # 总部的某个字段（根 hqs.yml）
    "hq_trucks",           # 总部补给卡车数（根 hqs.yml）
    "hq_branch_level",     # 总部分支等级（根 hqs.yml）
    "hq_branch_suppressed",  # 总部分支「被压制的等级数」（根 hqs.yml）
    "hq_branch_sp",        # 总部技能的专精次数（根 hqs.yml → branches）
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
    "theater_asset_add",   # 往当前 phase 组**加**一项战区资产（U45）
    "theater_asset_remove",  # 从当前 phase 组**删**一项战区资产（U45）
    "city_restore",       # 修复一座被摧毁的城市（废墟）—— 规范 §6.5
)

#: 商店的两个子商店（`store.yml` = `{战线: {store: [...], elite_store: [...]}}`）
STORE_SUBS = ("store", "elite_store")


class _Unset:
    """「这个字段这次不改」的哨兵。

    必须和 `None` 区分开：`None` 在战区资产里是一个**有意义的值**
    （`uses_total=None` = 「本场景剩余总次数无限」），不能拿来表示「不改」。
    """

    __slots__ = ()
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "<不改>"

    def __bool__(self) -> bool:
        return False


#: 「该字段这次不改」—— 默认值用这个，而不是 `None`
UNSET = _Unset()


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
    def level(value: str) -> "Edit":
        """改难度（根 `main.yml` 的 `level`）。

        `value` ∈ `easy` / `normal` / `classic` / `hard`（游戏常量 `play_levels`）。

        ⚠️ **难度决定手牌上限**（easy/normal 5、classic 4、hard 3）——
        手里牌数超过新上限时核心库会**硬拦**（让玩家先删手牌）。
        """
        return Edit("level", {"value": value})

    @staticmethod
    def unit_field(unit_id: int, field: str, value: Any) -> "Edit":
        """改单位的某个字段：`xp` / `act_st` / `sup_st` / `name_brief` / `name_full`。"""
        return Edit("unit_field",
                    {"unit_id": unit_id, "field": field, "value": value})

    @staticmethod
    def unit_spec_add(unit_id: int, spec_type: str, active: bool = True) -> "Edit":
        """给单位挂一个特种。

        `active=False` = 这个特种兵**一挂上就是被压制的** ——
        游戏里没有独立的 suppressed 字段（被压制 = `active=False`，
        见 `Edit.unit_spec_active` 的字节码实证）⇒ 与「先挂再压制」
        写出来的存档**完全一样**（U105：存档里原有的和我们新增的用同一套逻辑）。
        """
        return Edit("unit_spec_add",
                    {"unit_id": unit_id, "spec_type": spec_type, "active": active})

    @staticmethod
    def unit_spec_remove(unit_id: int, spec_type: str,
                         idx: int | None = None) -> "Edit":
        """卸一个特种；同名有多个时卸一条（给 `idx` 指定卸哪一条）。"""
        return Edit("unit_spec_remove",
                    {"unit_id": unit_id, "spec_type": spec_type, "idx": idx})

    @staticmethod
    def unit_spec_active(unit_id: int, spec_type: str, idx: int | None,
                         active: bool) -> "Edit":
        """特种兵的「被压制」状态（`active=False` = 被压制）。

        游戏里特种兵条目只有 4 个字段：`type` / `active` / `captured` / `idx`
        （`uoc2.state.entities.unit.SpecialistState.__init__` 实证）——
        **没有独立的 suppressed 字段**，`active=False` 就是被压制
        （渲染走 `specialist/<类型>/status_sup`，见 `uoc2.common.scalables._render_status`）。
        """
        # ⚠️ **不转换** —— 非法值要原样送到 handler 去报错（那里校验是不是 bool）
        return Edit("unit_spec_active",
                    {"unit_id": unit_id, "spec_type": spec_type, "idx": idx,
                     "value": active})

    @staticmethod
    def unit_orders(unit_id: int, orders: list[str]) -> "Edit":
        """单位身上的**作战标记**（U89）。

        `orders` 是标记 key 的列表，取值：
        `no_retreat`（不能撤退）/ `rearguard`（后卫部队）/ `elastic_defense`（反击）。

        ⚠️ 写的是**战斗层** `games/<场景>/main.yml` 的三个单位 id 列表
        （本仓库第二个 L3 例外，用户 2026-11-20 批准）。
        ⚠️ 这些是 **HQ 技能下的命令**，敌方下一回合结束前有效
        ⇒ 游戏回合开始会清掉。
        """
        return Edit("unit_orders",
                    {"unit_id": unit_id, "orders": list(orders)})

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
    def hq_trucks(hq_id: int, trucks: int) -> "Edit":
        """改总部的**补给卡车数**（`hqs.yml` → `trucks`）。

        * 合法值 **1–5**（0 不行 —— 总部至少要有一辆补给卡车）；
        * 1–5 辆依次对应补给作用范围 **5 / 8 / 10 / 11 / 12** 格；
        * **不涉及声望** —— 改卡车不动 `main.yml` 的任何数值。
        """
        return Edit("hq_trucks", {"hq_id": hq_id, "trucks": trucks})

    @staticmethod
    def hq_branch_level(hq_id: int, branch: str, level: int,
                        suppressed: int | None = None) -> "Edit":
        """改总部的**分支等级**（总部"升级"= 五个分支各一个等级）。

        `branch_levels[分支] = {level, suppressed}`：

        * `level` = **当前生效**的等级（0–3）；
        * `suppressed` = **被压制的等级数**（0–3，**不是布尔开关**）——
          游戏内部「解锁到几级」= `level + suppressed`。

        想调压制请用 `Edit.hq_branch_suppressed`（它会自动重算 `level`）。
        """
        return Edit("hq_branch_level", {"hq_id": hq_id, "branch": branch,
                                        "level": level, "suppressed": suppressed})

    @staticmethod
    def hq_branch_suppressed(hq_id: int, branch: str, suppressed: int) -> "Edit":
        """调总部分支的**被压制的等级数**（`branch_levels[分支].suppressed`）。

        语义 = 游戏的 `branch_suppress`：压制 N 级 ⇒ 生效等级 −N、被压制数 +N，
        而「真实等级（`level + suppressed`）」**不变**。核心库会自动重算 `level`：

            新 level = (旧 level + 旧 suppressed) − 新 suppressed

        ⚠️ 压制只写在**战役进行中**的存档里才有意义 —— 游戏在一局结束时
        （`set_end_game` → `unsuppress_branch_levels`）会把压制还原。
        """
        return Edit("hq_branch_suppressed",
                    {"hq_id": hq_id, "branch": branch, "suppressed": suppressed})

    @staticmethod
    def hq_branch_sp(hq_id: int, branch: str, action: str,
                     sp_used: int) -> "Edit":
        """改总部分支里**某个技能的专精次数**（`branches` 里那条的 `sp_used`）。

        **专精（specialization）= 让该技能发动时消耗的 CP 减 1**（`e165` 字节码坐实：
        `a.cost = max(0, a.cost - 1)`）。

        ⇒ 写 `sp_used` 的同时**必须同步 `cost`** —— 存档里存的是**已经扣减过的** CP，
        原始 CP = `cost + sp_used`。核心库会自动同步，调用方只管给 `sp_used`。

        * 上限 = 该技能的 `sp_avail`（默认 `min(2, 原始cost - 1)` ⇒ 最多 2 次）；
        * `force_pool` 分支的四个动作与 `motor_pool` **没有技能点**
          （`sp_avail = null`）⇒ 传 `sp_used` 会报错。
        """
        return Edit("hq_branch_sp",
                    {"hq_id": hq_id, "branch": branch, "action": action,
                     "sp_used": sp_used})

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
    def theater_asset(asset: str, *, to_use: Any = UNSET,
                      uses_total: Any = UNSET,
                      uses_turn: Any = UNSET,
                      side: str | None = None) -> "Edit":
        """改战区资产（**只在当前进行中的战斗里有效**，L3 唯一白名单）。

        ⚠️ **U143**：`side` = 改**哪一方**的战区资产 ——
        `"player"`（默认，玩家那一方）/ `"opponent"`（对手那一方）/
        `"current"`（当前行动方，旧语义）。
        ⚠️ 存档里 `theater_assets` 的**两组 = 两个阵营各一组**
        （战斗 `main.yml` 的 `factions` 第 i 项 = 第 i 组的拥有者，
        `player: local` / `player: ai` 直接标出玩家是谁）。

        **三个字段都能单独改**，也能都不改（默认全是 `UNSET` = 不改）：

        * `to_use` —— **当前剩余可用次数**（≥ 0）
        * `uses_total` —— **本场景剩余总次数**（≥ 0，或 `None` = 无限）
        * `uses_turn` —— **每回合恢复次数**（≥ 1）

        ⚠️ `uses_total=None` 表示「改成无限」，**不是**「不改」——
        不改要传 `UNSET`（或者干脆不传这个参数）。
        """
        params = {
            "asset": asset, "to_use": to_use,
            "uses_total": uses_total, "uses_turn": uses_turn,
        }
        if side:
            params["side"] = side
        return Edit("theater_asset", params)

    @staticmethod
    def theater_asset_add(asset: str, *, uses_total: Any = None,
                          uses_turn: int = 1,
                          side: str | None = None) -> "Edit":
        """往**某一方**的战区资产组里**加**一项（U45）。

        ⚠️ **U143**：`side` 决定加到**哪一方**（默认玩家那一方）。

        ⚠️ `asset` 只能是游戏那 **7 种**之一（`THEATER_ASSET_TYPES`）——
        游戏的 `scenario_data_validation.theater_asset_dict` 是
        `Required('asset'): In(theater_asset_types)` ⇒ 写别的名字**存档直接打不开**。

        ⚠️ **不给 `to_use`** —— handler 会按（`uses_turn`, `uses_total`）
        算出**自洽**的一组值（`to_use` / `to_use_not_used`）写全，
        这样不会留下「次数全是 0」的死条目。

        ⚠️ `uses_total=None` = **无限**（游戏自己的「空袭」就是无限）。
        """
        params = {"asset": asset, "uses_total": uses_total,
                  "uses_turn": uses_turn}
        if side:
            params["side"] = side
        return Edit("theater_asset_add", params)

    @staticmethod
    def theater_asset_remove(asset: str,
                              side: str | None = None) -> "Edit":
        """从**某一方**的战区资产组里**删掉**这一项（U45）。

        ⚠️ **U143**：`side` 决定从**哪一方**删（默认玩家那一方）。

        删的是**整项**，不是把次数清零 —— 清零会留下一个永远用不了的
        死条目，游戏里还白占一个按钮。
        """
        params = {"asset": asset}
        if side:
            params["side"] = side
        return Edit("theater_asset_remove", params)

    @staticmethod
    def city_restore(uv, restore_forts: bool = True) -> "Edit":
        """修复一座被摧毁的城市（废墟）—— 规范 §6.5。

        `uv` = 地图坐标 `(x, y)`。

        **一次只修一座** —— 修复要同时改三处（战役清单 + 每个场景的废墟快照
        + 同格要塞），批量改会让「到底改了哪些」看不清（§6.5.2）。

        `restore_forts` = 要不要把**同格要塞**的 `functional` 一起改回 `true`
        （默认要 —— `set_destroyed_cities` 摧毁城市时会把同格要塞置 `false`）。

        ⚠️ **战斗中不许用** —— 游戏会在存档时从内存重写当前战斗目录与根 `main.yml`，
        改了会被覆盖回去（§6.5.5-1，handler 会硬拦）。
        """
        return Edit("city_restore",
                    {"uv": uv, "restore_forts": bool(restore_forts)})

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
        if k == "unit_spec_active":
            return (f"单位 {p.get('unit_id')} 的特种 {p.get('spec_type')}"
                    + (f"（槽位 {p.get('idx')}）" if p.get("idx") is not None else "")
                    + ("：设为被压制" if not p.get("value") else "：恢复活跃"))
        if k == "unit_orders":
            return f"单位 {p.get('unit_id')} 的作战标记：{', '.join(p.get('orders') or []) or '无'}"
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
        if k == "hq_branch_sp":
            return (f"总部 {p.get('hq_id')} 的 {p.get('branch')} 分支 · "
                    f"{p.get('action')}：专精 {p.get('sp_used')}")
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
            bits = []
            for fname, cn in (("to_use", "当前可用"),
                              ("uses_total", "本场景剩余"),
                              ("uses_turn", "每回合恢复")):
                v = p.get(fname, UNSET)
                if v is UNSET:
                    continue
                if fname == "uses_total" and v is None:
                    v = "无限"
                bits.append(f"{cn} → {v}")
            return f"战区资产 {p.get('asset')}：" + "、".join(bits)
        if k == "theater_asset_add":
            v = "无限" if p.get("uses_total") is None else p.get("uses_total")
            return (f"加战区资产 {p.get('asset')}"
                    f"（每回合恢复 {p.get('uses_turn')}，本场景剩余 {v}）")
        if k == "theater_asset_remove":
            return f"删战区资产 {p.get('asset')}"
        if k == "city_restore":
            uv = p.get("uv")
            return "修复废墟城市 %s" % (tuple(uv) if isinstance(uv, (list, tuple)) else uv,)
        return k
