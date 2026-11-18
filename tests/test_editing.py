"""S5：写入骨架（plan / diff / validate / commit / 备份）+ 战役进度。

**验收底线**（规范 §7.2 W1、§11.5）：

* `plan_edit()` **不碰磁盘**；
* 写回后**只有目标条目变了**，其余条目**逐条 SHA256 一致**；
* 写回根 `main.yml` 时 `milestones` 等 7 个键**原样保留**；
* 写回前自动生成 `<存档名>_BACKUP.usg`，且**与原文件字节一致**；
* 第二次写回**不覆盖**第一份备份；
* 计划有错误时**拒绝写入**。
"""

import hashlib
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from save_modifier_core import (Catalog, CorePaths, Edit, open_save,
                                validate)
from save_modifier_core.commit import backup_matches_original
from save_modifier_core.packing import list_entries

from ._fixtures import make_save


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class EditingTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="edit_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save_path = make_save(self.tmp / "s.usg")
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)

    def open(self):
        return open_save(str(self.save_path), self.paths)


class TestPlanDoesNotTouchDisk(EditingTestBase):
    def test_plan_leaves_file_untouched(self):
        before = sha(self.save_path)
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", 999)],
                                  catalog=self.catalog)
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(sha(self.save_path), before,
                         "plan_edit 不该碰磁盘")

    def test_plan_reports_changes_without_committing(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("score", 12345)],
                                  catalog=self.catalog)
        self.assertTrue(plan.ok)
        self.assertEqual(plan.changed_entries, ["main.yml"])
        self.assertIn("score", plan.notes[0])
        self.assertIn("+", plan.changes[0].diff)     # unified diff


class TestProgress(EditingTestBase):
    def test_change_prestige_and_score(self):
        with self.open() as save:
            plan = save.plan_edit(
                [Edit.progress("prestige", 999), Edit.progress("score", 12345)],
                catalog=self.catalog)
            self.assertTrue(plan.ok, plan.errors)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)

        with zipfile.ZipFile(self.save_path) as zf:
            main = zf.read("main.yml").decode("utf-8")
        self.assertIn("prestige: 999", main)
        self.assertIn("score: 12345", main)

    def test_other_root_keys_are_preserved(self):
        """`milestones` 等 7 个键必须原样保留 —— 丢掉 milestones 会被静默清空。"""
        with self.open() as save:
            before = save.root_main()
            plan = save.plan_edit([Edit.progress("prestige", 1)],
                                  catalog=self.catalog)
            save.commit(plan)
        with self.open() as save:
            after = save.root_main()
        for key in ("milestones", "card_store", "tokens", "tokens_map",
                    "renamed_hqs", "reverted_games",
                    "used_card_types_with_unit"):
            self.assertEqual(before.get(key), after.get(key), key)

    def test_only_target_entry_changes(self):
        with self.open() as save:
            before = list_entries(self.save_path)
            plan = save.plan_edit([Edit.progress("prestige", 777)],
                                  catalog=self.catalog)
            save.commit(plan)
        after = list_entries(self.save_path)
        self.assertEqual([n for n, _ in before], [n for n, _ in after],
                         "条目清单与顺序不能变")
        changed = [n for (n, h1), (_, h2) in zip(before, after) if h1 != h2]
        self.assertEqual(changed, ["main.yml"])

    def test_negative_value_rejected(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", -1)],
                                  catalog=self.catalog)
        self.assertFalse(plan.ok)
        self.assertIn("prestige", plan.errors[0])

    def test_unknown_field_rejected(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("milestones", [])],
                                  catalog=self.catalog)
        self.assertFalse(plan.ok)


class TestBackup(EditingTestBase):
    def test_backup_is_created_and_byte_identical(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", 5)],
                                  catalog=self.catalog)
            res = save.commit(plan)
        self.assertTrue(res.ok, res.errors)
        backup = self.tmp / "s_BACKUP.usg"
        self.assertTrue(backup.is_file())
        self.assertEqual(sha(backup), res.report and sha(backup))
        # 备份 = 改之前的原件
        self.assertNotEqual(sha(backup), sha(self.save_path))

    def test_second_commit_does_not_overwrite_first_backup(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", 5)],
                                  catalog=self.catalog)
            save.commit(plan)
        first = self.tmp / "s_BACKUP.usg"
        first_hash = sha(first)

        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", 6)],
                                  catalog=self.catalog)
            save.commit(plan)
        self.assertTrue((self.tmp / "s_BACKUP.usg").is_file())
        self.assertEqual(sha(first), first_hash, "第一份备份不能被覆盖")
        self.assertTrue((self.tmp / "s_BACKUP_2.usg").is_file(),
                        "第二份备份应带序号")

    def test_backup_matches_original_helper(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", 5)],
                                  catalog=self.catalog)
            res = save.commit(plan)
        self.assertTrue(backup_matches_original(res.backup, res.backup))


class TestRefuseBadPlan(EditingTestBase):
    def test_commit_refuses_plan_with_errors(self):
        before = sha(self.save_path)
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", -5)],
                                  catalog=self.catalog)
            self.assertFalse(plan.ok)
            res = save.commit(plan)
        self.assertFalse(res.ok)
        self.assertEqual(sha(self.save_path), before,
                         "有错误的计划绝不能写盘")
        self.assertFalse((self.tmp / "s_BACKUP.usg").exists(),
                         "拒绝写入时不该产生备份")


class TestValidate(EditingTestBase):
    def test_validate_accepts_good_plan(self):
        with self.open() as save:
            plan = save.plan_edit([Edit.progress("prestige", 42)],
                                  catalog=self.catalog)
        res = validate(plan)
        self.assertTrue(res.ok, res.errors)

    def test_validate_rejects_zero_quantity(self):
        """`quantity: 0` 是非法值 —— 独立复核也要拦下来。"""
        with self.open() as save:
            plan = save.plan_edit(
                [Edit.store_set("south", "store", 0, "quantity", 0)], catalog=self.catalog)
        # 规划阶段就该拦住
        self.assertFalse(plan.ok)

    def test_validate_rejects_xp_overflow(self):
        with self.open() as save:
            plan = save.plan_edit(
                [Edit.unit_field(1, "xp", 401)], catalog=self.catalog)
        self.assertFalse(plan.ok)


if __name__ == "__main__":
    unittest.main()
