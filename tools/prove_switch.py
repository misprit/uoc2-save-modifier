# -*- coding: utf-8 -*-
"""切换存档护栏的反证：去掉 `VIEW` 空保护 ⇒ 对应测试必须红。"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
REL = "src/save_modifier_web/web/index.html"
BAK = os.path.join(ROOT, ".scratch", "bak_switch")

CASES = [
    ("① loadPickers 去掉 VIEW 空保护",
     "  if(!VIEW || !VIEW._save_id) return null;\n  const q = \"?save_id=\" + encOnce(VIEW._save_id) + (unitType ? \"&unit_type=\" + encOnce(unitType) : \"\");\n",
     "  const q = \"?save_id=\" + encOnce(VIEW._save_id) + (unitType ? \"&unit_type=\" + encOnce(unitType) : \"\");\n",
     "tests.test_switch_save_null.TestSwitchSaveWithoutView.test_no_request_without_view"),
    ("② renderPage 去掉 VIEW 空保护",
     "  if(!VIEW){\n    const splash = document.getElementById(\"splash\");\n    const app = document.getElementById(\"app\");\n    if(splash) splash.style.display = \"block\";\n    if(app) app.style.display = \"none\";\n    return;\n  }\n",
     "",
     "tests.test_switch_save_null.TestSwitchSaveWithoutView."
     "test_render_page_returns_to_splash_without_view"),
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
