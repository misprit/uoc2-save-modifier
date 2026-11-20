#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读校验：存档里的「总部经验目标（xp_target）」是否符合游戏的计算公式。

**公式**（游戏字节码实证，`state/campaign/campaign.pyc::Campaign._set_hqs_xp_target`）：

    num_turns    = Σ(所有战线 · 当前会议段 · 全部场景 的 base_num_turns)
    n_hq         = 该总部在那些场景**预设**里出现过的不同单位数
    xp_target    = ceil(int(n_hq × num_turns × f) / 5) × 5      # 向上取整到 5 的倍数
    f            = hq_xp_taget_fudge_factor（默认 0.75，战役包可覆盖）

用法
----
```bash
python tools/verify_hq_xp_target.py                  # 扫默认的存档目录
python tools/verify_hq_xp_target.py 某个存档.usg      # 只看一个
```

⚠️ **只读**：本脚本只读游戏包与存档，绝不写盘。
⚠️ 存档里的 `xp_target` 是**上一次战役推进时**算出来的 ⇒ 玩家在此期间
增兵 / 战役推进过的存档，数值会与"按当前局面重算"不同 ⇒ 报 `✘（旧值）` 是正常的。
"""

from __future__ import annotations

import argparse
import io
import math
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:                                   # pragma: no cover
    print("需要 PyYAML", file=sys.stderr)
    raise


def default_game_dir() -> Path | None:
    """游戏安装目录（找 `_packages` 与 `lib/uoc2`）。"""
    env = os.environ.get("UOC2_GAME_DIR")
    cands = [Path(env)] if env else []
    cands += [
        Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2"),
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Unity of Command 2"),
        Path.home() / ".steam/steam/steamapps/common/Unity of Command 2",
    ]
    for c in cands:
        if (c / "_packages").is_dir() and (c / "lib" / "uoc2").is_dir():
            return c
    return None


def default_save_dir() -> Path | None:
    env = os.environ.get("UOC2_APPDATA")
    if env:
        p = Path(env) / "save" / "campaigns"
        if p.is_dir():
            return p
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = Path(local) / ".uoc2" / "save" / "campaigns"
        if p.is_dir():
            return p
    return None


def load(p):
    with io.open(str(p), encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_campaign(packs: Path, campaign_id: str) -> Path | None:
    """战役包目录：`_packages/<包>/data/campaigns/<战役>.usc`。"""
    if not campaign_id:
        return None
    roots = [packs]                       # 直接放在 _packages 下的（少见）
    if packs.is_dir():
        roots += [packs / p for p in sorted(os.listdir(packs))
                  if (packs / p).is_dir()]
    for r in roots:
        cdir = r / "data" / "campaigns"
        if not cdir.is_dir():
            continue
        for d in sorted(os.listdir(cdir)):
            if d.split(".")[0] == campaign_id:
                return cdir / d
    return None


def fudge_factor(camp: Path | None, base_cfg: Path) -> float:
    if camp:
        ov = camp / "overrides" / "game.yml"
        if ov.exists():
            d = load(ov) or {}
            if "hq_xp_taget_fudge_factor" in d:
                return d["hq_xp_taget_fudge_factor"]
    cfg = load(base_cfg) or {}
    return cfg.get("hq_xp_taget_fudge_factor", 0.75)


def verify(save_path: Path, game_dir: Path):
    packs = game_dir / "_packages"
    base = packs / "base"
    with zipfile.ZipFile(save_path) as zf:
        main = yaml.safe_load(zf.read("main.yml")) or {}
        hqs = yaml.safe_load(zf.read("hqs.yml")) or []
    st = main.get("in_state") or {}
    camp = find_campaign(packs, main.get("campaign_id"))
    fronts = st.get("fronts") or {}
    if not (camp and fronts):
        return None, "（战役包 / 战线信息不全，跳过）"

    scenarios = []
    for fr, v in fronts.items():
        seg = (v or {}).get("segment")
        if not seg:
            continue
        f = camp / "fronts" / str(fr) / "segments" / str(seg) / "data.yml"
        if not f.exists():
            continue
        for sit in (load(f) or {}).get("situations") or []:
            for s in sit:
                if s not in scenarios:
                    scenarios.append(s)
    if not scenarios:
        return None, "（找不到当前段的场景，跳过）"

    num_turns = 0
    units_per_hq = defaultdict(set)
    for s in scenarios:
        sp = camp / "scenarios" / s / "main.yml"
        up = camp / "scenarios" / s / "units.yml"
        if sp.exists():
            num_turns += (load(sp) or {}).get("base_num_turns") or 0
        if up.exists():
            for u in (load(up) or []):
                if isinstance(u, dict) and u.get("hq_id") is not None:
                    units_per_hq[u["hq_id"]].add(u.get("id"))

    f = fudge_factor(camp, base / "config" / "game.yml")
    rows, ok = [], True
    for h in sorted(hqs, key=lambda x: x.get("id") or 0):
        if not h.get("persistent"):
            continue
        hid = h.get("id")
        n = len(units_per_hq.get(hid, ()))
        calc = math.ceil(int(n * num_turns * f) / 5) * 5
        tgt = h.get("xp_target")
        if calc == tgt:
            state = "✔"
        elif calc == 0 and tgt:
            # 该总部在**当前段的场景里没有单位** ⇒ 存档里的值是
            # 「上一次战役推进时」算的（旧值），不是公式错。
            state = "· 旧值（当前段场景里没有它的单位）"
        else:
            state = "✘ 不一致"
            ok = False
        rows.append((hid, n, calc, tgt, state))
    head = ("场景=%s num_turns=%s f=%s"
            % (",".join(scenarios), num_turns, f))
    return (rows, ok), head


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="只读校验总部经验目标 xp_target")
    ap.add_argument("saves", nargs="*", help="存档路径（不给就扫存档目录）")
    ap.add_argument("--game-dir", default=None, help="游戏安装目录")
    ap.add_argument("--save-dir", default=None, help="存档目录")
    args = ap.parse_args(argv)

    game_dir = Path(args.game_dir) if args.game_dir else default_game_dir()
    if not game_dir or not game_dir.is_dir():
        print("找不到游戏目录（用 --game-dir 指定）", file=sys.stderr)
        return 2
    if args.saves:
        files = [Path(p) for p in args.saves]
    else:
        sd = Path(args.save_dir) if args.save_dir else default_save_dir()
        if not sd or not sd.is_dir():
            print("找不到存档目录（用 --save-dir 指定）", file=sys.stderr)
            return 2
        files = sorted(sd.glob("*.usg"))

    all_ok = True
    for p in files:
        print("==", p.name)
        res, head = verify(p, game_dir)
        if res is None:
            print("   ", head)
            print()
            continue
        rows, ok = res
        all_ok &= ok
        print("   ", head)
        print("    %-5s %-6s %-9s %-9s %s"
              % ("hq", "场景n", "算出", "存档", ""))
        for hid, n, calc, tgt, state in rows:
            print("    %-5s %-6s %-9s %-9s %s"
                  % (hid, n, calc, tgt, state))
        print("    ⇒", "全部吻合" if ok else "有不一致")
        print()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
