"""路径定位：游戏数据目录、存档目录、游戏包目录。

核心库**不读配置文件**也能工作 —— 全部路径靠探测 + 环境变量覆盖。
这样 GUI 那边不用先跑一遍配置向导。

环境变量
--------
* `UOC2_APPDATA` —— 游戏数据目录（默认 `%LOCALAPPDATA%\\.uoc2`）
* `UOC2_GAME_DIR` —— 游戏安装目录（默认自动探测）
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CorePaths", "APP_DIR_NAME", "config_path", "read_config",
           "write_config", "detect_game_dir", "game_dir_candidates",
           "looks_like_game_dir", "set_game_dir", "steam_libraries"]

APP_DIR_NAME = ".uoc2"

#: 修改器自己的设置文件（放在**游戏数据目录**下，不进存档目录）
#:
#: ⚠️ **只存设置**，绝不写存档内容 —— 存档层（L1–L5）一个字都不动。
CONFIG_FILENAME = "modifier_config.json"

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


def steam_libraries() -> list[Path]:
    """Steam 的**所有**库目录（含自定义库）。

    ⚠️ 只查默认库会漏掉装在别的盘的 Steam —— 注册表里只有一个 `SteamPath`，
    而库是另一回事（`steamapps/libraryfolders.vcf` 里列着全部库，
    但**这个文件不一定存在**，非标准安装下常常没有 ⇒ 还要兜底扫常见库位置）。

    字节码依据：`paths.pyc::all_package_dirs` ⇒ 游戏自己的包目录是
    `_mod_packages_dirs + [_user_packages_dir] + [_game_package_dir]`；
    游戏本体目录由**安装位置**决定（`_Paths.__init__`）。
    """
    libs: list[Path] = []
    root = _steam_root()
    if root is not None:
        libs.append(root)
        for vcf in (root / "steamapps" / "libraryfolders.vcf",
                    root / "config" / "libraryfolders.vcf"):
            try:
                text = vcf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in re.finditer(r'"path"\s*"([^"]+)"', text):
                try:
                    p = Path(m.group(1).replace("\\", "\\"))
                except Exception:
                    continue
                if p.is_dir() and p not in libs:
                    libs.append(p)
    # 兜底：常见库位置（libraryfolders.vcf 缺失时）
    for extra in (Path("D:/SteamLibrary"), Path("D:/Steam"),
                  Path("E:/SteamLibrary"), Path("C:/SteamLibrary")):
        if extra.is_dir() and extra not in libs:
            libs.append(extra)
    return libs


def library_game_dirs() -> list[tuple]:
    """在各个 Steam 库里找「像游戏本体」的目录。

    ⚠️ **不靠 appmanifest 的 `installdir`** —— 实测那个字段和磁盘上的文件夹名
    可能对不上（本机 manifest 写的是 `Unity of Command II`，
    磁盘上却是 `Unity of Command 2`）⇒ 直接扫 `steamapps/common/*`，
    用「里面有 `_packages` 或 `lib/uoc2`」判定。
    """
    out: list[tuple] = []
    for lib in steam_libraries():
        common = lib / "steamapps" / "common"
        if not common.is_dir():
            continue
        try:
            for d in sorted(common.iterdir()):
                if d.is_dir() and looks_like_game_dir(d):
                    out.append(("Steam 库", d))
        except OSError:
            continue
    return out



def _candidate_game_dirs() -> list[Path]:
    out: list[Path] = []
    cfg = read_config().get("game_dir")
    if cfg:
        out.append(Path(str(cfg)).expanduser())
    env = os.environ.get("UOC2_GAME_DIR")
    if env:
        out.append(Path(env).expanduser())
    for lib in steam_libraries():
        out.append(lib / "steamapps" / "common" / "Unity of Command 2")
    for _label, p in library_game_dirs():
        out.append(p)
    out.extend(Path(p) for p in _GAME_DIR_CANDIDATES)
    return out
    out.extend(Path(p) for p in _GAME_DIR_CANDIDATES)
    return out


def looks_like_game_dir(p: Path) -> bool:
    """判断一个目录是不是游戏安装目录。

    判定依据（与游戏自己的目录结构一致）：里面有 `_packages` 或 `lib/uoc2`。
    """
    try:
        return (p / "_packages").is_dir() or (p / "lib" / "uoc2").is_dir()
    except OSError:
        return False


#: 旧名保留（内部用）
_looks_like_game_dir = looks_like_game_dir


def config_path() -> Path:
    """修改器自己的设置文件路径（`<游戏数据目录>/modifier_config.json`）。"""
    return _default_appdata() / CONFIG_FILENAME


def read_config() -> dict:
    """读设置（文件不存在 / 坏了都当空设置）。"""
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_config(data: dict) -> Path:
    """写设置（只写我们自己那几个键；**绝不碰存档**）。"""
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


def set_game_dir(path) -> Path:
    """把游戏本体目录记下来（写设置文件）。

    ⚠️ 只校验「像不像游戏目录」，**不移动任何文件**。
    """
    p = Path(path).expanduser()
    if not p.is_dir():
        raise ValueError("目录不存在：%s" % p)
    if not looks_like_game_dir(p):
        raise ValueError("这个目录不像游戏本体（里面应该有 _packages 或 lib/uoc2）：%s" % p)
    cfg = read_config()
    cfg["game_dir"] = str(p.resolve())
    write_config(cfg)
    return p.resolve()


def game_dir_candidates() -> list[dict]:
    """所有候选游戏目录 + 命中与否 —— 界面用它告诉玩家「都找过哪儿了」。"""
    out = []
    cfg = read_config().get("game_dir")
    if cfg:
        p = Path(str(cfg)).expanduser()
        out.append({"label": "设置文件里指定的", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    env = os.environ.get("UOC2_GAME_DIR")
    if env:
        p = Path(env).expanduser()
        out.append({"label": "环境变量 UOC2_GAME_DIR", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    for lib in steam_libraries():
        p = lib / "steamapps" / "common" / "Unity of Command 2"
        out.append({"label": "Steam 库", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    for _label, p in library_game_dirs():
        out.append({"label": "Steam 库里扫到的", "path": str(p), "ok": True})
    for c in _GAME_DIR_CANDIDATES:
        p = Path(c)
        out.append({"label": "常见安装位置", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    return out


def detect_game_dir() -> Path | None:
    """探测游戏安装目录；找不到返回 None（不报错 —— 存档功能不依赖游戏本体）。

    **优先级（U69）**
    1. 设置文件里用户手动指定的（`<游戏数据目录>/modifier_config.json`）；
    2. 环境变量 `UOC2_GAME_DIR`；
    3. Steam 注册表 → **所有库**（`libraryfolders.vcf`）+ 常见安装位置。

    ⚠️ 设置文件里指的目录要是没了（游戏被移动 / 卸载），**自动忽略它**继续往下找 ——
    否则用户会被一个失效的设置卡住。
    """
    seen: set[Path] = set()
    for cand in _candidate_game_dirs():
        try:
            rp = cand.resolve()
        except OSError:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        if looks_like_game_dir(rp):
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
