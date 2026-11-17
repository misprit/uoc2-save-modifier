"""GUI 图标资产映射取证：单位头像 / 特种兵图标 / step / 战区资产 四态变体。

产出写 D:\\MiniMax\\_analysis\\e135_assetmap.md（供 GUI 设计文档引用）。
"""

from __future__ import annotations

import json
import struct
from collections import Counter
from pathlib import Path

PK = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base")
SUR = PK / "assets" / "surfaces"
OUT = Path(r"D:\MiniMax\_analysis\e135_assetmap.md")


def png_size(path: Path) -> tuple[int, int]:
    """直读 PNG IHDR，不依赖 PIL。"""
    with path.open("rb") as fh:
        head = fh.read(26)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    width, height = struct.unpack(">II", head[16:24])
    return (width, height)


lines: list[str] = []


def w(text: str = "") -> None:
    lines.append(text)


# ---------------------------------------------------------------- 单位头像
unit_dirs = sorted(p for p in (SUR / "unit").iterdir() if p.is_dir())
has_l = [p for p in unit_dirs if (p / "sheet_L.png").is_file()]
has_r = [p for p in unit_dirs if (p / "sheet_R.png").is_file()]
both = [p for p in unit_dirs if (p / "sheet_L.png").is_file() and (p / "sheet_R.png").is_file()]
extra: Counter[str] = Counter()
for p in unit_dirs:
    for f in p.iterdir():
        if f.suffix.lower() == ".png":
            extra[f.name] += 1

w("# GUI 图标资产映射（实证）")
w("")
w("## 1. 单位头像 `assets/surfaces/unit/<type>/`")
w("")
w(f"- 类型目录总数：**{len(unit_dirs)}**")
w(f"- 同时有 `sheet_L.png` + `sheet_R.png`：**{len(both)}**")
w(f"- 只有 L：{len(has_l) - len(both)}；只有 R：{len(has_r) - len(both)}；两者都没有：{len(unit_dirs) - len(has_l) - len(has_r) + len(both)}")
w(f"- 目录内出现过的 png 文件名分布：{dict(extra)}")
w("")

# 尺寸统计（抽样 60 个，避免全量解码慢）
sizes = Counter()
for p in both[:60]:
    sizes[png_size(p / "sheet_L.png")] += 1
w(f"- `sheet_L.png` 尺寸分布（前 60 个类型）：{dict(sizes)}")
w("")
w("样例类型名（前 12）：" + ", ".join(p.name for p in both[:12]))
w("")

# ------------------------------------------------------------ 特种兵图标
spec_dirs = sorted(p for p in (SUR / "specialist").iterdir() if p.is_dir())
spec_files: Counter[str] = Counter()
spec_missing: Counter[str] = Counter()
SPEC_EXPECTED = [
    "sheet_act.png",
    "sheet_sup.png",
    "status_act.png",
    "status_sup.png",
    "sheet_large.png",
    "hq_action_icon.png",
    "hq_menu_icon.png",
]
for p in spec_dirs:
    have = {f.name for f in p.iterdir() if f.suffix.lower() == ".png"}
    for name in SPEC_EXPECTED:
        (spec_files if name in have else spec_missing)[name] += 1

w("## 2. 特种兵图标 `assets/surfaces/specialist/<type>/`")
w("")
w(f"- 特种兵类型目录总数：**{len(spec_dirs)}**")
w("")
w("| 文件 | 存在的类型数 | 缺失的类型数 | 用途 |")
w("|---|---|---|---|")
usage = {
    "sheet_act.png": "战斗条上的活跃兵小图标（24×30）",
    "sheet_sup.png": "战斗条上的压制兵小图标（39×50）",
    "status_act.png": "状态面板里的活跃兵（52×68）",
    "status_sup.png": "状态面板里的压制兵（72×48）",
    "sheet_large.png": "大图，单位详情页用（160×160）",
    "hq_action_icon.png": "总部菜单行动图标",
    "hq_menu_icon.png": "总部菜单条目图标",
}
for name in SPEC_EXPECTED:
    w(f"| `{name}` | {spec_files[name]} | {spec_missing[name]} | {usage[name]} |")
w("")
try:
    spec_sizes: dict[str, Counter] = {}
    for p in spec_dirs[:30]:
        for name in SPEC_EXPECTED:
            f = p / name
            if f.is_file():
                spec_sizes.setdefault(name, Counter())[png_size(f)] += 1
    w("尺寸抽样（前 30 个类型）：")
    w("")
    for name in SPEC_EXPECTED:
        if name in spec_sizes:
            w(f"- `{name}`：{dict(spec_sizes[name])}")
except Exception as exc:  # pragma: no cover
    w(f"- 尺寸统计跳过：{exc}")
w("")

# ------------------------------------------------------------------ steps
w("## 3. 战力阶梯 `assets/surfaces/steps/`")
w("")
step_files = sorted((SUR / "steps").glob("*.png"))
for f in step_files:
    size = png_size(f)
    w(f"- `{f.name}` — {size[0]}×{size[1]}")
w("")

# ---------------------------------------------------------------- theater
w("## 4. 战区资产 `assets/surfaces/theater/`")
w("")
th_files = sorted((SUR / "theater").glob("*.png"))
base_names = Counter()
for f in th_files:
    stem = f.stem
    for suffix in ("_neutral", "_hover", "_down", "_disabled"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    base_names[stem] += 1
w(f"- 文件总数：**{len(th_files)}**；归一化后的资产条目数：**{len(base_names)}**")
w("")
w("| 资产条目 | 变体数 | 变体文件名 |")
w("|---|---|---|")
for stem in sorted(base_names):
    variants = sorted(f.name for f in th_files if f.stem.replace("_neutral", "").replace("_hover", "").replace("_down", "").replace("_disabled", "") == stem)
    w(f"| {stem} | {len(variants)} | {', '.join(variants)} |")
w("")

# ----------------------------------------------------------------- status
w("## 5. 状态图标 `assets/surfaces/status/`")
w("")
for f in sorted((SUR / "status").glob("*.png")):
    w(f"- `{f.name}`")
w("")

# ----------------------------------------------------------------- icon
icon_files = sorted((SUR / "icon").glob("*.png"))
w(f"## 6. 通用图标 `assets/surfaces/icon/` —— 共 {len(icon_files)} 个")
w("")
w(", ".join(f.name for f in icon_files))
w("")

# ------------------------------------------------------------- 其他批次
w("## 7. 其它资源批次")
w("")
for sub in ("cards", "hq_insignia", "buttons", "ui", "sheet", "milestones", "nationality", "faction"):
    d = SUR / sub
    if not d.is_dir():
        w(f"- `{sub}/`：目录不存在")
        continue
    pngs = [f for f in d.rglob("*.png")]
    w(f"- `{sub}/`：{len(pngs)} 个 png")
w("")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"写入 {OUT} （{len(lines)} 行）")
print("\n".join(lines[:60]))
