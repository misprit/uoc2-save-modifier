import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from save_modifier_core import paths  # noqa: E402


class ModifierDataPathsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="r2_paths_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.old_appdata = os.environ.get("UOC2_APPDATA")
        self.old_modifier_home = os.environ.get("UOC2_MODIFIER_HOME")
        os.environ["UOC2_APPDATA"] = str(self.tmp / "appdata")
        os.environ["UOC2_MODIFIER_HOME"] = str(self.tmp / "modifier")
        self.addCleanup(self._restore_appdata)

    def _restore_appdata(self):
        if self.old_appdata is None:
            os.environ.pop("UOC2_APPDATA", None)
        else:
            os.environ["UOC2_APPDATA"] = self.old_appdata
        if self.old_modifier_home is None:
            os.environ.pop("UOC2_MODIFIER_HOME", None)
        else:
            os.environ["UOC2_MODIFIER_HOME"] = self.old_modifier_home

    def test_new_paths_are_under_modifier_and_are_pure(self):
        appdata = self.tmp / "appdata"
        modifier = self.tmp / "modifier"
        self.assertEqual(modifier / "data", paths.modifier_data_dir())
        self.assertEqual(modifier / "data" / "imports", paths.modifier_imports_dir())
        self.assertEqual(modifier / "data" / "logs" / "modifier.log", paths.modifier_log_path())
        self.assertEqual(modifier / "data" / "cache" / "edge", paths.modifier_profile_dir())
        self.assertEqual(modifier / "data" / "bak", paths.modifier_fallback_backup_dir())
        self.assertFalse(appdata.exists(), "路径 helper 不应创建真实目录")
        self.assertFalse(modifier.exists(), "路径 helper 不应创建真实目录")

    def test_appdata_override_is_preserved(self):
        self.assertEqual(self.tmp / "appdata", paths.appdata_dir())
        self.assertEqual(self.tmp / "modifier" / "data" / "config" / "modifier_config.json",
                         paths.config_path())

    def test_old_config_is_read_then_new_write_preserves_all_settings(self):
        old = paths.legacy_config_path()
        old.parent.mkdir(parents=True)
        original = {"game_dir": str(self.tmp / "game"), "ui_language": "zh-CN",
                    "future_setting": {"enabled": True}}
        old.write_text(json.dumps(original), encoding="utf-8")

        self.assertEqual(original, paths.read_config())
        updated = paths.read_config()
        updated["ui_language"] = "en"
        written = paths.write_config(updated)

        self.assertEqual(paths.config_path(), written)
        self.assertEqual(updated, json.loads(written.read_text(encoding="utf-8")))
        self.assertEqual(json.dumps(original), old.read_text(encoding="utf-8"))
        self.assertTrue(old.is_file(), "旧副本应保留，供未来用户触发迁移")

    def test_new_config_wins_over_old_config(self):
        old = paths.legacy_config_path()
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps({"source": "old"}), encoding="utf-8")
        new = paths.config_path()
        new.parent.mkdir(parents=True)
        new.write_text(json.dumps({"source": "new"}), encoding="utf-8")
        self.assertEqual({"source": "new"}, paths.read_config())

    def test_server_writes_new_log_path(self):
        from save_modifier_web import server
        self.assertEqual(paths.modifier_log_path(), server._log_path())
        server._log("r2")
        self.assertEqual("r2\n", paths.modifier_log_path().read_text(encoding="utf-8"))
        self.assertFalse(paths.legacy_log_path().exists())

    def test_server_writes_new_import_path(self):
        import base64
        from save_modifier_web import server
        raw = b"PK\x03\x04test"
        result = server.api_import_save({
            "name": "sample.usg", "data": base64.b64encode(raw).decode("ascii")})
        self.assertTrue(result["ok"], result)
        self.assertEqual(paths.modifier_imports_dir(), Path(result["path"]).parent)
        self.assertTrue(Path(result["path"]).is_file())
        self.assertFalse(paths.legacy_imports_dir().exists())

    def test_server_accepts_old_import_path_for_reading(self):
        from save_modifier_web import server
        old = paths.legacy_imports_dir()
        old.mkdir(parents=True)
        imported = old / "old.usg"
        imported.write_bytes(b"old")
        self.assertEqual(str(imported.resolve()), server._save_id_checked(str(imported)))

    def test_legacy_read_helpers_are_separate_and_non_mutating(self):
        appdata = self.tmp / "appdata"
        self.assertEqual(appdata / "modifier_imports", paths.legacy_imports_dir())
        self.assertEqual(appdata / "modifier" / "modifier_imports", paths.legacy_modifier_imports_dir())
        self.assertEqual(appdata / "modifier.log", paths.legacy_log_path())
        self.assertEqual(appdata / "modifier" / "modifier.log", paths.legacy_modifier_log_path())
        self.assertEqual(appdata / "edge_profile", paths.legacy_profile_dir())
        self.assertEqual(appdata / "modifier" / "edge_profile", paths.legacy_modifier_profile_dir())
        self.assertEqual((paths.modifier_imports_dir(), paths.legacy_modifier_imports_dir(), paths.legacy_imports_dir()), paths.import_roots())
        self.assertFalse(appdata.exists())


if __name__ == "__main__":
    unittest.main()
