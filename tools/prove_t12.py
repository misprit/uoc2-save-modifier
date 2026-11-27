# -*- coding: utf-8 -*-
"""T12 护栏的反证：把实现改坏 ⇒ 对应测试必须红在目标断言上。

① 显示的等级改回「生效等级」（= 压制会把它拉低）⇒ 「压制不联动」的测试必须红；
② 写盘时不再减去压制（`level = real`）⇒ 「不写负数 / 不超范围」的测试必须红。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
REL = "src/save_modifier_web/web/index.html"
BAK = os.path.join(ROOT, ".scratch", "bak_t12")

CASES = [
    ("① 显示的等级退回生效等级",
     "    const lvl = st.real;\n",
     "    const lvl = st.level;\n",
     "tests.test_t12_hq_branch_levels.TestHqMatrixRender."
     "test_rendered_level_is_unlock_level_not_effective"),
    ("② 写盘时不再减去压制",
     "  const level = real - suppressed;\n",
     "  const level = real;\n",
     "tests.test_t12_hq_branch_levels.TestHqBranchLevels."
     "test_level_and_suppress_together_never_write_negative"),
]

os.makedirs(BAK, exist_ok=True)
path = os.path.join(ROOT, REL)
shutil.copyfile(path, os.path.join(BAK, "index.html"))
results = []
try:
    with io.open(path, encoding="utf-8", newline="") as f:
        orig = f.read()
    for name, old, new, target in CASES:
        assert orig.count(old) == 1, "%s：命中 %d 次" % (name, orig.count(old))
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig.replace(old, new))
        code = ("import sys, unittest; sys.path.insert(0, %r); "
                "unittest.main(module=None, argv=['x', %r], exit=True)" % (ROOT, target))
        r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        red = (target.split(".")[-1] in out) and ("FAIL:" in out or "ERROR:" in out)
        results.append((name, r.returncode != 0, red))
finally:
    shutil.copyfile(os.path.join(BAK, "index.html"), path)
    shutil.rmtree(BAK, ignore_errors=True)

print()
ok = True
for name, nonzero, red in results:
    print("%s ⇒ 退出码非零=%s，红在目标断言上=%s" % (name, nonzero, red))
    ok = ok and nonzero and red
print("\n反证结论：%s" % ("两条护栏都能红，且红在目标断言上 ✔" if ok else "有护栏没红 ✘"))
sys.exit(0 if ok else 1)
