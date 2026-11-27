# -*- coding: utf-8 -*-
"""T5 护栏的反证：把实现改坏 ⇒ 对应测试必须红在目标断言上。

① `cardSetUsed` 的 base 退回**投影值** ⇒ 「点两次回到原值应撤掉待应用」必须红；
② 卡面又变回「状态单独占一行」 ⇒ 「状态不在单独一行」必须红。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
REL = "src/save_modifier_web/web/index.html"
BAK = os.path.join(ROOT, ".scratch", "bak_t5")

CASES = [
    ("① cardSetUsed 的 base 退回投影值",
     "     ⇒ 撤不掉那条待应用 ⇒ 界面与待应用对不上（T5 实测）。 */\n"
     "  const c = (VIEW.hand||[]).find(x=>x.position===position);\n",
     "     ⇒ 撤不掉那条待应用 ⇒ 界面与待应用对不上（T5 实测）。 */\n"
     "  const c = projectedCards(VIEW.hand,\"hand\").find(x=>x.position===position);\n",
     "tests.test_n5_card_used_ui.TestCardUsedUI."
     "test_toggling_back_to_the_stored_value_drops_the_pending"),
    ("② 状态又变回单独占一行",
     "    <div class=\"acts\">\n",
     "    <div class=\"cp usedline\">已使用</div>\n    <div class=\"acts\">\n",
     "tests.test_n5_card_used_ui.TestCardUsedUI."
     "test_status_is_not_a_separate_line"),
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
