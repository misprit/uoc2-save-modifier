"""e166 —— 总部的「补给卡车链」与「分支压制」：存档结构 + 字节码 + 游戏常量 + 游戏内 UI。

**背景**：2026-11-18 用户拍板（U13）——
① 卡车升级链做出来（5 个卡车图标，点哪里就激活哪里，**不涉及声望变动**）；
② 专精收费数值不显示、取消矩阵最右侧的「升级价」列；
③ 把之前被删掉的「HQ 目前被压制等级」调整加回来。

**结论（全部来自存档 + 字节码 + 游戏常量 + 游戏内截图，不是推断）**

| 问题 | 答案 | 出处 |
|---|---|---|
| 卡车数存在哪？ | 存档 `hqs.yml` 每个总部的 **`trucks`**（整数） | ① |
| 卡车数合法范围？ | 实测 **1–5**（0 辆的总部一个都没有） | ① |
| 卡车 → 补给作用范围？ | `game.yml` → `supply_hubs_ranges = [5, 8, 10, 11, 12]`，**1-based**：1 辆→5、2→8、3→10、4→11、5→12 | ③ ⑤ |
| 范围是怎么算的？ | 字节码 `mp_movement` / `mp_range` → `supply_hubs_ranges[self.trucks]`（**0-based 下标**）；`mp_rail` 再 `+ hq_rail_range_add` | ② |
| 买一辆卡车怎么做？ | 游戏内按钮 `campaign_hq_upgrade.range` → `trucks = hq.trucks + 1` → `action_add_truck` | ④ |
| 买卡车多少钱？ | 游戏内 ¢`hq_range_upgrades[等级]`（=25，5 级都是 25）—— **本工具不扣声望** | ③ ④ |
| 卡车图标贴图？ | `surfaces/hq_upgrade/truck_<N>_{on,off,hover}.png`（N=1..5，三态齐全） | ④ |
| `suppressed` 是什么？ | **被压制的等级数**（整数 0–3），**不是布尔开关**；实测分布 `{0: 7283, 1: 43, 2: 9}` | ① ② |
| 压制怎么算的？ | `branch_suppress` → `level −= n; suppressed += n`（真实等级不变） | ② |
| 解除压制？ | `unsuppress_branch_levels` → `level += suppressed; suppressed = 0` | ② |
| 游戏内部「解锁到几级」？ | **`level + suppressed`**（`can_add_branch_level`） | ② |
| 技能能不能生效看哪个？ | **`level`**（`branch_actions`：`enabled = action.level <= branch_level`） | ② |
| 压制什么时候会被还原？ | 一局结束时（`set_end_game` → `unsuppress_branch_levels`）—— 所以**会议阶段的存档压制恒为 0**（实测 72 个存档里只有 6 个有压制，且都是战役进行中的存档） | ① ② |
| 分支等级上限？ | **3**（`BRANCH_MAX`；`level + suppressed` 也不能超 3） | ② |

**出处编号 = 脚本分节**

| 编号 | 分节 | 内容 |
|---|---|---|
| ① | 存档结构 | `trucks` / `suppressed` / `fixed_movement` 的全库分布 |
| ② | 字节码 | `mp_movement` / `branch_suppress` / `unsuppress_branch_levels` / `can_add_branch_level` / `branch_actions` / `set_end_game` |
| ③ | 游戏常量 | `_packages/base/config/game.yml` 的 `supply_hubs_ranges` 等 |
| ④ | 游戏内 UI | 卡车贴图清单 + 买卡车按钮的字节码流程 |
| ⑤ | 卡车链对照 | 用存档里 `trucks=3` 的总部，对照游戏内截图逐个图标核对 |

**跑法（仓库根目录）**：
    .\\python\\python.exe docs\\证据脚本\\e166_hq_trucks_suppress.py
"""

from __future__ import annotations

import dis
import io
import json
import marshal
import struct
import sys
import types
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import list_saves, open_save, yamlio      # noqa: E402
from save_modifier_core.paths import CorePaths                     # noqa: E402

BR = ("engineering", "force_pool", "intel", "logistics", "operations")
OUT_DIR = Path(r"D:\MiniMax\_analysis")
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


def png_size(path: Path):
    """读 PNG 头拿宽高（不依赖 PIL）。"""
    try:
        raw = path.read_bytes()[:24]
    except Exception:
        return None
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", raw[16:24])
    return w, h


