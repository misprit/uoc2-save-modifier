"""配置加载与路径解析。

工具采用“每存档隔离”的状态模型：所有属于某个存档的派生状态（解压工作区、
单位类型绑定、生成的参考列表等）都放在 <状态目录>/<存档名>/ 下。

状态目录（state_dir）默认是启动脚本同目录下的 data/（源码运行时即项目根目录），
也可以在 config.yml 中指定：

    state_dir: ""            # 默认：<启动脚本目录>/data
    state_dir: "appdata"     # 游戏数据目录：<uoc2_appdata>/modifier
    state_dir: "D:/其他地方"  # 自定义绝对路径（支持环境变量）

只有临时 mod 目录（游戏要从 _packages 加载）必须留在 <uoc2_appdata>/_packages/。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

APP_NAME = "modifier"
DEFAULT_APP_DATA = "%LOCALAPPDATA%/.uoc2"
CONFIG_FILENAME = "config.yml"
CONFIG_EXAMPLE_FILENAME = "config.example.yml"  # 仅供人工参考，引导不依赖它
CONFIG_DEFAULT_FILENAME = "config.default.yml"  # 随分发提供的初始配置（带注释）

# 状态目录默认名：启动脚本同目录下的 data/
DEFAULT_STATE_DIRNAME = "data"
# state_dir 取这些值（不区分大小写）时表示使用默认的“启动脚本同目录”
_STATE_DEFAULT_ALIASES = {"", "default", "script", "launcher"}
# state_dir 取这些值时表示放回游戏数据目录（旧行为）
_STATE_APPDATA_ALIASES = {"appdata", "uoc2", "game", "game_data"}

# 存档目录相对 uoc2_appdata 的路径
SAVE_CAMPAIGNS_REL = Path("save/campaigns")  # 战役存档
SAVE_GAMES_REL = Path("save/games")  # 独立场景存档（standalone scenario）

# 游戏原版 _packages 的默认位置（Steam 默认库）。配置留空时按此探测。
DEFAULT_ORIG_PACKAGES = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages"

# 自动探测的候选位置（仅默认位置）。
_ORIG_PACKAGES_CANDIDATES = [DEFAULT_ORIG_PACKAGES]


def _expand_env(path: str) -> str:
    return os.path.expandvars(path)


def _base_dir() -> Path:
    """工具可执行文件/脚本所在目录（兼容 PyInstaller 打包）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def find_config_file(base: Path | None = None) -> Path:
    """定位配置文件：可执行文件目录优先，其次脚本目录。

    配置文件属于工具本体，跟随工具位置，不放在存档目录。缺省时返回
    base/config/config.yml（可能不存在，由调用方决定是否回退到默认值）。
    """
    base = base or _base_dir()
    # 兼容把 config.yml 直接放在工具目录的分发方式
    for cand in (base / "config.yml", base / "config" / CONFIG_FILENAME):
        if cand.exists():
            return cand
    return base / "config" / CONFIG_FILENAME


def default_config_template(base: Path | None = None) -> Path:
    """随分发提供的初始配置文件（带注释，首次运行时复制为 config.yml）。

    与 config.yml 的查找顺序一致：工具目录优先，其次 config/ 子目录。
    """
    base = base or _base_dir()
    for cand in (base / CONFIG_DEFAULT_FILENAME,
                 base / "config" / CONFIG_DEFAULT_FILENAME):
        if cand.is_file():
            return cand
    return base / "config" / CONFIG_DEFAULT_FILENAME


def resolve_state_dir(value: Any, uoc2_appdata: Path,
                      base: Path | None = None) -> Path:
    """把配置中的 state_dir 解析为绝对路径。

    留空或 "default" → <启动脚本目录>/data；"appdata"/"uoc2"/"game" →
    <uoc2_appdata>/modifier（旧行为）；其余按路径处理并展开环境变量。
    """
    text = str(value or "").strip()
    key = text.lower()
    if key in _STATE_DEFAULT_ALIASES:
        return (base or _base_dir()) / DEFAULT_STATE_DIRNAME
    if key in _STATE_APPDATA_ALIASES:
        return uoc2_appdata / APP_NAME
    return Path(_expand_env(text))


