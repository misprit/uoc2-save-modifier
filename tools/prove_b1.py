# -*- coding: utf-8 -*-
"""B1 护栏的反证：把实现改坏 ⇒ 对应测试必须红在目标断言上。

① 商店库存退回滚轮 span            ⇒ 「是输入框」测试必须红
② bindNumIn 不再挂滚轮              ⇒ 滚轮行为测试必须红
③ 数量 onChange 又去整页重绘         ⇒ 「不许重绘」测试必须红
每条改完立即跑对应测试，最后**逐字节还原**。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
BAK = os.path.join(ROOT, ".scratch", "bak_b1")

CASES = [
    ("① 商店库存退回滚轮 span",
     "src/save_modifier_web/web/index.html",
     '      <td class="num"><input class="numin" id="st_q_{13}_{14}_{15}" type="text"\n'
     '        inputmode="numeric" autocomplete="off" value="{19}"></td>\n',
     '      <td class="num"><span class="spin" id="st_q_{13}_{14}_{15}"></span></td>\n',
     "tests.test_b1_quantity_input.TestQuantityControlsAreInputs.test_store_quantity_is_an_input"),
    ("② bindNumIn 不再挂滚轮",
     "src/save_modifier_web/web/index.html",
     '  if(opts.wheel){\n',
     '  if(false){\n',
     "tests.test_b1_quantity_input.TestBindNumIn.test_wheel_steps_by_one_when_asked"),
    ("③ 数量 onChange 又去整页重绘",
     "src/save_modifier_web/web/index.html",
     '        if(isNew){ setNewEntry("quantity", v); return; }\n',
     '        if(isNew){ setNewEntry("quantity", v); show("store"); return; }\n',
     "tests.test_b1_quantity_input.TestQuantityControlsAreInputs.test_quantity_bindings_use_bind_num_in"),
]

os.makedirs(BAK, exist_ok=True)
results = []
try:
    for name, rel, old, new, target in CASES:
        path = os.path.join(ROOT, rel)
        with io.open(path, encoding="utf-8", newline="") as f:
            orig = f.read()
        assert orig.count(old) == 1, "%s：目标片段命中 %d 次" % (rel, orig.count(old))
        bak = os.path.join(BAK, os.path.basename(rel))
        shutil.copyfile(path, bak)
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig.replace(old, new))
        try:
            code = ("import sys, unittest; sys.path.insert(0, %r); "
                    "unittest.main(module=None, argv=['x', %r], exit=True)" % (ROOT, target))
            r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            out = r.stdout + r.stderr
            failed = ("FAIL: " + target.split(".")[-1]) in out
            others = [ln for ln in out.splitlines()
                      if ln.startswith("FAIL: ") or ln.startswith("ERROR: ")]
            results.append((name, r.returncode != 0, failed, others))
        finally:
            shutil.copyfile(bak, path)
finally:
    shutil.rmtree(BAK, ignore_errors=True)

print()
ok = True
for name, red, on_target, others in results:
    print("%s ⇒ 退出码非零=%s，红在目标断言上=%s" % (name, red, on_target))
    if others:
        print("    失败用例：%s" % "; ".join(others))
    ok = ok and red and on_target
print("\n反证结论：%s" % ("三条护栏都能红，且红在目标断言上 ✔" if ok else "有护栏没红或红错了地方 ✘"))
sys.exit(0 if ok else 1)
