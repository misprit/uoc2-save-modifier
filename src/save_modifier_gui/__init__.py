"""UOC2 存档修改器 —— GUI 层。

面向《Unity of Command II》(统一指挥 2) 的存档修改器**界面**，
核心能力全在 `save_modifier_core` 里，这里只管"好看、傻瓜式、丝滑"。

分层（开发规范 §11）
--------------------
```
save_modifier_core   解析、校验、计划、写盘、备份、撤销   ← 无界面
save_modifier_gui    表格、下拉框、diff、能力位驱动的启用/禁用 ← 有界面
```

GUI **不直接碰存档文件**：不自己解析 YAML，不自己打包，
只通过核心库的 8 个函数交互（规范 §0.2）。

跑起来：

```powershell
run_gui.bat
```
或
```python
from save_modifier_gui.app import run
run()
```
"""

from __future__ import annotations

__all__ = ["run"]


def run() -> int:
    """启动 GUI（阻塞直到关窗）。"""
    from .app import run as _run
    return _run()
