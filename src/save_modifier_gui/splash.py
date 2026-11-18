"""启动页 —— 选存档。

《GUI设计规范.md》§3.2 的要求：
* 只列 `is_primary=True` 的存档在主区；备份 / 副本归入「历史存档」分组；
* 双击一行 = 打开；
* 选中后底部按钮才可用；
* 常驻提示「改存档前请先退出游戏」。
"""

from __future__ import annotations

import datetime as _dt
import tkinter as tk
from tkinter import ttk

from save_modifier_core import list_saves

from .theme import (C, FS_BODY, FS_H1, FS_MID, FS_SMALL, MONO_FONT,
                    UI_FONT, apply_theme, configure_tree)
from .names import pretty_name
from .pages.base import FlatButton, PlaceholderEntry

__all__ = ["SavePicker"]

#: 每一组的名字（按存档位置分）
GROUPS = (
    ("campaigns", "战役存档"),
    ("games", "独立场景存档"),
)


def _fmt_size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{n / 1024:.0f} KB"


def _fmt_time(ts: float) -> str:
    try:
        d = _dt.datetime.fromtimestamp(ts)
        return f"{d.month}月{d.day}日 {d:%H:%M}"
    except (OSError, OverflowError, ValueError):
        return ""


class SavePicker(tk.Frame):
    """存档选择页。`on_open(save_id)` 回调即进入主界面。"""

    def __init__(self, master, app):
        super().__init__(master, bg=C.WINDOW)
        self.app = app
        self.on_open = app.open_save
        self.saves = []
        self._build()
        self.refresh()

    # ---- 界面 ----

    def _build(self) -> None:
        wrap = tk.Frame(self, bg=C.WINDOW)
        wrap.pack(fill="both", expand=True)

        tk.Label(wrap, text="统一指挥 2  存档修改器", bg=C.WINDOW,
                 fg=C.ACCENT_DARK, font=(UI_FONT, FS_H1, "bold")).pack(pady=(46, 4))
        tk.Label(wrap, text="选一个存档开始", bg=C.WINDOW, fg=C.MUTED,
                 font=(UI_FONT, FS_BODY)).pack(pady=(0, 20))

        card = tk.Frame(wrap, bg=C.SURFACE, highlightbackground=C.BORDER,
                        highlightthickness=1)
        card.pack(fill="both", expand=True, padx=90, pady=(0, 16))

        # ---- 工具条：搜索 + 刷新 ----
        bar = tk.Frame(card, bg=C.SURFACE_ALT)
        bar.pack(fill="x")
        self.search = PlaceholderEntry(bar, "搜索存档…")
        self.search.pack(side="left", fill="x", expand=True, padx=12, pady=10,
                         ipady=3)
        self.search.bind("<Return>", lambda _e: self.refresh())
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())
        FlatButton(bar, "刷新", self.refresh, kind="ghost").pack(
            side="right", padx=(0, 12), pady=8)

        # ---- 列表 ----
        wrap_tbl = tk.Frame(card, bg=C.SURFACE)
        wrap_tbl.pack(fill="both", expand=True)
        cols = ("group", "name", "stage", "time", "size")
        self.tree = ttk.Treeview(wrap_tbl, columns=cols, show="headings",
                                 selectmode="browse")
        configure_tree(
            self.tree, height=16, columns=cols,
            widths=(0, 320, 110, 120, 90),
            stretch=1,                 # 「存档」那一列拉伸
            headings={"group": "", "name": "存档", "stage": "状态",
                      "time": "最后修改", "size": "大小"})
        self.tree.heading("group", text="")
        self.tree.column("group", width=0, stretch=False)
        sb = ttk.Scrollbar(wrap_tbl, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_button())

        # ---- 底部：打开 + 常驻提示 ----
        bottom = tk.Frame(card, bg=C.SURFACE_ALT)
        bottom.pack(fill="x")
        tk.Label(bottom, text="ⓘ 改存档前请先退出游戏（文件被占用时写回会失败）",
                 bg=C.SURFACE_ALT, fg=C.WARN,
                 font=(UI_FONT, FS_SMALL)).pack(side="left", padx=14, pady=10)
        self.open_btn = FlatButton(bottom, "打开这个存档", self._open_selected,
                                   kind="pri")
        self.open_btn.pack(side="right", padx=14, pady=10)
        self.open_btn.set_enabled(False)

    # ---- 数据 ----

    def refresh(self) -> None:
        """重列存档（按搜索词过滤）。"""
        self.tree.delete(*self.tree.get_children())
        needle = self.search.get_text().strip().lower()
        try:
            saves = list_saves()
        except Exception as exc:                # pragma: no cover
            self.tree.insert("", "end", values=("", f"读取存档目录失败：{exc}",
                                                "", "", ""))
            return
        self.saves = saves

        primaries = [s for s in saves if s.is_primary]
        archived = [s for s in saves if not s.is_primary]

        for s in primaries:
            if needle and needle not in pretty_name(s).lower():
                continue
            self.tree.insert("", "end", iid=s.save_id,
                             values=("", pretty_name(s), self._stage_of(s),
                                     _fmt_time(s.mtime), _fmt_size(s.size)))
        for s in archived:
            if needle and needle not in pretty_name(s).lower():
                continue
            self.tree.insert("", "end", iid=s.save_id,
                             values=("历史存档（游戏自己的「Old Saves」）",
                                     pretty_name(s), self._stage_of(s),
                                     _fmt_time(s.mtime), _fmt_size(s.size)))
        self._sync_button()

    @staticmethod
    def _stage_of(info) -> str:
        if info.standalone_scenario:
            return "独立场景"
        return "战役"

    def _sync_button(self) -> None:
        sel = self.tree.selection()
        self.open_btn.set_enabled(bool(sel))

    def _open_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        self.on_open(sel[0])
