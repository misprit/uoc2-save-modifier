#!../../.venv/Scripts/python.exe
"""UOC2 存档修改器入口。

首行的 shebang 指向本项目虚拟环境中的解释器（路径相对本文件所在目录）。
Windows 的 py 启动器（py.exe）会解析这一行，因此本文件可以直接双击运行，
也可以用 `py <路径>` 或 `./main.py` 启动；工具依赖的 PyYAML 装在虚拟环境里，
系统 Python 里没有，所以这里不能写 `python3` 之类的通用命令。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_imports():
    """确保以源码方式运行时能导入包（兼容未安装的临时运行）。"""
    import os
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)


def main(argv: list[str] | None = None) -> int:
    _bootstrap_imports()
    from . import config as config_mod

    parser = argparse.ArgumentParser(
        prog="uoc2mod",
        description="Unity of Command II 战役存档修改工具（REPL 与命令行快速存读档）")
    parser.add_argument("--config", help="配置文件路径（默认自动查找；不存在时进入配置引导）")
    parser.add_argument("--setup", action="store_true",
                        help="强制重新运行配置引导并覆盖现有配置文件")
    parser.add_argument("--save", help="直接打开指定存档名（跳过选择）")
    parser.add_argument(
        "action", nargs="?", choices=["qs", "ql"], metavar="动作",
        help="快捷操作（不进入 REPL）：qs=把默认存档备份为 <名>_quick.usg；"
             "ql=用该备份恢复默认存档。默认存档由 last_save.txt 决定")
    args = parser.parse_args(argv)

    if args.action:
        from .quick_cli import run_quick
        return run_quick(args.action, args.config)

    from .repl import run_repl

    config_path = (Path(args.config) if args.config
                   else config_mod.find_config_file())
    # 初次使用（配置不存在，或仍是未完成引导的初始模板）：走一遍配置引导
    from . import setup_guide

    if args.setup or not setup_guide.setup_completed(config_path):
        from .setup_guide import SetupAborted, run_setup

        try:
            config_path = run_setup(config_path)
        except SetupAborted:
            print("已取消配置引导，未写入配置文件。")
            return 1
        print()
    config = config_mod.Config.load(config_path)
    if config.orig_packages is None:
        print("警告：未找到原版包路径（uoc2_orig_packages_path）：单位与卡牌只能显示"
              "本地化 id，find 无法按中文名搜索，cardBuy 与创建自定义类型不可用。")

    repl_mod = __import__("save_modifier.repl", fromlist=["Repl"])
    repl = repl_mod.Repl(config)
    if args.save:
        if not repl.open_save(args.save):
            return 1
        run_repl(config, repl=repl, skip_open=True)
    else:
        run_repl(config, repl=repl)
    return 0


if __name__ == "__main__":
    if not __package__:
        # 以脚本方式直接运行时（双击本文件，或 `py main.py`）本模块不属于任何包，
        # 包内的相对导入会失败；补上包名即可，sys.path 由 main() 里的引导函数负责。
        __package__ = "save_modifier"
    raise SystemExit(main())
