# -*- coding: utf-8 -*-
"""U76：**发布前自检** —— 一条命令跑完发版前该验的东西。

```
.\\python\\python.exe tools\\release_check.py            # 默认全套（不含干净环境测试）
.\\python\\python.exe tools\\release_check.py --clean    # 额外跑「无游戏环境」的随包测试
```

**为什么要有这个**：发版前要验的东西散在几个地方（打包自检 / 真实存档演练 / 版本号一致性），
每次靠回忆会漏。本脚本把它们收成一份**可重复**的检查单。

⚠️ 真实存档那一项**只在副本上做**（复制到临时目录再改）⇒ **不碰玩家存档**。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = REPO / "python" / "python.exe"
DIST = REPO / "dist"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    print("%s %s%s" % ("[OK ]" if ok else "[NG ]", name,
                       ("  —— " + detail) if detail else ""))
    return ok


def _version() -> str:
    src = (REPO / "src" / "save_modifier_web" / "version.py").read_text(encoding="utf-8")
    import re
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', src, re.M)
    return m.group(1) if m else "?"


# ---------------------------------------------------------------- ① 仓库状态
def step_git():
    r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True)
    dirty = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    check("仓库工作区干净", not dirty,
          ("有 %d 处未提交：%s" % (len(dirty), dirty[:3])) if dirty else "")


# ---------------------------------------------------------------- ② 打包产物
MUST_IN_ZIP = [
    "uoc2-save-modifier/run.bat",
    "uoc2-save-modifier/run_web.bat",
    "uoc2-save-modifier/统一指挥2存档修改器.exe",   # U80 启动器（放包根）
    "uoc2-save-modifier/run_tests.bat",
    "uoc2-save-modifier/使用说明.txt",
    "uoc2-save-modifier/src/save_modifier_core/__init__.py",
    "uoc2-save-modifier/src/save_modifier_core/data/campaign_index.json",
    "uoc2-save-modifier/src/save_modifier_web/web/index.html",
    "uoc2-save-modifier/src/save_modifier_web/web/i18n.json",
    "uoc2-save-modifier/src/save_modifier_web/version.py",
    "uoc2-save-modifier/python/python314.zip",
    "uoc2-save-modifier/python/Lib/site-packages/yaml/__init__.py",
]


def step_zip():
    ver = _version()
    zp = DIST / ("uoc2-save-modifier-v%s.zip" % ver)
    if not zp.is_file():
        check("成品 zip 存在（v%s）" % ver, False, "没找到 %s" % zp.name)
        return
    with zipfile.ZipFile(zp) as z:
        names = set(z.namelist())
        bad = z.testzip()
        missing = [m for m in MUST_IN_ZIP if m not in names]
    check("成品 zip 完整（%s，%.1f MB）" % (zp.name, zp.stat().st_size / 1048576.0),
          bad is None and not missing,
          ("损坏：%s" % bad) if bad else (("缺：%s" % missing) if missing else ""))
    step_zip_fresh(zp)


def step_zip_fresh(zp):
    """**包里的东西是不是当前的？** —— 逐字节比（U100）。

    ⚠️ 原来的第②项只验「文件齐全 + 没损坏」⇒ **旧包照样报 OK**
    （2026-11-20 实测：09:58 打的旧包四项全绿，包里却没有 U89 之后的改动）。
    ⇒ 这里把 zip 里每个条目与工作区同名文件逐字节比一遍。

    * 只比**仓库里存在**的那些（zip 里多出来的构建残留不算不一致）；
    * zip 里没有、工作区有的 ⇒ 也算不一致（漏打）。
    """
    prefix = "uoc2-save-modifier/"
    diff: list[str] = []
    checked = 0
    with zipfile.ZipFile(zp) as z:
        for name in z.namelist():
            if name.endswith("/") or not name.startswith(prefix):
                continue
            rel = name[len(prefix):]
            f = REPO / rel
            if not f.is_file():
                continue                      # 仓库里没有的（构建残留）⇒ 不管
            try:
                a = z.read(name)
            except KeyError:
                continue
            try:
                b = f.read_bytes()
            except OSError:
                diff.append(rel + "（读不到）")
                continue
            checked += 1
            if hashlib.sha256(a).digest() != hashlib.sha256(b).digest():
                diff.append(rel)
    check("成品 zip 与当前代码**逐字节一致**", not diff,
          ("%d/%d 个文件不同：%s" % (len(diff), checked, "、".join(diff[:5])))
          if diff else "比对 %d 个文件，全一致" % checked)
    _check_not_missing(zp)


def _check_not_missing(zp):
    """**漏打检测**：工作区里有、包里没有的文件。

    ⚠️ 不自己实现打包规则 —— 直接用 `build_dist.collect()`（打包脚本自己的清单），
    否则两份规则迟早对不上（U100 就是只做了内容比对，漏打查不出来）。
    """
    try:
        sys.path.insert(0, str(REPO / "tools"))
        import build_dist
        expected = {entry for _, entry in build_dist.collect()}
    except Exception as e:      # 打包脚本自己坏了 ⇒ 报出来，别静默放过
        check("成品 zip **没漏打**文件", False, "打包规则算不出来：%s" % e)
        return
    with zipfile.ZipFile(zp) as z:
        names = set(z.namelist())
    missing = sorted(expected - names)
    check("成品 zip **没漏打**文件", not missing,
          ("应进包但没进：%s" % "、".join(missing[:5])) if missing
          else "应进包 %d 个文件，全在包里" % len(expected))


# ---------------------------------------------------------------- ③ 真实存档演练
def step_real_save():
    """复制一个真实存档 ⇒ 改 ⇒ 写回 ⇒ 撤销 ⇒ **逐条比对**（不碰原存档）。"""
    sys.path.insert(0, str(REPO / "src"))
    from save_modifier_core import Catalog, CorePaths, Edit, open_save
    from save_modifier_core.packing import list_entries

    paths = CorePaths.discover()
    cands: list[Path] = []
    for sub in ("campaigns", "games"):
        d = paths.save_root / sub
        if d.is_dir():
            cands += sorted(d.glob("*.usg"))
    if not cands:
        check("真实存档写回 + 撤销演练", True, "本机没有存档 ⇒ 跳过（没法验）")
        return
    src = max(cands, key=lambda p: p.stat().st_size)
    tmp = Path(tempfile.mkdtemp(prefix="release_check_"))
    dst = tmp / "check.usg"
    shutil.copy2(src, dst)
    # U109：备份改放 `<修改器目录>/bak/` ⇒ 演练时指到临时目录
    # （别在仓库里留一个 bak/ 目录出来）。
    os.environ["UOC2_BAK_DIR"] = str(tmp / "bak")
    cat = Catalog(paths)
    before = list_entries(dst)
    t0 = time.time()
    try:
        with open_save(str(dst), paths) as s:
            v = s.view(cat)
            n_units = len(v.units)
            plan = s.plan_edit([Edit.progress("prestige", 999)], catalog=cat)
            if not plan.ok:
                check("真实存档写回 + 撤销演练", False, "规划失败：%s" % plan.errors[:2])
                return
            res = s.commit(plan)
        t_commit = time.time() - t0
        if not res.ok:
            check("真实存档写回 + 撤销演练", False, "写回失败：%s" % res.errors[:2])
            return
        with open_save(str(dst), paths) as s:
            r = s.undo()
        after = list_entries(dst)
        ok = bool(getattr(r, "ok", False)) and before == after
        check("真实存档写回 + 撤销演练（副本）", ok,
              "%s：%d 单位 / %d 总部；打开+写回 %.1fs；撤销后逐条%s"
              % (src.name, n_units, len(v.hqs), t_commit,
                 "一致 ✓" if before == after else "不一致 ✗"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- ④ 干净环境随包测试
def step_clean_tests():
    """没有游戏、没有存档的机器上，随包测试**必须不红**。"""
    tmp = Path(tempfile.mkdtemp(prefix="release_clean_"))
    try:
        env = dict(os.environ)
        env["UOC2_APPDATA"] = str(tmp / "appdata")
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run([str(PY), "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                           cwd=REPO, capture_output=True, env=env, timeout=1800)
        txt = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
        summary = [l for l in txt.splitlines()
                   if l.startswith("Ran ") or l.startswith("OK") or l.startswith("FAILED")]
        check("随包测试在**无游戏环境**下不红", r.returncode == 0, " | ".join(summary[-2:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    print("=" * 66)
    print("发布前自检（v%s）" % _version())
    print("=" * 66)
    step_git()
    step_zip()
    step_real_save()
    if "--clean" in argv:
        step_clean_tests()
    ng = [n for n, ok, _ in RESULTS if not ok]
    print("-" * 66)
    if ng:
        print("未通过 %d 项：%s" % (len(ng), "；".join(ng)))
        return 1
    print("全部通过（%d 项）" % len(RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
