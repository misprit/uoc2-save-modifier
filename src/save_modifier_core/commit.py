"""提交：把一个 `Plan` 写回存档。

**顺序是硬的，一步都不能省**（见 `writer.py`）：

1. **备份** —— 把原 `.usg` 整体复制为 `<存档名>_BACKUP.usg`（同名不覆盖，用 `_BACKUP_2`…）。
   备份必须是**原文件的字节拷贝**，不是"重新打包"的产物（§6.4.1）。
2. **写临时文件** —— 用保真打包器重建，条目顺序与元数据沿用原存档（§7.2 W7）。
3. **校验** —— 逐条 SHA256 比对，确认**只有计划里那几个条目变了**。
   校验不过就地丢弃临时文件，**原存档一个字都不动**。
4. **原子替换** —— `os.replace` 覆盖原文件。

提交成功后，**把本次改动压进撤销栈**（§6.4.2）——
不压栈的提交等于"改了就撤不回来"，那是产品的底线。

⚠️ **只写 L1**（根目录的 5 个 YAML），加上**唯一的 L3 例外**：
当前进行中战斗的 `theater_assets`（§7.2 W8）。
检查点（L2）、回合历史（L4）、战役文档（L5）**一律不碰**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .packing import PackReport
from .plan import Plan
from .undo import make_record, push
from .writer import (WriteOutcome, backup_matches_original, backup_path_for,
                     make_backup, read_entries, sha256_bytes, write_overlay)

__all__ = [
    "CommitResult",
    "backup_matches_original",
    "backup_path_for",
    "commit",
    "make_backup",
]


@dataclass
class CommitResult:
    ok: bool = False
    #: 计划里没有任何需要写入的改动（不是错误，只是没事可做）
    nothing_to_do: bool = False
    path: Path | None = None
    backup: Path | None = None
    #: 实际变了的条目
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report: PackReport | None = None

    def summary(self) -> str:
        if self.nothing_to_do:
            return "没有需要写入的改动"
        if not self.ok:
            return "❌ " + "；".join(self.errors[:3])
        return f"已写入 {self.path.name}（改动 {len(self.changed)} 个文件）"


def commit(plan: Plan) -> CommitResult:
    """把一个 `Plan` 写回存档。

    **任何一步失败都会完整回滚** —— 原存档保持原样，不留半写坏的文件。
    """
    res = CommitResult(path=plan.path)
    res.warnings.extend(plan.warnings)

    if not plan.ok:
        res.errors.append("计划里有错误，拒绝写入")
        return res
    if not plan.changes:
        res.nothing_to_do = True
        return res

    save_path = Path(plan.path)

    # 0) 存档自打规划以来有没有被改动过？
    #    （玩家可能在游戏里手动改了同一个存档 —— 这时按旧计划写下去会覆盖掉人家的改动）
    stale = _stale_entries(save_path, plan)
    if stale:
        res.errors.append(
            "存档在规划之后被改动过（" + "、".join(stale) +
            "），拒绝写入 —— 请重新规划一次")
        return res

    # 1~4) 备份 → 临时文件 → 校验 → 原子替换（共享写回管线）
    overlay = {entry: text.encode("utf-8") for entry, text in plan._payload.items()}
    out: WriteOutcome = write_overlay(save_path, overlay)
    res.report = out.report
    res.backup = out.backup
    if not out.ok:
        res.errors.extend(out.errors)
        return res
    res.changed = list(out.changed)

    # 5) 压撤销栈（失败只提醒，不影响已经成功的提交）
    record = make_record(
        entries={
            entry: (plan._before_raw.get(entry, b""),
                    sha256_bytes(overlay[entry]))
            for entry in plan._payload
        },
        summary=_undo_summary(plan),
    )
    res.warnings.extend(push(save_path, record))

    res.ok = True
    return res


def _stale_entries(save_path: Path, plan: Plan) -> list[str]:
    """哪些条目在"规划之后"被改动了（存档被别人动过）。"""
    names = list(plan._payload.keys())
    cur = read_entries(save_path, names)
    stale: list[str] = []
    for entry in names:
        want = plan._before_raw.get(entry)
        if want is None:
            continue
        now = cur.get(entry)
        if now is None or sha256_bytes(now) != sha256_bytes(want):
            stale.append(entry)
    return stale


def _undo_summary(plan: Plan) -> str:
    """给撤销栈的一句话描述（GUI 显示用）。"""
    names = plan.changed_entries
    head = f"改了 {len(names)} 个文件"
    if plan.notes:
        return f"{head}：{plan.notes[0]}"
    if names:
        return f"{head}：{'、'.join(names)}"
    return head