def probe_orig_packages() -> Path | None:
    """在常见安装位置探测原版 _packages 目录；未找到返回 None。"""
    for cand in _ORIG_PACKAGES_CANDIDATES:
        p = Path(cand)
        if (p / "base").is_dir():
            return p
    return None


def _load_raw(config_path: Path | None = None) -> dict[str, Any]:
    config_path = config_path or find_config_file()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                return data
        except yaml.YAMLError as e:
            print(f"警告：配置文件 {config_path} 解析失败：{e}，将使用默认配置。")
    return {}


class ConfigError(Exception):
    """配置文件缺失、无法读取或结构不合法。"""


class Config:
    """聚合后的运行配置。所有成员为解析后的绝对 Path 或标量。"""

    def __init__(self, raw: dict[str, Any], config_file: Path):
        self.config_file = config_file

        app_data_raw = raw.get("uoc2_appdata", DEFAULT_APP_DATA)
        self.uoc2_appdata = Path(_expand_env(str(app_data_raw)))

        orig = raw.get("uoc2_orig_packages_path")
        if orig:
            self.orig_packages = Path(_expand_env(str(orig)))
        else:
            probed = probe_orig_packages()
            if probed is not None:
                self.orig_packages = probed
                print(f"已自动探测原版包目录: {probed}")
            else:
                self.orig_packages = None

        self.locale = str(raw.get("locale", "chi"))
        self.mod_search_paths = [
            Path(_expand_env(str(p)))
            for p in (raw.get("mod_search_paths") or [])
            if str(p).strip()
        ]

        # 派生路径
        self.campaigns_dir = self.uoc2_appdata / SAVE_CAMPAIGNS_REL
        self.games_dir = self.uoc2_appdata / SAVE_GAMES_REL
        # 解包工作区 / 参考列表 / 绑定文件 / last_save.txt 的根目录
        self.state_dir = resolve_state_dir(raw.get("state_dir"),
                                           self.uoc2_appdata)
        self.modifier_root = self.state_dir

    def save_dir_for(self, save_name: str) -> Path:
        """每存档隔离目录：<state_dir>/<存档名>/"""
        return self.modifier_root / save_name

    def temp_mod_dir_for(self, save_name: str) -> Path:
        """该存档使用的临时 mod 目录（游戏从 _packages 加载）。"""
        return self.uoc2_appdata / "_packages" / f"{save_name}_temp"

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Config":
        config_path = config_path or find_config_file()
        return cls(_load_raw(config_path), config_path)


def load_config_strict(config_path: Path) -> Config:
    """严格加载配置，不套用默认值：任何缺失或解析失败都抛 ConfigError。

    与 Config.load 的区别在于后者会回退默认配置，适合交互式启动时容错；
    命令行快速接口需要把“配置异常”明确暴露给调用方，不能静默改用默认路径
    操作真实游戏数据。
    """
    if not config_path.is_file():
        raise ConfigError(f"未找到配置文件: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"配置文件读取或解析失败: {config_path}: {e}") from e
    if data is None:
        raise ConfigError(f"配置文件为空: {config_path}")
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是键值映射: {config_path}")
    return Config(data, config_path)


def ensure_config_present(config_path: Path | None = None) -> Path:
    """确保配置文件已完成引导：缺失或未完成时执行配置引导。

    返回配置文件路径；用户在引导中取消时抛 SetupAborted。
    """
    from .setup_guide import run_setup, setup_completed

    cfg = Path(config_path) if config_path else find_config_file()
    if setup_completed(cfg):
        return cfg
    return run_setup(cfg)
