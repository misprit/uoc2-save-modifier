# -*- coding: utf-8 -*-
"""候选池搜索框护栏的反证：把功能改坏 ⇒ 对应测试必须红在目标断言上。

三个退化点：
① 去掉搜索过滤（池子里什么都不筛）⇒ 「按中文名搜」必须红；
② 去掉「有搜索词时强制展开」⇒ 「搜到的分组自动展开」必须红；
③ 搜索时顺带重画输入框（重画整个 fullPoolHTML）⇒ 「只重画池体」必须红。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
REL = "src/save_modifier_web/web/index.html"
BAK = os.path.join(ROOT, ".scratch", "bak_pool_search")

CASES = [
    # (退化说明, 原文, 改坏后, 目标测试全名)
    ("搜索不过滤（候选池全显示）",
     """  const all = Object.keys(cat.spec_types||{})
                 .filter(t=>spickMatch(specPoolItem(t), qy));""",
     """  const all = Object.keys(cat.spec_types||{});""",
     "tests.test_pool_search.TestPoolSearch.test_search_filters_by_chinese_name"),
    ("搜到也不展开分组",
     """      const open = qy ? true : poolGroupOpen(n.nat);""",
     """      const open = poolGroupOpen(n.nat);""",
     "tests.test_pool_search.TestPoolSearch.test_matched_group_is_expanded"),
    ("搜索时连输入框一起重画",
     """  body.innerHTML = fullPoolBodyHTML(u, projectedSpecs(u), (q||"").trim().toLowerCase());""",
     """  const box = document.getElementById("poolq");
  if(box) box.value = q;
  body.innerHTML = fullPoolBodyHTML(u, projectedSpecs(u), (q||"").trim().toLowerCase());""",
     "tests.test_pool_search.TestPoolSearch.test_search_only_redraws_the_pool_body"),
]


def run_target(target):
    code = ("import sys, unittest; sys.path.insert(0, %r); "
            "unittest.main(module=None, argv=['x', %r], exit=True)" % (ROOT, target))
    r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    name = target.rsplit(".", 1)[1]
    red = (name in out and ("FAIL:" in out or "ERROR:" in out))
    return r.returncode != 0 and red, out


def main():
    os.makedirs(BAK, exist_ok=True)
    path = os.path.join(ROOT, REL)
    shutil.copyfile(path, os.path.join(BAK, "index.html"))
    ok_all = True
    try:
        base = io.open(path, encoding="utf-8", newline="").read()
        for desc, old, new, target in CASES:
            assert base.count(old) == 1, "%s：锚点命中 %d 次" % (desc, base.count(old))
            with io.open(path, "w", encoding="utf-8", newline="") as f:
                f.write(base.replace(old, new))
            try:
                red, out = run_target(target)
            finally:
                with io.open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(base)
            print("退化「%s」⇒ 变红=%s" % (desc, red))
            for ln in out.splitlines():
                if ln.startswith(("FAIL:", "ERROR:")):
                    print("   ", ln)
            ok_all = ok_all and red
    finally:
        shutil.copyfile(os.path.join(BAK, "index.html"), path)
        shutil.rmtree(BAK, ignore_errors=True)
    print("全部退化都能被护栏抓住：%s" % ok_all)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
