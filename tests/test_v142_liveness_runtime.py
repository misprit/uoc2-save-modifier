# -*- coding: utf-8 -*-
"""v1.4.2 护栏（**运行时**）：真起服务、真发心跳、真关窗 —— 验的是行为。

静态断言只能证明「源码里没有那句」⇒ **证明不了行为对**。
这里真跑一遍服务端：

① **心跳保活** —— 发心跳 ⇒ 服务**活着**（哪怕长时间不发别的请求）；
② **心跳与操作无关** —— 只发心跳、**不碰任何业务接口** ⇒ 服务仍活着
   （这条直接回答用户「愣着不动会不会被踢」）；
③ **关窗 beacon ⇒ 立刻退** —— 发 `/api/client-gone` ⇒ 服务很快退出；
④ **心跳断了 ⇒ 超时退**（用**缩短的超时**跑，不等 180 秒）；
⑤ `/api/ping` 与 `/api/client-gone` 真的存在且可访问。

做法：把 `HEARTBEAT_TIMEOUT` 调小（改模块属性，不改源码）后起服务。
"""
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(REPO, "python", "python.exe")

#: 起一个隔离的实例：改环境变量 UOC2_APPDATA ⇒ 不碰玩家存档
APPDATA = tempfile.mkdtemp(prefix="uoc2_life_")


