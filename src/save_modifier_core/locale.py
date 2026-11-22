"""本地化查询 —— 中文显示名。

⚠️ **这是从旧 REPL 复活的一份实现**，不是新写的。
旧文件 `src/save_modifier/translations.py` 在 S11 重构（`0444628`）时
当"冗余"删掉了，但它本来就能：

* 读多个包的 `localization/<locale>/strings.yml` + `ui.yml`；
* 按**自然序**合并包名（`dlc2` 排在 `dlc10` 之前）；
* 后加载的覆盖先加载的；
* `get(key, default)` 查不到就返回默认值。

`e159` 对真实游戏包实测：合并结果 16764 条，与直读 base 包
**键集合相同、值零差异** ⇒ 机制正确，搬过来即可（规范 §5.7、§8.1）。

**比旧实现多做的两件事**

1. **参数化模板也留下**。游戏里 `idp_*` 的值是 dict
   （`{"default": "每回合{}次空袭", "1": "…"}`），按数量取变体、
   缺省取 `default`。旧实现只收 `str` 值，把这 22 条**全丢了**。
2. **用户包优先**。mod 的 `localization/` 要能盖掉游戏包的，
   所以顺序是「游戏包 → 用户包」，后者覆盖前者。

用法
----
```python
from save_modifier_core import locale

locale.text("id_card_Ju_87")            # 'Ju 87'
locale.text("id_card_THEATER_ASSET")    # '战区资产'
locale.text("没有这个键")                # ''
locale.template("idp_air_attack", 3)    # 参数化模板
```
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from . import yamlio

__all__ = ["TranslationStore", "default", "text", "template", "keys"]


#: 本地化文件在包里的相对路径
LOCALE_SUBDIR = "localization"

#: 每个 locale 目录里的**主**文件（保留旧名；U74 起不再用白名单）
#:
#: ⚠️ 改成「扫该目录下所有 `.yml`」** ——
#: ① `eng` 目录里**没有** `strings.yml`（英文被拆成 **40 个** 按功能分的 yml）
#:    ⇒ 旧白名单会让英文**一个字符串都读不到**；
#: ② mod 往 `localization/<lang>/` 里加的**新文件**（如所见即所得 mod 的
#:    `wysiwyg_preview.yml`）也不再被漏掉。
STRING_FILENAMES = ("strings.yml", "ui.yml")


def _natural_key(name: str) -> tuple:
    """包名自然序键：数字段按数值比较，使 `dlc2` 排在 `dlc10` 之前。

    （旧实现原样保留 —— 这不是 `sorted()` 的字典序。）
    """
    return tuple(int(part) if part.isdigit() else part
                 for part in re.split(r"(\d+)", name))


class TranslationStore:
    """合并多包本地化文件，提供 `id → 中文` 查询。

    参数
    ----
    packages_path : 游戏包**容器**目录（`<游戏>/_packages`），
                    或直接给一个 `CorePaths`（内部取 `package_roots()`）。
                    给 None 就什么都不加载，`get()` 恒返回默认值。
    locale        : 语言目录名，游戏简体中文是 `chi`。

    ⚠️ **找不到文件不报错** —— `get()` 返回空串。
    核心库没有游戏本体也能工作（规范 §0.3）。
    """

    def __init__(self, packages_path: "Any" = None, locale: str = "chi"):
        self.locale = locale
        self._data: dict[str, str] = {}
        self._templates: dict[str, dict] = {}
        self.packages_path: Path | None = None
        roots = self._roots(packages_path)
        if roots:
            self._load_all(roots)

    # ---- 构造辅助 ----

    @staticmethod
    def _roots(packages_path: "Any") -> list[Path]:
        """把参数变成「包容器目录」列表。

        * `CorePaths` → `package_roots()`（用户包在前）；
        * `Path` → 当作一个容器目录；
        * `None` → 空。
        """
        if packages_path is None:
            return []
        # CorePaths 有 package_roots 属性 —— 不 import 它，避免循环依赖
        roots = getattr(packages_path, "package_roots", None)
        if callable(roots):
            return [Path(r) for r in roots()]
        return [Path(packages_path)]

    # ---- 加载 ----

    def _load_all(self, roots: list[Path]) -> None:
        """按「游戏包 → 用户包」顺序加载，**后加载的覆盖先加载的**。

        同一个容器内，包名按自然序（`dlc2` 先于 `dlc10`）。
        """
        for root in reversed(roots):        # 用户包在后 ⇒ 覆盖游戏包
            if not root.is_dir():
                continue
            try:
                pkgs = [p for p in root.iterdir() if p.is_dir()]
            except OSError:
                continue
            pkgs.sort(key=lambda p: _natural_key(p.name))
            for pkg in pkgs:
                self._load_package(pkg)

    def _load_package(self, pkg: Path) -> None:
        loc_dir = pkg / LOCALE_SUBDIR / self.locale
        if not loc_dir.is_dir():
            return
        # 读该目录下**所有** `.yml`（不挑名字）—— 见 STRING_FILENAMES 的说明
        try:
            files = sorted(f for f in loc_dir.glob("*.yml") if f.is_file())
        except OSError:
            files = []
        for f in files:
            try:
                data = yamlio.load(f.read_bytes())
            except Exception:
                continue          # 一个坏文件不能拖垮整个 locale
            if not isinstance(data, dict):
                continue
            for k, v in data.items():
                key = str(k)
                if isinstance(v, str):
                    self._data[key] = v
                    self._templates.pop(key, None)
                elif isinstance(v, dict):
                    # 参数化模板（`idp_*`）—— 旧实现会把这些丢掉
                    # 键统一转成字符串：YAML 里 `1:` 会解析成 int 1
                    self._templates[key] = {str(k): v2 for k, v2 in v.items()}
                    self._data.pop(key, None)

    # ---- 查询 ----

    def get(self, key: str, default: str = "") -> str:
        """查一条文本；查不到返回 `default`（默认空串）。"""
        if not key:
            return default
        return self._data.get(key, default)

    def template(self, key: str, count: int | None = None, *args) -> str:
        """查一条**参数化模板**（`idp_*`）。

        模板的值是 dict：按数量取变体（键是数量的字符串），
        没有对应变体就取 `default`；再把 `args` 填进 `{}` 占位。

        查不到返回空串 —— 模板不是硬要求。
        """
        tmpl = self._templates.get(key)
        if not isinstance(tmpl, dict):
            return self.get(key, "")
        text = tmpl.get("default", "")
        if count is not None:
            text = tmpl.get(str(count), text)
        if not isinstance(text, str):
            text = ""
        if args:
            try:
                text = text.format(*args)
            except (IndexError, KeyError, ValueError):
                pass                 # 占位对不上就原样返回
        return text

    def is_template(self, key: str) -> bool:
        """这个键是不是参数化模板。"""
        return key in self._templates

    def __contains__(self, key: str) -> bool:
        return key in self._data or key in self._templates

    def __len__(self) -> int:
        return len(self._data) + len(self._templates)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def keys(self) -> list[str]:
        """全部键（普通文本 + 参数化模板）。"""
        return sorted(set(self._data) | set(self._templates))

    @property
    def templates(self) -> dict[str, dict]:
        """参数化模板（只读副本）。"""
        return dict(self._templates)


# ---------------------------------------------------------------- 模块级便捷函数
#
# 与 `catalog.py` 同一套用法：GUI 直接 `from save_modifier_core import locale`。

_default: TranslationStore | None = None


def default() -> TranslationStore:
    """全局默认实例（第一次调用时创建）。"""
    global _default
    if _default is None:
        from .paths import CorePaths
        try:
            paths = CorePaths.discover()
        except Exception:
            paths = None
        _default = TranslationStore(paths)
    return _default


def text(key: str, fallback: str = "") -> str:
    """查一条中文文本；查不到返回 `fallback`。

    （参数叫 `fallback` 而不是 `default`，免得把模块级的 `default()` 遮住。）
    """
    return default().get(key, fallback)


def template(key: str, count: int | None = None, *args) -> str:
    """查一条参数化模板。"""
    return default().template(key, count, *args)


def keys() -> list[str]:
    """全部 locale 键。"""
    return default().keys()
