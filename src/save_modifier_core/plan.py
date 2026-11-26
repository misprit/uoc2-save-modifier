"""编辑规划：把一组 `Edit` 变成「将要改哪些文件、改成什么样」的**计划**。

`plan_edit()` **不碰磁盘**。它产出：

* 每个被改条目的**前后文本 + unified diff**；
* 人类可读的一行行**变更说明**（GUI 的主视图用这个，不是 diff）；
* **错误**（不该做的改动）与**警告**（做了会被游戏覆盖的改动）。

`commit()`（见 `commit.py`）才会真正写回。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import yamlio
from .edits import Edit
from .handlers import Outcome, apply_edit
from .paths import CorePaths

__all__ = ["Plan", "FileChange", "ValidationResult", "plan_edit", "validate"]


@dataclass
class FileChange:
    """一个被改动的存档条目。"""

    #: ZIP 内的条目名（如 `main.yml`、`units.yml`）
    entry: str
    #: 该条目属于哪一层（L1 根状态 / L3 战斗实时层 —— 后者只有一个例外）
    layer: str = "L1"
    before: str = ""
    after: str = ""
    diff: str = ""
    #: 这一条上做了什么（人类可读）
    notes: list[str] = field(default_factory=list)

    @property
    def is_l3_exception(self) -> bool:
        return self.layer == "L3"


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.ok:
            return f"不可提交：{len(self.errors)} 个错误"
        if self.warnings:
            return f"可提交（{len(self.warnings)} 条提醒）"
        return "可提交"


@dataclass
class Plan:
    """一次编辑的完整计划。"""

    save_id: str
    path: Any
    changes: list[FileChange] = field(default_factory=list)
    #: 一行行的变更说明
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: 内部：entry -> 新的 YAML 文本（commit 用）
    _payload: dict[str, str] = field(default_factory=dict, repr=False)
    #: 内部：entry -> **改前的原始字节**（撤销栈用；提交时还要拿它校验存档没被改动过）
    _before_raw: dict[str, bytes] = field(default_factory=dict, repr=False)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def changed_entries(self) -> list[str]:
        return [c.entry for c in self.changes]

    def summary(self) -> str:
        if self.errors:
            return f"❌ {len(self.errors)} 个错误，未提交：" + "；".join(self.errors[:3])
        if not self.changes:
            return "没有需要写入的改动"
        warn = f"，{len(self.warnings)} 条提醒" if self.warnings else ""
        return (f"将修改 {len(self.changes)} 个文件"
                f"（{', '.join(self.changed_entries)}）{warn}")


class Work:
    """编辑过程中的可变工作区。

    只在内存里操作 —— `plan_edit` 全程不碰磁盘。
    """

    def __init__(self, save, catalog=None):
        self.save = save
        self.catalog = catalog
        self.caps = save.capabilities()
        self._tables: dict[str, Any] = {}
        self._texts: dict[str, str] = {}
        self._raws: dict[str, bytes] = {}
        self.touched: set[str] = set()
        self.outcomes: list[Outcome] = []
        #: **本批要执行的所有编辑** —— handler 可以据此判断
        #: 「这一批改完之后」的值（而不是执行到一半的中间态）。
        #: 同一批编辑是**依次执行**的 ⇒ 中间态会误报
        #: （U96 的兵力上限、U97 的总部 CP 都是这么来的）。
        self.batch_edits: list = []
        #: **解析失败**的条目（`YAML 解析失败`）——
        #: 这一批**不许写盘**（见 `table()`）。
        self.parse_errors: list[str] = []

    # ---- 条目读写 ----

    def table(self, entry: str, default: Any = None) -> Any:
        """取某个条目的解析结果（**返回可直接修改的对象**）。"""
        if entry in self._tables:
            return self._tables[entry]
        raw = self.save.read_bytes(entry)
        if raw is None:
            value = default
        else:
            try:
                value = yamlio.load(raw)
            except Exception as exc:
                # ⚠️ 原来这里直接 `value = default` ——
                # **静默**把一个解析失败的条目当成「空表」，
                # 改完再写回去 = **残缺的存档**（外部审阅报告 P1-5）。
                # ⇒ 记一条错误 ⇒ 这一批**整批不许写盘**。
                self.parse_errors.append(
                    "%s：YAML 解析失败（%s）—— 已阻止写入；"
                    "请先把这个存档备份好，再检查该文件" % (entry, exc))
                value = default
            if value is None:
                value = default
        self._tables[entry] = value
        self._texts[entry] = raw.decode("utf-8", errors="replace") if raw else ""
        self._raws[entry] = raw or b""
        return value

    def text(self, entry: str) -> str:
        self.table(entry, None)
        return self._texts.get(entry, "")

    def touch(self, entry: str) -> None:
        """标记该条目被改动（提交时会重新序列化它）。"""
        self.touched.add(entry)

    # ---- 能力位 ----

    def require(self, capability: bool, feature: str, entry: str) -> bool:
        """能力位不满足就记一条错误，并返回 False。"""
        if capability:
            return True
        reason = self.caps.unavailable_reason(feature)
        self.outcomes.append(Outcome(errors=[f"{entry}：{reason}"]))
        return False


#: **根层（L1）**允许改写的条目 —— 只有这五张表。
ROOT_WRITABLE = ("main.yml", "units.yml", "hqs.yml", "cards.yml", "store.yml")

#: **战役名册**那两张表（**U148**）—— 改名必须**两份都改**：
#: 战役地图显示的名字来自名册（`document/`），战斗中显示的来自根表
#: ⇒ 只改一份 ⇒ 玩家在一处看到名字变了、另一处没变（实测：只改根表 ⇒ 战役地图上完全没变化）。
#:
#: ⚠️ **只有这两张**可以写 —— `document/` 下别的条目（战役文档 / 上次会议的检查点）
#: 仍然**只读**（U124 的结论不变）。
ROSTER_WRITABLE = ("document/units.yml", "document/hqs.yml")

#: **战斗层（L3）**条目的形状 —— 战役是 `games/<场景>/main.yml`，
#: **独立场景是 `game/main.yml`（单数目录！）**。
_BATTLE_MAIN_RE = re.compile(r"^(?:games/[^/]+|game)/main\.yml$")

#: **废墟快照**那两张表（**U184**）—— 修复城市必须同时改它们（规范 §6.5.3）：
#: `games/<场景>/cities.yml`（该场景的废墟快照）与
#: `games/<场景>/forts.yml`（同格要塞的 `functional`）。
#:
#: ⚠️ **只放行这两张、且只放行存档里真实存在的那几份** ——
#: `games/**` 的其它条目（`units.yml` / `ar_list.yml` / `archive` …）仍然一律只读。
RUIN_SNAPSHOT_RE = re.compile(r"^games/[^/]+/(?:cities|forts)\.yml$")


def _layer_of(entry: str) -> str:
    """条目属于哪一层。

    * **L1** = 根层（`main.yml` / `units.yml` / `hqs.yml` / `cards.yml` / `store.yml`）；
    * **L3** = 战斗层 —— 战役是 `games/<场景>/main.yml`，
      **独立场景是 `game/main.yml`**（单数目录）。

    ⚠️ **U124**：原来只认 `games/*/main.yml` ⇒ **独立场景**的战斗层被标成 L1
    （外部审阅报告 P1-7）。
    """
    if _BATTLE_MAIN_RE.match(entry) or RUIN_SNAPSHOT_RE.match(entry):
        return "L3"
    return "L1"


def writable_entries(save) -> set:
    """**写盘白名单**：这个存档里哪些条目允许被改写。

    * 根层那五张表（`ROOT_WRITABLE`）；
    * **战役名册**那两张表（`ROSTER_WRITABLE`）—— 改名要两份都改（U148）；
    * **当前战斗**的那张 `main.yml`（战役 `games/<场景>/main.yml`，
      独立场景 `game/main.yml`）；
    * **废墟快照**那两张表（`RUIN_SNAPSHOT_RE`，**U184**）——
      `games/<场景>/cities.yml` 与 `games/<场景>/forts.yml`，
      **只放行存档里真实存在的那几份**（§6.5.3 的 ②③）。

    ⚠️ **U124**：以前**没有白名单** ⇒ 理论上能往存档里写**任意条目**
    （`document/`、`last_conference/`、`last_game/` …）——
    那些是**只读**的（战役文档 / 上次会议的检查点，改了游戏会出问题）。
    ⚠️ **U148**：名册那两张是**唯一的例外**（只放行改名字要用的那两张）。
    """
    out = set(ROOT_WRITABLE)
    out.update(ROSTER_WRITABLE)
    try:
        battle_dir = save.battle_dir()
    except Exception:
        battle_dir = None
    if battle_dir:
        out.add("%s/main.yml" % battle_dir)
    # 废墟快照（U184）：只放行存档里**真实存在**的那几份
    try:
        for name in save.list_names():
            if RUIN_SNAPSHOT_RE.match(name):
                out.add(name)
    except Exception:
        pass
    return out


#: **按下标删除**的编辑 —— 删的是**某个列表里的第 N 项**。
#:
#: | kind | 删的是哪份列表 |
#: |---|---|
#: | `hq_force_pool_remove` | 某个总部的 `force_pool` |
#: | `store_remove` | 某个 战线/子商店 的商品列表 |
#:
    #: ⚠️ 以前只把 `hq_force_pool_remove` 当成「按下标删除」，
#: **`store_remove` 漏了** ⇒ 一次改两个商店条目时**删错行**
#: （外部审阅报告 P0-2）。
#:
#: ⇒ 用 `kind` 分组（同组 = 同一份列表），**组内按 index 降序**。
#: （不同组之间互不影响，先后随便。）
#:
#: ⚠️ `unit_spec_remove` / `card_remove` / `card_store_remove` /
#: `theater_asset_remove` **不在此列** —— 它们是**按属性匹配**删的
#: （特种按 `idx`、卡牌按 `position`、战区资产按 `asset` 名），
#: 删别人**不会**让它们的下标漂移。
_DELETE_BY_INDEX = {
    "hq_force_pool_remove": lambda p: "hq|%s" % (p.get("hq_id"),),
    "store_remove": lambda p: "store|%s|%s" % (p.get("front"), p.get("sub")),
}


def _delete_group(e) -> str:
    """这条删除属于**哪份列表**（同组的才会互相影响下标）。"""
    key = _DELETE_BY_INDEX.get(e.kind)
    if key is None:
        return ""
    return key(e.params or {})


def _delete_index(e) -> int:
    idx = (e.params or {}).get("index")
    if isinstance(idx, bool) or not isinstance(idx, int):
        return 0
    return idx


def order_edits(edits):
    """把编辑**按安全顺序**排好再执行。

    * **按下标删除**的编辑（兵库删条目 / 商店下架）要排在**最后** ——
      删了会让后面条目的下标整体前移，先删再改数量就会改错行（U35）；
    * 同一份列表里的多条删除之间要按 index **降序** ——
      删了 idx0 之后原 idx1 前移到 idx1，再删 idx1 就**删到了别的条目**
      （U91 实测：升序删两条 ⇒ 步兵那条被误删；U121：商店下架同款）。
      ⇒ 降序 ⇒ 顺序与玩家点按钮的先后**无关**。

    其余编辑保持原顺序（Python 的 sort 是稳定的）。
    """
    removes = [e for e in edits if e.kind in _DELETE_BY_INDEX]
    others = [e for e in edits if e.kind not in _DELETE_BY_INDEX]
    removes.sort(key=lambda e: (_delete_group(e), _delete_index(e)), reverse=True)
    return others + removes


def plan_edit(save, edits: Iterable[Edit], catalog=None) -> Plan:
    """规划一批编辑。**不碰磁盘。**

    参数
    ----
    save    : 已打开的存档
    edits   : 一组 `Edit`
    catalog : 类型目录（可选）。给了才能校验 `specs[].type` 等类型合法性。

    返回 `Plan`：`plan.ok` 为真才允许提交。
    """
    plan = Plan(save_id=save.info.save_id, path=save.path)
    w = Work(save, catalog)

    edit_list = order_edits(list(edits))
    if not edit_list:
        return plan
    w.batch_edits = list(edit_list)

    for edit in edit_list:
        outcome = apply_edit(w, edit)
        w.outcomes.append(outcome)

    # 汇总
    for oc in w.outcomes:
        if oc.summary:
            plan.notes.append(oc.summary)
        plan.errors.extend(oc.errors)
        plan.warnings.extend(oc.warnings)

    # 有条目**解析失败** ⇒ 这一批**整批不许写盘**
    # （否则会把「空表」写回去 = 残缺存档）。
    plan.errors.extend(w.parse_errors)

    # 生成每个被改条目的 diff
    for entry in sorted(w.touched):
        table = w._tables.get(entry)
        after = yamlio.dump(table).decode("utf-8") if table is not None else ""
        before = w._texts.get(entry, "")
        if before == after:
            continue
        diff = "\n".join(difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile=f"{entry}（改前）", tofile=f"{entry}（改后）",
            lineterm="", n=2))
        plan.changes.append(FileChange(
            entry=entry,
            layer=_layer_of(entry),
            before=before,
            after=after,
            diff=diff,
            notes=[oc.summary for oc in w.outcomes if oc.summary],
        ))
        plan._payload[entry] = after
        plan._before_raw[entry] = w._raws.get(entry, b"")

    # **写盘白名单** —— 只允许改根层那五张表 + 当前战斗层那张 main.yml
    allowed = writable_entries(save)
    illegal = sorted({c.entry for c in plan.changes if c.entry not in allowed})
    if illegal:
        plan.errors.append(
            "这些条目不允许写入：%s（只允许改根层的 %s、战役名册的 %s、"
            "当前战斗层的那张 main.yml，以及废墟快照那两张 "
            "games/<场景>/cities.yml 与 forts.yml）"
            % ("、".join(illegal), "、".join(ROOT_WRITABLE),
               "、".join(ROSTER_WRITABLE)))

    # 有错误就不该有任何"改动"可提交
    if plan.errors:
        plan.changes.clear()
        plan._payload.clear()
        plan._before_raw.clear()
    return plan


# ---------------------------------------------------------------- 复核


def _check_unit(unit: dict) -> list[str]:
    """单位字段的硬约束（规范 §5.2）。"""
    errs: list[str] = []
    uid = unit.get("id")
    xp = unit.get("xp")
    # ⚠️ 上限 **399**（不是 400）：游戏的 `add_xp` 是 `min(self.xp + xp, 399)`，
    #    `_repair_data` 也是 `max(0, min(v, 399))`
    #    （游戏安装目录 `lib\uoc2\state\entities\unit.pyc` 字节码实证）
    if isinstance(xp, int) and not (0 <= xp <= 399):
        errs.append(f"单位 {uid} 的 xp={xp} 越界（必须 0..399）")
    for f, hi in (("entr", 2), ("supply", 3), ("ap", 3)):
        v = unit.get(f)
        if isinstance(v, int) and not (0 <= v <= hi):
            errs.append(f"单位 {uid} 的 {f}={v} 越界（必须 0..{hi}）")
    for f in ("act_st", "sup_st"):
        v = unit.get(f)
        if isinstance(v, int) and v < 0:
            errs.append(f"单位 {uid} 的 {f}={v} 为负")
    specs = unit.get("specs")
    if isinstance(specs, list) and len(specs) > 3:
        errs.append(f"单位 {uid} 的特种有 {len(specs)} 个（上限 3）")
    return errs


def validate(plan: Plan) -> ValidationResult:
    """对计划的结果做一次**独立复核**。

    规划时已经查过一遍；这里是第二道防线 —— 防止任何一条路径绕过校验。
    """
    res = ValidationResult(errors=list(plan.errors), warnings=list(plan.warnings))
    if plan.errors:
        res.ok = False
        return res

    for entry, text in plan._payload.items():
        try:
            data = yamlio.load(text)
        except Exception as exc:
            res.errors.append(f"{entry}：生成的 YAML 解析失败（{exc}）")
            continue

        if entry == "units.yml" and isinstance(data, list):
            for u in data:
                if isinstance(u, dict):
                    res.errors.extend(_check_unit(u))
        if entry == "store.yml" and isinstance(data, dict):
            # store.yml 是两层：{战线: {store: [...], elite_store: [...]}}
            for front, blob in data.items():
                if not isinstance(blob, dict):
                    continue
                for sub, entries in blob.items():
                    if not isinstance(entries, list):
                        continue
                    for i, e in enumerate(entries):
                        if not isinstance(e, dict):
                            continue
                        q = e.get("quantity")
                        if isinstance(q, int) and q < 1:
                            res.errors.append(
                                f"商店 {front}/{sub} 第 {i} 条的 quantity={q} 是非法值"
                                "（游戏没有售罄标记，下架请删条目）")
                        p = e.get("price")
                        if isinstance(p, int) and p < 0:
                            res.errors.append(
                                f"商店 {front}/{sub} 第 {i} 条的 price={p} 为负")
                        if "spec" in e and "equipment" in e:
                            res.errors.append(
                                f"商店 {front}/{sub} 第 {i} 条同时有 spec 与 equipment"
                                "（二选一）")

    res.ok = not res.errors
    return res
