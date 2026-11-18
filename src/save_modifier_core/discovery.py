"""存档发现：扫描存档目录，产出存档清单。

目录布局（游戏自己定的）
------------------------
```
%LOCALAPPDATA%\\.uoc2\\save\\
├─ campaigns\\<战役>.usg          战役存档（游戏正在写的那份）
├─ games\\<战役>_<场景>.usg        独立场景存档
└─ Old Saves\\<战役>\\<难度>\\*.usg 游戏自己归档的历史存档
```

`save_id` 用**相对存档根目录的 posix 路径**（如 `campaigns/west.usg`）——
它稳定、唯一、可反解回路径，跨机器也能用。
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import yamlio
from .paths import CorePaths

__all__ = ["SaveInfo", "list_saves", "resolve_save_id", "read_root_main"]


@dataclass(frozen=True)
class SaveInfo:
    """一个存档的清单条目。"""

    #: 相对存档根目录的 posix 路径，例如 `campaigns/west-Conference3-1.usg`
    save_id: str
    #: 绝对路径
    path: Path
    #: `campaign`（战役存档）| `standalone`（独立场景存档）
    kind: str = "campaign"
    #: 是否在游戏的「Old Saves」归档目录里
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
    """备份 / 副本类文件名 —— 游戏或玩家自己造的，不算"当前存档"。"""
    low = stem.lower()
    if low.endswith("_backup") or low.endswith("_quick"):
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


def list_saves(paths: CorePaths | None = None, *,
               include_archived: bool = True) -> list[SaveInfo]:
    """扫描全部存档，按最后修改时间倒序。

    参数
    ----
    paths : 路径集合；不给就自动探测。
    include_archived : 是否包含「Old Saves」里的历史存档（默认包含）。
    """
    paths = paths or CorePaths.discover()
    root = paths.save_root
    out: list[SaveInfo] = []
    _scan_dir(paths.campaigns_dir, "campaign", False, root, out)
    _scan_dir(paths.games_dir, "standalone", False, root, out)
    if include_archived:
        _scan_dir(paths.old_saves_dir, "campaign", True, root, out)
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
