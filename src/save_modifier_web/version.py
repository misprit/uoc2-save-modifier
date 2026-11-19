# -*- coding: utf-8 -*-
"""**成品版本号**（发给外部测试者的那一版）。

⚠️ 与 `save_modifier_core.__version__`（**核心库**的 API 版本，0.1.0）不是一回事：
那是「库的状态」，这里是「整包的状态」。
`tools/build_dist.py`（zip 文件名）与界面显示的版本号都读这里 —— **唯一来源**。
"""

__version__ = "1.0.0"

#: 作者署名（启动器 exe 的版本信息 / 界面「关于」/ 日志头 都用它）
AUTHOR = "烟柳边城 misprit"
