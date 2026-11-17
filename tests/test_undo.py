"""S10：撤销栈。

**验收底线**（规范 §6.4.2、§10 第 58 条、§12 验收清单）：

* 撤销栈**落盘**在存档旁边（`<存档名>.undo.json`）—— 关掉程序仍能撤；
* 撤销粒度是**一次 commit** —— 一次改了 3 个单位就一起撤销；
* 撤销走的是**和 commit 完全相同的写回流程**（备份 → 校验 → 原子替换）；
* **基准过期时拒绝撤销**并明确提示，不硬改；
* 撤销栈与游戏内回退互不干扰（游戏内回退会让基准过期 → 拒绝）。
"""

import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from save_modifier_core import Catalog, CorePaths, Edit, open_save
from save_modifier_core.packing import list_entries, repack_overlay
from save_modifier_core.undo import (MAX_RECORDS, load_stack, peek,
                                     stack_path_for)

from ._fixtures import make_save


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class UndoTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="undo_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def open(self):
        return open_save(str(self.save_path), self.paths)

    def commit(self, edits):
        """提交一批编辑，返回 CommitResult。"""
        with self.open() as save:
            plan = save.plan_edit(edits, catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        return res

    def entries(self) -> list[tuple[str, str]]:
        return list_entries(self.save_path)


class TestStackIsPersisted(UndoTestBase):
    def test_commit_creates_undo_file_next_to_save(self):
        self.commit([Edit.progress("prestige", 999)])
        stack = stack_path_for(self.save_path)
        self.assertTrue(stack.is_file(), "撤销栈必须落盘在存档旁边")
        self.assertEqual(stack.name, "s.undo.json")
        # 游戏只扫 *.usg —— .undo.json 不会被当成存档
        self.assertFalse(stack.suffix == ".usg")

    def test_stack_file_is_valid_json_with_one_record(self):
        self.commit([Edit.progress("prestige", 999)])
        data = json.loads(stack_path_for(self.save_path).read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["records"]), 1)
        rec = data["records"][0]
        self.assertEqual([e["entry"] for e in rec["entries"]], ["main.yml"])
        self.assertIn("prestige", rec["summary"])

    def test_stack_survives_reopen(self):
        """关掉程序再打开 —— 撤销仍然可用。"""
        self.commit([Edit.progress("prestige", 999)])
        # 换一个进程/实例重新打开
        with self.open() as save:
            self.assertTrue(save.undo_available())
            self.assertIsNotNone(save.undo_peek())

    def test_broken_stack_file_is_reported_not_swallowed(self):
        stack = stack_path_for(self.save_path)
        stack.write_text("{ 这不是 JSON", encoding="utf-8")
        records, errs = load_stack(self.save_path)
        self.assertEqual(records, [])
        self.assertTrue(errs, "坏掉的撤销栈必须报错，不能静默吞掉")


class TestUndoRestores(UndoTestBase):
    def test_undo_returns_to_pre_commit_state(self):
        before = self.entries()
        self.commit([Edit.progress("prestige", 999), Edit.progress("score", 1)])
        with self.open() as save:
            res = save.undo()
        self.assertTrue(res.ok, res.errors)
        after = self.entries()
        self.assertEqual(before, after, "撤销后每一条内容都必须精确回到改前")

    def test_undo_restores_only_changed_entries(self):
        before = dict(self.entries())
        self.commit([Edit.progress("prestige", 999)])
        with self.open() as save:
            save.undo()
        after = dict(self.entries())
        changed = [n for n in before if before[n] != after[n]]
        self.assertEqual(changed, [], "撤销不该动任何条目")

    def test_undo_also_makes_a_backup(self):
        """撤销走的是**完整写回流程** —— 也要有备份。"""
        self.commit([Edit.progress("prestige", 999)])
        with self.open() as save:
            res = save.undo()
        self.assertTrue(res.ok, res.errors)
        self.assertIsNotNone(res.backup)
        self.assertTrue(res.backup.is_file())
        self.assertEqual(res.backup.name, "s_BACKUP_2.usg")

    def test_undo_pops_the_stack(self):
        self.commit([Edit.progress("prestige", 999)])
        with self.open() as save:
            self.assertTrue(save.undo_available())
            save.undo()
            self.assertFalse(save.undo_available())
            res = save.undo()
        self.assertTrue(res.nothing_to_do)
        self.assertFalse(res.ok)

    def test_undo_of_empty_stack_is_not_an_error(self):
        with self.open() as save:
            res = save.undo()
        self.assertTrue(res.nothing_to_do)
        self.assertIn("没有可撤销", res.summary())


