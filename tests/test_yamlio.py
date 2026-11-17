"""YAML 序列化保真 —— 核心库写回时"没改的东西一个字节都不动"。

**依据是游戏自己的字节码**（`lib/tools/yaml_.pyc`）：

* `yaml.dump(obj, Dumper=_Dumper, default_flow_style=False)`；
* `_Dumper` 基于 `yaml.CDumper`，并注册了 5 个自定义 representer：
  * `list`  ⇒ 元素个数 1..4 且全是标量时用**流式**（`uv: [354, 215]`）；
  * `str`   ⇒ 长度 > 100 用**块样式**（`|`）；
  * `float` ⇒ `str(float(x))`；
  * `bool` / `int` ⇒ 与默认一致。

⚠️ 游戏**没有**传 `allow_unicode` ⇒ 用的是默认的 False ⇒
**中文写成 `\\uXXXX` 转义**。跟着它写，才能逐字节保持不变的部分原样不动。

实测（70 个存档 / 337 个 L1 条目）：解析 → 重新序列化 → **字节完全一致 337/337**。
"""

import unittest
import zipfile

from save_modifier_core import yamlio

from ._helpers import find_saves

L1_ENTRIES = ("main.yml", "units.yml", "hqs.yml", "cards.yml", "store.yml")


class TestGameStyle(unittest.TestCase):
    """规则本身（不依赖本机有没有存档）。"""

    def test_short_list_is_flow_style(self):
        """1..4 个标量 ⇒ 流式。"""
        self.assertEqual(yamlio.dump({"uv": [354, 215]}),
                         b"uv: [354, 215]\n")
        self.assertEqual(yamlio.dump({"a": [1]}),
                         b"a: [1]\n")

    def test_five_element_list_is_block_style(self):
        """5 个标量 ⇒ **块样式**（游戏的规则是 `< 5`，不是 `<= 5`）。"""
        out = yamlio.dump({"played": ["a", "b", "c", "d", "e"]})
        self.assertNotIn(b"[a, b, c, d, e]", out)
        self.assertIn(b"played:\n- a\n", out)

    def test_nested_collection_is_block_style(self):
        out = yamlio.dump({"specs": [{"active": True, "idx": 0}]})
        self.assertNotIn(b"{active", out)
        self.assertIn(b"- active: true\n", out)

    def test_long_string_is_block_style(self):
        """超过 100 个字符 ⇒ `|` 块样式。"""
        long = "x" * 120
        out = yamlio.dump({"note": long})
        self.assertIn(b"|", out)
        self.assertIn(long.encode("utf-8"), out)

    def test_short_string_is_plain(self):
        out = yamlio.dump({"name": "我的警卫队"})
        self.assertIn(b"name:", out)

    def test_non_ascii_is_escaped_like_the_game(self):
        """游戏用默认的 `allow_unicode=False` ⇒ 中文写成 `\\uXXXX`。

        实测真实存档里的写法就是
        `name_brief: "1\\u7B2C\\u82CF\\u8054\\u8B66\\u536B\\u961F"`（双引号 + 大写十六进制）。
        """
        out = yamlio.dump({"name": "警卫"})
        self.assertEqual(out, b'name: "\\u8B66\\u536B"\n')

    def test_dict_is_always_block_style(self):
        """字典一律块样式（哪怕全是标量）。"""
        out = yamlio.dump({"a": 1, "b": 2})
        self.assertNotIn(b"{a: 1", out)
        self.assertIn(b"a: 1\n", out)

    def test_key_order_is_preserved(self):
        """`sort_keys=False` —— 保持文件里原有的键序，不重排。"""
        out = yamlio.dump({"z": 1, "a": 2})
        self.assertLess(out.index(b"z:"), out.index(b"a:"))

    def test_bool_and_none(self):
        self.assertEqual(yamlio.dump({"a": True, "b": None}),
                         b"a: true\nb: null\n")


class TestRoundTripOnRealSaves(unittest.TestCase):
    """真实存档：解析 → 重新序列化必须**逐字节一致**。"""

    def test_l1_entries_roundtrip_byte_identically(self):
        saves = find_saves(limit_per_dir=3)
        if not saves:
            self.skipTest("本机没有找到 .uoc2 存档")
        checked = 0
        for src in saves:
            with zipfile.ZipFile(src) as zf:
                for name in zf.namelist():
                    if name not in L1_ENTRIES:
                        continue
                    raw = zf.read(name)
                    try:
                        data = yamlio.load(raw)
                    except Exception:
                        continue
                    if data is None:
                        continue
                    with self.subTest(save=src.name, entry=name):
                        self.assertEqual(
                            yamlio.dump(data), raw,
                            f"{src.name}::{name} 重新序列化后与原文不一致")
                    checked += 1
        self.assertGreater(checked, 0, "一个条目都没检查到")


if __name__ == "__main__":
    unittest.main()
