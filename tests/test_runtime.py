"""S1：运行时自检。

内置解释器必须**自带 PyYAML**，否则整个工具起不来
（历史缺陷：`python/Lib/site-packages` 目录缺失，run.bat 直接
`ModuleNotFoundError: No module named 'yaml'` —— 见文档 §10 第 51 条）。
"""

import sys
import unittest


class TestRuntime(unittest.TestCase):
    def test_python_version(self):
        """解释器版本要够新 —— `_yaml` C 扩展是针对特定 ABI 编译的。"""
        self.assertGreaterEqual(
            sys.version_info[:2], (3, 14),
            "内置解释器版本过低，_yaml C 扩展的 ABI 可能对不上")

    def test_yaml_available(self):
        import yaml
        self.assertTrue(hasattr(yaml, "safe_load"))
        self.assertTrue(hasattr(yaml, "safe_dump"))

    def test_libyaml_extension_available(self):
        """必须能用 C 加速器。

        没有它，解析速度会差一个量级 —— 实测游戏包整树 YAML 解析要 1~3 秒，
        全量遍历更慢（文档 §9.1.0）。此外 `yaml.safe_dump` 在纯 Python 模式下
        的输出格式与 C 模式不同，会影响打包结果的稳定性。
        """
        import yaml
        self.assertTrue(
            getattr(yaml, "__with_libyaml__", False),
            "yaml._yaml C 扩展没加载上；检查 python/Lib/site-packages/yaml/")

    def test_yaml_roundtrip_unicode(self):
        """改名功能依赖 YAML 能原样往返中文明文（文档 §5.5）。"""
        import yaml
        data = {"name_brief": "1第德国警卫队", "quantity": 5, "specs": []}
        dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        self.assertEqual(yaml.safe_load(dumped), data)
        self.assertIn("1第德国警卫队", dumped)

    def test_yaml_dump_keeps_key_order(self):
        """safe_dump(sort_keys=False) 必须保序 —— 写回时要原样搬运未改动的键。"""
        import yaml
        data = {"b": 1, "a": 2, "c": 3}
        dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        self.assertEqual(list(yaml.safe_load(dumped).keys()), ["b", "a", "c"])

    def test_package_importable(self):
        """核心包必须能从 `src/` 直接 import（靠 python314._pth 的 `..\\src`）。"""
        import save_modifier
        self.assertIsNotNone(save_modifier.__file__)


if __name__ == "__main__":
    unittest.main()
