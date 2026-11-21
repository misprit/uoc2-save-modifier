"""写回管线：备份 → 写临时文件 → 校验 → 原子替换。

**这是唯一的写盘路径。** `commit()`（提交）与 `undo()`（撤销）都走它，
谁都不许另写一条"简化的"写路径 —— 规范 §6.4.2 明确要求：

> 撤销栈弹出的内容，同样走完整的"备份 → 写临时文件 → 校验 → 原子替换"流程，
> **不复用**任何简化的写路径。

四步，一步都不能省：

1. **备份** —— 把原 `.usg` 整体复制为 `<存档名>_BACKUP.usg`
   （同名不覆盖，用 `_BACKUP_2`…）。备份是**原文件的字节拷贝**，不是重打包的产物。
2. **写临时文件** —— 用保真打包器重建，条目顺序与元数据沿用原存档。
3. **校验** —— 逐条 SHA256 比对，确认**只有 overlay 里那几个条目变了**。
   校验不过就地丢弃临时文件，原存档一个字都不动。
4. **原子替换** —— `os.replace` 覆盖原文件。

任何一步失败都**完整回滚**：原存档保持原样，不留半写坏的文件。
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .packing import PackReport, repack_overlay, verify
from .paths import backup_dir, fallback_backup_dir

__all__ = [
    "WriteOutcome",
    "backup_path_for",
    "make_backup",
    "read_entries",
    "sha256_bytes",
    "write_overlay",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class WriteOutcome:
    """一次写回的结果。"""

    ok: bool = False
    backup: Path | None = None
    #: 实际变了的条目（应当恰好等于 overlay 的键）
    changed: list[str] = field(default_factory=list)
    report: PackReport | None = None
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return f"已写入 {len(self.changed)} 个条目"
        return "❌ " + "；".join(self.errors[:3])


def _next_free(folder: Path, stem: str, suffix: str) -> Path:
    """`<folder>/<stem>_BACKUP[_n]<suffix>` —— **同名绝不覆盖**。

    ⚠️ 递增是必须的：否则第二次修改会把第一次的救命备份冲掉
    （§6.4.1、§10 第 59 条）。
    """
    base = folder / f"{stem}_BACKUP{suffix}"
    if not base.exists():
        return base
    n = 2
    while True:
        cand = folder / f"{stem}_BACKUP_{n}{suffix}"
        if not cand.exists():
            return cand
        n += 1


def backup_path_for(save_path: Path) -> Path:
    """备份文件的目标路径（**`<修改器目录>/bak/<存档名>_BACKUP.usg`**，U109）。

    ⚠️ **不再放在存档旁边**：游戏只扫存档目录里的 `*.usg` ⇒ 备份放那儿
    会被**游戏当成存档**列出来；改一次多一个文件也把存档目录弄得很乱。
    ⇒ 统一放 `<修改器目录>/bak/`（见 `paths.backup_dir()`）。

    ⚠️ **同名已存在时不要覆盖** —— 用 `_BACKUP_2` / `_BACKUP_3`… 递增。
    """
    p = Path(save_path)
    return _next_free(backup_dir(), p.stem, p.suffix)


def legacy_backup_path_for(save_path: Path) -> Path:
    """**老**位置（存档旁边的 `<存档名>_BACKUP.usg`）—— 只在 `bak/` 不可写时兜底。"""
    p = Path(save_path)
    return _next_free(p.parent, p.stem, p.suffix)


def make_backup(save_path: Path) -> Path:
    """生成备份（**原文件的字节拷贝**），返回备份路径。

    ⚠️ 优先放 `<修改器目录>/bak/`（U109）；那个目录**建不出来 / 不可写**
    （例如整个修改器装在 Program Files 下）⇒ 退到 `<游戏数据目录>/bak/`。

    ⚠️ **U132**：**不再退回「存档旁边」** —— 游戏只扫存档目录里的 `*.usg`
    ⇒ 备份放那儿会被**游戏当成存档**列出来（U109 的问题又回来了；
    外部审阅报告 P2-13）。⇒ 两处都不行就**报错**
    （写盘流程会因此停下 ⇒ **绝不出现「没备份就写存档」**）。
    """
    target = backup_path_for(save_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(save_path, target)
        return target
    except OSError as exc:
        first = exc
    # 兜底：`<游戏数据目录>/bak/`（游戏不扫那儿）
    alt_dir = fallback_backup_dir()
    try:
        alt_dir.mkdir(parents=True, exist_ok=True)
        p = Path(save_path)
        alt = _next_free(alt_dir, p.stem, p.suffix)
        shutil.copy2(save_path, alt)
        return alt
    except OSError as exc:
        raise OSError("备份放不下（%s；备用目录也不行：%s）" % (first, exc))


class _LockBusy(Exception):
    """同一个存档**已经有另一个写盘在进行**。"""


class _SaveLock:
    """同一存档的**写盘互斥锁**（U133）。

    ⚠️ 为什么要锁：服务端是多线程的 ⇒ 玩家**连点两下「应用更改」**
    就可能有两次写盘同时进行 ⇒ 临时文件、备份、`os.replace` 全都撞车
    ⇒ 存档可能损坏。

    ⚠️ 锁文件叫 `<存档名>.usg.lock` ⇒ **不是 `*.usg`** ⇒ 游戏不会把它
    当存档（游戏只认 `*.usg`）。

    ⚠️ **陈旧锁**：进程崩了会留下锁文件 ⇒ 超过 `stale_after` 秒
    就当它过期（可以直接拿走），否则玩家会永远写不了盘。
    """

    def __init__(self, save_path: Path, stale_after: float = 300.0):
        p = Path(save_path)
        self.path = p.with_name(p.name + ".lock")
        self.stale_after = stale_after
        self._fd = None

    def acquire(self) -> None:
        try:
            if self.path.exists() and \
                    (time.time() - self.path.stat().st_mtime) > self.stale_after:
                self.path.unlink()          # 陈旧锁 ⇒ 拿走
        except OSError:
            pass
        try:
            self._fd = os.open(str(self.path),
                               os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise _LockBusy("这个存档正在被写入（另一个写盘还没结束）—— 请稍后再试")
        try:
            os.write(self._fd, str(os.getpid()).encode("ascii"))
        except OSError:
            pass

    def release(self) -> None:
        try:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
        except OSError:
            pass
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass


def _temp_path_for(save_path: Path) -> Path:
    """写盘用的**临时文件**路径（**必须唯一**，U133）。

    ⚠️ 原来固定叫 `<存档名>.usg.new` ⇒ 两个写盘同时进行时会**写进同一个
    文件** ⇒ 互相踩 ⇒ 存档可能损坏。
    ⇒ 加上进程号 + 随机串（名字仍以 `.new` 结尾 ⇒ **不是 `*.usg`**，
    游戏不会把它当存档）。
    """
    p = Path(save_path)
    return p.with_name("%s.%d.%s.new" % (p.name, os.getpid(),
                                         secrets.token_hex(4)))


def read_entries(save_path: Path, names) -> dict[str, bytes]:
    """从存档里读出指定条目的**原始字节**（读不到的条目不出现在字典里）。"""
    out: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(save_path, "r") as zf:
            available = set(zf.namelist())
            for n in names:
                if n in available:
                    out[n] = zf.read(n)
    except (OSError, zipfile.BadZipFile):
        return out
    return out


def write_overlay(save_path: Path, overlay: dict[str, bytes]) -> WriteOutcome:
    """把 `overlay` 里的条目写进存档，其余条目原样搬运。

    参数
    ----
    save_path : 存档路径
    overlay   : {条目名: 新内容}。**只装真正被改过的条目**。

    返回 `WriteOutcome`；`ok` 为真才代表存档已被替换。

    ⚠️ **U133**：整个流程在**互斥锁**里跑 ⇒ 同一个存档不会有两个写盘
    同时进行（玩家连点「应用更改」也不会撞车）。
    """
    res = WriteOutcome()
    save_path = Path(save_path)

    if not overlay:
        res.errors.append("没有要写入的内容")
        return res

    lock = _SaveLock(save_path)
    try:
        lock.acquire()
    except _LockBusy as exc:
        res.errors.append(str(exc))
        return res
    try:
        return _write_overlay_locked(save_path, overlay, res)
    finally:
        lock.release()


def _write_overlay_locked(save_path: Path, overlay: dict[str, bytes],
                           res: WriteOutcome) -> WriteOutcome:
    """真正的四步（**调用方必须已经拿到锁**）。"""
    # 1) 备份
    try:
        res.backup = make_backup(save_path)
    except OSError as exc:
        res.errors.append(f"备份失败：{exc}")
        return res

    # 2) 写临时文件（**唯一名字**，U133）
    tmp = _temp_path_for(save_path)
    try:
        res.report = repack_overlay(save_path, overlay, tmp)
    except Exception as exc:
        res.errors.append(f"打包失败：{exc}")
        _quiet_unlink(tmp)
        return res

    # 3) 校验：只有 overlay 里那几个条目变了
    try:
        v = verify(save_path, tmp)
    except Exception as exc:
        res.errors.append(f"校验失败：{exc}")
        _quiet_unlink(tmp)
        return res

    expected = set(overlay.keys())
    actual = set(v.changed)
    unexpected = actual - expected
    lost = expected - actual
    if unexpected:
        res.errors.append(f"写回结果与计划不符：多变了 {sorted(unexpected)}")
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
        return sha256_file(save_path) == sha256_file(backup)
    except OSError:
        return False
