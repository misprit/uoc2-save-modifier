# -*- coding: utf-8 -*-
"""T16 护栏的反证：把判据改回「hr != 0 即失败」⇒ 对应测试必须红。"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
TARGET = "src/save_modifier_web/backup_cleanup.py"
BAK = os.path.join(ROOT, ".scratch", "bak_t16")

OLD = "    if hr < 0:\n        raise BackupCleanupError(\"Windows 回收失败 (0x%08X)\" % (hr & 0xffffffff))\n    if not recycled:\n"
NEW = "    if hr != 0:\n        raise BackupCleanupError(\"Windows 回收失败 (0x%08X)\" % (hr & 0xffffffff))\n    if not recycled:\n"

os.makedirs(BAK, exist_ok=True)
path = os.path.join(ROOT, TARGET)
shutil.copyfile(path, os.path.join(BAK, "backup_cleanup.py"))
try:
    with io.open(path, encoding="utf-8", newline="") as f:
        s = f.read()
    assert s.count(OLD) == 1, "命中 %d 次" % s.count(OLD)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(s.replace(OLD, NEW))
    code = ("import sys, unittest; sys.path.insert(0, %r); "
            "unittest.main(module=None, argv=['x', %r], exit=True)"
            % (ROOT, "tests.test_backup_cleanup.BackupCleanupTest."
                     "test_recycle_result_judges_by_behaviour_not_hresult"))
    r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    red = ("test_recycle_result_judges_by_behaviour_not_hresult" in out
           and ("FAIL:" in out or "ERROR:" in out))
    print("退化「hr != 0 即失败」⇒ 退出码非零=%s，红在目标断言上=%s"
          % (r.returncode != 0, red))
    for ln in out.splitlines():
        if ln.startswith(("FAIL:", "ERROR:")):
            print("   ", ln)
    sys.exit(0 if (r.returncode != 0 and red) else 1)
finally:
    shutil.copyfile(os.path.join(BAK, "backup_cleanup.py"), path)
    shutil.rmtree(BAK, ignore_errors=True)
