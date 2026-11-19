"""GUI 界面层 —— **本地 HTTP 桥 + Edge `--app` 独立窗口**（U26 技术路线）。

界面是 `web/index.html`（单文件前端）；Python 这边只提供一个
**只读**的本地服务（见 `server.py`），核心库 `save_modifier_core` 不受影响。

⚠️ `docs/GUI视觉稿.html` 已于 2026-11-19 **冻结**：界面改动直接改 `web/index.html`，
不再与视觉稿比对，也不再更新视觉稿（见 `docs/开发上下文.md` §5.1kk）。
"""

from __future__ import annotations

__all__ = ["server"]
