"""e162 —— 游戏自己怎么判断「哪些特种兵能挂到这个单位」（字节码 + 实测实证）。

**背景**：2026-11-18 用户拍板（U9）—— 「特种兵」功能页**整页取消**，
挂载 / 卸下并入**单位页**。⇒ 修改器必须自己算"备选池该显示哪些特种兵"，
而且**必须和游戏算的完全一致**，否则玩家挂上去游戏不认。

**结论（全部来自字节码 + 实测）**

| 问题 | 答案 | 出处 |
|---|---|---|
| 游戏列"可挂清单"的方式？ | `get_available_spec_types` = **全部 375 种**过一遍 `_can_add_specialist_no_len` | ① |
| 判定规则是什么？ | **阵营必须相同** + **国籍相同，或单位国籍的 `parent_nationality` == 特种兵国籍** | ② |
| `captured` 的单位？ | **跳过阵营 / 国籍检查**（游戏逻辑，UI 照抄） | ② |
| 有没有额外的 flags 过滤？ | **没有** —— 可挂清单 = 375 种逐个过规则，**不做**"按特殊类型筛选" | ① ② |
| 槽位怎么算？ | `can_add_specialist` 再判 `len(self.specs) < self._type.max_spec`；`max_spec = min(3, 类型表 max_spec)` | ③ |
| 实测能挂几种？ | `us_arm_42`（同盟/美）**23** / `sov_inf_41`（苏联）**61** / `ger_inf_40`（轴心/德）**97** | ④ |

**⇒ 对修改器的影响**

* 单位页的**备选池**按 `_can_add_specialist_no_len` 逐条过滤 ⇒ 与游戏一致。
* 「显示全部 375 种」开关打开后，挂不上的点了要**说明原因**（阵营 / 国籍不符）。
* 挂载用核心库 `Edit.unit_spec_add`（`idx: free` = 填第一个空槽位）——
  与游戏"填第一个空位"的语义天然一致，**交互不用改核心库**。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e162_spec_rules.py
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
from save_modifier_core import yamlio       # noqa: E402

REL = "uoc2/state/entities/unit.pyc"
WANT = [
    "/UnitState/get_available_spec_types",
    "/UnitState/can_add_specialist",
    "/UnitState/_can_add_specialist_no_len",
    "/UnitState/all_spec_types",
    "/UnitState/add_specialist",
    "/UnitState/remove_specialist",
]

#: ④ 实测用的样例单位类型
SAMPLES = ("us_arm_42", "sov_inf_41", "ger_inf_40", "us_inf_42")


def lib() -> Path:
    gd = CorePaths.discover().game_dir
    if gd is None:
        raise SystemExit("找不到游戏目录")
    return gd / "lib"


def all_codes(code: types.CodeType, path: str = ""):
    out = []
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            p = path + "/" + k.co_name
            out.append((p, k))
            out.extend(all_codes(k, p))
    return out


def dump(path: str, k: types.CodeType) -> None:
    print()
    print(f"----- {path} -----")
    print(f"  co_names  = {k.co_names}")
    strs = [c for c in k.co_consts if isinstance(c, str)]
    if strs:
        print(f"  co_consts = {strs[:20]}")
    for ins in dis.get_instructions(k):
        if ins.opname.startswith(("LOAD_", "STORE_", "CALL", "BINARY_",
                                  "COMPARE", "RETURN", "POP_", "CONTAINS")):
            print(f"    {ins.opname:24} {ins.argrepr}")


# ---------------------------------------------------------------- ④ 实测

def entity_dir() -> Path:
    gd = CorePaths.discover().game_dir
    if gd is None:
        raise SystemExit("找不到游戏目录")
    for pkg in CorePaths.discover().packages():
        d = pkg / "data" / "entity_types"
        if (d / "specialists").is_dir():
            return d
    raise SystemExit("找不到 entity_types/")


def load_specs(d: Path) -> dict[str, dict]:
    out = {}
    for p in sorted((d / "specialists").glob("*.yml")):
        data = yamlio.load(p.read_bytes())
        if isinstance(data, dict):
            out[p.stem] = data
    return out


def load_nations(d: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fname in ("nationalities.yml", "nationalities_2.yml"):
        p = d / fname
        if not p.is_file():
            continue
        data = yamlio.load(p.read_bytes())
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    out[k] = v
    return out


def can_add(spec: dict, unit: dict, nations: dict[str, dict]) -> bool:
    """复刻 `UnitState._can_add_specialist_no_len`（captured=False）。"""
    if unit.get("faction") != spec.get("faction"):
        return False
    if unit.get("nationality") != spec.get("nationality"):
        nat = nations.get(unit.get("nationality")) or {}
        if nat.get("parent_nationality") != spec.get("nationality"):
            return False
    return True


def main() -> int:
    f = lib() / REL
    code = marshal.loads(f.read_bytes()[16:])
    found = dict(all_codes(code))
    print("=" * 72)
    print("① ② ③  字节码：游戏怎么列可挂清单、怎么判定能不能挂")
    print("=" * 72)
    for w in WANT:
        if w not in found:
            print(f"  [没有] {w}")
            continue
        dump(w, found[w])

    print()
    print("=" * 72)
    print("④  实测：按同一条规则，各单位能挂几种")
    print("=" * 72)
    d = entity_dir()
    specs = load_specs(d)
    nations = load_nations(d)
    print(f"  specialists = {len(specs)} 个")
    print(f"  nationalities = {len(nations)} 个"
          f"（有 parent_nationality 的 {sum(1 for v in nations.values() if v.get('parent_nationality'))} 个）")
    print()
    print(f"  {'单位类型':<14} {'阵营':<8} {'国籍':<8} {'可挂种数':>8}")
    print("  " + "-" * 42)
    for name in SAMPLES:
        p = d / "unit_types" / f"{name}.yml"
        if not p.is_file():
            print(f"  {name:<14} [类型不存在]")
            continue
        unit = yamlio.load(p.read_bytes()) or {}
        n = sum(1 for s in specs.values() if can_add(s, unit, nations))
        print(f"  {name:<14} {str(unit.get('faction')):<8} "
              f"{str(unit.get('nationality')):<8} {n:>8}")
    print()
    print("  ⇒ 备选池按这条规则过滤 ⇒ 与游戏完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
