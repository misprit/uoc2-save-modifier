import json
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer

from save_modifier_web import backup_cleanup, server


class _FakeSave:
    path = "fake-save.usg"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class BackupRecycleApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "r1-api-token"
        server._Handler.token = cls.token
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server._Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def post(self, body, token=True):
        req = urllib.request.Request(
            self.url + "/api/backups/recycle",
            data=json.dumps(body).encode("utf-8"), method="POST")
        if token:
            req.add_header("X-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_token_protection(self):
        status, body = self.post({"save_id": "west.usg", "ids": ["1." + "a" * 64]}, token=False)
        self.assertEqual(403, status)
        self.assertEqual("token 无效", body["error"])

    def test_strict_input_rejected_before_open_or_recycle(self):
        bad = [
            {},
            {"save_id": "west.usg", "ids": []},
            {"save_id": "west.usg", "ids": "x"},
            {"save_id": "west.usg", "ids": ["1." + "a" * 64] * 2},
            {"save_id": "west.usg", "ids": ["../outside"]},
            {"save_id": "west.usg", "ids": [1]},
            {"save_id": "west.usg", "ids": ["1." + "a" * 64], "extra": 1},
        ]
        with patch.object(server, "_backup_cleanup") as service, patch.object(server, "_save_id_checked") as checked:
            for payload in bad:
                with self.subTest(payload=payload):
                    status, body = self.post(payload)
                    self.assertEqual(400, status)
                    self.assertFalse(body["ok"])
            checked.assert_not_called()
            service.recycle_one.assert_not_called()

    def test_partial_success_stops_and_reports_unattempted(self):
        ids = ["1." + c * 64 for c in "abc"]
        fake = Mock()
        fake.recycle_one.side_effect = [None, ValueError("expired")]
        with patch.object(server, "_backup_cleanup", fake), patch.object(server, "_save_id_checked", return_value="safe.usg"):
            with patch("save_modifier_core.open_save", return_value=_FakeSave()):
                status, body = self.post({"save_id": "west.usg", "ids": ids})
        self.assertEqual(200, status)
        self.assertEqual({"ok": False, "completed": ids[:1], "failed": ids[1],
                          "remaining": ids[2:], "errors": ["expired"]}, body)
        self.assertEqual([(("fake-save.usg", ids[0]), {}), (("fake-save.usg", ids[1]), {})],
                         fake.recycle_one.call_args_list)

    def test_expired_is_failure_not_success(self):
        item = "1." + "a" * 64
        fake = Mock()
        fake.recycle_one.side_effect = backup_cleanup.BackupCleanupError("预览过期，请刷新")
        with patch.object(server, "_backup_cleanup", fake), patch.object(server, "_save_id_checked", return_value="safe.usg"):
            with patch("save_modifier_core.open_save", return_value=_FakeSave()):
                status, body = self.post({"save_id": "west.usg", "ids": [item]})
        self.assertEqual(200, status)
        self.assertFalse(body["ok"])
        self.assertEqual([], body["completed"])
        self.assertEqual(item, body["failed"])
        self.assertEqual([], body["remaining"])


if __name__ == "__main__":
    unittest.main()
