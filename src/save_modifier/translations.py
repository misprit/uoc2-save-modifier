"""本地化（翻译）解析。

翻译用于把单位/总部的 name_brief（如 id_unit_name_brief_21_dot__ID）
解析成中文名，供参考列表与 find 使用。

数据源：游戏原版包的 <packages>/<pkg>/localization/<locale>/strings.yml。
工具支持从多个包合并（base + 各 dlc），后加载的覆盖先加载的。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

_LOCALE_DIRS = ["localization"]
_STRING_FILENAMES = ["strings.yml", "ui.yml"]  # 主字符串 + 可能的 UI 补充


def _natural_key(name: str) -> tuple:
    """包名自然序键：数字段按数值比较，使 dlc2 排在 dlc10 之前。"""
    return tuple(int(part) if part.isdigit() else part
                 for part in re.split(r"(\d+)", name))


class TranslationStore:
    """合并多包本地化文件，提供 id -> 中文 查询。"""

    def __init__(self, packages_path: Optional[Path], locale: str = "chi"):
        self.packages_path = Path(packages_path) if packages_path else None
        self.locale = locale
        self._data: dict[str, str] = {}
        if self.packages_path:
            self._load_all()

    def _load_all(self) -> None:
        root = self.packages_path
        if root is None:
            return
        # 按包名自然序加载（dlc2 先于 dlc10），后加载的包覆盖先加载的
        pkg_dirs = [p for p in root.iterdir() if p.is_dir()]
        pkg_dirs.sort(key=lambda p: _natural_key(p.name))
        for pkg in pkg_dirs:
            loc_dir = pkg / _LOCALE_DIRS[0] / self.locale
            if not loc_dir.is_dir():
                continue
            for fname in _STRING_FILENAMES:
                f = loc_dir / fname
                if f.is_file():
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            data = yaml.safe_load(fh)
                        if isinstance(data, dict):
                            self._data.update({str(k): v for k, v in data.items()
                                               if isinstance(v, str)})
                    except yaml.YAMLError:
                        pass

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._data
