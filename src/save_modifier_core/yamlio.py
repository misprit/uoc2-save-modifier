"""YAML 读写的统一入口。

**读用 C 解析器，写用纯 Python 的 `safe_dump`** —— 两者各有理由：

* **读**：`yaml.CSafeLoader`（libyaml）比纯 Python 的 `SafeLoader` 快 5~10 倍。
  存档里最大的两张表是根 `units.yml`（1000+ 条）和 `document/units.yml`（1185 条），
  用纯 Python 解析的话，打开一个存档要 300 ms 以上
  （规范 §9.1.0：**慢的不是 I/O，是 YAML 解析**）。
* **写**：必须用 `yaml.safe_dump` —— C 版 `CSafeDumper` 的输出格式与纯 Python 版
  **不一样**，而我们写回的 YAML 要与游戏写出来的风格保持一致
  （`allow_unicode=True, sort_keys=False`，规范 §8）。

C 解析器不可用时（没 vendor PyYAML、或 libyaml 没编上）自动退回纯 Python。
"""

from __future__ import annotations

from typing import Any

import yaml

__all__ = ["load", "dump", "has_fast_loader"]


try:                                    # pragma: no cover - 取决于运行环境
    from yaml import CSafeLoader as _Loader
    _HAS_FAST = True
except ImportError:                     # pragma: no cover
    from yaml import SafeLoader as _Loader
    _HAS_FAST = False


def has_fast_loader() -> bool:
    """是否有 libyaml C 解析器（用于自检与性能提示）。"""
    return _HAS_FAST


def load(raw: bytes | str) -> Any:
    """解析 YAML。失败抛 `yaml.YAMLError`（由调用方决定怎么处理）。"""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return yaml.load(raw, Loader=_Loader)


def dump(data: Any) -> bytes:
    """序列化为 YAML 字节流（UTF-8，中文不转义，保持键序）。"""
    return yaml.safe_dump(data, allow_unicode=True,
                          sort_keys=False).encode("utf-8")
