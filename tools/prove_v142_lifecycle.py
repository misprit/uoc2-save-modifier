# -*- coding: utf-8 -*-
"""v1.4.2 护栏的反证：把修复改坏 ⇒ 对应测试必须红在目标断言上。

四个退化点：
① 服务端改回 `proc.wait()`（等 Edge 进程退出）⇒ 「服务端不再等浏览器进程」必须红；
② 启动器改回 `browser.WaitForExit()` ⇒ 「启动器不再等 Edge 进程」必须红；
③ 心跳超时改成 90 秒 ⇒ 「超时至少 180 秒」必须红；
④ 去掉前端心跳的 `setInterval` ⇒ 「心跳由定时器发」必须红。
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python", "python.exe")
SERVER = os.path.join(ROOT, "src", "save_modifier_web", "server.py")
HTML = os.path.join(ROOT, "src", "save_modifier_web", "web", "index.html")
LAUNCHER = os.path.join(ROOT, "tools", "launcher", "Launcher.cs")
BAK = os.path.join(ROOT, ".scratch", "bak_v142")

CASES = [
    # (说明, 文件, 原文, 改坏后, 目标测试)
    ("服务端又写回了 `proc.wait()`（等 Edge 进程退出 ⇒ relaunch 误判成关窗）",
     SERVER,
     """    try:
        while _client_present():
            time.sleep(1)""",
     """    try:
        proc.wait()
        while _client_present():
            time.sleep(1)""",
     "tests.test_v142_lifecycle.TestServerPresenceEndpoints."
     "test_server_does_not_wait_on_the_browser_process"),

    ("启动器改回等 Edge 进程退出（relaunch ⇒ 误判成关窗 ⇒ 杀服务）",
     LAUNCHER,
     """        try
        {
            proc.WaitForExit();
            Log("[launcher] 服务进程已退出（码=" + proc.ExitCode + "）");
        }""",
     """        try
        {
            browser.WaitForExit();
            Log("[launcher] Edge 退出了");
        }""",
     "tests.test_v142_lifecycle.TestLauncherLiveness."
     "test_launcher_does_not_wait_for_the_edge_process"),

    ("心跳超时改成 90 秒（Edge 会节流定时器 ⇒ 会误杀）",
     SERVER,
     "HEARTBEAT_TIMEOUT = 180",
     "HEARTBEAT_TIMEOUT = 90",
     "tests.test_v142_lifecycle.TestServerPresenceEndpoints."
     "test_heartbeat_timeout_is_at_least_180s"),

    ("去掉心跳的定时器（不再是『与操作无关』的保活）",
     HTML,
     "  setInterval(clientHeartbeat, 15000);\n",
     "",          # ⚠️ **删掉那一行**（不是注释掉 —— 断言查函数体原文）
     "tests.test_v142_lifecycle.TestClientPresenceSignal."
     "test_heartbeat_pings_the_server"),
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
    for path in (SERVER, HTML, LAUNCHER):
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
