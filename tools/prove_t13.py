# -*- coding: utf-8 -*-
"""T13 护栏的反证：把搜索改回整页重绘 ⇒ 对应测试必须红在目标断言上。"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
REL = "src/save_modifier_web/web/index.html"
BAK = os.path.join(ROOT, ".scratch", "bak_t13")

OLD = """    /* ⚠️ **只刷列表，不整页重绘**（T13）——
       整页重绘会把**输入框本身**重建 ⇒ 浏览器正在进行的 **IME 组合被打断**
       ⇒ 汉字打不进去（英文能打，因为不需要组合）。
       ⇒ 这里只更新列表 + 计数 + 详情，输入框节点原封不动。 */
    refreshUnitsList();"""
NEW = """    show("units");"""

os.makedirs(BAK, exist_ok=True)
path = os.path.join(ROOT, REL)
shutil.copyfile(path, os.path.join(BAK, "index.html"))
try:
    with io.open(path, encoding="utf-8", newline="") as f:
        s = f.read()
    assert s.count(OLD) == 1, "命中 %d 次" % s.count(OLD)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(s.replace(OLD, NEW))
    target = ("tests.test_t13_unit_search_ime.TestUnitSearchKeepsTheInputBox."
              "test_search_handler_does_not_repaint_the_page")
    code = ("import sys, unittest; sys.path.insert(0, %r); "
            "unittest.main(module=None, argv=['x', %r], exit=True)" % (ROOT, target))
    r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    red = ("test_search_handler_does_not_repaint_the_page" in out
           and ("FAIL:" in out or "ERROR:" in out))
    print("退化「搜索时整页重绘」⇒ 退出码非零=%s，红在目标断言上=%s"
          % (r.returncode != 0, red))
    for ln in out.splitlines():
        if ln.startswith(("FAIL:", "ERROR:")):
            print("   ", ln)
    sys.exit(0 if (r.returncode != 0 and red) else 1)
finally:
    shutil.copyfile(os.path.join(BAK, "index.html"), path)
    shutil.rmtree(BAK, ignore_errors=True)
