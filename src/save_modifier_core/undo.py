"""撤销栈：落盘、按 commit 粒度、撤销前校验基准。

规范 §6.4.2 的四条硬要求
------------------------

1. **粒度 = 一次 commit** —— 一次改了 3 个单位，就一起撤销。
   更细的粒度对傻瓜式 GUI 反而更难用。
2. **落盘** —— 栈写在存档旁边（`<存档名>.undo.json`），关掉程序也能撤。
   游戏只扫 `*.usg`，`.undo.json` 不会被它当成存档。
3. **撤销前重新校验基准** —— 玩家可能在游戏里手动改过同一个存档，
   这时栈里记的"我改完时的样子"已经过期 ⇒ **拒绝撤销并明确提示**，不硬改。
4. **走完整写回管线** —— 撤销不是"直接写回旧值"，而是和 `commit` 走同一条路
   （备份 → 写临时文件 → 校验 → 原子替换）。

栈里存什么
----------

每次 commit 成功后，压一条记录：

* `before` —— 被改条目的**改前原始字节**（zlib 压缩 + base64）；
* `after_sha256` —— 被改条目**改后内容**的 SHA256。

`after_sha256` 就是**基准**：撤销前先读当前存档，算这几个条目的 SHA256，
和记录里的对不上 ⇒ 基准过期 ⇒ 拒绝。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .paths import modifier_data_dir
from .writer import WriteOutcome, read_entries, sha256_bytes, write_overlay

__all__ = [
    "STACK_VERSION",
    "UndoEntry",
    "UndoRecord",
    "UndoResult",
    "load_stack",
    "make_record",
    "peek",
    "push",
    "remove_top",
    "stack_path_for",
    "undo_save",
]

#: 栈文件格式版本
STACK_VERSION = 1

#: 最多保留多少条记录（一次 commit 一条）
MAX_RECORDS = 20

#: 栈文件大小上限；超了就从最旧的开始丢
MAX_STACK_BYTES = 32 * 1024 * 1024

#: `before` 字节的编码方式
_CODEC = "zlib+b64"


# ---------------------------------------------------------------- 数据结构


@dataclass
class UndoEntry:
    """一个被改条目的撤销信息。"""

    #: ZIP 内的条目名（如 `units.yml`）
    entry: str
    #: 改前的**原始字节**（还原时逐字节写回）
    before: bytes = b""
    #: 改后内容的 SHA256 —— 撤销前的基准
    after_sha256: str = ""

    def to_json(self) -> dict:
        return {
            "entry": self.entry,
            "codec": _CODEC,
            "before": base64.b64encode(
                zlib.compress(self.before, 6)).decode("ascii"),
            "after_sha256": self.after_sha256,
        }

    @staticmethod
    def from_json(d: dict) -> "UndoEntry | None":
        entry = d.get("entry")
        if not isinstance(entry, str) or not entry:
            return None
        blob = d.get("before")
        if not isinstance(blob, str):
            return None
        try:
            if d.get("codec") == _CODEC:
                raw = zlib.decompress(base64.b64decode(blob.encode("ascii")))
            else:
                # 老格式（未压缩的 base64）
                raw = base64.b64decode(blob.encode("ascii"))
        except (ValueError, zlib.error):
            return None
        after = d.get("after_sha256")
        return UndoEntry(
            entry=entry,
            before=raw,
            after_sha256=after if isinstance(after, str) else "",
        )


@dataclass
class UndoRecord:
    """一次 commit 的撤销记录。"""

    #: 记录 id（uuid4 hex）
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    #: ISO 时间戳
    time: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    #: 人类可读的一句话描述（GUI 显示用）
    summary: str = ""
    #: 被改的条目
    entries: list[UndoEntry] = field(default_factory=list)

    @property
    def entry_names(self) -> list[str]:
        return [e.entry for e in self.entries]

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "time": self.time,
            "summary": self.summary,
            "entries": [e.to_json() for e in self.entries],
        }

    @staticmethod
    def from_json(d: dict) -> "UndoRecord | None":
        if not isinstance(d, dict):
            return None
        raw_entries = d.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            return None
        entries = []
        for re_ in raw_entries:
            if not isinstance(re_, dict):
                continue
            e = UndoEntry.from_json(re_)
            if e is not None:
                entries.append(e)
        if not entries:
            return None
        return UndoRecord(
            id=str(d.get("id") or uuid.uuid4().hex),
            time=str(d.get("time") or ""),
            summary=str(d.get("summary") or ""),
            entries=entries,
        )


@dataclass
class UndoResult:
    """撤销的结果。"""

    ok: bool = False
    #: 栈是空的 —— 不是错误，只是没什么可撤
    nothing_to_do: bool = False
    path: Path | None = None
    backup: Path | None = None
    #: 被还原的条目
    restored: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.nothing_to_do:
            return "没有可撤销的修改"
        if not self.ok:
            return "❌ " + "；".join(self.errors[:3])
        return f"已撤销 {len(self.restored)} 个文件的修改"


# ---------------------------------------------------------------- 栈文件


def _normalized_save_identity(save_path: Path) -> str:
    """返回用于撤销栈命名的规范化绝对存档路径。"""
    p = Path(save_path).expanduser()
    try:
        p = p.resolve(strict=False)
    except OSError:
        p = Path(os.path.abspath(os.path.normpath(str(p))))
    return os.path.normcase(os.path.normpath(str(p)))


def _legacy_stack_path_for(save_path: Path) -> Path:
    """旧布局：存档旁边的 `<存档名>.undo.json`；仅用于读取兼容。"""
    p = Path(save_path)
    return p.with_name(f"{p.stem}.undo.json")


def stack_path_for(save_path: Path) -> Path:
    """新撤销栈路径：`<appdata>/modifier/undo/` 下按存档路径身份命名。"""
    identity = _normalized_save_identity(save_path).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    return modifier_data_dir() / "undo" / f"{digest}.undo.json"


def load_stack(save_path: Path) -> tuple[list[UndoRecord], list[str]]:
    """读栈。

    返回 `(记录列表, 错误信息)`。
    文件不存在 ⇒ 空列表、空错误；文件坏了 ⇒ 空列表 + 一条错误（**不静默吞掉**）。
    """
    p = stack_path_for(save_path)
    # 新栈文件存在（包括撤空后的空栈）时，绝不回读旧栈，避免旧记录复活。
    if not p.is_file():
        p = _legacy_stack_path_for(save_path)
    if not p.is_file():
        return [], []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"撤销栈文件读不出来：{exc}"]
    if not isinstance(data, dict):
        return [], ["撤销栈文件格式不对（不是对象）"]
    raw_records = data.get("records")
    if not isinstance(raw_records, list):
        return [], ["撤销栈文件格式不对（records 不是数组）"]
    out: list[UndoRecord] = []
    errors: list[str] = []
    for r in raw_records:
        rec = UndoRecord.from_json(r) if isinstance(r, dict) else None
        if rec is None:
            errors.append("撤销栈里有 1 条记录读不出来，已跳过")
            continue
        out.append(rec)
    return out, errors


def _dump_stack(records: list[UndoRecord]) -> bytes:
    payload = {
        "version": STACK_VERSION,
        "records": [r.to_json() for r in records],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")


def _prune(records: list[UndoRecord]) -> list[UndoRecord]:
    """丢掉太旧的记录，直到条数与体积都在限额内。"""
    records = records[-MAX_RECORDS:]
    while len(records) > 1 and len(_dump_stack(records)) > MAX_STACK_BYTES:
        records = records[1:]
    return records


def _write_stack(save_path: Path, records: list[UndoRecord]) -> list[str]:
    """把栈原子写盘（先写 `.tmp` 再 `os.replace`）。返回警告。

    新栈目录创建失败、临时写入失败或原子替换失败都会返回警告；
    旧旁置栈不会被改动。
    """
    p = stack_path_for(save_path)
    data = _dump_stack(records)
    tmp = p.with_name(p.name + ".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        os.replace(tmp, p)
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return [f"撤销栈写盘失败：{exc}"]
    return []


def push(save_path: Path, record: UndoRecord) -> list[str]:
    """压栈并落盘。返回警告（落盘失败时**不抛异常** —— 提交本身已经成功了）。"""
    records, errors = load_stack(save_path)
    records.append(record)
    records = _prune(records)
    return errors + _write_stack(save_path, records)


def peek(save_path: Path) -> UndoRecord | None:
    """看栈顶（不改动任何东西）。"""
    records, _ = load_stack(save_path)
    return records[-1] if records else None


def remove_top(save_path: Path) -> list[str]:
    """弹掉栈顶并落盘。返回警告。"""
    records, errors = load_stack(save_path)
    if records:
        records = records[:-1]
        errors = errors + _write_stack(save_path, records)
    return errors


# ---------------------------------------------------------------- 撤销


def _baseline_errors(save_path: Path, record: UndoRecord) -> list[str]:
    """基准校验：当前存档里的那几个条目必须还是"我改完时的样子"。"""
    cur = read_entries(save_path, record.entry_names)
    errs: list[str] = []
    for e in record.entries:
        raw = cur.get(e.entry)
        if raw is None:
            errs.append(f"{e.entry}：存档里已经没有这个条目了")
            continue
        h = sha256_bytes(raw)
        if h != e.after_sha256:
            errs.append(
                f"{e.entry}：内容与我改完时对不上"
                f"（现在 {h[:12]}…，记录 {e.after_sha256[:12]}…）")
    return errs


def baseline_ok(save_path: Path, record: UndoRecord) -> bool:
    """这条记录**现在**还能撤吗？（基准校验的公开入口，U134）

    ⚠️ 栈顶可能**撤不了**（存档后来又被改过）⇒ 界面要如实说
    （`api_undo_stack` 的 `undoable`），别让玩家反复点一个注定失败的按钮。
    """
    return not _baseline_errors(save_path, record)


def undo_save(save_path: Path) -> UndoResult:
    """撤销上一次 commit。

    完整流程：
    1. 读栈顶；
    2. **校验基准** —— 当前内容必须等于记录里的"改后哈希"；
    3. 走**和 commit 完全相同**的写回管线（备份 → 临时文件 → 校验 → 原子替换），
       把条目还原成"改前字节"；
    4. 成功后弹栈并落盘。
    """
    save_path = Path(save_path)
    res = UndoResult(path=save_path)

    records, errs = load_stack(save_path)
    res.warnings.extend(errs)
    if not records:
        res.nothing_to_do = True
        if errs:
            res.errors.extend(errs)
        return res

    record = records[-1]

    # 基准校验 —— 不过就拒绝，绝不硬改
    # ⚠️ 这条记录**撤不了**了（存档后来又被改过），
    # 但**不弹栈** —— 玩家把存档从备份还原回来之后，它又能撤了
    # （仓库护栏：`tests/test_undo.py::test_stack_survives_rejected_undo`）。
    # ⇒ 改成让**界面知道**：服务端算「还有几条能撤」（`undoable`），
    #   界面据此禁用撤销按钮、标出「已过期」的记录。
    bad = _baseline_errors(save_path, record)
    if bad:
        res.errors.append(
            "撤销基准已过期，拒绝执行：存档在你改完之后又被动过"
            "（可能是在游戏里手动改的）")
        res.errors.extend(bad)
        res.warnings.append(
            # ⚠️ U109 起备份改放 `<修改器目录>/bak/` ⇒ 提示也要跟着改
            "提示：可以把 bak 文件夹里的 `_BACKUP.usg` 复制回去作为回退")
        return res

    # 走完整写回管线
    overlay = {e.entry: e.before for e in record.entries}
    out: WriteOutcome = write_overlay(save_path, overlay)
    if not out.ok:
        res.errors.extend(out.errors)
        return res

    res.backup = out.backup
    res.restored = list(out.changed)
    res.ok = True

    # 弹栈
    res.warnings.extend(remove_top(save_path))
    return res


def make_record(entries: dict[str, tuple[bytes, str]], summary: str) -> UndoRecord:
    """用 commit 的前后内容造一条撤销记录。

    参数
    ----
    entries : {条目名: (改前字节, 改后内容的 SHA256)}
    summary : 一句话描述
    """
    return UndoRecord(
        summary=summary,
        entries=[UndoEntry(entry=name, before=before, after_sha256=after)
                 for name, (before, after) in entries.items()],
    )
