"""存档发现：扫描存档目录，产出存档清单。

目录布局
--------
```
%LOCALAPPDATA%\\.uoc2\\save\\
├─ campaigns\\<战役>.usg       战役存档（**游戏认**）
├─ games\\<战役>_<场景>.usg     独立场景存档（**游戏认**）
└─ <玩家自建的目录>\\*.usg      玩家自己整理的旧存档（**游戏不认**，改名叫什么都行）
```

⚠️ **游戏只读 `campaigns` 与 `games` 两个目录**（实测）⇒ 根下其它目录都是
玩家自己放的归档区 ⇒ 修改器**照样识别**（`archived=True`），不挑目录名。

`save_id` 用**相对存档根目录的 posix 路径**（如 `campaigns/west.usg`）——
它稳定、唯一、可反解回路径，跨机器也能用。
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import yamlio
from .paths import CorePaths

__all__ = ["SaveInfo", "list_saves", "resolve_save_id", "read_root_main",
           "is_archived_path"]


@dataclass(frozen=True)
class SaveInfo:
    """一个存档的清单条目。"""

    #: 相对存档根目录的 posix 路径，例如 `campaigns/west-Conference3-1.usg`
    save_id: str
    #: 绝对路径
    path: Path
    #: `campaign`（战役存档）| `standalone`（独立场景存档）
    kind: str = "campaign"
    #: 是否在**玩家自建的归档目录**里（游戏不认的位置 —— 存档根下非 campaigns/games）
    archived: bool = False
    #: 是否是游戏当前会写的那一份（排除备份/副本）
    is_primary: bool = True
    #: 战役包 id（根 `main.yml` 的 `campaign_id`）
    campaign_id: str | None = None
    #: 当前战斗的场景 id（`in_state.scenario`），不在战斗里为 None
    scenario: str | None = None
    #: 独立场景 id（`standalone_scenario`）
    standalone_scenario: str | None = None
    #: 战役名的**本地化键**（如 `id_campaign_name_c_stalingrad_p_dlc4`）
    #: —— 中文名要用 `locale` 查，别自己猜（实测 → 「斯大林格勒」）
    campaign_name: str | None = None
    #: 最后修改时间（epoch 秒）
    mtime: float = 0.0
    #: 文件字节数
    size: int = 0

    @property
    def name(self) -> str:
        """存档文件名（不含扩展名）。"""
        return self.path.stem

    @property
    def display_name(self) -> str:
        """给 GUI 用的可读名。"""
        if self.standalone_scenario:
            return f"{self.name}（独立场景 · {self.standalone_scenario}）"
        if self.campaign_id:
            return f"{self.name}（战役 · {self.campaign_id}）"
        return self.name

    @property
    def is_standalone(self) -> bool:
        return self.kind == "standalone"


def read_root_main(path: Path) -> dict:
    """只读存档根 `main.yml`。读不到就返回空字典（不抛异常）。"""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read("main.yml")
    except (KeyError, OSError, zipfile.BadZipFile):
        return {}
    try:
        data = yamlio.load(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _is_backup_name(stem: str) -> bool:
    """备份 / 副本类文件名 —— 游戏或玩家自己造的，不算"当前存档"。

    ⚠️ **必须认得备份链**（U28 修）：`make_backup` 的命名是
    `<名字>_BACKUP.usg` / `_BACKUP_2.usg` / `_BACKUP_3.usg` …（数字递增）。
    只认 `_backup` 结尾的话，**第 2 个以后的备份会被当成正常存档列进列表**
    —— 实测用户的存档列表里混进过 `_BACKUP_2.usg`。
    """
    low = stem.lower()
    if low.endswith("_backup") or low.endswith("_quick"):
        return True
    # 备份链：`<名字>_backup_<数字>`
    if "_backup_" in low:
        tail = low.rsplit("_backup_", 1)[-1]
        if tail.isdigit():
            return True
    return "副本" in stem or "copy" in low


def _scan_dir(directory: Path, kind: str, archived: bool,
              root: Path, out: list[SaveInfo]) -> None:
    if not directory.is_dir():
        return
    for p in sorted(directory.rglob("*.usg")):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        main = read_root_main(p)
        standalone = main.get("standalone_scenario") or None
        in_state = main.get("in_state") or {}
        scenario = in_state.get("scenario") or None
        out.append(SaveInfo(
            save_id=rel,
            path=p,
            kind="standalone" if standalone else kind,
            archived=archived,
            is_primary=not _is_backup_name(p.stem),
            campaign_id=main.get("campaign_id") or None,
            campaign_name=main.get("campaign_name") or None,
            scenario=scenario,
            standalone_scenario=standalone,
            mtime=st.st_mtime,
            size=st.st_size,
        ))


def is_archived_path(path: Path, paths: CorePaths | None = None) -> bool:
    """这个存档是不是放在**玩家自建的归档目录**里（游戏不认的位置）。

    ⚠️ 判定只看**相对存档根的第一段目录名**是不是 `campaigns` / `games`
    ⇒ 玩家把归档区叫什么都行（不挑 "Old Saves" 这个名字）。
    """
    paths = paths or CorePaths.discover()
    try:
        rel = Path(path).resolve().relative_to(paths.save_root.resolve())
    except (ValueError, OSError):
        return False
    parts = rel.parts
    return bool(parts) and parts[0] not in ("campaigns", "games")


def list_saves(paths: CorePaths | None = None, *,
               include_archived: bool = True) -> list[SaveInfo]:
    """扫描全部存档，按最后修改时间倒序。

    参数
    ----
    paths : 路径集合；不给就自动探测。
    include_archived : 是否包含**玩家自建归档目录**里的存档（默认包含）。

        ⚠️ 游戏只认 `campaigns` 与 `games` 两个目录；根下其它目录都是玩家
        自己整理的旧存档 —— **目录名叫什么都行**（不挑 "Old Saves"）。
    """
    paths = paths or CorePaths.discover()
    root = paths.save_root
    out: list[SaveInfo] = []
    _scan_dir(paths.campaigns_dir, "campaign", False, root, out)
    _scan_dir(paths.games_dir, "standalone", False, root, out)
    if include_archived:
        for d in paths.archive_dirs():
            _scan_dir(d, "campaign", True, root, out)
    out.sort(key=lambda s: s.mtime, reverse=True)
    return out


def resolve_save_id(save_id: str, paths: CorePaths | None = None) -> Path:
    """把 `save_id` 还原成绝对路径。

    接受 posix 相对路径（`campaigns/west.usg`），也接受绝对路径。
    """
    paths = paths or CorePaths.discover()
    p = Path(save_id)
    if p.is_absolute():
        return p
    return paths.save_root / Path(*save_id.split("/"))
