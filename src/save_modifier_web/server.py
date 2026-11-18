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


def _summary_of(obj) -> str:
    """`summary` 在不同结果类上**有的方法是属性** —— 两种都要认。"""
    v = getattr(obj, "summary", "")
    if callable(v):
        try:
            v = v()
        except Exception:
            v = ""
    return str(v or "")


def _edits_from(payload):
    """把前端传来的 `[{kind, params}]` 转成核心库的 `Edit` 列表。

    ⚠️ `Edit.__post_init__` 会校验 `kind` 必须在 `EDIT_KINDS` 里 —— 非法 kind 直接抛。
    """
    from save_modifier_core.edits import Edit

    out = []
    for item in (payload or {}).get("edits") or []:
        if not isinstance(item, dict):
            raise ValueError("每条编辑必须是 {kind, params} 字典")
        kind = item.get("kind")
        params = item.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("params 必须是字典")
        out.append(Edit(kind, params))
    return out


def find_surface(rel: str):
    """在游戏包里找 `assets/surfaces/<rel>` —— **用户包优先**（mod 覆盖）。

    返回 `Path` 或 `None`。找不到**不报错**（界面退化成占位方块，§5.6）。
    ⚠️ `package_roots()` 是**容器**目录（`_packages`）；真正的包在它下面
    （`base` / `dlc1` … / 用户 mod）⇒ 要用 `packages()`。
    """
    from save_modifier_core import CorePaths

    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    paths = CorePaths.discover()
    for pkg in paths.packages():
        cand = Path(pkg) / "assets" / "surfaces" / rel
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def api_plan(payload) -> dict:
    """规划一批编辑（**不碰磁盘**）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    save_id = (payload or {}).get("save_id") or ""
    catalog = Catalog(CorePaths.discover())
    with open_save(save_id) as save:
        plan = save.plan_edit(_edits_from(payload), catalog=catalog)
        return {
            "ok": plan.ok,
            "errors": list(plan.errors),
            "warnings": list(plan.warnings),
            "notes": list(plan.notes),
            "changes": [{"entry": c.entry, "notes": list(c.notes),
                         "diff": c.diff, "layer": c.layer,
                         "is_l3_exception": c.is_l3_exception}
                        for c in plan.changes],
        }


def api_commit(payload) -> dict:
    """提交一批编辑（备份 → 写回 → 压撤销栈）。"""
    from save_modifier_core import Catalog, CorePaths, open_save

    save_id = (payload or {}).get("save_id") or ""
    catalog = Catalog(CorePaths.discover())
    with open_save(save_id) as save:
        plan = save.plan_edit(_edits_from(payload), catalog=catalog)
        if not plan.ok:
            return {"ok": False, "errors": list(plan.errors),
                    "warnings": list(plan.warnings), "changes": []}
        res = save.commit(plan)
        return {"ok": res.ok or res.nothing_to_do,
                "nothing_to_do": bool(res.nothing_to_do),
                "errors": list(res.errors),
                "warnings": list(res.warnings),
                "changed": list(res.changed),
                "backup": str(res.backup) if res.backup else "",
                "summary": _summary_of(res)}


def api_undo(payload) -> dict:
    """撤销上一次提交（核心库自己的撤销栈）。"""
    from save_modifier_core import open_save

    save_id = (payload or {}).get("save_id") or ""
    with open_save(save_id) as save:
        if not save.undo_available():
            return {"ok": False, "errors": ["没有可撤销的改动"], "summary": ""}
        r = save.undo()
        return {"ok": bool(getattr(r, "ok", True)),
                "errors": list(getattr(r, "errors", []) or []),
                "summary": _summary_of(r)}


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

        # ---- 游戏贴图（代理；http 页面不能直接读 file://）----
        if path.startswith("/surfaces/"):
            if not self._check_token():
                return
            target = find_surface(path[len("/surfaces/"):])
            if target is None:
                self._send(404, b"surface not found", "text/plain; charset=utf-8")
                return
            ctype = mimetypes.guess_type(str(target))[0] or "image/png"
            try:
                self._send(200, target.read_bytes(), ctype)
            except OSError:
                self._send(404, b"surface unreadable", "text/plain; charset=utf-8")
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
        u = urlparse(self.path)
        path = unquote(u.path)
        if not path.startswith("/api/"):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        if not self._check_token():
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            self._json({"ok": False, "errors": ["请求体不是合法 JSON：%s" % exc]}, 400)
            return
        try:
            if path == "/api/plan":
                self._json(_jsonable(api_plan(payload)))
            elif path == "/api/commit":
                self._json(_jsonable(api_commit(payload)))
            elif path == "/api/undo":
                self._json(_jsonable(api_undo(payload)))
            else:
                self._json({"ok": False, "errors": ["未知接口"]}, 404)
        except ValueError as exc:
            # 请求体不合法（非法 kind / params 不是字典 …）⇒ 400，不是 500
            self._json({"ok": False, "errors": [str(exc)]}, 400)
        except Exception as exc:
            self._json({"ok": False, "errors": ["%s: %s" % (type(exc).__name__, exc)]}, 500)


# ---------------------------------------------------------------- 启动


def _serve_forever(httpd):
    httpd.serve_forever(poll_interval=0.3)


def run(serve_only: bool = False, no_window: bool = False) -> int:
    """起服务 + 拉起 Edge 独立窗口；窗口关掉 ⇒ 服务一起退。"""
    token = secrets.token_urlsafe(16)
    _Handler.token = token

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=_serve_forever, args=(httpd,), daemon=True).start()
    url = "http://127.0.0.1:%d/?t=%s" % (port, token)
    print("[OK ] GUI 服务已启动：%s" % url)

    if no_window:
        print("（--no-window：只起服务，不拉窗口）")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()
        return 0

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


def check() -> int:
    """自检（不弹窗）：起服务 → 探接口 → 探贴图 → 退出。

    用来回答「装好了没 / 能不能跑」：游戏目录、存档列表、贴图代理、
    Edge 在不在，一项一项报出来。
    """
    import urllib.request

    ok = True
    token = secrets.token_urlsafe(16)
    _Handler.token = token
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=_serve_forever, args=(httpd,), daemon=True).start()
    base = "http://127.0.0.1:%d" % port

    def get(path):
        req = urllib.request.Request(base + path)
        req.add_header("X-Token", token)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()

    try:
        st, _, body = get("/api/saves")
        n = len(json.loads(body.decode("utf-8")).get("saves") or [])
        print("[OK ] 存档列表接口正常 —— %d 个存档" % n)
    except Exception as exc:
        print("[NG ] 存档列表接口失败：%s" % exc)
        ok = False

    try:
        st, ct, body = get("/surfaces/unit/ger_inf_42/sheet_L.png")
        good = body[:4] == b"\x89PNG"
        print("[%s ] 贴图代理：%s（%d 字节）"
              % ("OK" if good else "NG", ct, len(body)))
        ok = ok and good
    except Exception as exc:
        print("[NG ] 贴图代理失败：%s" % exc)
        ok = False

    edge = find_edge()
    if edge:
        print("[OK ] Edge：%s" % edge)
    else:
        print("[NG ] 找不到 Edge —— 装 Edge，或用 run_web.bat --serve 自己开浏览器")
        ok = False

    httpd.shutdown()
    print("自检" + ("通过" if ok else "失败"))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return check()
    return run(serve_only="--serve" in argv, no_window="--no-window" in argv)


if __name__ == "__main__":
    sys.exit(main())
