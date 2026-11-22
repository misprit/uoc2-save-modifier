# -*- coding: utf-8 -*-
"""发一个 release：打 tag → 推 tag → 建 release → 上传成品 zip → **端到端校验**。

```bat
python tools\\release_publish.py            :: 用当前版本号（version.py）
python tools\\release_publish.py --dry      :: 只看要做什么，不动手
```

⚠️ **两个坑（都踩过，别再踩）**

1. **multipart 不会被解析** ——
   `Content-Type: multipart/form-data` 上传时，GitHub 把**整个请求体**
   当成了文件（下载下来开头是 `--boundary…` 而不是 `PK\\x03\\x04`）⇒
   **要用裸字节 + `Content-Type: application/zip`**。
2. **下载 URL 有 CDN 缓存** —— 同名资产删了重建，URL 不变 ⇒ 边缘缓存还留着旧内容
   ⇒ 校验要走 **API 直读**（`GET /repos/…/releases/assets/{id}`），
   下载比对时要加 cache-buster。

⚠️ **凭据**：用这台机器上 `git push` 的同一套凭据（`git credential fill`）
⇒ token **只在内存里用**，不打印、不落盘。

⚠️ **发布是对外可见的动作** —— 脚本只做「打 tag / 建 release / 传包」，
**不**改代码、**不**动工作区。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
ZIP_MAGIC = b"PK\x03\x04"
OWNER, NAME = "misprit", "uoc2-save-modifier"


def git(*args, **kw):
    return subprocess.run(["git"] + list(args), cwd=str(REPO),
                          capture_output=True, **kw)


def version() -> str:
    src = (REPO / "src" / "save_modifier_web" / "version.py").read_text(
        encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', src, re.M)
    return m.group(1) if m else "0.0.0"


def token() -> str:
    p = subprocess.run(["git", "credential", "fill"], cwd=str(REPO),
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, timeout=45)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def call(method, url, tok, data=None, ctype=None, accept=None, retries=6):
    last = ""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", "Bearer " + tok)
            req.add_header("Accept", accept or "application/vnd.github+json")
            req.add_header("X-GitHub-Api-Version", "2022-11-28")
            req.add_header("User-Agent", "uoc2-release-tool")
            if ctype:
                req.add_header("Content-Type", ctype)
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = "HTTP %s: %s" % (e.code,
                                    e.read().decode("utf-8", "replace")[:200])
            if e.code in (422,):
                break
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        time.sleep(5 + i * 4)
    raise SystemExit("API 调用失败：%s" % last)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只看要做什么")
    ap.add_argument("--notes", default="", help="release 正文（默认用 docs/发布说明-<版本>.md）")
    args = ap.parse_args()

    ver = version()
    tag = "v" + ver
    zpath = REPO / "dist" / ("uoc2-save-modifier-%s.zip" % tag)
    notes_path = REPO / "docs" / ("发布说明-v%s.md" % ver)
    if not notes_path.is_file():
        notes_path = REPO / "docs" / ("发布说明-%s.md" % ver)

    print("版本 %s  tag %s" % (ver, tag))
    print("成品  %s（存在：%s）" % (zpath.name, zpath.is_file()))
    print("说明  %s（存在：%s）" % (notes_path.name, notes_path.is_file()))
    if args.dry:
        return 0
    if not zpath.is_file():
        raise SystemExit("没有成品包 ⇒ 先跑 tools\\build_dist.py")

    tok = token()
    if not tok:
        raise SystemExit("取不到 GitHub 凭据")

    # ---- ① tag ----------------------------------------------------------
    # ⚠️ **查远端失败 ≠ tag 不在远端** —— 网络抖动会误导（曾因此白推一次）
    on_remote = None
    for i in range(4):
        r = git("ls-remote", "--tags", "origin", "refs/tags/" + tag)
        if r.returncode == 0:
            on_remote = bool(r.stdout.strip())
            break
        print("查远端 tag 失败（第 %d 次，网络）" % (i + 1))
        time.sleep(6)
    if on_remote is None:
        raise SystemExit("连不上远端 ⇒ 不动 tag（别把网络故障当成『tag 不存在』）")
    if git("rev-parse", "-q", "--verify", "refs/tags/" + tag).returncode == 0:
        print("本地已有 tag：%s" % tag)
    else:
        git("tag", "-a", tag, "-m", "%s：%s" % (tag, _tag_summary(ver)))
        print("已打 tag：%s" % tag)
    if on_remote:
        print("tag 已在远端 ⇒ 跳过推送")
    else:
        for i in range(5):
            r = git("push", "origin", tag)
            if r.returncode == 0:
                print("tag 已推送")
                break
            print("推 tag 失败（第 %d 次，网络）：%s"
                  % (i + 1, r.stderr.decode("utf-8", "replace")[:120]))
            time.sleep(8 + i * 6)
        else:
            raise SystemExit("tag 没推上去 ⇒ 停在这一步")

    # ---- ② release ------------------------------------------------------
    body = (Path(args.notes).read_text(encoding="utf-8") if args.notes
            else (notes_path.read_text(encoding="utf-8")
                  if notes_path.is_file() else ""))
    payload = {"tag_name": tag, "name": "统一指挥 2 存档修改器 %s" % tag,
               "body": body, "draft": False, "prerelease": False,
               "target_commitish": "main"}
    try:
        rel = json.loads(call("GET", "%s/repos/%s/%s/releases/tags/%s"
                              % (API, OWNER, NAME, tag), tok).decode("utf-8"))
        print("release 已存在：%s" % rel.get("html_url"))
    except SystemExit:
        rel = json.loads(call("POST", "%s/repos/%s/%s/releases"
                              % (API, OWNER, NAME), tok,
                              data=json.dumps(payload).encode("utf-8"),
                              ctype="application/json").decode("utf-8"))
        print("release 已创建：%s" % rel.get("html_url"))
    rid = rel["id"]
    upload = (rel.get("upload_url") or "").split("{")[0]

    # ---- ③ 资产（**裸字节**！不是 multipart）------------------------------
    asset_name = zpath.name
    zbytes = zpath.read_bytes()
    zsha = hashlib.sha256(zbytes).hexdigest()
    good = None
    for a in rel.get("assets") or []:
        if a.get("name") != asset_name:
            continue
        # ⚠️ **幂等**：远端已经有**且内容正确**的资产 ⇒ 不动它
        # （同名重建会撞上 CDN 缓存 ⇒ 下载拿到旧的）
        try:
            cur = call("GET", "%s/repos/%s/%s/releases/assets/%s"
                       % (API, OWNER, NAME, a["id"]), tok,
                       accept="application/octet-stream")
        except SystemExit:
            cur = b""
        if cur[:4] == ZIP_MAGIC and hashlib.sha256(cur).hexdigest() == zsha:
            good = a
            print("远端已有正确的资产（逐字节一致）⇒ 不重传：id=%s" % a["id"])
            break
        call("DELETE", "%s/repos/%s/%s/releases/assets/%s"
             % (API, OWNER, NAME, a["id"]), tok)
        print("删掉内容不对的同名资产 id=%s" % a["id"])
    if good is None:
        out = json.loads(call("POST", "%s?name=%s" % (upload, asset_name), tok,
                              data=zbytes, ctype="application/zip").decode("utf-8"))
        good = out
        print("资产已上传：%s（%.2f MB）" % (out.get("name"),
                                      out.get("size", 0) / 1048576.0))

    # ---- ④ 端到端校验（API 直读 + 下载比对）------------------------------
    got = call("GET", "%s/repos/%s/%s/releases/assets/%s"
               % (API, OWNER, NAME, good["id"]), tok,
               accept="application/octet-stream")
    same = hashlib.sha256(got).hexdigest() == hashlib.sha256(zbytes).hexdigest()
    print("API 直读：%d 字节  开头 %s  与本地一致：%s"
          % (len(got), " ".join("%02X" % b for b in got[:4]), same))
    if not same or got[:4] != ZIP_MAGIC:
        raise SystemExit("⚠️ 资产内容不对（不是那个 zip）")

    url = ("https://github.com/%s/%s/releases/download/%s/%s?cb=%d"
           % (OWNER, NAME, tag, asset_name, int(time.time())))
    data = b""
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "uoc2-verify"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            break
        except Exception as e:
            print("下载重试 %d：%s" % (i + 1, e))
            time.sleep(8)
    ok = hashlib.sha256(data).hexdigest() == hashlib.sha256(zbytes).hexdigest()
    print("下载比对：%d 字节  开头 %s  一致：%s"
          % (len(data), " ".join("%02X" % b for b in data[:4]), ok))
    if not ok:
        raise SystemExit("⚠️ 下载到的与本地不一致")
    print("\n✅ 发布完成：%s" % rel.get("html_url"))
    return 0


def _tag_summary(ver: str) -> str:
    """tag 的一句话概括（取发布说明里的第一段）。"""
    p = REPO / "docs" / ("发布说明-%s.md" % ver)
    if p.is_file():
        for ln in p.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s and not s.startswith("#"):
                return s[:180]
    return "统一指挥 2 存档修改器 %s" % ver


if __name__ == "__main__":
    sys.exit(main())
