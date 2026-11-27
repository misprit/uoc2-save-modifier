# -*- coding: utf-8 -*-
"""解锁的护栏反证：把「战斗中硬拦」加回去 ⇒ 对应测试必须红。

（目标是「战斗中也允许」这个行为 —— 反证要证明护栏真的在守它。）
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
REL = "src/save_modifier_core/handlers.py"
BAK = os.path.join(ROOT, ".scratch", "bak_unlock")

OLD = """    # ---- ① 战役清单（权威） ----"""
NEW = """    if not w.require(not w.caps.in_battle, "ruins", "main.yml"):
        return oc

    # ---- ① 战役清单（权威） ----"""

TARGETS = [
    "tests.test_city_restore.TestCityRestore.test_in_battle_is_allowed",
    "tests.test_city_restore.TestCityRestore.test_in_battle_commit_writes_all_three",
]

os.makedirs(BAK, exist_ok=True)
path = os.path.join(ROOT, REL)
shutil.copyfile(path, os.path.join(BAK, "handlers.py"))
ok = True
try:
    with io.open(path, encoding="utf-8", newline="") as f:
        s = f.read()
    assert s.count(OLD) == 1, "命中 %d 次" % s.count(OLD)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(s.replace(OLD, NEW))
    for target in TARGETS:
        code = ("import sys, unittest; sys.path.insert(0, %r); "
                "unittest.main(module=None, argv=['x', %r], exit=True)" % (ROOT, target))
        r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        red = (target.split(".")[-1] in out) and ("FAIL:" in out or "ERROR:" in out)
        print("%s ⇒ 退出码非零=%s，红在目标断言上=%s"
              % (target.split(".")[-1], r.returncode != 0, red))
        ok = ok and (r.returncode != 0) and red
finally:
    shutil.copyfile(os.path.join(BAK, "handlers.py"), path)
    shutil.rmtree(BAK, ignore_errors=True)

print("\n反证结论：%s" % ("护栏能红 ✔" if ok else "有护栏没红 ✘"))
sys.exit(0 if ok else 1)