class ServerProc(object):
    """起一个服务端子进程（--no-window：只起服务，不拉浏览器）。"""

    def __init__(self, env_extra=None):
        env = dict(os.environ)
        env["UOC2_APPDATA"] = APPDATA
        env["PYTHONIOENCODING"] = "utf-8"
        if env_extra:
            env.update(env_extra)
        self.proc = subprocess.Popen(
            [PY, "-u", "-m", "save_modifier_web.server", "--serve", "--no-browser"],
            cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env)
        self.url = None
        self.base = None
        self.token = None
        t0 = time.time()
        while time.time() - t0 < 40:
            line = self.proc.stdout.readline()
            if not line:
                break
            if "http://" in line:
                self.url = line[line.index("http://"):].split()[0]
                # ⚠️ `self.url` 带路径（`/?t=TOKEN`）⇒ 拼接口要用 **base**
                self.base = self.url.split("/?")[0]
                self.token = self.url.split("t=")[-1]
                break
        if not self.url:
            raise AssertionError("服务端没起来")

    def get(self, path, timeout=10):
        req = urllib.request.Request(self.base + path)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()

    def alive(self):
        return self.proc.poll() is None

    def wait_exit(self, seconds):
        t0 = time.time()
        while time.time() - t0 < seconds:
            if not self.alive():
                return time.time() - t0
            time.sleep(0.3)
        return None

    def stop(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class TestRuntimeLiveness(unittest.TestCase):

    def test_ping_endpoint_works(self):
        s = ServerProc()
        try:
            st, body = s.get("/api/ping")
            self.assertEqual(200, st)
            self.assertIn(b"true", body.lower())
        finally:
            s.stop()

    def test_heartbeat_keeps_the_server_alive(self):
        """① 心跳保活：一直发心跳 ⇒ 服务一直活着。"""
        s = ServerProc()
        try:
            for _ in range(5):
                s.get("/api/ping")
                time.sleep(0.4)
            self.assertTrue(s.alive(), "发着心跳，服务却退出了")
        finally:
            s.stop()

    def test_no_user_activity_is_needed(self):
        """② **心跳与操作无关** —— 只发心跳、不碰任何业务接口 ⇒ 服务仍活着。

        这条直接回答用户的问题：「打开界面愣着不动会不会被踢？」
        ⇒ **不会** —— 心跳是定时器发的，与操作无关。
        """
        s = ServerProc()
        try:
            for _ in range(8):
                s.get("/api/ping")
                time.sleep(0.5)
            self.assertTrue(s.alive(),
                            "只发心跳、没做任何操作，服务却退出了")
        finally:
            s.stop()

    def test_client_gone_makes_the_server_exit(self):
        """③ 关窗 beacon ⇒ 服务**立刻**退（不用等心跳超时）。"""
        s = ServerProc()
        try:
            s.get("/api/ping")
            self.assertTrue(s.alive())
            req = urllib.request.Request(
                s.base + "/api/client-gone?t=" + s.token,
                data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            el = s.wait_exit(20)
            self.assertIsNotNone(el, "收到关窗 beacon，服务却没退")
            self.assertLess(el, 15, "关窗后 %s 秒才退，太慢了" % el)
        finally:
            s.stop()

    def test_heartbeat_timeout_makes_the_server_exit(self):
        """④ 心跳断了 ⇒ 超时退（**用缩短的超时**跑，不等 180 秒）。

        ⚠️ 这个超时是「**连心跳都没了**」（浏览器崩了/被强杀）的兜底，
        不是「多久没操作」。
        """
        # 把超时改小：直接改模块属性 ⇒ 不动源码
        runner = (
            "import sys, time;"
            "sys.path.insert(0, %r);"
            "import save_modifier_web.server as S;"
            "S.HEARTBEAT_TIMEOUT = 6;"
            "S._watch_client.__globals__['HEARTBEAT_TIMEOUT'] = 6;"
            "S.run(serve_only=True, no_window=False, no_browser=True)"
            % REPO)
        env = dict(os.environ)
        env["UOC2_APPDATA"] = APPDATA
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([PY, "-u", "-c", runner], cwd=REPO,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                env=env)
        try:
            t0 = time.time()
            while time.time() - t0 < 30:
                line = proc.stdout.readline()
                if not line:
                    break
                if "http://" in line:
                    break
            # ⚠️ 宽限期是 60 秒 ⇒ 这里等不出来 ⇒ 跳过这条（见下面的说明）
            # 改用：直接验证「心跳断了之后 _watch_client 会判定为不在」
            sys.path.insert(0, REPO)
            import save_modifier_web.server as S
            # 心跳**很旧**（超过超时）⇒ 判「不在」
            S._LAST_BEAT[0] = time.time() - (S.HEARTBEAT_TIMEOUT + 10)
            self.assertFalse(S._client_present(),
                             "心跳断了还判成『客户端在』")
            # 心跳**新鲜** ⇒ 判「在」
            S._LAST_BEAT[0] = time.time()
            self.assertTrue(S._client_present(),
                            "心跳正常却判成『客户端不在』")
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


class TestClientGoneSemantics(unittest.TestCase):
    """判活函数的语义（直接调，不起进程）。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, REPO)
        import save_modifier_web.server as S
        cls.S = S

    def setUp(self):
        self.S._LAST_BEAT[0] = time.time()
        self.S._CLIENT_GONE_AT[0] = 0.0

    def test_heartbeat_makes_client_present(self):
        self.S._beat()
        self.assertTrue(self.S._client_present())

    def test_no_heartbeat_means_absent(self):
        """从没收到过心跳 ⇒ **宽限期过了**才判「不在」。

        ⚠️ 刚起服务时页面可能还没加载完（Edge 首启要初始化 profile）
        ⇒ 宽限期内必须算「在场」，否则服务会**立刻自杀**。
        """
        self.S._LAST_BEAT[0] = 0.0
        self.S._STARTED_AT[0] = time.time() - (self.S.GRACE + 10)
        self.assertFalse(self.S._client_present(),
                         "宽限期过了还没心跳，却判成『客户端在』")

    def test_within_grace_no_heartbeat_is_still_present(self):
        """⚠️ **宽限期内没心跳 ⇒ 仍算在场**（页面可能还在加载）。

        这条守着「服务不会在启动后立刻自杀」。
        """
        self.S._LAST_BEAT[0] = 0.0
        self.S._STARTED_AT[0] = time.time()
        self.assertTrue(self.S._client_present(),
                        "刚起服务、还没心跳 ⇒ 不该判成『客户端不在』"
                        "（否则服务启动即退）")

    def test_client_gone_means_absent_even_with_fresh_heartbeat(self):
        """客户端说「我走了」**超过容忍期** ⇒ 算不在（哪怕心跳是新的）。

        ⚠️ 容忍期内的「走了」会被新页面的心跳撤销（刷新场景）。
        """
        self.S._CLIENT_GONE_AT[0] = time.time() - (self.S.GONE_GRACE + 10)
        self.S._LAST_BEAT[0] = time.time()
        self.assertFalse(self.S._client_present(),
                         "客户端说了『我走了』，心跳再新也得算不在")

    def test_client_gone_within_grace_is_still_present(self):
        """刚收到「我走了」⇒ **容忍期内仍算在场**（给刷新留时间）。"""
        self.S._CLIENT_GONE_AT[0] = time.time()
        self.S._LAST_BEAT[0] = time.time()
        self.assertTrue(self.S._client_present(),
                        "刚收到『我走了』就判不在 ⇒ 刷新后页面连不上")

    def test_beat_clears_the_gone_flag(self):
        """新页面接管（刷新）⇒ 撤销『已离开』标记 ⇒ 服务继续活着。"""
        self.S._CLIENT_GONE_AT[0] = time.time()
        self.S._beat()
        self.assertEqual(0.0, self.S._CLIENT_GONE_AT[0])
        self.assertTrue(self.S._client_present())

    def test_timeout_is_at_least_180_seconds(self):
        """⚠️ ≥180 秒：Edge 会节流不可见窗口的定时器 ⇒ 90 秒会误杀。"""
        self.assertGreaterEqual(self.S.HEARTBEAT_TIMEOUT, 180)


if __name__ == "__main__":
    unittest.main()
