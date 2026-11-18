"""概览页 —— **存档体检**。

G1 的验收口径就是这一页：「能打开存档并看到能力位体检」。

体检内容：
* 战役进度（声望 / 分数 / 阶段）；
* **能力位矩阵** —— 7 个功能分别能不能用，不能用的**给原因**（直接显示给玩家）；
* 该存档的注意事项（`view.warnings`）。
"""

from __future__ import annotations

import tkinter as tk

from ..theme import C, FS_BODY, FS_MID, FS_SMALL, UI_FONT, MONO_FONT
from .base import Page, Panel

__all__ = ["OverviewPage"]


class OverviewPage(Page):
    key = "overview"
    icon = "▤"
    title = "概览"
    caption = "存档体检"
    #: 这一页是**真内容**（下面自己建面板）⇒ 不叠 `Page` 的通用占位框。
    #: ⚠️ 忘了置空的话，页首会出现"这一页将在后续阶段实现"，
    #: 与下方的真实体检结果自相矛盾（2026-11-18 实测踩到）。
    default_placeholder = ""

    def build(self) -> None:
        super().build()
        cols = tk.Frame(self.body, bg=C.WINDOW)
        cols.pack(fill="both", expand=True)

        # ---- 左：能力位体检 ----
        left = Panel(cols, "能力位体检")
        left.pack(side="left", fill="both", expand=True)
        self._check_rows: list[tuple[str, tk.Label, tk.Label]] = []
        self._check_body = left.content

        # ---- 右：战役进度 + 注意事项 ----
        right = tk.Frame(cols, bg=C.WINDOW)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))

        prog = Panel(right, "战役进度")
        prog.pack(fill="x")
        self._progress_body = prog.content

        warn = Panel(right, "注意事项")
        warn.pack(fill="both", expand=True, pady=(14, 0))
        self._warn_body = warn.content

    # ---- 刷新 ----

    def refresh(self, view) -> None:
        super().refresh(view)
        self._fill_checks(view)
        self._fill_progress(view)
        self._fill_warnings(view)

    def _fill_checks(self, view) -> None:
        for w in self._check_body.winfo_children():
            w.destroy()
        self._check_rows = []
        caps = view.capabilities
        items = self.app.capability_items(view)
        for name, ok, why in items:
            row = tk.Frame(self._check_body, bg=C.SURFACE)
            row.pack(fill="x", padx=12, pady=3)
            mark = tk.Label(row, text="✓" if ok else "✗", bg=C.SURFACE,
                            fg=C.OK if ok else C.DANGER,
                            font=(UI_FONT, FS_BODY, "bold"), width=2)
            mark.pack(side="left")
            tk.Label(row, text=name, bg=C.SURFACE, fg=C.TEXT,
                     font=(UI_FONT, FS_BODY)).pack(side="left")
            tk.Label(row, text="" if ok else (why or ""), bg=C.SURFACE,
                     fg=C.MUTED, font=(UI_FONT, FS_SMALL)).pack(side="left",
                                                                padx=(8, 0))
            self._check_rows.append((name, mark, row))

    def _fill_progress(self, view) -> None:
        for w in self._progress_body.winfo_children():
            w.destroy()
        rows = [
            ("阶段", view.stage or "—"),
            ("声望", "—" if view.prestige is None else str(view.prestige)),
            ("分数", "—" if view.score is None else str(view.score)),
            ("单位", str(len(view.units))),
            ("总部", str(len(view.hqs))),
            ("手牌", str(len(view.hand))),
            ("货架", str(len(view.shelf))),
            ("商店条目", str(len(view.store))),
        ]
        for i, (k, v) in enumerate(rows):
            line = tk.Frame(self._progress_body, bg=C.SURFACE)
            line.pack(fill="x", padx=12, pady=2)
            tk.Label(line, text=k, bg=C.SURFACE, fg=C.MUTED,
                     font=(UI_FONT, FS_SMALL), width=9, anchor="w").pack(side="left")
            tk.Label(line, text=v, bg=C.SURFACE, fg=C.TEXT,
                     font=(MONO_FONT, FS_MID, "bold")).pack(side="left")

    def _fill_warnings(self, view) -> None:
        for w in self._warn_body.winfo_children():
            w.destroy()
        items = list(view.warnings)
        if not items:
            tk.Label(self._warn_body, text="没有需要注意的地方。",
                     bg=C.SURFACE, fg=C.OK,
                     font=(UI_FONT, FS_BODY)).pack(anchor="w", padx=12, pady=10)
            return
        for text in items:
            line = tk.Frame(self._warn_body, bg=C.SURFACE)
            line.pack(fill="x", padx=12, pady=2)
            tk.Label(line, text="·", bg=C.SURFACE, fg=C.WARN,
                     font=(UI_FONT, FS_BODY)).pack(side="left")
            tk.Label(line, text=text, bg=C.SURFACE, fg=C.TEXT,
                     font=(UI_FONT, FS_SMALL), wraplength=380,
                     justify="left").pack(side="left", fill="x", expand=True)
