"""页面基类与共用小控件。

每个页面是一个 `tk.Frame`，由 `AppShell` 预先建好、按需 `raise()` 切换
（**不重建** —— 重建会把滚动位置、选中项全丢掉）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..theme import C, FS_BODY, FS_MID, FS_SMALL, UI_FONT, MONO_FONT

__all__ = ["Page", "SimplePage", "FlatButton", "Badge", "Panel"]


class Page(tk.Frame):
    """一个功能页的基类。

    子类要填的元信息：`key` / `icon` / `title` / `caption`。
    `refresh(view)` 在换存档或重新读盘后被调用。
    """

    key: str = ""
    icon: str = ""
    title: str = ""
    caption: str = ""
    #: 决定这一页在 Rail 上能不能点（见 `AppShell.capability_of`）
    capability: str = ""
    #: 默认占位文案；子类自己写了文案就把它置空（否则会出现两个框）
    default_placeholder = ("这一页将在后续阶段实现。\n\n"
                           "当前阶段（G1）只做应用骨架：能打开存档、"
                           "看到能力位体检、在左边切换页面。")

    def __init__(self, master, app):
        super().__init__(master, bg=C.WINDOW)
        self.app = app
        self.view = None
        #: 占位框（`None` = 这一页没有占位框，是有真内容的页）
        #: —— 留给 `tests/test_gui_smoke.py` 做回归断言
        self._placeholder_box = None
        self.build()

    # ---- 子类实现 ----

    def build(self) -> None:
        """建界面（只跑一次）。"""
        head = tk.Frame(self, bg=C.WINDOW)
        head.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(head, text=self.title, bg=C.WINDOW, fg=C.ACCENT_DARK,
                 font=(UI_FONT, FS_MID + 2, "bold")).pack(side="left")
        if self.caption:
            tk.Label(head, text=self.caption, bg=C.WINDOW, fg=C.MUTED,
                     font=(UI_FONT, FS_SMALL)).pack(side="left", padx=(10, 0))
        self.body = tk.Frame(self, bg=C.WINDOW)
        self.body.pack(fill="both", expand=True, padx=16, pady=(10, 14))
        if self.default_placeholder:
            self.placeholder(self.default_placeholder)

    def refresh(self, view) -> None:
        """换存档 / 重新读盘后刷新内容。"""
        self.view = view

    # ---- 常用小工具 ----

    def placeholder(self, text: str) -> None:
        """占位说明（还没做的部分）。"""
        box = tk.Frame(self.body, bg=C.SURFACE, highlightbackground=C.BORDER,
                       highlightthickness=1, bd=0)
        box.pack(fill="both", expand=True)
        tk.Label(box, text=text, bg=C.SURFACE, fg=C.MUTED,
                 font=(UI_FONT, FS_BODY), wraplength=560,
                 justify="left").pack(padx=22, pady=26, anchor="nw")
        self._placeholder_box = box


class SimplePage(Page):
    """G1 的空页占位（G2–G5 逐页填实）。

    子类自己写占位文案，所以**不要**再叠一个通用的框。
    """

    default_placeholder = ""


class FlatButton(tk.Label):
    """设计稿里的 `.btn` —— 用 `Label` 手搓，才能有圆角感与 hover。

    `ttk.Button` 在 clam 主题下边框太"系统"，跟设计稿差得远。
    """

    def __init__(self, master, text: str, command=None, *, kind: str = "",
                 font=None, **kw):
        bg = {"": C.SURFACE, "pri": C.ACCENT, "danger": C.DANGER,
              "ghost": C.WINDOW}.get(kind, C.SURFACE)
        fg = "#ffffff" if kind in ("pri", "danger") else C.TEXT
        super().__init__(master, text=text, bg=bg, fg=fg,
                         font=font or (UI_FONT, FS_BODY, "bold" if kind == "pri" else "normal"),
                         padx=12, pady=6, cursor="hand2", **kw)
        self.kind = kind
        self.command = command
        self._bg = bg
        self._fg = fg
        self._enabled = True
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def set_enabled(self, on: bool) -> None:
        self._enabled = on
        self.configure(
            bg=self._bg if on else C.SURFACE_ALT,
            fg=self._fg if on else C.MUTED,
            cursor="hand2" if on else "arrow")

    def _click(self, _evt=None):
        if self._enabled and self.command:
            self.command()

    def _enter(self, _evt=None):
        if self._enabled:
            self.configure(bg=C.ACCENT_DARK if self.kind == "pri"
                           else (C.DANGER if self.kind == "danger"
                                 else C.SURFACE_ALT))

    def _leave(self, _evt=None):
        self.configure(bg=self._bg if self._enabled else C.SURFACE_ALT)


class Badge(tk.Label):
    """小徽标（阶段 / 计数）。

    ⚠️ `kind` **不是** Tk 的选项 —— 换配色要走 `set_kind()`。
    """

    KINDS = {
        "": (C.ACCENT_LIGHT, C.ACCENT_DARK),
        "battle": (C.DANGER_LIGHT, C.DANGER),
        "ok": (C.OK_LIGHT, C.OK),
        "warn": (C.WARN_LIGHT, C.WARN),
    }

    def __init__(self, master, text: str = "", *, kind: str = "", **kw):
        bg, fg = self.KINDS.get(kind, self.KINDS[""])
        super().__init__(master, text=text, bg=bg, fg=fg,
                         font=(UI_FONT, FS_SMALL, "bold"), padx=8, pady=2, **kw)
        self.kind = kind

    def set_kind(self, kind: str) -> None:
        """换配色（`""` / `battle` / `ok` / `warn`）。"""
        self.kind = kind
        bg, fg = self.KINDS.get(kind, self.KINDS[""])
        self.configure(bg=bg, fg=fg)


class Panel(tk.Frame):
    """设计稿里的 `.panel` —— 白底 + 边框 + 标题条。"""

    def __init__(self, master, title: str = "", **kw):
        super().__init__(master, bg=C.SURFACE, highlightbackground=C.BORDER,
                         highlightthickness=1, bd=0, **kw)
        if title:
            tk.Label(self, text=title, bg=C.SURFACE_ALT, fg=C.ACCENT_DARK,
                     font=(UI_FONT, FS_MID, "bold"), anchor="w",
                     padx=12, pady=7).pack(fill="x")
            tk.Frame(self, bg=C.BORDER, height=1).pack(fill="x")
        self.content = tk.Frame(self, bg=C.SURFACE)
        self.content.pack(fill="both", expand=True)


class PlaceholderEntry(tk.Entry):
    """带占位提示的输入框（Tk 的 `Entry` 没有 placeholder）。

    做法：把提示文字当普通内容放进去（灰的），聚焦时清空、离焦且为空时放回去。
    """

    def __init__(self, master, placeholder: str = "", **kw):
        kw.setdefault("bg", C.SURFACE)
        kw.setdefault("fg", C.TEXT)
        kw.setdefault("insertbackground", C.TEXT)
        kw.setdefault("relief", "flat")
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", C.BORDER)
        kw.setdefault("highlightcolor", C.ACCENT)
        kw.setdefault("font", (UI_FONT, FS_BODY))
        super().__init__(master, **kw)
        self.placeholder = placeholder
        self._showing = False
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)
        self._show_placeholder()

    def get_text(self) -> str:
        """用户真正输入的内容（占位提示不算）。"""
        return "" if self._showing else self.get()

    def _show_placeholder(self) -> None:
        self.delete(0, "end")
        self.insert(0, self.placeholder)
        self.configure(fg=C.MUTED)
        self._showing = True

    def _focus_in(self, _evt=None):
        if self._showing:
            self.delete(0, "end")
            self.configure(fg=C.TEXT)
            self._showing = False

    def _focus_out(self, _evt=None):
        if not self.get().strip():
            self._show_placeholder()
