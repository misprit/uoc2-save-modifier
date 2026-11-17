"""编辑规划：把一组 `Edit` 变成「将要改哪些文件、改成什么样」的**计划**。

`plan_edit()` **不碰磁盘**。它产出：

* 每个被改条目的**前后文本 + unified diff**；
* 人类可读的一行行**变更说明**（GUI 的主视图用这个，不是 diff）；
* **错误**（不该做的改动）与**警告**（做了会被游戏覆盖的改动）。

`commit()`（见 `commit.py`）才会真正写回。
"""

from __future__ import annotations

import difflib
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
            except Exception:
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


def _layer_of(entry: str) -> str:
    """条目属于哪一层。L3 里只有 `games/<场景>/main.yml` 可能被写（战区资产）。"""
    if entry.startswith("games/") and entry.endswith("/main.yml"):
        return "L3"
    return "L1"


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

    edit_list = list(edits)
    if not edit_list:
        return plan

    for edit in edit_list:
        outcome = apply_edit(w, edit)
        w.outcomes.append(outcome)

    # 汇总
    for oc in w.outcomes:
        if oc.summary:
            plan.notes.append(oc.summary)
        plan.errors.extend(oc.errors)
        plan.warnings.extend(oc.warnings)

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
    if isinstance(xp, int) and not (0 <= xp <= 400):
        errs.append(f"单位 {uid} 的 xp={xp} 越界（必须 0..400）")
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
            for front, entries in data.items():
                if not isinstance(entries, list):
                    continue
                for i, e in enumerate(entries):
                    if not isinstance(e, dict):
                        continue
                    q = e.get("quantity")
                    if isinstance(q, int) and q < 1:
                        res.errors.append(
                            f"商店 {front} 第 {i} 条的 quantity={q} 是非法值"
                            "（游戏没有售罄标记，下架请删条目）")
                    p = e.get("price")
                    if isinstance(p, int) and p < 0:
                        res.errors.append(f"商店 {front} 第 {i} 条的 price={p} 为负")
                    if "spec" in e and "equipment" in e:
                        res.errors.append(
                            f"商店 {front} 第 {i} 条同时有 spec 与 equipment（二选一）")

    res.ok = not res.errors
    return res
