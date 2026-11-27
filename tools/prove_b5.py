# -*- coding: utf-8 -*-
"""B-5 收窄的护栏反证：

① 判重退回「所有卡型都拦」⇒ 「普通卡可以重复上架」必须红；
② 白名单里删掉「手牌里已有同类型」⇒ 「手牌与商店不能同时出现召唤卡」必须红
   （证明这条规则被钉住了，不会以后被顺手放宽）。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
BAK = os.path.join(ROOT, ".scratch", "bak_b5")

CASES = [
    ("① 判重退回「所有卡型都拦」",
     "src/save_modifier_core/handlers.py",
     '    if info.get("has_unit") and _shelf_has_card_type(w, shelf, card_type):\n',
     '    if _shelf_has_card_type(w, shelf, card_type):\n',
     "tests.test_b5_scope_summon_only.TestOrdinaryCardsMayRepeat."
     "test_ordinary_card_can_be_listed_twice"),
    ("② 白名单不再管「手牌里已有同类型」",
     "src/save_modifier_core/catalog.py",
     '                elif name in hand_types:\n'
     '                    reasons.append("手牌里已有同类型")\n',
     '',
     "tests.test_b5_scope_summon_only.TestSummonCardsStayRestricted."
     "test_summon_card_in_hand_cannot_be_listed_on_the_shelf"),
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
