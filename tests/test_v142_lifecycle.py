# -*- coding: utf-8 -*-
"""v1.4.2 护栏测试：客户端「在场」信号 + 启动器不再按 Edge pid 判关窗。

**这些测试守着**：
① 前端有**心跳**（定时 ping）与**关窗 beacon**（pagehide）；
② 服务端有 `/api/ping` 与 `/api/client-gone` 两个接口；
③ 服务端**不再**用 `proc.wait()`（Edge 进程）当退出依据；
④ 启动器**不再**用 `browser.WaitForExit()` 当关窗依据；
⑤ **心跳超时不是「多久没操作」** —— 心跳由定时器发（与操作无关）；
⑥ 超时值 ≥ 180 秒（Edge 会节流不可见窗口的定时器 ⇒ 90 秒会误杀）；
⑦ 启动页有「特别鸣谢 IQ180 的学生会会计」一行。

**为什么要有 ③ ④**：v1.4.1 的实测故障 —— Edge 启动 `--app` 时**首个进程
会自己退出**（relaunch，窗口照常开着）⇒ 启动器误判成「用户关了窗口」
⇒ **把服务杀了** ⇒ 首次打开「无法访问此网站」、写回报 "Failed to fetch"。
⇒ 退出判定必须改成「**客户端还在不在**」（心跳/beacon）。

**反证脚本**：`tools/prove_v142_lifecycle.py`
（把 ③ ④ 改回旧写法 ⇒ 对应测试必须红）。
"""
import io
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(REPO, "src", "save_modifier_web", "web", "index.html")
SERVER = os.path.join(REPO, "src", "save_modifier_web", "server.py")
LAUNCHER = os.path.join(REPO, "tools", "launcher", "Launcher.cs")


def read(path):
    return io.open(path, encoding="utf-8", newline="").read()