class TestUndoGranularity(UndoTestBase):
    def test_one_commit_undoes_all_three_units_at_once(self):
        """一次改了 3 个单位 → 一次撤销全回退（粒度 = 一次 commit）。"""
        before = self.entries()
        self.commit([
            Edit.unit_field(1, "xp", 120),
            Edit.unit_field(2, "xp", 130),
            Edit.unit_field(2, "act_st", 5),
        ])
        with self.open() as save:
            res = save.undo()
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(before, self.entries())

    def test_multi_step_undo_is_lifo(self):
        """两次提交 → 撤两次 → 回到最初；每次撤一层。"""
        original = self.entries()
        self.commit([Edit.progress("prestige", 111)])
        after_first = self.entries()
        self.commit([Edit.progress("prestige", 222)])
        self.assertNotEqual(after_first, self.entries())

        with self.open() as save:
            res = save.undo()
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(after_first, self.entries(), "第一次撤销应回到第一次提交后")

        with self.open() as save:
            res = save.undo()
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(original, self.entries(), "第二次撤销应回到最初")


class TestBaselineGuard(UndoTestBase):
    def test_undo_refused_when_save_changed_after_commit(self):
        """基准过期 ⇒ 拒绝撤销并明确提示（§10 第 58 条）。"""
        self.commit([Edit.progress("prestige", 999)])

        # 模拟玩家在游戏里手动改了同一个存档
        raw = zipfile.ZipFile(self.save_path).read("main.yml").decode("utf-8")
        hacked = raw.replace("prestige: 999", "prestige: 12345")
        tmp = self.tmp / "hacked.usg"
        repack_overlay(self.save_path, {"main.yml": hacked.encode("utf-8")}, tmp)
        shutil.copy2(tmp, self.save_path)

        with self.open() as save:
            res = save.undo()
        self.assertFalse(res.ok, "基准过期必须拒绝撤销")
        self.assertTrue(any("基准" in e for e in res.errors), res.errors)
        # 存档不能被硬改回去
        with zipfile.ZipFile(self.save_path) as zf:
            self.assertIn("prestige: 12345", zf.read("main.yml").decode("utf-8"))

    def test_undo_refused_when_entry_removed(self):
        self.commit([Edit.progress("prestige", 999)])
        rec = peek(self.save_path)
        self.assertIsNotNone(rec)
        # 手工把栈里那条记录的基准改坏 —— 模拟"存档被换掉了"
        stack = stack_path_for(self.save_path)
        data = json.loads(stack.read_text(encoding="utf-8"))
        data["records"][0]["entries"][0]["after_sha256"] = "0" * 64
        stack.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with self.open() as save:
            res = save.undo()
        self.assertFalse(res.ok)
        self.assertTrue(any("对不上" in e for e in res.errors), res.errors)

    def test_stack_survives_rejected_undo(self):
        """拒绝之后栈不能被弹掉 —— 否则玩家就永远撤不回来了。"""
        self.commit([Edit.progress("prestige", 999)])
        stack = stack_path_for(self.save_path)
        data = json.loads(stack.read_text(encoding="utf-8"))
        data["records"][0]["entries"][0]["after_sha256"] = "0" * 64
        stack.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with self.open() as save:
            save.undo()
        records, _ = load_stack(self.save_path)
        self.assertEqual(len(records), 1, "拒绝撤销不该弹栈")


class TestStackLimit(UndoTestBase):
    def test_stack_is_capped(self):
        """栈只保留最近 N 条 —— 不能无限长。"""
        for i in range(MAX_RECORDS + 3):
            self.commit([Edit.progress("prestige", 1000 + i)])
        records, _ = load_stack(self.save_path)
        self.assertLessEqual(len(records), MAX_RECORDS)


class TestStalePlanGuard(UndoTestBase):
    def test_commit_refused_when_save_changed_after_planning(self):
        """规划之后存档被别人改了 ⇒ 拒绝写入，别把人家的改动覆盖掉。"""
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", 999)],
                                  catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)

            # 模拟规划之后玩家在游戏里动过这个存档
            raw = zipfile.ZipFile(self.save_path).read("main.yml").decode("utf-8")
            hacked = raw.replace("prestige: 320", "prestige: 321")
            tmp = self.tmp / "hacked.usg"
            repack_overlay(self.save_path,
                           {"main.yml": hacked.encode("utf-8")}, tmp)
            shutil.copy2(tmp, self.save_path)

            res = save.commit(plan)
        self.assertFalse(res.ok, "存档被改动后必须拒绝写入")
        self.assertTrue(any("被改动过" in e for e in res.errors), res.errors)


if __name__ == "__main__":
    unittest.main()