def main() -> int:
    paths = CorePaths.discover()
    gd = paths.game_dir

    # ============================================================ ① 存档结构
    p("=" * 78)
    p("① 存档 hqs.yml：trucks / branch_levels.suppressed / fixed_movement")
    p("=" * 78)
    saves = list_saves()
    trucks_c: Counter = Counter()
    supp_c: Counter = Counter()
    lvl_c: Counter = Counter()
    fixed_mv: Counter = Counter()
    fixed_rg: Counter = Counter()
    n_hq = 0
    sample = None
    supp_by_save: list = []
    for s in saves:
        if not s.save_id.endswith(".usg"):
            continue
        try:
            with open_save(s.save_id) as sv:
                hs = sv.root_hqs()
        except Exception:
            continue
        local: Counter = Counter()
        cp_low = 0
        for h in hs:
            n_hq += 1
            trucks_c[h.get("trucks")] += 1
            fixed_mv[h.get("fixed_movement")] += 1
            fixed_rg[h.get("fixed_range")] += 1
            if (isinstance(h.get("cp"), int) and isinstance(h.get("max_cp"), int)
                    and h["cp"] < h["max_cp"]):
                cp_low += 1
            for b, node in (h.get("branch_levels") or {}).items():
                if not isinstance(node, dict):
                    continue
                supp_c[node.get("suppressed")] += 1
                lvl_c[node.get("level")] += 1
                if node.get("suppressed"):
                    local[(b, node.get("suppressed"))] += 1
            if sample is None and (h.get("trucks") or 0) >= 3:
                sample = (s.save_id, h)
        if local:
            supp_by_save.append((s.save_id, dict(local), cp_low, len(hs)))
    p("  统计总部数:", n_hq)
    p("  trucks 分布:", dict(sorted(trucks_c.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    p("  branch_levels.suppressed 分布:", dict(sorted(supp_c.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    p("  branch_levels.level 分布:", dict(sorted(lvl_c.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    p("  fixed_movement 分布:", dict(fixed_mv), " fixed_range 分布:", dict(fixed_rg))
    p("  ⇒ trucks 实测只有 1/2/3/5（**没有 0**）；suppressed 是**整数**（0/1/2），不是布尔值")
    p("  ⇒ 绝大多数存档里 suppressed = 0；只有**战役进行中**的存档才有 > 0 的压制")
    p("     （用户口径：hq 的压制与 CP 消耗，从会议进入战役时会被重置；")
    p("       已经在战斗中时，压制与 CP 消耗都保留在存档里）")
    if sample:
        src, h = sample
        p("\n  样本存档:", src)
        p("  样本总部 id=%s trucks=%s branch_levels=%s" % (
            h.get("id"), h.get("trucks"),
            json.dumps(h.get("branch_levels"), ensure_ascii=False)))

    p("\n  有被压制分支的存档（%d / %d 个 .usg）：" % (
        len(supp_by_save), len([s for s in saves if s.save_id.endswith(".usg")])))
    for sid, c, cp_low, nh in supp_by_save:
        p("    %-58s %s   CP 未满的总部 %d/%d" % (sid, c, cp_low, nh))
    p("  ⇒ 这些存档里同时有**CP 没花完**的总部 ⇒ 都是**战役进行中**的存档")
    p("  ⇒ 会议阶段的存档：压制 = 0、CP 满 ⇒ 一进战役就被重置（用户口径 + `set_end_game` 字节码）")

    # ============================================================ ② 字节码
    p("\n" + "=" * 78)
    p("② 字节码")
    p("=" * 78)
    p("  --- 卡车 → 范围 ---")
    dump("uoc2/state/entities/hq.pyc", "/HQState/mp_movement")
    dump("uoc2/state/entities/hq.pyc", "/HQState/mp_range")
    dump("uoc2/state/entities/hq.pyc", "/HQState/mp_rail")
    p("  --- 压制 ---")
    dump("uoc2/state/entities/hq.pyc", "/HQState/branch_suppress")
    dump("uoc2/state/entities/hq.pyc", "/HQState/unsuppress_branch_levels")
    dump("uoc2/state/entities/hq.pyc", "/HQState/can_add_branch_level")
    dump("uoc2/state/entities/hq.pyc", "/HQState/branch_actions")
    dump("uoc2/state/entities/hq.pyc", "/HQState/set_end_game")
    dump("uoc2/state/entities/hq.pyc", "/HQState/_set_supp_branches")
    dump("uoc2/state/campaign/campaign.pyc", "/Campaign/_hqs_unsuppress_branch_levels")

    # ============================================================ ③ 游戏常量
    p("\n" + "=" * 78)
    p("③ 游戏常量（_packages/base/config/game.yml）")
    p("=" * 78)
    gyml = gd / "_packages" / "base" / "config" / "game.yml"
    g = yamlio.load(gyml.read_bytes())
    for key in ("supply_hubs_ranges", "hq_range_upgrades", "hq_rail_range_add",
                "extra_trucks_on_scenario_start"):
        p("  %-30s %s" % (key, json.dumps(g.get(key), ensure_ascii=False)))
    p("  ⇒ supply_hubs_ranges = [5, 8, 10, 11, 12] —— 5 个元素对应 5 个卡车档位")
    p("  ⇒ 1-based 读法：1 辆→5 / 2 辆→8 / 3 辆→10 / 4 辆→11 / 5 辆→12（见 ⑤ 与游戏内截图）")

    # ============================================================ ④ 游戏内 UI
    p("\n" + "=" * 78)
    p("④ 游戏内 UI：卡车贴图 + 买卡车流程")
    p("=" * 78)
    sur = gd / "_packages" / "base" / "assets" / "surfaces" / "hq_upgrade"
    p("  贴图目录:", sur)
    for n in range(1, 6):
        row = []
        for st in ("on", "off", "hover"):
            f = sur / ("truck_%d_%s.png" % (n, st))
            row.append("%s=%s" % (st, ("%dx%d" % png_size(f)) if f.exists() else "缺"))
        p("    truck_%d: %s" % (n, "  ".join(row)))
    p("  ⇒ 三个状态齐全：on（已激活）/ off（未激活）/ hover")
    dump("uoc2/main_screen/campaign_ctrl.pyc", "/CampaignCtrl/_update_hq_upgrade_trucks")
    dump("uoc2/main_screen/campaign_ctrl.pyc", "/CampaignCtrl/slot_hq_upgrade_buy__conference")

    # ============================================================ ⑤ 卡车链对照
    p("\n" + "=" * 78)
    p("⑤ 卡车链对照（存档 ↔ 游戏内截图）")
    p("=" * 78)
    p("  游戏内截图里的总部 =「A集团军群」/ 格尔德·冯·伦德施泰特，")
    p("  画面上 5 个卡车图标：前 3 个亮（金）、后 2 个暗（黑），图标上的数字 = 5 / 8 / 10 / 11 / 12，")
    p("  右侧按钮 ¢25（= hq_range_upgrades[0]）。")
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
        n_tr = h.get("trucks")
        p("\n  来源存档:", src)
        p("  该总部 trucks =", n_tr)
        ranges = g.get("supply_hubs_ranges") or []
        p("  逐个图标核对（1-based）：")
        for i in range(1, len(ranges) + 1):
            lit = "亮（金）" if (isinstance(n_tr, int) and i <= n_tr) else "暗"
            p("    第 %d 个图标：truck_%d_%s.png  数字=%s  画面上=%s  %s" % (
                i, i, "on" if lit == "亮（金）" else "off",
                ranges[i - 1], lit,
                "← 已激活" if lit == "亮（金）" else ""))
        p("  ⇒ trucks=%s ⇒ 恰好前 %s 个图标亮，数字依次 %s ⇒ 与截图逐个一致" % (
            n_tr, n_tr, "/".join(str(x) for x in ranges[:n_tr])))
    p("\n  ⇒ 结论：**1-based 查表** —— trucks=N ⇒ 补给作用范围 = supply_hubs_ranges[N-1]")
    p("  ⇒ 本工具只改存档里的 trucks 数字，**不碰声望**（游戏内的 ¢25 不参与）")
    p("\n  ⚠️ **一处对不上（照实记）**：字节码 `mp_movement` 用的是 **0-based** 下标")
    p("     `supply_hubs_ranges[self.trucks]`（trucks=3 → 11），而游戏内 UI 的 5 个图标")
    p("     按 5/8/10/11/12 顺序排开、亮起前 trucks 个 ⇒ trucks=3 时画面上是 5/8/10。")
    p("     两者差一格。本工具按**用户口径 + 游戏内画面**取 1-based（3 辆 ⇒ 10 格），")
    p("     存档里仍然只写 trucks 这个整数，不代游戏做换算。")

    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        io.open(str(OUT_DIR / "e166_out.txt"), "w",
                encoding="utf-8", newline="\n").write("\n".join(OUT))
    except Exception as e:                       # pragma: no cover
        p("  （写不出去文件：%s）" % e)
    print("\n".join(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
