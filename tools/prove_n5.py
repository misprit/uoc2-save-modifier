# -*- coding: utf-8 -*-
"""N-5 护栏的反证：把实现改坏 ⇒ 对应测试必须红在目标断言上。

三条退化：
  ① 前端不判 persistent（谁都给「已使用」开关）⇒ 非持续卡测试必须红
  ② 核心库不判 persistent（谁都能改 used）⇒ 非持续卡核心测试必须红
  ③ 服务端不带 persistent ⇒ 前端拿不到标记的测试必须红
每条改完立即跑对应测试、记录失败用例名，最后**逐字节还原**。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
BAK = os.path.join(ROOT, ".scratch", "bak_n5")

CASES = [
    ("① 前端不判 persistent",
     "src/save_modifier_web/web/index.html",
     '  const persist = (kind==="hand") && !!cardInfo(c.card_type).persistent;',
     '  const persist = (kind==="hand");',
     "tests.test_n5_card_used_ui.TestCardUsedUI.test_non_persistent_card_has_no_used_line"),
    ("② 核心库不判 persistent",
     "src/save_modifier_core/handlers.py",
     '        if definition.get("persistent") is not True:',
     '        if False:',
     "tests.test_n5_card_used.TestCardUsedPersistent.test_nonpersistent_card_used_is_rejected"),
    ("③ 服务端不带 persistent",
     "src/save_modifier_web/server.py",
     '            "persistent": bool(d.get("persistent")),\n',
     '',
     "tests.test_n5_card_used_ui.TestCatalogPersistentFlag.test_catalog_payload_exposes_persistent_flag"),
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
            # ⚠️ 随包 python 用 `python314._pth`（隔离模式）⇒ **cwd 不在 sys.path 上**
            #    ⇒ 不能直接 `python -m unittest tests.xxx`（会 loader 失败）。
            #    改成运行时 sys.path.insert(ROOT) 再按点名跑。
            code = ("import sys, unittest; sys.path.insert(0, %r); "
                    "unittest.main(module=None, argv=['x', %r], exit=True)"
                    % (ROOT, target))
            r = subprocess.run([PY, "-c", code],
                               cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            out = r.stdout + r.stderr
            failed = ("FAIL: " + target.split(".")[-1]) in out
            others = [ln for ln in out.splitlines()
                      if ln.startswith("FAIL: ") or ln.startswith("ERROR: ")]
            results.append((name, target, r.returncode != 0, failed, others))
        finally:
            shutil.copyfile(bak, path)
finally:
    shutil.rmtree(BAK, ignore_errors=True)

print()
ok = True
for name, target, red, on_target, others in results:
    print("%s ⇒ 退出码非零=%s，红在目标断言上=%s" % (name, red, on_target))
    if others:
        print("    失败用例：%s" % "; ".join(others))
    ok = ok and red and on_target
print("\n反证结论：%s" % ("三条护栏都能红，且红在目标断言上 ✔" if ok else "有护栏没红或红错了地方 ✘"))
sys.exit(0 if ok else 1)
