"""uoc2-save-modifier 的自动化测试。

用**标准库 unittest**（内置解释器没有 pip，装不了 pytest，也不想为此多背一个依赖）。

在项目根目录运行：

    python\\python.exe -m unittest discover -s tests -t .

或直接双击 / 调用：

    run_tests.bat
"""

#: U109：备份存档改放 `<修改器目录>/bak/` ⇒ 测试期间**不要**把备份写进仓库，
#: 统一指到一个临时目录（个别断言确切路径的测试会自己覆盖它）。
import os as _os
import tempfile as _tempfile
from pathlib import Path as _Path

import atexit as _atexit

if "UOC2_MODIFIER_HOME" not in _os.environ:
    _runtime = _tempfile.TemporaryDirectory(prefix="uoc2_test_program_")
    _os.environ["UOC2_MODIFIER_HOME"] = _runtime.name
    _atexit.register(_runtime.cleanup)

_os.environ.setdefault(
    "UOC2_BAK_DIR",
    str(_Path(_tempfile.gettempdir()) / "uoc2_save_modifier_test_bak"))
