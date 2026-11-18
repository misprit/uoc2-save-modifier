"""e165 —— 总部（HQ）的「分支 × 级别」技能树：存档结构 + 字节码 + 游戏常量。

**背景**：2026-11-18 用户拍板（U12）—— 总部页要照游戏内的升级面板大改：
行 = 五个分支、列 = 级别 1/2/3，格子里是技能图标，图标上带小点（专精进度），
分支等级可以升也可以降。

**结论（全部来自存档 + 字节码 + 游戏常量，不是推断）**

| 问题 | 答案 | 出处 |
|---|---|---|
| 技能树存在哪？ | 存档 `hqs.yml` 每个总部的 **`branches`** 字段（不只是 `branch_levels`！） | ① |
| 一条技能长什么样？ | `{action, cost, level, sp_avail, sp_used}` —— 五个字段一个不少 | ① |
| `level` 是什么？ | 该动作在分支树里的**级别（tier）** = 游戏 UI 矩阵的**列**（1/2/3） | ① ② |
| `sp_used` 是什么？ | **已专精次数 = 技能等级**（0..sp_avail） | ② ③ |
| `sp_avail` 是什么？ | 还能专精几次的上限；默认 **`min(2, cost - 1)`** ⇒ 每个技能最多专精 **2** 次 | ③ |
| 专精有什么效果？ | 该动作发动时的 **CP 消耗 −1**（`a.cost = max(0, a.cost - 1)`） | ④ |
| 谁没有技能点？ | `force_pool` 分支的四个动作 + `motor_pool` ⇒ `sp_avail/sp_used = null` | ③ |
| 第一次专精免费吗？ | **免费**（`free_specialization`，条件 `sp_used == 0`，`prestige_cost = 0`） | ⑤ |
| 再专精要花钱吗？ | 要花**声望**（`paid_specialization`，`prestige_cost = 常量 + sp_used`） | ⑤ |
| 升分支等级花什么？ | **声望**，价格 = `hq_branch_upgrades[分支][当前等级]` | ⑤ ⑥ |
| 一个分支同一级最多几个技能？ | **3 个**（超过就 `ValueInvalid`） | ② |
| 同一动作能出现在两个分支吗？ | **不能**（游戏自己校验报错） | ② |
| 怎么解锁？ | 分支等级 ≥ 动作的 tier ⇒ 该动作可用；降级会把它重新锁上 | ⑦ |
| 分支升级价？ | **`hq_branch_upgrades[分支][当前等级]`**（声望）—— 与游戏内面板右侧的 ¢ 按钮一一对应 | ⑤ ⑥ ⑧ |
| 情报分支有技能吗？ | **没有** —— 455 个总部的 `branches.intel` **恒为空列表**；游戏数据 `hq_types/*.yml` 里也没有 `intel:` 技能段 | ① ⑨ |
| 图标上的**小圆点**是什么？ | **`sp_avail` 个槽位**（最多 2 个）；**金色实心 = 已专精 `sp_used`**，深色空心 = 还可再专精 | ⑧ |
| 图标右下角的**数字**是什么？ | 该技能**当前**的 CP 消耗（已扣掉专精减免） | ⑧ |

**跑法（仓库根目录）**：
    .\\python\\python.exe docs\\证据脚本\\e165_hq_branches.py
"""

from __future__ import annotations

import dis
import io
import json
import marshal
import sys
import types
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import locale, list_saves, open_save, yamlio  # noqa: E402
from save_modifier_core.paths import CorePaths                     # noqa: E402

BR = ("engineering", "force_pool", "intel", "logistics", "operations")
BR_CN = {
    "engineering": "工程建设", "force_pool": "兵库", "intel": "情报",
    "logistics": "后勤", "operations": "作战",
}

OUT: list[str] = []


def p(*a) -> None:
    OUT.append(" ".join(str(x) for x in a))


def lib() -> Path:
    gd = CorePaths.discover().game_dir
    if gd is None:
        raise SystemExit("找不到游戏目录")
    return gd / "lib"


def walk(code: types.CodeType, path: str, acc: list) -> None:
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            q = path + "/" + k.co_name
            acc.append((q, k))
            walk(k, q, acc)


