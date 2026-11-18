"""主窗口 —— 应用骨架（Header / Rail / Work / Status）。

《GUI设计规范.md》§3.1：
* 窗口默认 **1440 × 900**，最小 **1180 × 700**；
* Header / Rail / Status **固定**，只有工作区随页切换；
* Rail 上**不能用的页要灰掉并给原因** —— 不是隐藏（玩家要知道有这么个功能）。

⚠️ **按能力位开关，不按状态分支**（规范 §3.4.5）——
页面能不能点，由核心库的 `Capabilities` 决定，**不是**由"当前在什么阶段"决定。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from save_modifier_core import CorePaths, open_save
from save_modifier_core import catalog as catalog_mod

from .theme import (C, FS_BODY, FS_MID, FS_SMALL, ICON_FONT, MONO_FONT,
                    UI_FONT, apply_theme)
from .names import pretty_name
from .pages import PAGES
from .pages.base import Badge, FlatButton
from .splash import SavePicker

__all__ = ["Application", "AppShell"]

#: Rail / 状态栏上显示的能力位（顺序 = 规范 §2 的页面表）
CAPABILITY_ITEMS = (
    ("单位", "units"),
    ("特种兵", "units"),
    ("总部", "hqs"),
    ("卡牌", "cards"),
    ("商店", "store"),
    ("战区资产", "theater_assets"),
)

#: Rail 上灰掉时显示的**短**原因（状态栏用完整原因）
SHORT_REASON = {
    "units": "无可改单位",
    "hqs": "无总部数据",
    "cards": "无卡牌数据",
    "store": "无商店数据",
    "theater_assets": "不在战斗中",
}


def capability_ok(caps, key: str) -> bool:
    """某个能力位对这个存档是否可用。**只认能力位，不认阶段**。"""
    if key == "units":
        return caps.can_edit_units
    if key == "hqs":
        return caps.can_edit_hqs
    if key == "cards":
        # 手牌或货架有一样能改就算这页可用
        return caps.can_edit_hand or caps.can_edit_shelf
    if key == "store":
        return caps.can_edit_store
    if key == "theater_assets":
        return caps.can_edit_theater_assets
    return True


def capability_items(view) -> list[tuple[str, bool, str]]:
    """`[(显示名, 能不能用, 原因)]` —— 状态栏与概览页共用。"""
    caps = view.capabilities
    out: list[tuple[str, bool, str]] = []
    for name, key in CAPABILITY_ITEMS:
        ok = capability_ok(caps, key)
        why = "" if ok else caps.unavailable_reason(key)
        out.append((name, ok, why))
    return out


class AppShell(tk.Frame):
    """打开存档后的主界面。"""

    def __init__(self, master, app, save, catalog):
        super().__init__(master, bg=C.WINDOW)
        self.app = app
        self.save = save
        self.catalog = catalog
        self.view = save.view(catalog)
        self.pages: dict[str, object] = {}
        self.current: str | None = None
        self._build()
        self.refresh()

    # ---- 界面 ----

    def _build(self) -> None:
        self._build_header()
        body = tk.Frame(self, bg=C.WINDOW)
        body.pack(fill="both", expand=True)
        self._build_rail(body)
        self._build_work(body)
        self._build_status()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=C.SURFACE)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=C.BORDER, height=1).pack(fill="x", side="bottom")

        logo = tk.Label(hdr, text="U2", bg=C.ACCENT, fg="#ffffff",
                        font=(UI_FONT, FS_SMALL + 1, "bold"), width=3, height=1)
        logo.pack(side="left", padx=(16, 0), pady=10)
        tk.Label(hdr, text="存档修改器", bg=C.SURFACE, fg=C.ACCENT_DARK,
                 font=(UI_FONT, FS_MID, "bold")).pack(side="left", padx=(8, 0))

        self.save_box = tk.Frame(hdr, bg=C.SURFACE_ALT,
                                 highlightbackground=C.BORDER,
                                 highlightthickness=1)
        self.save_box.pack(side="left", padx=(22, 0), pady=9)
        self.save_label = tk.Label(self.save_box, text="", bg=C.SURFACE_ALT,
                                   fg=C.TEXT, font=(UI_FONT, FS_BODY))
        self.save_label.pack(side="left", padx=(11, 6), pady=4)
        self.stage_badge = Badge(self.save_box, "", kind="")
        self.stage_badge.pack(side="left", padx=(0, 9), pady=4)

        tk.Label(hdr, text="改动会先备份原存档", bg=C.SURFACE, fg=C.MUTED,
                 font=(UI_FONT, FS_SMALL)).pack(side="left", padx=12)

        self.undo_btn = FlatButton(hdr, "↶ 撤销", self.app.do_undo, kind="ghost")
        self.undo_btn.pack(side="right", padx=(6, 16), pady=10)
        self.apply_btn = FlatButton(hdr, "应用更改", self.app.do_apply, kind="pri")
        self.apply_btn.pack(side="right", pady=10)

    def _build_rail(self, body) -> None:
        rail = tk.Frame(body, bg=C.SURFACE, width=180)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Frame(rail, bg=C.BORDER, width=1).pack(side="right", fill="y")

        tk.Label(rail, text="功能", bg=C.SURFACE, fg=C.MUTED,
                 font=(UI_FONT, FS_SMALL), anchor="w",
                 padx=14).pack(fill="x", pady=(12, 4))

        self.nav_items: dict[str, dict] = {}
        for cls in PAGES:
            self._add_nav(rail, cls)

        tk.Frame(rail, bg=C.BORDER, height=1).pack(fill="x", padx=12, pady=10)
        self.undo_label = tk.Label(rail, text="撤销栈 0 条", bg=C.SURFACE,
                                   fg=C.MUTED, font=(UI_FONT, FS_SMALL),
                                   anchor="w", padx=14)
        self.undo_label.pack(fill="x")

    def _add_nav(self, rail, cls) -> None:
        item = tk.Frame(rail, bg=C.SURFACE, cursor="hand2")
        item.pack(fill="x", padx=6, pady=1)
        icon = tk.Label(item, text=cls.icon, bg=C.SURFACE, fg=C.TEXT,
                        font=(ICON_FONT, FS_MID + 1))
        icon.pack(side="left", padx=(8, 8), pady=6)
        name = tk.Label(item, text=cls.title, bg=C.SURFACE, fg=C.TEXT,
                        font=(UI_FONT, FS_BODY))
        name.pack(side="left", pady=6)
        why = tk.Label(item, text="", bg=C.SURFACE, fg=C.MUTED,
                       font=(UI_FONT, FS_SMALL - 1))
        why.pack(side="right", padx=8)
        for w in (item, icon, name, why):
            w.bind("<Button-1>", lambda _e, c=cls: self.select(c.key))
        self.nav_items[cls.key] = {"frame": item, "icon": icon, "name": name,
                                   "why": why, "cls": cls}

    def _build_work(self, body) -> None:
        self.work = tk.Frame(body, bg=C.WINDOW)
        self.work.pack(side="left", fill="both", expand=True)
        for cls in PAGES:
            page = cls(self.work, self.app)
            # ⚠️ **不要在这里 pack** —— 全部 pack 会让 7 个页竖着堆在一起。
            # 页面由 `select()` 负责 pack / pack_forget。
            self.pages[cls.key] = page

    def _build_status(self) -> None:
        bar = tk.Frame(self, bg=C.SURFACE)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=C.BORDER, height=1).pack(fill="x", side="top")
        self.caps_label = tk.Label(bar, text="", bg=C.SURFACE, fg=C.MUTED,
                                   font=(UI_FONT, FS_SMALL), anchor="w")
        self.caps_label.pack(side="left", padx=16, pady=5)
        self.state_label = tk.Label(bar, text="就绪 · 未改动磁盘", bg=C.SURFACE,
                                    fg=C.MUTED, font=(UI_FONT, FS_SMALL))
        self.state_label.pack(side="right", padx=16, pady=5)

    # ---- 能力位 ----

    def capability_items(self, view) -> list[tuple[str, bool, str]]:
        """`[(显示名, 能不能用, 原因)]` —— 状态栏与概览页共用。"""
        return capability_items(view)

    @staticmethod
    def _cap_ok(caps, key: str) -> bool:
        return capability_ok(caps, key)

    # ---- 刷新 ----

    def refresh(self) -> None:
        """重新读盘并刷新所有界面。"""
        self.view = self.save.view(self.catalog)
        self._refresh_header()
        self._refresh_rail()
        self._refresh_status()
        for page in self.pages.values():
            page.refresh(self.view)
        if self.current is None:
            self.select(self._first_available())

    def _refresh_header(self) -> None:
        info = self.view.save
        self.save_label.configure(text=pretty_name(info))
        stage = self.view.stage or ""
        self.stage_badge.configure(text=stage)
        self.stage_badge.set_kind(
            "battle" if self.view.capabilities.in_battle else "")
        n = self.app.undo_count()
        self.undo_btn.set_enabled(n > 0)
        self.undo_label.configure(text=f"撤销栈 {n} 条")

    def _refresh_rail(self) -> None:
        caps = self.view.capabilities
        for key, ui in self.nav_items.items():
            cls = ui["cls"]
            ok = True if not cls.capability else self._cap_ok(caps, cls.capability)
            why = "" if ok else SHORT_REASON.get(cls.capability, "不可用")
            ui["why"].configure(text=why)
            # ⚠️ Frame 只有 bg，没有 fg —— 颜色要分开设
            ui["frame"].configure(bg=C.SURFACE,
                                  cursor="hand2" if ok else "arrow")
            ui["icon"].configure(bg=C.SURFACE, fg=C.TEXT if ok else C.MUTED)
            ui["name"].configure(bg=C.SURFACE, fg=C.TEXT if ok else C.MUTED)
            ui["why"].configure(bg=C.SURFACE, fg=C.MUTED)

    def _refresh_status(self) -> None:
        caps = self.view.capabilities
        parts = []
        for name, ok, why in self.capability_items(self.view):
            if ok:
                parts.append(f" {name}✓")
            else:
                parts.append(f" {name}✗（{why}）")
        self.caps_label.configure(text="能力位：" + "".join(parts))

    def _first_available(self) -> str:
        caps = self.view.capabilities
        for cls in PAGES:
            if not cls.capability or self._cap_ok(caps, cls.capability):
                return cls.key
        return PAGES[0].key

    # ---- 切页 ----

    def select(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        cls = self.nav_items[key]["cls"]
        if cls.capability and not self._cap_ok(self.view.capabilities,
                                                cls.capability):
            return
        if self.current is not None and self.current in self.pages:
            self.pages[self.current].pack_forget()
        page.pack(fill="both", expand=True)
        self.current = key
        for k, ui in self.nav_items.items():
            on = (k == key)
            ui["frame"].configure(bg=C.ACCENT if on else C.SURFACE)
            ui["icon"].configure(bg=C.ACCENT if on else C.SURFACE,
                                 fg="#ffffff" if on else C.TEXT)
            ui["name"].configure(bg=C.ACCENT if on else C.SURFACE,
                                 fg="#ffffff" if on else C.TEXT)


class Application(tk.Tk):
    """应用根窗口：先启动页，选定存档后切成主界面。"""

    def __init__(self):
        super().__init__()
        self.title("统一指挥 2 存档修改器")
        self.minsize(1180, 700)
        self.configure(bg=C.WINDOW)
        apply_theme(self)
        self._center(1440, 900)

        self.paths = CorePaths.discover()
        try:
            self.catalog = catalog_mod.Catalog(self.paths)
        except Exception:                       # pragma: no cover
            self.catalog = None
        self.save = None
        self.shell: AppShell | None = None

        self.container = tk.Frame(self, bg=C.WINDOW)
        self.container.pack(fill="both", expand=True)
        self.splash = SavePicker(self.container, self)
        self.splash.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 动作 ----

    def _center(self, w: int, h: int) -> None:
        """窗口居中 —— 别让它随机飘到屏幕角落。"""
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(w, sw - 40)
        h = min(h, sh - 60)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def open_save(self, save_id: str) -> None:
        """打开存档并切到主界面。"""
        try:
            self.save = open_save(save_id, self.paths)
        except Exception as exc:
            self._error(f"打不开存档：{exc}")
            return
        self.splash.pack_forget()
        if self.shell is not None:
            self.shell.destroy()
        self.shell = AppShell(self.container, self, self.save, self.catalog)
        self.shell.pack(fill="both", expand=True)

    def reload(self) -> None:
        """重新读盘（G4 提交后用）。"""
        if self.shell is not None:
            self.shell.refresh()

    def capability_items(self, view) -> list[tuple[str, bool, str]]:
        """`[(显示名, 能不能用, 原因)]` —— 概览页直接调这个。"""
        return capability_items(view)

    def undo_count(self) -> int:
        if self.save is None:
            return 0
        try:
            return self.save.undo_count() if hasattr(self.save, "undo_count") else 0
        except Exception:
            return 0

    def do_undo(self) -> None:
        """G4 实现。"""
        self._error("撤销还没接上（G4 实现）。")

    def do_apply(self) -> None:
        """G4 实现。"""
        self._error("应用更改还没接上（G4 实现）。")

    def _error(self, text: str) -> None:
        from tkinter import messagebox
        messagebox.showwarning("存档修改器", text, parent=self)

    def _on_close(self) -> None:
        if self.save is not None:
            try:
                self.save.close()
            except Exception:
                pass
        self.destroy()


def run() -> int:
    app = Application()
    app.mainloop()
    return 0
