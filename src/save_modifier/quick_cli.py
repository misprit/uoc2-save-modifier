"""供外部程序调用的快速存读档接口。

面向 AHK 之类的热键工具：一条命令完成一次备份或恢复，不进入 REPL，也不
接受存档名或后缀参数。目标固定为 last_save.txt 记录的默认存档与 _quick
后缀，与 REPL 的 qs / ql 语义一致（qs 备份磁盘上的 .usg，ql 用备份覆盖它）。

约定：成功时向 stdout 输出一行结果并以 0 退出；失败时向 stderr 输出中文
错误并以非零退出，退出码区分类别，调用方可据此判断“没有可恢复的备份”等情况。
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

from . import config as config_mod
from .config import Config, ConfigError
from .savefile import SaveFile, detect_save_kind, quick_load_file, quick_save_file

QUICK_SUFFIX = "_quick"
LAST_SAVE_FILENAME = "last_save.txt"

EXIT_OK = 0
EXIT_BAD_CONFIG = 1
EXIT_NO_LAST_SAVE = 2
EXIT_NO_SAVE_FILE = 3
EXIT_NO_BACKUP = 4
EXIT_IO_ERROR = 5


class QuickError(Exception):
    """可预期的失败：携带退出码，由 run_quick 统一打印。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_default_save(config: Config) -> SaveFile:
    """按 last_save.txt 定位默认存档，失败时抛 QuickError。

    last_save.txt 只应保存存档名本身。含路径分隔符或为 . / .. 时视为记录
    异常：若照常拼接，存档名会被解释成本目录之外的路径。
    """
    marker = config.modifier_root / LAST_SAVE_FILENAME
    try:
        name = marker.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise QuickError(
            EXIT_NO_LAST_SAVE,
            f"没有默认存档记录（{marker} 不存在），请先在 REPL 中打开一次存档",
        ) from None
    except OSError as e:
        raise QuickError(EXIT_NO_LAST_SAVE,
                         f"无法读取默认存档记录 {marker}: {e}") from e
    if not name:
        raise QuickError(EXIT_NO_LAST_SAVE, f"默认存档记录 {marker} 为空")
    if name != Path(name).name or name in (".", ".."):
        raise QuickError(EXIT_NO_LAST_SAVE,
                         f"默认存档记录内容不是合法存档名: {name!r}")

    for save_dir in (config.campaigns_dir, config.games_dir):
        path = save_dir / f"{name}.usg"
        if path.is_file():
            return SaveFile(path, kind=detect_save_kind(path))
    raise QuickError(
        EXIT_NO_SAVE_FILE,
        f"默认存档 {name} 在 {config.campaigns_dir} 与 "
        f"{config.games_dir} 中均不存在",
    )


def _load_strict_config(config_path: Path) -> Config:
    # Config 构造时可能打印“自动探测原版包目录”，快速接口要求输出干净
    with contextlib.redirect_stdout(io.StringIO()):
        return config_mod.load_config_strict(config_path)


def run_quick(action: str, config_path: Path | None = None) -> int:
    """执行一次快速操作，返回进程退出码。

    action: "qs"（备份）或 "ql"（恢复）。
    config_path: 配置文件路径；None 时按默认规则查找。
    """
    if action not in ("qs", "ql"):
        print(f"错误: 未知操作 {action!r}（仅支持 qs / ql）", file=sys.stderr)
        return EXIT_BAD_CONFIG

    path = Path(config_path) if config_path else config_mod.find_config_file()
    try:
        config = _load_strict_config(path)
        if not config.uoc2_appdata.is_dir():
            raise QuickError(
                EXIT_BAD_CONFIG,
                f"配置的 uoc2_appdata 目录不存在: {config.uoc2_appdata}",
            )
        save = resolve_default_save(config)

        if action == "qs":
            target = quick_save_file(save, QUICK_SUFFIX)
            print(f"已快速保存: {target.name}")
            return EXIT_OK

        source = quick_load_file(save, QUICK_SUFFIX)
        if source is None:
            raise QuickError(
                EXIT_NO_BACKUP,
                f"未找到备份存档 {save.name}{QUICK_SUFFIX}.usg"
                f"（先用 qs 备份一次）",
            )
        print(f"已快速恢复: {source.name} -> {save.path.name}")
        return EXIT_OK
    except ConfigError as e:
        print(f"错误: {e}", file=sys.stderr)
        return EXIT_BAD_CONFIG
    except QuickError as e:
        print(f"错误: {e.message}", file=sys.stderr)
        return e.code
    except OSError as e:
        print(f"错误: 文件操作失败: {e}", file=sys.stderr)
        return EXIT_IO_ERROR
