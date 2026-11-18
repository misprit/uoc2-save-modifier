"""YAML 读写的统一入口。

**读用 C 解析器，写用复刻游戏自己的序列化器** —— 两者都有明确理由。

读
----
`yaml.CSafeLoader`（libyaml）比纯 Python 的 `SafeLoader` 快 5~10 倍。
存档里最大的两张表是根 `units.yml`（1000+ 条）和 `document/units.yml`（1185 条），
用纯 Python 解析的话，打开一个存档要 300 ms 以上
（规范 §9.1.0：**慢的不是 I/O，是 YAML 解析**）。
C 解析器不可用时（没 vendor PyYAML、或 libyaml 没编上）自动退回纯 Python。

写
----
**复刻游戏自己的 `_Dumper`**（字节码实证，见 `lib/tools/yaml_.pyc`）：

```python
# 游戏侧（tools/yaml_.py）
class _Dumper(yaml.CDumper):
    def check_short_list(self, l):     # 1 <= len(l) < 5 且全是标量 ⇒ 流式
    def set_representer(self, l):      # set ⇒ sorted
    def str_representer(self, data):   # len > 100 ⇒ 块样式 '|'
    def float_representer(self, data): # str(float(data))
    ...
_Dumper.add_representer(list, _Dumper.check_short_list)
_Dumper.add_representer(str,   _Dumper.str_representer)
_Dumper.add_representer(float, _Dumper.float_representer)
_Dumper.add_representer(bool,  _Dumper.bool_representer)
_Dumper.add_representer(int,   _Dumper.int_representer)

yaml.dump(obj, Dumper=d, default_flow_style=False)
```

⚠️ **注意 `allow_unicode` 用的是默认值 False** —— 游戏把中文写成 `\\uXXXX` 转义，
不是明文。跟着游戏写，写回的文件才能**逐字节保持不变的部分原样不动**。

**实测（本机 70 个存档、337 个 L1 条目）**：用这套序列化器
**解析 → 重新序列化 → 字节完全一致 337/337**；而用通用 `safe_dump`
（`allow_unicode=True`）只有 281/337 —— 56 个含中文的条目会被改写。

这直接兑现了规范 §0.4 的铁律：**"写回时未改动的一切原样搬运"**。
"""

from __future__ import annotations

from typing import Any

import yaml

__all__ = ["load", "dump", "has_fast_loader", "has_fast_dumper"]


try:                                    # pragma: no cover - 取决于运行环境
    from yaml import CSafeLoader as _Loader
    _HAS_FAST = True
except ImportError:                     # pragma: no cover
    from yaml import SafeLoader as _Loader
    _HAS_FAST = False


def has_fast_loader() -> bool:
    """是否有 libyaml C 解析器（用于自检与性能提示）。"""
    return _HAS_FAST


# ---------------------------------------------------------------- 写


def _build_dumper():
    """造一个和游戏 `_Dumper` 等价的序列化器。

    游戏用的是 `yaml.CDumper`（C emitter）；没有 libyaml 时退回纯 Python 版
    —— 两者在本项目涉及的 YAML 构造上输出**一致**（337/337 字节回归已验证）。
    """
    base = getattr(yaml, "CDumper", None) or yaml.SafeDumper

    class GameDumper(base):                       # type: ignore[misc, valid-type]
        """游戏自己的 YAML 序列化规则（字节码还原）。"""

        def check_short_list(self, l):
            """1..4 个标量的列表 ⇒ 流式（`uv: [354, 215]`）；其余块式。"""
            s = 1 <= len(l) < 5 and all(
                isinstance(e, (int, float, str)) for e in l)
            return self.represent_sequence(
                'tag:yaml.org,2002:seq', l, flow_style=s)

        def str_representer(self, data):
            """超过 100 个字符 ⇒ 块样式（`|`），否则普通标量。"""
            if len(data) > 100:
                return self.represent_scalar(
                    'tag:yaml.org,2002:str', data, style='|')
            return self.represent_scalar('tag:yaml.org,2002:str', data)

        def float_representer(self, data):
            """`str(float(data))` —— 与游戏一致（避免 `1.0e-05` 这类写法）。

            ⚠️ **必须直接给 `represent_scalar`**，不能绕 `represent_float`：
            PyYAML 的 `represent_float(data)` 内部是 `repr(data).lower()`，
            传字符串进去 ⇒ `repr("80.0")` = `"'80.0'"`（**带引号**）
            ⇒ 写出 `!!float '''80.0'''` ⇒ **游戏读这个文件会直接崩**（U38 实测）。
            """
            return self.represent_scalar('tag:yaml.org,2002:float', str(float(data)))

        def bool_representer(self, data):
            return self.represent_bool(data)

        def int_representer(self, data):
            return self.represent_int(data)

    GameDumper.add_representer(list, GameDumper.check_short_list)
    GameDumper.add_representer(str, GameDumper.str_representer)
    GameDumper.add_representer(float, GameDumper.float_representer)
    GameDumper.add_representer(bool, GameDumper.bool_representer)
    GameDumper.add_representer(int, GameDumper.int_representer)
    return GameDumper


_Dumper = _build_dumper()


def has_fast_dumper() -> bool:
    """是否用的是 C emitter（与游戏一致）。"""
    return getattr(yaml, "CDumper", None) is not None


def load(raw: bytes | str) -> Any:
    """解析 YAML。失败抛 `yaml.YAMLError`（由调用方决定怎么处理）。"""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return yaml.load(raw, Loader=_Loader)


def dump(data: Any) -> bytes:
    """序列化为 YAML 字节流（**与游戏同一个风格**）。

    * `default_flow_style=False` —— 字典与长列表一律块样式；
    * `allow_unicode=False` —— 中文写成 `\\uXXXX`（游戏就是这样）；
    * `sort_keys=False` —— **保持文件里原有的键序**（游戏自己写出来的文件
      本来就是字母序，所以两者结果一致；但手改过的文件不会被我们重排）。
    """
    return yaml.dump(data, Dumper=_Dumper, default_flow_style=False,
                     allow_unicode=False, sort_keys=False).encode("utf-8")
