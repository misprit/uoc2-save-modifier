# -*- coding: utf-8 -*-
"""准备一次安全的实测：把真存档**复制成测试副本**放进游戏存档目录。

为什么要复制而不是直接改原档：
* 修改器写盘后，游戏读到的必须是**同一个文件**，改副本、在游戏里才看得到效果；
* 但直接改原档有风险 ⇒ 所以复制成 `*-test.usg`，**原档一个字节都不动**。

放哪：`%LOCALAPPDATA%\\.uoc2\\save\\campaigns\\`（游戏只扫 `campaigns` 与 `games`
两个目录 ⇒ 放进去游戏就能在存档列表里看到）。

用法：
    python tools/prepare_test_run.py            # 复制（默认：3 个战役档）
    python tools/prepare_test_run.py --clean    # 删掉这些测试副本
    python tools/prepare_test_run.py --list     # 只看现状
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

APP_DIR = ".uoc2"
SAVE_DIRNAME = "save"
SUFFIX = "-test.usg"


def save_root() -> str:
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local, APP_DIR, SAVE_DIRNAME)


def campaigns_dir(root: str) -> str:
    return os.path.join(root, "campaigns")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true", help="删掉所有 *-test.usg")
    ap.add_argument("--list", action="store_true", help="只列出现状")
    ap.add_argument("--only", default="", help="只处理这些名字（逗号分隔，不含扩展名）")
    args = ap.parse_args()

    root = save_root()
    camp = campaigns_dir(root)
    if not os.path.isdir(camp):
        print("找不到存档目录：%s" % camp)
        return 1

    tests = [f for f in os.listdir(camp) if f.endswith(SUFFIX)]

    if args.clean:
        for f in tests:
            p = os.path.join(camp, f)
            os.remove(p)
            print("已删除测试副本：%s" % f)
        print("清理完成（共 %d 个）" % len(tests))
        return 0

    if args.list:
        print("存档目录：%s" % camp)
        for f in sorted(os.listdir(camp)):
            if f.endswith(".usg"):
                print("  %s%s" % (f, "（测试副本）" if f.endswith(SUFFIX) else ""))
        return 0

    want = [x.strip() for x in args.only.split(",") if x.strip()]
    made = 0
    for f in sorted(os.listdir(camp)):
        if not f.endswith(".usg") or f.endswith(SUFFIX):
            continue
        stem = f[:-4]
        if want and stem not in want:
            continue
        src = os.path.join(camp, f)
        dst = os.path.join(camp, stem + SUFFIX)
        shutil.copy2(src, dst)
        print("已复制测试副本：%s  （%d 字节）" % (os.path.basename(dst),
                                           os.path.getsize(dst)))
        made += 1
    if made == 0:
        print("没有复制任何文件（用 --only 指定名字，或看看 --list 的输出）")
    print("\n提示：游戏与修改器都能看到这些副本；测完用 --clean 删掉。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