def strip_comments(src, lang="js"):
    """剥掉注释，只留**代码**（字符串字面量里的内容不算注释）。

    ⚠️ **为什么自己写**：现成的两套都不靠谱 ——
    * JS 那套（`//` + `/* */`）在 **Python** 上会把后面全吞掉
      （`//` 在 Python 里不是注释，但出现在 URL / 字符串里）
      —— 实测 83252 字的源码被剥成 506 字 ⇒ 断言在空壳上跑 ⇒ 永远绿；
    * Python 的 `tokenize` 在 **C#** 上直接报错 ⇒ 原样返回
      ⇒ 断言又跑在含注释的源码上 ⇒ 被注释里的字面量误伤。

    ⇒ 自己写一个：逐字符扫描 + **识别字符串字面量**。

    `lang`：`"js"`（JS/C#：// 与 /* */）、`"py"`（# 行注释 + 三引号字符串）。
    注释一律换成**等长空格** ⇒ 原文结构与行号不变，
    代码里的 `proc.wait()` 仍是 `proc.wait()`（不会被拆成 `proc . wait ( )`）。
    """
    chars = list(src)
    n = len(src)
    i = 0
    line_c = "#" if lang == "py" else "//"
    while i < n:
        ch = src[i]
        # ---- 字符串字面量（跳过其内容）----
        if ch in ("'", '"'):
            quote = ch
            triple = src.startswith(quote * 3, i)
            endq = quote * 3 if triple else quote
            i += len(endq)
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src.startswith(endq, i):
                    i += len(endq)
                    break
                i += 1
            continue
        # ---- 行注释 ----
        if src.startswith(line_c, i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            for c in range(i, j):
                chars[c] = " "
            i = j
            continue
        # ---- 块注释 ----
        if lang != "py" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for c in range(i, j):
                chars[c] = " "
            i = j
            continue
        i += 1
    return "".join(chars)


class TestClientPresenceSignal(unittest.TestCase):
    """前端：心跳 + 关窗 beacon。"""

    @classmethod
    def setUpClass(cls):
        cls.html = read(HTML)
        # ⚠️ 查**函数体**（真代码，不含注释）—— 不要靠剥注释：
        #    HTML 里 `'` 出现在中文文案里 ⇒ 剥注释的扫描状态会乱
        #    （实测：剥完长度不变 ⇒ 注释没被剥掉）。
        m = re.search(r"function startClientHeartbeat\(\)\{(.*?)\n\}",
                      cls.html, re.S)
        assert m, "找不到 startClientHeartbeat"
        cls.body = m.group(1)

    def test_heartbeat_pings_the_server(self):
        """心跳：定时 ping `/api/ping`（**与操作无关** —— 只证明客户端还在）。"""
        self.assertIn("/api/ping", self.html)
        self.assertIn("function clientHeartbeat(", self.html)
        # ⚠️ 必须是**定时器**发的 ⇒ 界面开着就一直有 ⇒ 不会因为「没操作」被踢。
        self.assertRegex(self.body, r"setInterval\(\s*clientHeartbeat\s*,",
                         "心跳必须由定时器驱动（与用户操作无关）")

    def test_heartbeat_interval_is_short_enough(self):
        """心跳间隔 ≤ 30 秒 —— 配合 180 秒超时，至少有 6 次机会。"""
        m = re.search(r"setInterval\(\s*clientHeartbeat\s*,\s*(\d+)\s*\)",
                      self.body)
        self.assertIsNotNone(m, "找不到心跳的 setInterval")
        self.assertLessEqual(int(m.group(1)), 30000)

    def test_pagehide_sends_a_beacon(self):
        """关窗：发 beacon 通知服务端「我走了」⇒ **即时**退出。"""
        self.assertIn("function clientBeaconGone(", self.html)
        self.assertIn("/api/client-gone", self.html)
        self.assertIn("pagehide", self.html)
        self.assertIn("sendBeacon", self.html)

    def test_heartbeat_is_started(self):
        """心跳要在页面起来时就开（不等用户操作）。"""
        self.assertIn("function startClientHeartbeat(", self.html)
        self.assertIn("startClientHeartbeat();", self.html)

    def test_heartbeat_failure_does_not_throw(self):
        """心跳失败**不能**弹错（服务没了会自己退 ⇒ 不用打扰用户）。"""
        m = re.search(r"function clientHeartbeat\(\)\{(.*?)\n\}", self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn(".catch(function(){})", m.group(1))


class TestServerPresenceEndpoints(unittest.TestCase):
    """服务端：两个接口 + 按心跳判活。"""

    @classmethod
    def setUpClass(cls):
        cls.src = read(SERVER)

    def test_ping_endpoint_exists(self):
        self.assertIn('"/api/ping"', self.src)
        self.assertIn("def _beat(", self.src)

    def test_client_gone_endpoint_exists(self):
        self.assertIn('"/api/client-gone"', self.src)
        self.assertIn("_CLIENT_GONE_AT[0] = time.time()", self.src)

    def test_heartbeat_timeout_is_at_least_180s(self):
        """⚠️ **至少 180 秒** —— Edge 会节流不可见窗口的定时器
        （Chromium 的 intensive throttling ⇒ 最慢 1 分钟一次），
        90 秒的窗口在节流下只剩 1.5 次机会 ⇒ 会误杀。"""
        m = re.search(r"HEARTBEAT_TIMEOUT\s*=\s*(\d+)", self.src)
        self.assertIsNotNone(m, "找不到 HEARTBEAT_TIMEOUT")
        self.assertGreaterEqual(int(m.group(1)), 180,
                                "心跳超时不能少于 180 秒（Edge 会节流定时器）")

    def test_server_does_not_wait_on_the_browser_process(self):
        """⚠️ **核心护栏**：服务端**不能**用 `proc.wait()` 当「用户关了窗口」。

        v1.4.1 的实测故障：Edge 启动 `--app` 时**首个进程会自己退出**
        （relaunch，窗口照常开着）⇒ 等它返回 = 服务立刻自杀。
        """
        code = strip_comments(self.src, "py")
        self.assertNotIn("proc.wait()", code,
                         "服务端还在等 Edge 进程退出 ⇒ relaunch 会被误判成关窗")

    def test_watch_client_thread_is_started(self):
        """按心跳判活的守护线程要起来。"""
        self.assertIn("def _watch_client(", self.src)
        self.assertIn("target=_watch_client", self.src)

    def test_client_gone_makes_the_server_exit(self):
        """客户端说「我走了」⇒ 服务要退（关窗即退的语义保住）。"""
        m = re.search(r"def _watch_client\(.*?\n(?=def )", self.src, re.S)
        self.assertIsNotNone(m, "找不到 _watch_client")
        body = m.group(0)
        # ⚠️ 名字在 v1.4.2 改过：`_CLIENT_GONE`（布尔）⇒ `_CLIENT_GONE_AT`（时刻）
        self.assertIn("_CLIENT_GONE_AT[0]", body)
        self.assertIn("httpd.shutdown()", body)


class TestLauncherLiveness(unittest.TestCase):
    """启动器：不再按 Edge 的 pid 判关窗。"""

    @classmethod
    def setUpClass(cls):
        cls.src = read(LAUNCHER)

    def test_launcher_does_not_wait_for_the_edge_process(self):
        """⚠️ **核心护栏**：启动器**不能**用 `browser.WaitForExit()` 当关窗依据。

        这正是 v1.4.1 的故障根因：Edge 的首个进程会自己退出（relaunch），
        而窗口照常开着 ⇒ 启动器误判 ⇒ **把服务杀了**。

        ⚠️ **只查新起服务那条路**（`browser` 变量）——
        单实例分支里的 `existingBrowser.WaitForExit()` 是**另一回事**：
        它等的窗口属于**已经在跑的服务**，等完直接 `return 0`、**不杀服务** ⇒ 无害。
        """
        code = strip_comments(self.src, "js")   # C# 用 // 与 /* */
        # ⚠️ **词边界**匹配 —— 子串会误伤 `existingBrowser.WaitForExit()`
        #    （单实例分支，等的是**已有服务的窗口**，等完直接 return 0、
        #     **不杀服务** ⇒ 无害）。
        self.assertIsNone(
            re.search(r"(?<![A-Za-z0-9_])browser\.WaitForExit\(\)", code),
            "启动器还在等 Edge 进程退出 ⇒ relaunch 会被误判成关窗")

    def test_launcher_waits_for_the_server_process(self):
        """改成等 **python 服务进程**退出（服务端自己按心跳判活）。"""
        self.assertIn("proc.WaitForExit()", self.src)

    def test_launcher_logs_its_actions(self):
        """启动器每次动作都写日志 ⇒ 下次出问题能直接看出是谁杀的。"""
        self.assertIn("private static void Log(", self.src)
        self.assertIn("LogFile", self.src)
        # 关键节点都要有日志
        for key in ("服务已启动", "Edge 已拉起", "服务进程已退出"):
            self.assertIn(key, self.src, "启动器日志缺：" + key)


class TestSplashThanks(unittest.TestCase):
    """启动页：作者下面一行特别鸣谢。"""

    @classmethod
    def setUpClass(cls):
        cls.html = read(HTML)

    def test_thanks_line_exists(self):
        # ⚠️ v1.4.3：整句已拆成三段（可译 / **人名** / 可译）——
        #    人名是群友的名字 ⇒ **不翻译**（见 test_v143_thanks_name.py）。
        self.assertIn("特别鸣谢", self.html)
        self.assertIn("IQ180 的学生会会计", self.html)
        self.assertIn("的详细测试", self.html)

    def test_thanks_is_below_the_author(self):
        """位置：作者署名**下面**。"""
        i_author = self.html.index('<div class="by">烟柳边城 misprit</div>')
        i_thanks = self.html.index('class="thanks"')
        self.assertLess(i_author, i_thanks, "鸣谢行要在作者下面")

    def test_thanks_has_a_style(self):
        self.assertIn("#splash .thanks{", self.html)
        self.assertIn("#splash .thanks .nm{", self.html)


if __name__ == "__main__":
    unittest.main()
