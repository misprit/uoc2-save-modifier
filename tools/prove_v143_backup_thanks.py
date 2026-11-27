# -*- coding: utf-8 -*-
"""v1.4.3 护栏的反证：把修复改坏 ⇒ 对应测试必须红在目标断言上。

四个退化点：
① 备份闸门改回「`bak/` 落在存档目录里就整个跳过」⇒ 「程序在存档目录里也能列备份」必须红；
② 备份闸门去掉「程序专属 bak 豁免」⇒ 上面那条也要红（同一个退化，从另一头拆）；
③ 把人名塞进 i18n 词表 ⇒ 「人名不在词表里」必须红；
④ 去掉人名的 `NO_TRANS` 白名单 ⇒ 「人名在白名单里」必须红。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
CLEANUP = os.path.join(ROOT, "src", "save_modifier_web", "backup_cleanup.py")
I18N = os.path.join(ROOT, "src", "save_modifier_web", "web", "i18n.json")
AUDIT = os.path.join(ROOT, "tools", "i18n_audit.py")
BAK = os.path.join(ROOT, ".scratch", "bak_v143")

CASES = [
    # (说明, 文件, 原文, 改坏后, 目标测试)
    ("备份闸门改回「bak 落在存档目录里就整个跳过」",
     CLEANUP,
     """    own_backup_dir = (core_paths.modifier_home()
                      / core_paths.BACKUP_DIR_NAME).absolute()
    is_own_backup_dir = (root == own_backup_dir)
    if not is_own_backup_dir and (
            root.is_relative_to(core_paths.fallback_backup_dir().absolute())
            or any(root.is_relative_to(folder) for folder in sources)):
        return""",
     """    if (root.is_relative_to(core_paths.fallback_backup_dir().absolute())
            or any(root.is_relative_to(folder) for folder in sources)):
        return""",
     "tests.test_backup_dir_in_save_root.TestBackupDirInsideSaveRoot."
     "test_backups_are_listed_when_modifier_sits_inside_save_root"),

    ("把「IQ180 的学生会会计」塞进 i18n 词表（名字会被翻译）",
     I18N,
     '  "特别鸣谢": "Special thanks to",\n',
     '  "特别鸣谢": "Special thanks to",\n'
     '  "IQ180 的学生会会计": "the student union accountant of IQ180",\n',
     "tests.test_v143_thanks_name.TestThanksNameNotTranslated."
     "test_name_is_not_in_the_i18n_table"),

    ("去掉人名的 NO_TRANS 白名单（审计会把它当漏译）",
     AUDIT,
     'NO_TRANS = ("烟柳边城", "IQ180 的学生会会计")',
     'NO_TRANS = ("烟柳边城",)',
     "tests.test_v143_thanks_name.TestThanksNameNotTranslated."
     "test_name_is_in_the_no_translate_whitelist"),
]


def run_target(target):
    code = ("import sys, unittest; sys.path.insert(0, %r); "
            "unittest.main(module=None, argv=['x', %r], exit=True)" % (ROOT, target))
    r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    name = target.rsplit(".", 1)[1]
    red = (name in out and ("FAIL:" in out or "ERROR:" in out))
    return red, out


def main():
    os.makedirs(BAK, exist_ok=True)
    originals = {}
    for path in (CLEANUP, I18N, AUDIT):
        originals[path] = io.open(path, encoding="utf-8", newline="").read()
        shutil.copyfile(path, os.path.join(BAK, os.path.basename(path)))
    ok_all = True
    try:
        for desc, path, old, new, target in CASES:
            src = originals[path]
            if src.count(old) != 1:
                print("跳过（锚点命中 %d 次）：%s" % (src.count(old), desc))
                ok_all = False
                continue
            with io.open(path, "w", encoding="utf-8", newline="") as f:
                f.write(src.replace(old, new))
            try:
                red, out = run_target(target)
            finally:
                with io.open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(src)
            print("退化「%s」⇒ 变红=%s" % (desc, red))
            for ln in out.splitlines():
                if ln.startswith(("FAIL:", "ERROR:")):
                    print("   ", ln)
            ok_all = ok_all and red
    finally:
        for path, text in originals.items():
            with io.open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        shutil.rmtree(BAK, ignore_errors=True)
    print("全部退化都能被护栏抓住：%s" % ok_all)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
