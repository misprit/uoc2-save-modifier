# -*- coding: utf-8 -*-
"""U133：护栏 —— 写盘**不许并发**（唯一临时名 + 互斥锁）—— 外部审阅报告 P1-3。

**漏洞**

`writer.py::write_overlay` 的临时文件是**固定名** `<存档名>.usg.new`
⇒ 两个写盘同时进行（服务端是多线程的 ⇒ 玩家连点两下「应用更改」）
就**写进同一个文件** ⇒ 互相踩 ⇒ 存档可能损坏。

⇒ ① 临时文件名**唯一**（进程号 + 随机串）；
   ② 整个写盘流程在**互斥锁**里（`<存档名>.usg.lock`，不是 `*.usg` ⇒ 游戏看不到）。

**这些测试守着**

① 临时名**每次都不同**，且**不以 `.usg` 结尾**（游戏不会把它当存档）；
② 锁被占着时 ⇒ 写盘**直接失败**（不碰存档）；
③ 陈旧的锁（进程崩了留下的）⇒ 可以**接管**（不许把玩家永久锁死）；
④ 写完之后**不留** `.new` / `.lock` 残留。
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SRC = os.path.join(REPO, "src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from save_modifier_core import paths as core_paths  # noqa: E402
from save_modifier_core.writer import (_SaveLock, _temp_path_for,  # noqa: E402
                                       write_overlay)

from ._fixtures import make_save  # noqa: E402


class TempNameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u133_tmp_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")

    def test_the_temp_name_is_unique(self):
        a = _temp_path_for(self.save_path)
        b = _temp_path_for(self.save_path)
        self.assertNotEqual(a, b, "临时文件名不能固定（并发写盘会撞车）")

    def test_the_temp_name_is_not_a_save(self):
        """游戏只扫 `*.usg` ⇒ 临时文件**不能**以 `.usg` 结尾。"""
        p = _temp_path_for(self.save_path)
        self.assertFalse(p.name.endswith(".usg"),
                         "临时文件不能以 .usg 结尾（游戏会把它当存档）")
        self.assertTrue(p.name.endswith(".new"))

    def test_the_temp_file_lives_next_to_the_save(self):
        p = _temp_path_for(self.save_path)
        self.assertEqual(self.tmp, p.parent)


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u133_lock_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")

    def test_a_second_write_is_refused(self):
        """⭐ 锁被占着 ⇒ 写盘**直接失败**（存档一个字节都不动）。"""
        lock = _SaveLock(self.save_path)
        lock.acquire()
        self.addCleanup(lock.release)
        before = self.save_path.read_bytes()
        res = write_overlay(self.save_path, {"main.yml": b"prestige: 1\n"})
        self.assertFalse(res.ok, "有别的写盘在进行时，不该写成功")
        self.assertTrue(any("写入" in e for e in res.errors),
                        "错误里要说清是「正在被写入」：%r" % res.errors)
        self.assertEqual(before, self.save_path.read_bytes(),
                         "存档被动过了")

    def test_the_lock_is_released_afterwards(self):
        lock = _SaveLock(self.save_path)
        lock.acquire()
        lock.release()
        self.assertFalse(lock.path.exists(), "锁文件没删掉")

    def test_a_stale_lock_can_be_taken_over(self):
        """进程崩了会留下锁文件 ⇒ 太老的锁要能**接管**（不许永久锁死）。"""
        # 模拟「进程崩了 ⇒ 锁文件留在那儿」（**没人打开它**）
        lock = _SaveLock(self.save_path, stale_after=1.0)
        lock.path.write_text("999", encoding="utf-8")
        old = time.time() - 3600
        os.utime(str(lock.path), (old, old))
        lock.acquire()          # 不该抛异常
        lock.release()

    def test_the_lock_file_is_not_a_save(self):
        lock = _SaveLock(self.save_path)
        lock.acquire()
        self.addCleanup(lock.release)
        self.assertFalse(lock.path.name.endswith(".usg"),
                         "锁文件不能以 .usg 结尾（游戏会把它当存档）")


class WriteCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="u133_clean_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self._old_bak = os.environ.get("UOC2_BAK_DIR")
        os.environ["UOC2_BAK_DIR"] = str(self.tmp / "bak")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._old_bak is None:
            os.environ.pop("UOC2_BAK_DIR", None)
        else:
            os.environ["UOC2_BAK_DIR"] = self._old_bak

    def test_no_leftovers_after_a_successful_write(self):
        res = write_overlay(self.save_path, {"main.yml": b"prestige: 7\n"})
        self.assertTrue(res.ok, res.errors)
        leftovers = [p.name for p in self.tmp.iterdir()
                     if p.name.endswith(".new") or p.name.endswith(".lock")]
        self.assertEqual([], leftovers, "写完还留着临时文件/锁：%r" % leftovers)

    def test_the_save_is_still_a_valid_zip(self):
        res = write_overlay(self.save_path, {"main.yml": b"prestige: 7\n"})
        self.assertTrue(res.ok, res.errors)
        with zipfile.ZipFile(self.save_path) as zf:
            self.assertIn("main.yml", zf.namelist())


if __name__ == "__main__":
    unittest.main()
