"""e158 —— 卡牌商店的生成与购买机制（字节码实证）。

**背景**：e157 证实 `main.yml.card_store` 就是「卡牌商店货架」。
本脚本回答剩下的三个问题：

  1. **货架从哪来？** —— 进入会议时按**权重**抽取生成；
     权重 = 全局基础表 → 公共会议覆盖 → 前线缩放，三层叠加。
  2. **购买做了什么？** —— 扣**声望**（不是 CP），`card_store.pop(position)` + 进手牌。
  3. **能不能改？** —— `Campaign.load` 直接读存档（**不重掷**），
     重掷只发生在 `set_conference`（进入**新**会议时）⇒ 货架可改，但会被下次会议覆盖。

**关键常量**（`uoc2/state/constants.pyc`，按难度 easy/normal/classic/hard）：

  | 常量 | 含义 | 值 |
  |---|---|---|
  | `card_store_limit` | 货架格数 | 5 / 5 / 5 / 5 |
  | `card_store_free_cards` | 免费几张 | 2 / 1 / 0 / 0 |
  | `card_deck_limit` | 手牌上限 | 5 / 5 / 4 / 3 |

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e158_cardshop_bytecode.py
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
from save_modifier_core import catalog as catmod  # noqa: E402


def _lib() -> Path:
    gd = CorePaths.discover().game_dir
    if gd is None:
        raise SystemExit("找不到游戏目录（CorePaths.discover().game_dir is None）")
    return gd / "lib"


def all_codes(code: types.CodeType, path: str = ""):
    """递归列出模块里所有嵌套 code 对象，带路径名。"""
    out = []
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            p = path + "/" + k.co_name
            out.append((p, k))
            out.extend(all_codes(k, p))
    return out


def load_pyc(rel: str):
    f = _lib() / rel
    if not f.is_file():
        return None
    try:
        return marshal.loads(f.read_bytes()[16:])
    except Exception:
        return None


def _kw_dict_call(instrs: list, idx: int) -> dict | None:
    """向前解析 `dict(easy=5, normal=5, ...)` 形式的构造。

    字节码形如：
        LOAD_NAME 'dict' / PUSH_NULL / <值…> / LOAD_CONST (键元组) / CALL_KW n
    ⇒ 键元组给名字，前 n 个值依次对应。
    """
    for j in range(idx, max(idx - 40, -1), -1):
        if instrs[j].opname != "CALL_KW":
            continue
        n = instrs[j].arg
        keys = instrs[j - 1].argval
        if not isinstance(keys, tuple) or len(keys) != n:
            return None
        vals: list = []
        k = j - 2
        while len(vals) < n and k >= 0:
            o = instrs[k]
            if o.opname in ("LOAD_SMALL_INT", "LOAD_CONST"):
                vals.append(o.argval)
            k -= 1
        vals.reverse()
        return dict(zip(keys, vals))
    return None


def dump_const_dicts(rel: str, want: tuple[str, ...]) -> None:
    code = load_pyc(rel)
    if code is None:
        print(f"  [缺文件] {rel}")
        return
    instrs = list(dis.get_instructions(code))
    for i, ins in enumerate(instrs):
        if ins.opname != "STORE_NAME" or ins.argval not in want:
            continue
        d = _kw_dict_call(instrs, i)
        if d is not None:
            print(f"  {ins.argval} = {d}")
        else:
            print(f"  {ins.argval}: [未识别构造形式]")


def simple_numeric_assigns(code: types.CodeType) -> dict[str, object]:
    """模块级 `NAME = <数字常量>` 的简易赋值表（LOAD_SMALL_INT 与 LOAD_CONST 都算）。"""
    out: dict[str, object] = {}
    instrs = list(dis.get_instructions(code))
    for i, ins in enumerate(instrs):
        if ins.opname != "STORE_NAME":
            continue
        for back in range(i - 1, max(i - 8, -1), -1):
            b = instrs[back]
            if b.opname in ("LOAD_SMALL_INT", "LOAD_CONST") and isinstance(b.argval, (int, float)):
                out[ins.argval] = b.argval
                break
    return out


def section_constants() -> None:
    print("=" * 72)
    print("### A. 三个常量（uoc2/state/constants.pyc）")
    dump_const_dicts(
        "uoc2/state/constants.pyc",
        ("card_store_limit", "card_store_free_cards", "card_deck_limit"),
    )
    print("  ⇒ 键序固定为 ('easy', 'normal', 'classic', 'hard')。")


def section_base_probs() -> None:
    print("\n" + "=" * 72)
    print("### B. 基础抽卡权重（uoc2/state/entity_types/card_types.pyc）")
    code = load_pyc("uoc2/state/entity_types/card_types.pyc")
    if code is None:
        print("  [缺文件]")
        return
    nums = simple_numeric_assigns(code)
    instrs = list(dis.get_instructions(code))
    idx = None
    for i, ins in enumerate(instrs):
        if ins.opname == "STORE_NAME" and ins.argval == "card_meta_types_base_probabilities":
            idx = i
            break
    if idx is None:
        print("  [未找到 card_meta_types_base_probabilities]")
        return
    table: dict[str, object] = {}
    key = None
    val: object = None
    for ins in instrs[max(0, idx - 90):idx]:
        if ins.opname == "LOAD_CONST" and isinstance(ins.argval, str):
            key = ins.argval
        elif ins.opname == "LOAD_NAME":
            val = nums.get(ins.argval, f"<{ins.argval}>")
        elif ins.opname == "MAP_ADD" and key is not None:
            table[key] = val
            key = None
    print(f"  档位定义: "
          + ", ".join(f"{k}={v}" for k, v in sorted(nums.items())
                      if k.startswith("_p_pot")))
    print(f"  条目数: {len(table)}")
    for k, v in table.items():
        print(f"    {k:24s} = {v}")
    print("  ⇒ 三档权重：_p_pot_1=15 / _p_pot_2=6 / _p_pot_3=3。")


def show_code(rel: str, wanted: set[str], lines: int = 46) -> None:
    code = load_pyc(rel)
    if code is None:
        print(f"  [缺文件] {rel}")
        return
    print(f"\n--- {rel} ---")
    for path, c in all_codes(code):
        if path in wanted:
            print(f"\n  === {path} ===")
            print("   varnames:", c.co_varnames[:c.co_argcount])
            print("   names   :", c.co_names)
            strs = [x for x in c.co_consts if isinstance(x, str)]
            print("   strs    :", strs[:20])
            try:
                body = dis.Bytecode(c).dis().splitlines()
            except Exception as e:  # pragma: no cover
                print("   dis 失败:", e)
                continue
            for ln in body[:lines]:
                print("   ", ln)


def section_buy_card() -> None:
    print("\n" + "=" * 72)
    print("### C. 购买动作（uoc2/state/campaign/conference_actions.pyc :: BuyCard）")
    show_code(
        "uoc2/state/campaign/conference_actions.pyc",
        {
            "/BuyCard/can_perform",
            "/BuyCard/do",
            "/BuyCard/undo",
            "/BuyCard/__init__",
        },
    )
    print("\n  ⇒ 关键点：价格来自 card_types 的 cost，扣的是 prestige；"
          "成功后 card_store.pop(position)，牌进手牌。")


def section_load_vs_conference() -> None:
    print("\n" + "=" * 72)
    print("### D. 加载 vs 进会议（uoc2/state/campaign/campaign.pyc）")
    show_code(
        "uoc2/state/campaign/campaign.pyc",
        {
            "/Campaign/load",
            "/Campaign/set_conference",
            "/Campaign/create_random_card_data",
            "/Campaign/get_cards_probabilities",
            "/Campaign/get_store_cards",
        },
        lines=30,
    )
    print("\n  ⇒ load 读存档的 card_store（不重掷）；"
          "set_conference 才 create_random_card_data 重掷货架。")


def section_weight_chain() -> None:
    print("\n" + "=" * 72)
    print("### E. 权重链的三层函数")
    show_code(
        "uoc2/state/campaign/campaign_doc.pyc",
        {
            "/CampaignDoc/get_base_cards_probabilities",
            "/CampaignDoc/get_cards_probabilities",
        },
        lines=34,
    )
    show_code(
        "uoc2/state/campaign/conferences.pyc",
        {
            "/CommonConferences/get_card_probabilities",
            "/Conferences/get_card_probability_scales",
        },
        lines=20,
    )
    print("\n  ⇒ 链路：get_base_cards_probabilities()（= 基础表 15/6/3）"
          "\n     → .update(common_conferences.get_card_probabilities(conferences))"
          "\n     → 再按 fronts.get_card_probability_scales(front) 缩放。")


def section_package_weights() -> None:
    print("\n" + "=" * 72)
    print("### F. 战役包里的会议抽卡权重（第二/第三层）")
    cat = catmod.default()
    for cid in ("blitzkrieg", "barbarossa"):
        cdir = cat.campaign_dir(cid)
        print(f"\n  --- campaign_dir({cid}) = {cdir}")
        if not cdir or not cdir.is_dir():
            continue
        empty = 0
        shown = 0
        for f in sorted(cdir.rglob("conferences/*.yml")):
            try:
                d = catmod.yamlio.load(f.read_bytes())
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            cp = d.get("card_probabilities")
            cps = d.get("card_probability_scales")
            # 注意：空 dict 也是"这一层没覆盖"，不能用真值判断
            if cp is None and cps is None:
                continue
            if not cp and not cps:
                empty += 1
                continue
            if shown >= 4:
                continue
            shown += 1
            print(f"    {f.relative_to(cdir)}")
            if cp:
                print(f"      card_probabilities      = {cp}")
            if cps:
                print(f"      card_probability_scales = {cps}")
        print(f"    （另有 {empty} 个会议文件这两项都是空 dict ⇒ 该层未覆盖，"
              f"沿用全局基础表）")
    print("\n  ⇒ 覆盖层用的键就是基础表那 18 个 meta_type，值是浮点权重；"
          "\n     空 dict = 该层不覆盖。")


def main() -> None:
    section_constants()
    section_base_probs()
    section_buy_card()
    section_load_vs_conference()
    section_weight_chain()
    section_package_weights()


if __name__ == "__main__":
    main()
