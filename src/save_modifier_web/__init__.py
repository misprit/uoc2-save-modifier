"""GUI 界面层 —— **本地 HTTP 桥 + Edge `--app` 独立窗口**（U26 技术路线）。

界面就是 `docs/GUI视觉稿.html` 那份 HTML/CSS；Python 这边只提供一个
**只读**的本地服务（见 `server.py`），核心库 `save_modifier_core` 不受影响。
"""

from __future__ import annotations

__all__ = ["server"]
