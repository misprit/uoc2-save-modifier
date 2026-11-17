"""测试公用工具：定位本机的真实存档。

真实存档不是仓库的一部分（`.gitignore` 排除 `*.usg`），
所以找不到就跳过相关测试，而不是让测试失败。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["save_root", "find_saves", "game_dir"]


def save_root() -> Path:
    """游戏存档根目录 `%LOCALAPPDATA%\\.uoc2\\save`。"""
    return Path(os.environ.get(
        "UOC2_SAVE_ROOT",
        Path.home() / "AppData" / "Local" / ".uoc2" / "save"))


def game_dir() -> Path | None:
    """游戏安装目录（探测不到返回 None）。"""
    env = os.environ.get("UOC2_GAME_DIR")
    if env:
        return Path(env)
    from save_modifier_core.paths import detect_game_dir
    return detect_game_dir()


def find_saves(limit_per_dir: int = 2) -> list[Path]:
    """找出本机的真实存档（战役 / 独立场景 / 历史存档各取几个）。"""
    root = save_root()
    out: list[Path] = []
    for sub in ("campaigns", "games"):
        d = root / sub
        if d.is_dir():
            out.extend(sorted(d.glob("*.usg"))[:limit_per_dir])
    old = root / "Old Saves"
    if old.is_dir():
        out.extend(sorted(old.rglob("*.usg"))[:limit_per_dir])
    return out
