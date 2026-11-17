"""保真打包：按原存档的条目清单与顺序重建 .usg。

为什么要单独写一个打包器
------------------------
`savefile.pack_directory` 用 `rglob` 遍历工作目录再逐个 `zf.write()`，
实测（文档 §11.4）它会：

* **打乱条目顺序** —— `rglob` 的遍历顺序与原 ZIP 的条目顺序无关；
* **把时间戳全部改成打包时刻** —— 原存档里每个条目的 `date_time` 被覆盖。

内容本身是**无损**的（deflate 确定性，实测 562 个条目逐条 SHA256 全等），
但上面两点会让"这个存档到底被改过哪些文件"在 ZIP 层面不可判定。
本模块按下面三条规则重建：

1. **条目清单与顺序** —— 完全沿用原存档；
2. **元数据** —— `date_time` / `external_attr` / `create_system` / `compress_type`
   全部沿用原存档；
3. **内容** —— 优先取调用方给的内容（overlay）；没给的条目从原存档原样取回。

游戏自己的写盘约定（实测 70 个存档一致）
----------------------------------------
游戏写出的 .usg 里**所有条目共用同一个时间戳**（写盘那一刻），且

    external_attr = 0o600 << 16 = 0x01800000
    create_system = 0
    compress_type = ZIP_DEFLATED
    没有目录条目

沿用原存档的元数据，等于**自动符合这个约定**（原存档的时间戳本身就是游戏写的）。
"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

__all__ = [
    "PackReport",
    "list_entries",
    "repack",
    "repack_overlay",
    "verify",
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class PackReport:
    """一次打包 / 比对的结果。"""

    output: Path | None = None
    total: int = 0
    #: 内容与原存档不同的条目名（应当只有被显式修改过的那几个）
    changed: list[str] = field(default_factory=list)
    #: 新出现的条目 —— **正常情况下必须为空**（§7.2 W1：绝不新建文件）
    added: list[str] = field(default_factory=list)
    #: 工作目录里有、但没能从工作目录取到的条目（已从原存档原样回填）
    missing: list[str] = field(default_factory=list)
    #: 条目顺序与原存档不一致（只有重建才可能出现）
    reordered: bool = False

    @property
    def ok(self) -> bool:
        """打包结果是否"只改了该改的"。"""
        return not self.added and not self.reordered

    def summary(self) -> str:
        parts = [f"条目 {self.total}"]
        if self.changed:
            parts.append(f"改动 {len(self.changed)}")
        if self.added:
            parts.append(f"⚠️ 多出 {len(self.added)}")
        if self.missing:
            parts.append(f"缺失回填 {len(self.missing)}")
        if self.reordered:
            parts.append("⚠️ 顺序不一致")
        return " / ".join(parts)


def list_entries(path: Path) -> list[tuple[str, str]]:
    """返回 [(条目名, 内容 SHA256)]，顺序与 ZIP 内部一致。"""
    with zipfile.ZipFile(path, "r") as zf:
        return [(i.filename, _sha256(zf.read(i.filename))) for i in zf.infolist()]


def _work_path(work_dir: Path, entry_name: str) -> Path:
    """把 ZIP 条目名（posix 风格）映射到工作目录下的实际路径。"""
    return work_dir / Path(PurePosixPath(entry_name))


def repack_overlay(original: Path,
                   overlay: Mapping[str, bytes],
                   output: Path,
                   *,
                   extra_entries: Mapping[str, bytes] | None = None) -> PackReport:
    """按原存档的条目清单与顺序重建 ZIP，只把 `overlay` 里的条目换成新内容。

    这是核心库写回的主入口：**overlay 只装真正被改过的条目**，
    其余条目一律从原存档原样取回 —— 内存占用与改动量成正比，
    与存档总大小无关。

    参数
    ----
    original : 原存档路径（提供条目清单、顺序与元数据）
    overlay  : {条目名: 新内容}，条目名是 ZIP 内的 posix 路径
    output   : 输出路径（先写临时文件再原子替换）
    extra_entries : 允许**新增**的条目。默认空 —— §7.2 W1 规定"绝不新建文件"。

    返回 PackReport：哪些条目内容变了、哪些是多余的、顺序是否一致。
    """
    report = PackReport(output=output)

    # 先把内容全部读进内存并关闭源 ZIP —— 这样 output 可以和 original 同路径
    # （覆盖保存时就是这种情况），否则 Windows 上替换被打开的文件会失败。
    #
    # 原存档的内容哈希必须在这里抓 —— output 与 original 同路径时，
    # 打包完成后 original 已经是新文件，事后再读就分不出差异了。
    payloads: list[tuple[zipfile.ZipInfo, bytes]] = []
    original_hashes: dict[str, str] = {}
    with zipfile.ZipFile(original, "r") as src:
        src_infos = src.infolist()
        src_names = {i.filename for i in src_infos}

        report.added = sorted(set(overlay) - src_names)
        extra = dict(extra_entries or {})
        report.added.extend(sorted(set(extra) - src_names))

        for info in src_infos:
            orig_data = src.read(info.filename)
            original_hashes[info.filename] = _sha256(orig_data)
            if info.filename in overlay:
                data = overlay[info.filename]
            else:
                data = orig_data
            payloads.append((info, data))

        # 新增条目（正常为空）—— 追加在最后，保持原条目顺序不变
        new_names = []
        for name, data in extra.items():
            if name in src_names:
                continue
            zi = zipfile.ZipInfo(name, date_time=src_infos[0].date_time
                                 if src_infos else (1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zi.create_system = 0
            payloads.append((zi, data))
            new_names.append(name)

    tmp = output.with_name(output.name + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for info, data in payloads:
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zi.create_system = info.create_system
                zi.comment = info.comment
                dst.writestr(zi, data)
                report.total += 1
        tmp.replace(output)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise

    # 用实际结果覆盖"改动列表"与"顺序一致性"
    new_entries = list_entries(output)
    old_order = list(original_hashes.keys()) + new_names
    report.changed = [n for n, h in new_entries if original_hashes.get(n) != h]
    report.reordered = [n for n, _ in new_entries] != old_order
    return report


def repack(original: Path, work_dir: Path, output: Path, *,
           extra_entries: Mapping[str, bytes] | None = None) -> PackReport:
    """把工作目录的内容打包成 .usg（兼容旧 REPL 工具的入口）。

    与 `repack_overlay` 的区别：这里的内容来自**整个工作目录**，
    工作目录里有而原存档没有的文件会被记为 `added`（**不会写进存档**）；
    原存档里有而工作目录缺的文件会被记为 `missing`（已从原存档原样回填）。
    """
    overlay: dict[str, bytes] = {}
    for f in work_dir.rglob("*"):
        if f.is_file():
            overlay[f.relative_to(work_dir).as_posix()] = f.read_bytes()

    report = repack_overlay(original, overlay, output, extra_entries=extra_entries)

    # 工作目录应当包含原存档的全部条目 —— 少了的要报告出来（已自动回填）
    with zipfile.ZipFile(original, "r") as src:
        report.missing = sorted(set(src.namelist()) - set(overlay))
    return report


def verify(original: Path, output: Path) -> PackReport:
    """比对两个 .usg：条目数、顺序、逐条内容 SHA256。

    验收口径见文档 §11.5：除被显式修改的 L1 文件外，其余条目必须**字节级一致**。
    """
    report = PackReport(output=output)
    old_entries = list_entries(original)
    new_entries = list_entries(output)
    report.total = len(new_entries)

    old_map = dict(old_entries)
    new_map = dict(new_entries)
    report.changed = [n for n, h in new_entries if old_map.get(n) != h]
    report.missing = sorted(set(old_map) - set(new_map))
    report.added = sorted(set(new_map) - set(old_map))
    report.reordered = [n for n, _ in old_entries] != [n for n, _ in new_entries]
    return report
