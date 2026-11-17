"""路径定位：游戏数据目录、存档目录、游戏包目录。

核心库**不读配置文件**也能工作 —— 全部路径靠探测 + 环境变量覆盖。
这样 GUI 那边不用先跑一遍配置向导。

环境变量
--------
* `UOC2_APPDATA` —— 游戏数据目录（默认 `%LOCALAPPDATA%\\.uoc2`）
* `UOC2_GAME_DIR` —— 游戏安装目录（默认自动探测）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CorePaths", "APP_DIR_NAME"]

APP_DIR_NAME = ".uoc2"

#: 游戏安装目录的候选位置（按优先级）
_GAME_DIR_CANDIDATES = (
    r"D:\SteamLibrary\steamapps\common\Unity of Command 2",
    r"C:\Program Files (x86)\Steam\steamapps\common\Unity of Command 2",
    r"C:\Program Files\Steam\steamapps\common\Unity of Command 2",
    r"D:\Program Files (x86)\Steam\steamapps\common\Unity of Command 2",
)


def _default_appdata() -> Path:
    env = os.environ.get("UOC2_APPDATA")
    if env:
        return Path(env).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def _steam_root() -> Path | None:
    """从注册表里找 Steam 的安装目录（Windows）。"""
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:      # pragma: no cover - 非 Windows
        return None
    for hive, key in ((winreg.HKEY_CURRENT_USER,
                       r"Software\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE,
                       r"SOFTWARE\WOW6432Node\Valve\Steam")):
        try:
            with winreg.OpenKey(hive, key) as k:
                val, _ = winreg.QueryValueEx(k, "SteamPath")
                return Path(val)
        except OSError:
            continue
    return None


def _candidate_game_dirs() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("UOC2_GAME_DIR")
    if env:
        out.append(Path(env).expanduser())
    steam = _steam_root()
    if steam:
        out.append(steam / "steamapps" / "common" / "Unity of Command 2")
        libs = steam / "steamapps" / "libraryfolders.vdf"
        if libs.is_file():
            try:
                text = libs.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith('"') and "\\\\" in line:
                        p = Path(line.strip('"').replace("\\\\", "\\"))
                        out.append(p / "steamapps" / "common" / "Unity of Command 2")
            except OSError:
                pass
    out.extend(Path(p) for p in _GAME_DIR_CANDIDATES)
    return out


def _looks_like_game_dir(p: Path) -> bool:
    """判断一个目录是不是游戏安装目录。

    判定依据：里面有 `_packages` 或 `lib/uoc2`。
    """
    if not p.is_dir():
        return False
    return (p / "_packages").is_dir() or (p / "lib" / "uoc2").is_dir()


def detect_game_dir() -> Path | None:
    """探测游戏安装目录；找不到返回 None（不报错 —— 存档功能不依赖游戏本体）。"""
    seen: set[Path] = set()
    for cand in _candidate_game_dirs():
        try:
            rp = cand.resolve()
        except OSError:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        if _looks_like_game_dir(rp):
            return rp
    return None


@dataclass(frozen=True)
class CorePaths:
    """一组已定位的路径。"""

    uoc2_appdata: Path
    game_dir: Path | None = None

    # ---- 存档目录 ----

    @property
    def save_root(self) -> Path:
        return self.uoc2_appdata / "save"

    @property
    def campaigns_dir(self) -> Path:
        """战役存档目录。"""
        return self.save_root / "campaigns"

    @property
    def games_dir(self) -> Path:
        """独立场景存档目录。"""
        return self.save_root / "games"

    @property
    def old_saves_dir(self) -> Path:
        """游戏自己归档的历史存档目录。"""
        return self.save_root / "Old Saves"

    # ---- 游戏包 ----

    @property
    def user_packages_dir(self) -> Path:
        """用户包目录（mod 放这里），**优先级高于游戏包**。"""
        return self.uoc2_appdata / "_packages"

    @property
    def game_packages_dir(self) -> Path | None:
        if self.game_dir is None:
            return None
        return self.game_dir / "_packages"

    def package_roots(self) -> list[Path]:
        """包**容器**目录（**用户包在前**）。

        与游戏自己的 `uoc2.paths.all_package_dirs()` 实测顺序一致：
        `['%LOCALAPPDATA%\\.uoc2\\_packages', '<game>\\_packages']`。
        """
        out: list[Path] = []
        up = self.user_packages_dir
        if up.is_dir():
            out.append(up)
        gp = self.game_packages_dir
        if gp is not None and gp.is_dir():
            out.append(gp)
        return out

    def packages(self) -> list[Path]:
        """全部**包**目录（用户包在前）。

        ⚠️ `_packages/` 是**容器**，真正的包是它下面的子目录：
        游戏侧是 `base` / `dlc1` … `dlc10`，用户侧是 mod 目录（如 `fall_blau_2`）。
        每个包自己的数据在 `<包>/data/…`。
        """
        out: list[Path] = []
        for root in self.package_roots():
            try:
                subs = sorted(p for p in root.iterdir() if p.is_dir())
            except OSError:
                continue
            out.extend(subs)
        return out

    # 兼容旧名
    package_dirs = package_roots

    # ---- 构造 ----

    @classmethod
    def discover(cls, appdata: Path | None = None,
                 game_dir: Path | None = None) -> "CorePaths":
        """定位路径。`game_dir=None` 时自动探测；探测失败也不报错。"""
        return cls(
            uoc2_appdata=Path(appdata).expanduser() if appdata else _default_appdata(),
            game_dir=Path(game_dir).expanduser() if game_dir else detect_game_dir(),
        )

    def with_game_dir(self, game_dir: Path | None) -> "CorePaths":
        return CorePaths(uoc2_appdata=self.uoc2_appdata, game_dir=game_dir)
