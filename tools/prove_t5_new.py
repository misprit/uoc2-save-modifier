# -*- coding: utf-8 -*-
"""T5 续（新加卡标已用）的护栏反证。

① 核心库退回「写死 used=False」⇒ 「持续卡 + used=True 落盘后 used 真的为 True」必须红；
② 前端退回「待加的卡点已用 ⇒ 什么都不做」⇒ 「新加卡能一次落盘标成已用」必须红。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
BAK = os.path.join(ROOT, ".scratch", "bak_t5n")

CASES = [
    ("① 核心库退回写死 used=False",
     "src/save_modifier_core/handlers.py",
     '                  "unit_id": unit_id,\n                  "used": used_flag})',
     '                  "unit_id": unit_id,\n                  "used": False})',
     "tests.test_t5_new_card_used.TestCardAddUsed."
     "test_persistent_card_can_be_added_as_used"),
    ("② 前端退回「待加的卡点了什么都不做」",
     "src/save_modifier_web/web/index.html",
     '  const pend = pendingAddOf("card_add", position);\n'
     '  if(pend){\n'
     '    patchPendingParams("card_add", pend.key,\n'
     '      Object.assign({}, pend.params, {used:!!used}), pend.label);\n'
     '    show("cards");\n'
     '    return;\n'
     '  }\n',
     '  const pend = pendingAddOf("card_add", position);\n'
     '  if(pend){ show("cards"); return; }\n',
     "tests.test_t5_new_card_used.TestNewCardUsedButton."
     "test_new_card_can_be_marked_used_in_the_same_batch"),
]

os.makedirs(BAK, exist_ok=True)
results = []
try:
    for name, rel, old, new, target in CASES:
        path = os.path.join(ROOT, rel)
        shutil.copyfile(path, os.path.join(BAK, os.path.basename(rel)))
        with io.open(path, encoding="utf-8", newline="") as f:
            s = f.read()
        assert s.count(old) == 1, "%s：命中 %d 次" % (name, s.count(old))
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write(s.replace(old, new))
        code = ("import sys, unittest; sys.path.insert(0, %r); "
                "unittest.main(module=None, argv=['x', %r], exit=True)" % (ROOT, target))
        r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        red = (target.split(".")[-1] in out) and ("FAIL:" in out or "ERROR:" in out)
        results.append((name, r.returncode != 0, red))
        shutil.copyfile(os.path.join(BAK, os.path.basename(rel)), path)
finally:
    shutil.rmtree(BAK, ignore_errors=True)

print()
ok = True
for name, nonzero, red in results:
    print("%s ⇒ 退出码非零=%s，红在目标断言上=%s" % (name, nonzero, red))
    ok = ok and nonzero and red
print("\n反证结论：%s" % ("两条护栏都能红，且红在目标断言上 ✔" if ok else "有护栏没红 ✘"))
sys.exit(0 if ok else 1)
