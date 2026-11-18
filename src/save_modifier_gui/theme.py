"""GUI 主题 —— 设计令牌 + ttk 样式。

**设计稿的 CSS 变量在这里一一对应**（`docs/GUI视觉稿.html` 的 `:root`）。
Tk 没有 CSS，但配色、字号、间距要**一模一样** —— 否则视觉稿与真程序对不上。

⚠️ **Tk 的限制**（踩过的坑）：
* 没有 CSS 变量 ⇒ 颜色集中在这里，改一处就够；
* 没有 `box-shadow` / `border-radius` ⇒ 用 `relief` + `highlightthickness` 近似；
* 没有 `:hover` ⇒ 用 `<Enter>` / `<Leave>` 事件自己改背景色；
* `ttk` 的部分控件（`Treeview` / `Button`）不好完全自定义 ⇒ 复杂控件用
  `tk.Frame` + `tk.Label` 手搓。

字体：正文 `Microsoft YaHei UI`（Windows 自带，简体中文好看），
等宽 `Consolas`（数字/ID 对齐用）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

__all__ = ["C", "UI_FONT", "MONO_FONT", "ICON_FONT", "apply_theme",
           "configure_tree"]


class C:
    """设计令牌（= 视觉稿的 CSS 变量）。"""

    WINDOW = "#f4f6f8"
    SURFACE = "#ffffff"
    SURFACE_ALT = "#eef2f6"
    BORDER = "#d4dbe3"
    TEXT = "#1f2933"
    MUTED = "#5c6b78"
    ACCENT = "#245b8f"
    ACCENT_DARK = "#17456f"
    ACCENT_LIGHT = "#dceaf7"
    SELECTION = "#cfe3f5"
    OK = "#1e6b3a"
    OK_LIGHT = "#e4f2ea"
    WARN = "#8a5a00"
    WARN_LIGHT = "#fdf3e0"
    DANGER = "#a4262c"
    DANGER_LIGHT = "#fbe9ea"
    STAGE = "#e4eaf1"
    STAGE_SUP = "#b9c6d6"
    STAGE_EDGE = "#ccd6e2"
    DARK = "#1b2430"


UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"
#: 图标字体 —— ▤ ▥ ▦ ▧ ▨ ▩ ▪ 这些"几何图形"字形**微软雅黑里没有**
#: （会显示成空心方块），得用 Segoe UI Symbol（Win10/11 自带）。
ICON_FONT = "Segoe UI Symbol"

#: 字号（视觉稿的 px → Tk 的 pt，1.333 倍）
FS_TINY = 8
FS_SMALL = 9
FS_BODY = 10
FS_MID = 11
FS_TITLE = 13
FS_H1 = 18


def _font(size: int = FS_BODY, bold: bool = False, mono: bool = False):
    return (MONO_FONT if mono else UI_FONT, size, "bold" if bold else "normal")


def apply_theme(root: tk.Misc) -> ttk.Style:
    """给整个应用套上主题。返回 `ttk.Style`（后面还要继续调）。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")          # clam 最好改
    except tk.TclError:                  # pragma: no cover - 极端环境
        pass

    root.option_add("*Font", _font(FS_BODY))
    root.option_add("*TCombobox*Listbox.font", _font(FS_BODY))
    root.option_add("*TCombobox*Listbox.background", C.SURFACE)
    root.option_add("*TCombobox*Listbox.selectBackground", C.SELECTION)
    root.option_add("*TCombobox*Listbox.selectForeground", C.TEXT)

    style.configure(".", background=C.WINDOW, foreground=C.TEXT,
                    font=_font(FS_BODY), borderwidth=0)

    # ---- 面板 / 卡片 ----
    style.configure("Panel.TFrame", background=C.SURFACE)
    style.configure("PanelTitle.TLabel", background=C.SURFACE_ALT,
                    foreground=C.ACCENT_DARK, font=_font(FS_MID, bold=True),
                    padding=(12, 8))
    style.configure("Muted.TLabel", background=C.SURFACE, foreground=C.MUTED,
                    font=_font(FS_SMALL))
    style.configure("MutedOnWindow.TLabel", background=C.WINDOW,
                    foreground=C.MUTED, font=_font(FS_SMALL))
    style.configure("Title.TLabel", background=C.WINDOW,
                    foreground=C.ACCENT_DARK, font=_font(FS_TITLE, bold=True))
    style.configure("BigTitle.TLabel", background=C.WINDOW,
                    foreground=C.ACCENT_DARK, font=_font(FS_H1, bold=True))
    style.configure("Mono.TLabel", background=C.SURFACE,
                    foreground=C.TEXT, font=_font(FS_BODY, mono=True))
    style.configure("MonoMuted.TLabel", background=C.SURFACE,
                    foreground=C.MUTED, font=_font(FS_SMALL, mono=True))

    # ---- 按钮 ----
    style.configure("TButton", background=C.SURFACE, foreground=C.TEXT,
                    font=_font(FS_BODY), padding=(12, 6), relief="flat",
                    borderwidth=1, focuscolor=C.ACCENT_LIGHT)
    style.map("TButton",
              background=[("active", C.SURFACE_ALT),
                          ("disabled", C.SURFACE_ALT)],
              foreground=[("disabled", C.MUTED)])
    style.configure("Primary.TButton", background=C.ACCENT,
                    foreground="#ffffff", font=_font(FS_BODY, bold=True))
    style.map("Primary.TButton",
              background=[("active", C.ACCENT_DARK),
                          ("disabled", C.SURFACE_ALT)],
              foreground=[("disabled", C.MUTED)])
    style.configure("Danger.TButton", background=C.DANGER, foreground="#ffffff")
    style.map("Danger.TButton",
              background=[("active", "#8a1f24"), ("disabled", C.SURFACE_ALT)],
              foreground=[("disabled", C.MUTED)])
    style.configure("Ghost.TButton", background=C.WINDOW, foreground=C.MUTED,
                    borderwidth=0, padding=(10, 6))
    style.map("Ghost.TButton", background=[("active", C.SURFACE_ALT)])

    # ---- 输入 ----
    style.configure("TEntry", fieldbackground=C.SURFACE, foreground=C.TEXT,
                    bordercolor=C.BORDER, insertcolor=C.TEXT,
                    lightcolor=C.BORDER, darkcolor=C.BORDER,
                    padding=(7, 5), borderwidth=1)
    style.map("TEntry",
              bordercolor=[("focus", C.ACCENT)],
              lightcolor=[("focus", C.ACCENT)],
              darkcolor=[("focus", C.ACCENT)])
    style.configure("TCombobox", fieldbackground=C.SURFACE,
                    foreground=C.TEXT, bordercolor=C.BORDER,
                    arrowcolor=C.MUTED, padding=(7, 5))
    style.map("TCombobox",
              fieldbackground=[("readonly", C.SURFACE)],
              bordercolor=[("focus", C.ACCENT)])
    style.configure("TCheckbutton", background=C.WINDOW, foreground=C.TEXT)
    style.map("TCheckbutton", background=[("active", C.WINDOW)])

    # ---- 进度条 ----
    style.configure("TProgressbar", background=C.ACCENT,
                    troughcolor=C.SURFACE_ALT, bordercolor=C.SURFACE_ALT,
                    lightcolor=C.ACCENT, darkcolor=C.ACCENT)

    # ---- 滚动条 ----
    style.configure("Vertical.TScrollbar", background=C.SURFACE_ALT,
                    troughcolor=C.WINDOW, bordercolor=C.WINDOW,
                    arrowcolor=C.MUTED, width=12)
    style.map("Vertical.TScrollbar", background=[("active", C.BORDER)])

    return style