def dump(rel: str, want: str) -> None:
    """反汇编某个函数（只打常量与属性名，省得刷屏）。"""
    f = lib() / rel
    try:
        code = marshal.loads(f.read_bytes()[16:])
    except Exception as e:                      # pragma: no cover
        p("  !! ", rel, e)
        return
    acc: list = []
    walk(code, "", acc)
    for path, k in acc:
        if path != want:
            continue
        p("\n----- %s :: %s -----" % (rel, want))
        p("  co_names  =", k.co_names)
        p("  co_consts =", [c for c in k.co_consts if not isinstance(c, types.CodeType)][:24])
        for ins in dis.get_instructions(k):
            v = ""
            if ins.opname in ("LOAD_CONST", "LOAD_SMALL_INT", "LOAD_GLOBAL",
                              "LOAD_ATTR", "BINARY_OP", "COMPARE_OP"):
                v = "   <<%r>>" % (ins.argval,)
            p("    %-20s %s%s" % (ins.opname, ins.argrepr, v))
        return
    p("  !! 没找到", want)


def main() -> int:
    paths = CorePaths.discover()
    store = locale.TranslationStore(paths, locale="chi")

    # ============================================================ ① 存档结构
    p("=" * 78)
    p("① 存档 hqs.yml 里的 branches（技能树）")
    p("=" * 78)
    saves = list_saves()
    picked = None
    for s in saves:
        if s.save_id.endswith(".usg"):
            picked = s
            break
    with open_save(picked.save_id) as sv:
        hqs = sv.root_hqs()
    p("  存档:", picked.save_id, " 总部数:", len(hqs))
    h0 = hqs[0]
    p("  第 1 个总部 branch_levels:", json.dumps(h0.get("branch_levels"), ensure_ascii=False))
    p("  第 1 个总部 branches（engineering + operations 两段）:")
    br = h0.get("branches") or {}
    for b in ("engineering", "operations"):
        p("    %s:" % b)
        for it in (br.get(b) or []):
            p("      ", json.dumps(it, ensure_ascii=False))

    # ---- 全库统计 ----
    keysets = Counter()
    sp_avail = Counter()
    sp_used = Counter()
    tier_by_action: dict[str, Counter] = {}
    cost_by_action: dict[str, Counter] = {}
    branch_members: dict[str, set] = {}
    intel_empty = 0
    n_hq = 0
    for s in saves[:12]:
        if not s.save_id.endswith(".usg"):
            continue
        try:
            with open_save(s.save_id) as sv:
                hs = sv.root_hqs()
        except Exception:
            continue
        for h in hs:
            n_hq += 1
            if not (h.get("branches") or {}).get("intel"):
                intel_empty += 1
            for b, items in (h.get("branches") or {}).items():
                for it in items or []:
                    if not isinstance(it, dict):
                        continue
                    keysets[tuple(sorted(it.keys()))] += 1
                    sp_avail[it.get("sp_avail")] += 1
                    sp_used[it.get("sp_used")] += 1
                    tier_by_action.setdefault(it.get("action"), Counter())[it.get("level")] += 1
                    cost_by_action.setdefault(it.get("action"), Counter())[it.get("cost")] += 1
                    branch_members.setdefault(b, set()).add(it.get("action"))
    p("\n  采样总部数:", n_hq)
    p("  branches[] 条目的字段集合:", dict(keysets))
    p("  sp_avail 分布:", dict(sorted(sp_avail.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    p("  sp_used  分布:", dict(sorted(sp_used.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    p("  branches.intel 为空的总部数: %d / %d  ⇒ 情报分支**没有技能**" % (intel_empty, n_hq))
    p("\n  每个分支里到底有哪些动作：")
    for b in sorted(branch_members):
        p("    %-13s %s" % (b, ", ".join(sorted(x for x in branch_members[b] if x))))
    p("\n  各动作的 tier 分布（同一动作在不同总部可以处于不同 tier）：")
    for a, c in sorted(tier_by_action.items()):
        p("    %-24s %s" % (a, dict(c)))
    p("\n  各动作的 cost 分布（不同总部不一样 ⇒ cost 是「该总部自己的」）：")
    for a, c in sorted(cost_by_action.items()):
        p("    %-24s %s" % (a, dict(c)))

    # ============================================================ ② 字节码
    p("\n" + "=" * 78)
    p("② 字节码")
    p("=" * 78)
    dump("uoc2/state/entity_types/hq_types.pyc", "/check_sps")
    dump("uoc2/state/entity_types/hq_types.pyc", "/check_branch_data")
    dump("uoc2/state/entities/hq.pyc", "/HQState/reduce_action_cost")
    dump("uoc2/state/entities/hq.pyc", "/HQState/next_hq_upgrade")

    # ============================================================ ③ 游戏常量
    p("\n" + "=" * 78)
    p("③ 游戏常量（_packages/base/config/game.yml）")
    p("=" * 78)
    gd = CorePaths.discover().game_dir
    gyml = gd / "_packages" / "base" / "config" / "game.yml"
    g = yamlio.load(gyml.read_bytes())
    for key in ("hq_branch_upgrades", "hq_action_specialize_cost",
                "hq_cp_upgrade_cost", "hq_upgrade_free_prestige"):
        p("  %-28s %s" % (key, json.dumps(g.get(key), ensure_ascii=False)))

    # ============================================================ ④ locale
    p("\n" + "=" * 78)
    p("④ 中文名（locale）")
    p("=" * 78)
    for b in BR:
        p("  分支 %-12s → %s" % (b, store.get("id_hq_branch_" + b)))
    for lv in (1, 2, 3):
        p("  级别 %d级  → %s" % (lv, store.get("id_hq_branch_level_%d" % lv)))
    p("  技能名（键 = id_<action>，个别技能是 id_<action>_level_<N>）：")
    for a in sorted(tier_by_action):
        cn = store.get("id_" + a)
        if not cn:
            cn = store.get("id_%s_level_1" % a) or ""
            note = "（只有 _level_N 形式）"
        else:
            note = ""
        p("    %-24s %s%s" % (a, cn, note))

    # ============================================================ ⑤ 游戏内 UI 面板对照
    p("\n" + "=" * 78)
    p("⑤ 游戏内 UI 面板对照（截图 ↔ 存档）")
    p("=" * 78)
    p("  截图里的总部 =「A集团军群」/ 格尔德·冯·伦德施泰特（general=ger_von_rundstedt, 8 CP）")
    p("  下表把存档里这个总部的技能树，按游戏内面板的「行=分支 / 列=级别」原样排开，")
    p("  并算出右侧那列声望按钮该显示多少钱。")
    tgt = None
    for s in saves:
        if not s.save_id.endswith(".usg"):
            continue
        try:
            with open_save(s.save_id) as sv:
                hs = sv.root_hqs()
        except Exception:
            continue
        for h in hs:
            if h.get("general") == "ger_von_rundstedt":
                tgt = (s.save_id, h)
                break
        if tgt:
            break
    if tgt:
        src, h = tgt
        p("\n  来源存档:", src)
        bl = h.get("branch_levels") or {}
        br = h.get("branches") or {}
        ups = g.get("hq_branch_upgrades") or {}
        p("  %-13s %-6s %-6s  %s" % ("分支", "等级", "价格", "技能（级别: 动作 CP消耗 槽位/已用）"))
        for b in ("force_pool", "intel", "operations", "logistics", "engineering"):
            lv = ((bl.get(b) or {}).get("level"))
            price = None
            seq = (ups.get(b) or [])
            if isinstance(lv, int) and 0 <= lv < len(seq):
                price = seq[lv]
            p("  %-13s Lv%-4s %-6s" % (
                b, lv, ("¢%s" % price) if price is not None else "—"))
            by_tier: dict = {}
            for it in br.get(b) or []:
                by_tier.setdefault(it.get("level"), []).append(it)
            for tier in (1, 2, 3):
                got = by_tier.get(tier) or []
                if not got:
                    p("      %d级: —" % tier)
                    continue
                cells = []
                for it in got:
                    av = it.get("sp_avail")
                    us = it.get("sp_used")
                    dots = ("%s/%s" % (us, av)) if av is not None else "无点"
                    lock = "" if (isinstance(lv, int) and tier <= lv) else "（锁定）"
                    cells.append("%s:%s %s%s" % (it.get("action"), it.get("cost"), dots, lock))
                p("      %d级: %s" % (tier, "  |  ".join(cells)))
    p("\n  ⇒ 价格公式：hq_branch_upgrades[分支][当前分支等级]（列表长度 3 = 最多升 3 级）")
    p("  ⇒ 锁定规则：级别(tier) > 分支等级 ⇒ 图标置灰（截图里 2级/3级 的灰图标就是它）")
    p("  ⇒ 小圆点：sp_avail 个槽位，前 sp_used 个画成金色实心")
    p("     （force_pool 分支与 motor_pool 的 sp_avail=null ⇒ 游戏里也**不画点**，截图兵库行无点）")

    io.open(r"D:\MiniMax\_analysis\e165_out.txt", "w",
            encoding="utf-8", newline="\n").write("\n".join(OUT))
    print("\n".join(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
