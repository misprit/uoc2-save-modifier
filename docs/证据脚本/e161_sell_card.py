"""e161 —— 游戏里「出售手牌」（RecoupCard）这条路径的存在性与语义（字节码实证）。

**背景**：2026-11-18 用户指出 —— 玩家在游戏里移除手牌是通过**出售**实现的，
免费卡出售时也不扣回声望 ⇒ **游戏本身支持删牌** ⇒ 修改器允许删手牌是安全的。
本脚本把这条链路逐字节坐实。

**结论（全部来自字节码）**

| 问题 | 答案 | 出处 |
|---|---|---|
| 游戏有「卖牌」动作吗？ | **有** —— `conference_actions.pyc::RecoupCard`（`can_perform` / `do` / `undo` 三件套） | ① ② |
| 卖牌从哪张表里移除？ | `Campaign.recoup_card` → **`self.card_deck.pop(position)`**（手牌） | ③ |
| 卖牌返还多少声望？ | **`card.recoup`**（卡牌定义里的独立字段），**不是 `cost`** | ③ + ④ |
| 免费卡返还吗？ | 返还 —— 字节码里 `is_free` **根本没出现**；`recoup` 是 39 种卡全有的静态字段（取值 5–50） | ③ ④ |
| 已用过的牌（`used=True`）？ | **照样移除，但不返还声望**（`if not card.used` 才加钱） | ③ |
| 卖牌会写 L1 吗？ | 手牌本来就是 L1 `cards.yml` —— 游戏内存态 `card_deck` 落盘就是它 | ③ |
| 卖牌影响会议快照吗？ | **会** —— `RecoupCard.do` 先调 `conference_start_state.store_cards(None)` 存一份"卖牌前的手牌+货架+声望"快照 | ② ③ |
| 「恢复上次会议牌局」做什么？ | `_ConferenceStartState.restore` → 用快照 `data['cards']` **整体覆盖**手牌（`card_deck.clear()` + 重新 load） | ③ |

**⇒ 对修改器的影响**

* **删手牌是游戏原生语义** ⇒ `Edit.card_remove(position)` 安全，**给入口**（U8 已拍板）。
* **唯一已知限制**：会议快照在 **L2（只读）**，修改器按 §7.2 W2 不写它
  ⇒ 玩家在游戏里点「恢复上次会议牌局」会把删掉的牌恢复回来。
  这**不是崩溃、不破坏存档自洽**，只是"删牌可被游戏自己的恢复功能撤销"
  ⇒ 界面上写一句提示即可，**不需要二次确认**。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e161_sell_card.py
"""

from __future__ import annotations

import dis
import marshal
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import CorePaths  # noqa: E402

#: 全量扫描用的关键字
SCAN_KEYS = ("sell", "recoup", "discard", "trade", "remove_card")

#: 要深挖的 code 对象
DEEP = {
    "uoc2/state/campaign/conference_actions.pyc": [
        "/RecoupCard", "/RecoupCard/can_perform", "/RecoupCard/do",
        "/RecoupCard/undo",
    ],
    "uoc2/state/campaign/campaign.pyc": [
        "/Campaign/recoup_card", "/Campaign/undo_recoup",
        "/Campaign/remove_card", "/Campaign/get_card_at_position",
        "/_ConferenceStartState/store_cards", "/_ConferenceStartState/restore",
    ],
}


def lib() -> Path:
    gd = CorePaths.discover().game_dir
    if gd is None:
        raise SystemExit("找不到游戏目录（CorePaths.discover().game_dir is None）")
    return gd / "lib"


def load_pyc(rel: str):
    f = lib() / rel
    if not f.is_file():
        return None
    try:
        return marshal.loads(f.read_bytes()[16:])
    except Exception:
        return None


def all_codes(code: types.CodeType, path: str = ""):
    out = []
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            p = path + "/" + k.co_name
            out.append((p, k))
            out.extend(all_codes(k, p))
    return out


def blob_of(k: types.CodeType) -> str:
    return " ".join(
        [k.co_name] + [str(c) for c in k.co_names]
        + [str(c) for c in k.co_consts if isinstance(c, str)]
    ).lower()


def dump(path: str, k: types.CodeType) -> None:
    print()
    print(f"----- {path} -----")
    print(f"  co_names  = {k.co_names}")
    strs = [c for c in k.co_consts if isinstance(c, str)]
    if strs:
        print(f"  co_consts = {strs[:24]}")
    for ins in dis.get_instructions(k):
        if ins.opname.startswith(("LOAD_", "STORE_", "CALL", "BINARY_",
                                  "COMPARE", "RETURN", "POP_", "CONTAINS")):
            print(f"    {ins.opname:24} {ins.argrepr}")


def scan_tree() -> list[tuple[str, str]]:
    """全量扫 `lib/uoc2/**.pyc`，找 recoup / sell / discard 之类字样。"""
    hits: list[tuple[str, str]] = []
    root = lib() / "uoc2"
    for f in sorted(root.rglob("*.pyc")):
        code = load_pyc(f.relative_to(lib()).as_posix())
        if code is None:
            continue
        for path, k in all_codes(code):
            blob = blob_of(k)
            if any(key in blob for key in SCAN_KEYS):
                hits.append((f.relative_to(lib()).as_posix(), path))
    return hits


def main() -> int:
    print("=" * 74)
    print("① 全量扫描 lib/uoc2/**.pyc：recoup / sell / discard / remove_card")
    print("=" * 74)
    hits = scan_tree()
    for f, path in hits:
        print(f"  {f}  ::  {path}")
    if not hits:
        print("  （没有命中）")

    print()
    print("=" * 74)
    print("② conference_actions.pyc 的动作类清单")
    print("=" * 74)
    code = load_pyc("uoc2/state/campaign/conference_actions.pyc")
    if code is not None:
        for path, _ in all_codes(code):
            if path.count("/") == 1:
                print(f"  {path}")

    print()
    print("=" * 74)
    print("③ 关键 code 对象反汇编")
    print("=" * 74)
    for rel, wants in DEEP.items():
        print()
        print(f"### {rel}")
        c = load_pyc(rel)
        if c is None:
            print("  [缺文件]")
            continue
        found = dict(all_codes(c))
        for w in wants:
            if w not in found:
                print(f"  [没有] {w}")
                continue
            dump(w, found[w])

    print()
    print("=" * 74)
    print("④ 卡牌类型定义里的 recoup 字段（39 种）")
    print("=" * 74)
    from save_modifier_core import catalog as catmod
    cat = catmod.Catalog(CorePaths.discover())
    from collections import Counter
    dist: Counter = Counter()
    for n in cat.card_type_names():
        d = cat.card_type(n) or {}
        dist[d.get("recoup")] += 1
    print(f"  recoup 取值分布 = {dict(dist)}")
    print("  ⇒ recoup 是卡牌定义的静态字段，与 is_free 无关；")
    print("    字节码里 RecoupCard.do 只看 card.used，不看 is_free。")

    print()
    print("=" * 74)
    print("结论：游戏原生支持删手牌 ⇒ 修改器可以给「移除」入口")
    print("  唯一限制：会议快照在 L2（只读）⇒ 游戏内「恢复上次会议牌局」")
    print("  可能把删掉的牌带回来（不崩溃、不破坏自洽，界面提示即可）")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