def configure_tree(tree: ttk.Treeview, *, height: int = 12,
                   columns=(), widths=(), headings=None,
                   stretch: int | None = None) -> None:
    """把 `Treeview` 调成设计稿里的表格样式。

    Tk 的 `Treeview` 天生比 HTML 表格"硬"：没有圆角、没有单元格 padding，
    但**它就是虚拟的** —— 几千行也不卡，所以列表一律用它。

    ⚠️ `ttk.Treeview` **不认** `-background` / `-foreground` / `-font`
    也不认 `-borderwidth`（只认 style + `height` / `columns` / `show` …）——
    传了会报 `unknown option "-background"`。
    """
    tree.configure(height=height)
    style = ttk.Style(tree)
    style.configure("Treeview", background=C.SURFACE, fieldbackground=C.SURFACE,
                    foreground=C.TEXT, borderwidth=0, rowheight=26,
                    font=_font(FS_BODY))
    style.configure("Treeview.Heading", background=C.ACCENT_DARK,
                    foreground="#ffffff", font=_font(FS_SMALL, bold=True),
                    relief="flat", padding=(8, 6))
    style.map("Treeview.Heading", background=[("active", C.ACCENT)])
    style.map("Treeview",
              background=[("selected", C.SELECTION)],
              foreground=[("selected", C.TEXT)])
    if columns:
        tree.configure(columns=list(columns))
    if widths:
        tree.column("#0", width=0, stretch=False)
        # 拉伸列由 `stretch` 指定（默认最后一列）—— 表格通常要拉伸**名字**那一列
        idx = len(widths) - 1 if stretch is None else stretch
        for i, w in enumerate(widths):
            tree.column(columns[i] if i < len(columns) else i,
                        width=w, anchor="w", stretch=(i == idx))
    if headings:
        for key, text in headings.items():
            tree.heading(key, text=text)
