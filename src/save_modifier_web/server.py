"""GUI 界面层 —— **本地 HTTP 桥 + Edge `--app` 独立窗口**（U26 技术路线）。

为什么不是 tkinter：视觉稿用的是 HTML/CSS，而 ttk 没有圆角 / 阴影 / flex /
`gap` / 过渡这些能力 ⇒ 用 tkinter 复刻一遍既慢又到不了同样的水准
（《GUI设计规范.md》§10.10）。这里让**视觉稿直接就是实现**。

跑法
----
```
python -m save_modifier_web.server          # 起服务 + 拉起 Edge 独立窗口
python -m save_modifier_web.server --serve  # 只起服务（自己开浏览器调试）
```

安全
----
* 只监听 **127.0.0.1**（不外网）；
* 每个会话带一个 **随机 token**，`/api/*` 必须带上（防本机其它进程/网页访问）；
* **本轮只提供只读接口** —— 写操作（plan / commit / undo）等 GUI 需求定稿后再加
  （交互方式会变，接口形状跟着变；核心库那边早就有 `plan_edit` / `commit` / `undo`）。
"""

from __future__ import annotations

import dataclasses
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO_SRC = Path(__file__).resolve().parents[1]
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

WEB_DIR = Path(__file__).resolve().parent / "web"

#: Edge 的常见安装位置（U26 实测：`--app=` 模式能给独立窗口、无地址栏）
EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge Beta\Application\msedge.exe",
)

#: Edge 自己的独立 profile（跟用户日常浏览隔开）。
#: ⚠️ 放在 **LOCALAPPDATA** 下，**不进源码树** —— 它是几百 MB 的浏览器缓存。
PROFILE_DIR = Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) \
    / ".uoc2" / "edge_profile"


# ---------------------------------------------------------------- 小工具


def find_edge() -> str | None:
    """找 Edge；找不到返回 `None`。"""
    for p in EDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def _jsonable(obj):
    """把 dataclass / 容器转成能 `json.dumps` 的东西。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _jsonable(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _mtime(ts) -> str:
    import datetime
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _size(n) -> str:
    try:
        n = float(n)
    except Exception:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024
    return ""


# ---------------------------------------------------------------- 只读 API


def api_saves() -> dict:
    """存档列表（启动页用）。"""
    from save_modifier_core import list_saves

    rows = []
    for info in list_saves():
        if not info.is_primary:
            continue
        rows.append({
            "save_id": info.save_id,
            "name": os.path.basename(str(info.path)),
            "display": info.display_name,
            "campaign": info.campaign_name or info.campaign_id or "",
            "scenario": info.scenario or "",
            "kind": "战役" if info.kind == "campaign" else "独立场景",
            "mtime": _mtime(info.mtime),
            "size": _size(info.size),
        })
    return {"saves": rows}


def api_view(save_id: str) -> dict:
    """某个存档的完整只读投影（概览页 / 各功能页用）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    catalog = Catalog(CorePaths.discover())
    with open_save(save_id) as save:
        view = save.view(catalog=catalog)
        caps = view.capabilities
        data = _jsonable(view)
        # 能力位体检：可用性用 `can_edit_*` 判断；`unavailable_reason()` 只是**原因文案表**
        # （永远返回字符串，不能拿它判可用性）。
        features = []
        for feat, attr in (("units", "can_edit_units"),
                           ("hqs", "can_edit_hqs"),
                           ("hand", "can_edit_hand"),
                           ("shelf", "can_edit_shelf"),
                           ("store", "can_edit_store"),
                           ("theater_assets", "can_edit_theater_assets"),
                           ("restore_hand", "can_restore_hand")):
            ok = bool(getattr(caps, attr, False))
            features.append({
                "name": feat,
                "ok": ok,
                "reason": "" if ok else caps.unavailable_reason(feat),
            })
        data["_features"] = features
        data["_save_id"] = save_id
        return data


# ---------------------------------------------------------------- HTTP


class _Handler(BaseHTTPRequestHandler):
    server_version = "UOC2Web/1.0"

    # 路由里放 token
    token = ""

    def log_message(self, fmt, *args):     # 安静点
        pass

    # ---- 工具 ----
    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _check_token(self) -> bool:
        got = self.headers.get("X-Token") or ""
        if not got:
            q = parse_qs(urlparse(self.path).query)
            got = (q.get("t") or [""])[0]
        if not got or not secrets.compare_digest(got, self.token):
            self._json({"error": "token 无效"}, 403)
            return False
        return True

    # ---- GET ----
    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)

        if path.startswith("/api/"):
            if not self._check_token():
                return
            try:
                if path == "/api/saves":
                    self._json(api_saves())
                elif path.startswith("/api/view/"):
                    sid = path[len("/api/view/"):]
                    self._json(api_view(sid))
                else:
                    self._json({"error": "未知接口"}, 404)
            except Exception as exc:                     # 绝不让一条坏请求炸掉服务
                self._json({"error": "%s: %s" % (type(exc).__name__, exc)}, 500)
            return

        # ---- 静态文件 ----
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError:
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        if not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self):
        self._send(405, b"read-only for now", "text/plain; charset=utf-8")


# ---------------------------------------------------------------- 启动


def _serve_forever(httpd):
    httpd.serve_forever(poll_interval=0.3)


def run(serve_only: bool = False) -> int:
    """起服务 + 拉起 Edge 独立窗口；窗口关掉 ⇒ 服务一起退。"""
    token = secrets.token_urlsafe(16)
    _Handler.token = token

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=_serve_forever, args=(httpd,), daemon=True).start()
    url = "http://127.0.0.1:%d/?t=%s" % (port, token)
    print("[OK ] GUI 服务已启动：%s" % url)

    if serve_only:
        print("（--serve：自己开浏览器）")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()
        return 0

    edge = find_edge()
    if not edge:
        print("[NG ] 找不到 Edge —— 请装 Edge，或用 --serve 模式自己开浏览器。")
        httpd.shutdown()
        return 1

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [edge, "--app=" + url, "--user-data-dir=" + str(PROFILE_DIR),
         "--no-first-run", "--no-default-browser-check",
         "--disable-features=Translate,msEdgeSidebarV2,msEdgeShoppingAssistant"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[OK ] Edge 独立窗口已启动（pid=%d）—— 关掉窗口即退出。" % proc.pid)
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        httpd.shutdown()
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return run(serve_only="--serve" in argv)


if __name__ == "__main__":
    sys.exit(main())
