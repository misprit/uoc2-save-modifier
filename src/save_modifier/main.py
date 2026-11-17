#!../../.venv/Scripts/python.exe
"""UOC2 存档修改器 —— 启动器。

**这个入口只是自测外壳。** 真正的产品界面是 GUI（另一个项目里的静态查看器），
它直接 `import save_modifier_core` 调用核心库的 8 个函数（规范 §0.1、§0.2）。

旧版启动器里的"配置向导"与"快速存读档（AHK）"已经砍掉：

* **配置向导没了** —— 核心库自己会探测游戏目录与存档目录
  （`CorePaths.discover()`：读注册表找 Steam、扫常见安装位置），
  不需要用户先填一遍配置（规范 §0.1、§7.5）。
* **快速存读档没了** —— 产品决策：不做频繁存读档（§0.3、§7.5）。
  每一次写回仍然自动生成 `<存档名>_BACKUP.usg`，并有撤销栈（§6.4）。

用法::

    python -m save_modifier.main          # 进自测入口
    python -m save_modifier.main --help   # 看帮助
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_imports() -> None:
    """确保以源码方式运行时能导入包（兼容未安装的临时运行）。"""
    import os
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)


def main(argv: list[str] | None = None) -> int:
    _bootstrap_imports()
    parser = argparse.ArgumentParser(
        prog="uoc2mod",
        description="Unity of Command II 存档修改器 —— 核心库自测入口")
    parser.add_argument("--check", action="store_true",
                        help="只跑一遍自检（不开交互）")
    args = parser.parse_args(argv)

    from .repl import Repl, run_repl

    if args.check:
        repl = Repl()
        try:
            repl.cmd_selftest([])
        finally:
            repl.close()
        return 0

    return run_repl()


if __name__ == "__main__":
    if not __package__:
        # 以脚本方式直接运行时本模块不属于任何包，包内的相对导入会失败；
        # 补上包名即可，sys.path 由 main() 里的引导函数负责。
        __package__ = "save_modifier"
    raise SystemExit(main())
