"""存档的发现、解包与重打包。

存档 (.usg) 本质是 ZIP 容器。打开 = 解包到每存档工作目录；保存 = 把工作目录
重打包回原 .usg。

"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SaveFile:
    """存档目录中的一个 .usg 文件（含目录下用作备份的编号档）。

    kind: "campaign"（save/campaigns，战役）或 "standalone"（save/games，独立场景）。
    """

    path: Path
    kind: str = "campaign"

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def is_primary(self) -> bool:
        """主存档判定。

        战役档（campaign）：主档名不含 _ / -（游戏写读的 <存档名>.usg），
        带编号/后缀如 blitzkrieg2_0203.usg 是手动/自动备份。

        独立场景档（standalone）：游戏以 <战役>_<场景> 命名
        （如 blitzkrieg_low_countries.usg），含下划线是常态，故全部视为主档；
        仅排除本工具 quick_save 产生的 *_quick 与 *_BACKUP 备份。
        """
        if self.kind == "standalone":
            lowered = self.name.lower()
            return not (lowered.endswith("_quick")
                        or lowered.endswith("_backup"))
        return "_" not in self.name and "-" not in self.name


def scan_saves(save_dir: Path, kind: str = "campaign") -> list[SaveFile]:
    """扫描存档目录下所有 .usg，返回按修改时间倒序的列表。

    kind: "campaign"（save/campaigns）或 "standalone"（save/games）。
    """
    if not save_dir.is_dir():
        return []
    saves = [
        SaveFile(p, kind=kind)
        for p in save_dir.glob("*.usg")
        if p.is_file()
    ]
    saves.sort(key=lambda s: s.path.stat().st_mtime, reverse=True)
    return saves


def scan_all_saves(campaigns_dir: Path, games_dir: Path) -> list[SaveFile]:
    """扫描战役与独立场景两个存档目录，合并后按修改时间倒序返回。

    每个 SaveFile 携带 kind，便于调用方区分来自哪个目录。
    """
    saves = scan_saves(campaigns_dir, "campaign") + scan_saves(games_dir, "standalone")
    saves.sort(key=lambda s: s.path.stat().st_mtime, reverse=True)
    return saves


def primary_saves(saves: list[SaveFile]) -> list[SaveFile]:
    """过滤出“主存档”（用于选择打开的对象）。"""
    return [s for s in saves if s.is_primary]


def _relative_to(root: Path, file_path: Path) -> str:
    return str(file_path.relative_to(root))


def extract_archive(archive_path: Path, target_dir: Path) -> None:
    """把存档解包到 target_dir。

    解包前清空 target_dir：上次运行残留的文件既不属于本存档，又会被
    pack_directory 原样打包回 .usg，混入不属于本存档的内容。
    target_dir 只存放 .usg 的展开副本，清空不会丢掉唯一数据。
    """
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(path=target_dir)


def pack_directory(source_dir: Path, archive_path: Path) -> None:
    """把 source_dir 下所有内容打包为 .usg（ZIP），用于保存。

    ⚠️ **已弃用，请改用 `packing.repack`。**
    这个函数用 `rglob` 遍历目录再逐个 `zf.write()`，实测会**打乱条目顺序**
    并把时间戳全部改成打包时刻（文档 §11.4）。`packing.repack` 按原存档的
    条目清单与顺序重建，并沿用原存档的元数据。
    保留仅为兼容旧调用。
    """
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        for f in source_dir.rglob("*"):
            if f.is_file():
                zf.write(f, _relative_to(source_dir, f))


class SaveSession:
    """绑定到某个存档文件的会话：管理其工作目录。

    work_dir: 解包后的工作目录（读/写 YAML 都发生在这里）。
    所有对存档的修改先落在 work_dir，只有 save() 才真正写回 .usg。
    """

    def __init__(self, config, save: SaveFile):
        self.config = config
        self.save = save
        # 每存档隔离工作目录
        self.work_dir = config.save_dir_for(save.name) / "work"
        self.open()

    @property
    def name(self) -> str:
        return self.save.name

    def open(self) -> None:
        extract_archive(self.save.path, self.work_dir)
        print(f"已加载存档: {self.save.path.name} -> {self.work_dir}")

    def reload(self) -> None:
        """重新从磁盘 .usg 解包（相当于丢弃本地未保存修改）。"""
        self.open()

    def commit(self) -> bool:
        """把工作目录打包覆盖回 .usg。

        用保真打包器（packing.repack）：条目顺序与元数据沿用原存档，
        只有工作目录里被改过的文件内容会变（§11.4 / §11.5）。
        """
        from save_modifier_core import packing

        report = packing.repack(self.save.path, self.work_dir, self.save.path)
        if report.added:
            print(f"⚠️ 工作目录里有 {len(report.added)} 个原存档没有的文件，"
                  f"已忽略（不写进存档）：{', '.join(report.added[:5])}")
        if report.missing:
            print(f"ℹ️ 有 {len(report.missing)} 个条目在工作目录里缺失，"
                  f"已从原存档原样取回。")
        if report.changed:
            print(f"已保存到: {self.save.path.name}（改动 {len(report.changed)} 个文件）")
        else:
            print(f"已保存到: {self.save.path.name}（内容无变化）")
        return True


def quick_save_file(save: SaveFile, suffix: str) -> Path:
    """把存档文件备份为 <存档名><后缀>.usg（与游戏另存为同目录）。

    只复制磁盘上的 .usg，不触碰解包工作目录：与 REPL 的 qs 一致，
    未 save 的修改本来就不在磁盘档里。
    """
    target = save.path.with_name(f"{save.name}{suffix}.usg")
    shutil.copy2(save.path, target)
    return target


def quick_load_file(save: SaveFile, suffix: str) -> Path | None:
    """用 <存档名><后缀>.usg 覆盖主存档；备份不存在时返回 None。"""
    source = save.path.with_name(f"{save.name}{suffix}.usg")
    if not source.is_file():
        return None
    shutil.copy2(source, save.path)
    return source


def quick_save(session: SaveSession, suffix: str) -> Path | None:
    """备份当前 .usg 为 <存档名><后缀>.usg（与游戏另存为同目录）。"""
    return quick_save_file(session.save, suffix)


def quick_load(session: SaveSession, suffix: str) -> bool:
    """用备份 <存档名><后缀>.usg 覆盖主存档并重新加载。"""
    source = quick_load_file(session.save, suffix)
    if source is None:
        print(f"错误：未找到备份存档 {session.save.name}{suffix}.usg")
        return False
    session.reload()
    print(f"已从备份 {source.name} 恢复。")
    return True


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def detect_save_kind(archive_path: Path) -> str:
    """判定 .usg 的存档类型："campaign" 或 "standalone"。

    读压缩包内根 main.yml：standalone_scenario 非空 → 独立场景；否则视为战役。
    无法读取（损坏/缺 main.yml）时按战役处理并返回 "campaign"。
    """
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            raw = zf.read("main.yml").decode("utf-8")
        data = yaml.safe_load(raw) or {}
        if data.get("standalone_scenario"):
            return "standalone"
    except (KeyError, OSError, zipfile.BadZipFile, yaml.YAMLError):
        pass
    return "campaign"


def dump_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
