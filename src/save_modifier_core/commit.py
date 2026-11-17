"""写回：备份 → 写临时文件 → 校验 → 原子替换。

**顺序是硬的，一步都不能省：**

1. **备份** —— 把原 `.usg` 整体复制为 `<存档名>_BACKUP.usg`（同名不覆盖，用 `_BACKUP_2`…）。
   备份必须是**原文件的字节拷贝**，不是"重新打包"的产物（§6.4.1）。
2. **写临时文件** —— 用保真打包器重建，条目顺序与元数据沿用原存档（§7.2 W7）。
3. **校验** —— 逐条 SHA256 比对，确认**只有计划里那几个条目变了**。
   校验不过就地丢弃临时文件，**原存档一个字都不动**。
4. **原子替换** —— `os.replace` 覆盖原文件。

⚠️ **只写 L1**（根目录的 5 个 YAML），加上**唯一的 L3 例外**：
当前进行中战斗的 `theater_assets`（§7.2 W8）。
检查点（L2）、回合历史（L4）、战役文档（L5）**一律不碰**。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .packing import PackReport, repack_overlay, verify
from .plan import Plan

__all__ = ["CommitResult", "commit", "make_backup", "backup_path_for"]


@dataclass
class CommitResult:
    ok: bool = False
    path: Path | None = None
    backup: Path | None = None
    #: 实际变了的条目
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report: PackReport | None = None

    def summary(self) -> str:
        if not self.ok:
            return "❌ " + "；".join(self.errors[:3])
        return f"已写入 {self.path.name}（改动 {len(self.changed)} 个文件）"


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_path_for(save_path: Path) -> Path:
    """备份文件的目标路径（`<存档名>_BACKUP.usg`）。

    ⚠️ **同名已存在时不要覆盖** —— 用 `_BACKUP_2` / `_BACKUP_3`… 递增，
    否则第二次修改会把第一次的救命备份冲掉（§6.4.1、§10 第 59 条）。
    """
    base = save_path.with_name(f"{save_path.stem}_BACKUP{save_path.suffix}")
    if not base.exists():
        return base
    n = 2
    while True:
        cand = save_path.with_name(f"{save_path.stem}_BACKUP_{n}{save_path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def make_backup(save_path: Path) -> Path:
    """生成备份（**原文件的字节拷贝**），返回备份路径。"""
    target = backup_path_for(save_path)
    shutil.copy2(save_path, target)
    return target


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
        res.errors.append("没有需要写入的改动")
        return res

    save_path = Path(plan.path)

    # 1) 备份
    try:
        res.backup = make_backup(save_path)
    except OSError as exc:
        res.errors.append(f"备份失败：{exc}")
        return res

    # 2) 写临时文件
    overlay = {entry: text.encode("utf-8") for entry, text in plan._payload.items()}
    tmp = save_path.with_name(save_path.name + ".new")
    try:
        report = repack_overlay(save_path, overlay, tmp)
        res.report = report
    except Exception as exc:
        res.errors.append(f"打包失败：{exc}")
        _quiet_unlink(tmp)
        return res

    # 3) 校验：只有计划里那几个条目变了
    try:
        v = verify(save_path, tmp)
    except Exception as exc:
        res.errors.append(f"校验失败：{exc}")
        _quiet_unlink(tmp)
        return res

    expected = set(plan._payload.keys())
    actual = set(v.changed)
    unexpected = actual - expected
    lost = expected - actual
    if unexpected:
        res.errors.append(
            f"写回结果与计划不符：多变了 {sorted(unexpected)}")
        _quiet_unlink(tmp)
        return res
    if lost:
        res.errors.append(f"写回结果与计划不符：{sorted(lost)} 没有生效")
        _quiet_unlink(tmp)
        return res
    if v.added or v.reordered:
        res.errors.append(
            f"写回结果异常：新增条目 {v.added} / 顺序不一致 {v.reordered}")
        _quiet_unlink(tmp)
        return res

    res.changed = list(v.changed)

    # 4) 原子替换
    try:
        os.replace(tmp, save_path)
    except OSError as exc:
        res.errors.append(f"替换失败：{exc}")
        _quiet_unlink(tmp)
        return res

    res.ok = True
    return res


def _quiet_unlink(p: Path) -> None:
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


def backup_matches_original(save_path: Path, backup: Path) -> bool:
    """备份是否与原文件字节一致（验收项：备份必须是原件）。"""
    try:
        return _sha256_file(save_path) == _sha256_file(backup)
    except OSError:
        return False
