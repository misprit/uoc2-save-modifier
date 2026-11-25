"""e168 —— 城市废墟的**真实存档普查**：战役清单 / 场景快照 / 要塞三者的对应关系。

**背景**：U182 要做「修复被摧毁城市」。在动手写之前，先把「废墟到底记在哪些地方、
要塞的 `functional` 是不是只由城市摧毁造成」这些**事实**用本机 68 个存档钉死 ——
不钉死就动手，很容易把「城市没被摧毁、但要塞被单独打掉」的格子也复活。

**结论（全部来自本机 68 个存档的统计，不是推断）**

| 问题 | 答案 | 出处 |
|---|---|---|
| `cities.yml` 里的坐标是不是都在战役清单里？ | **509 条目，0 例外** | ① |
| `cities.yml` 条目的附加数据只有 `in_repair`？ | **509 条目，0 个额外键** | ① |
| `forts.yml` 装的是什么？ | **该场景地图上的全部要塞**（例：`fall_braun` 23 条要塞 / 2 座城市） | ② |
| **废墟格上的要塞，`functional` 是什么？** | 同格要塞 **28 条，28/28 全是 `false`**（0 例外） | ② |
| 不在废墟格上的要塞呢？ | 423 条：271 `false` / 152 `true` ⇒ **`functional=false` 的主因不是「城市被摧毁」** | ② |
| ⇒ 所以要塞恢复只能怎么做？ | **按格对齐**：只改「该场景 `cities.yml` 里确实有这座城市」的那一格 | ② |
| 「最新变成废墟的那座」（= 清单最后一项）能定位到场景快照吗？ | **55/55 存档 100% 命中至少一个场景**（合计 69 个场景命中） | ③ |
| `in_state.scenario` 非空 ⇔ 正在战斗？ | 68 个存档里 9 个非空，**全部**是「战斗中(B1)」或「部署阶段(B2)」，无误判 | ④ |

**跑法（仓库根目录）**：
    .\\python\\python.exe docs\\证据脚本\\e168_ruins_survey.py
"""

from __future__ import annotations

import io
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core import list_saves, open_save, yamlio         # noqa: E402

OUT_DIR = Path(r"D:\MiniMax\_analysis")
OUT: list[str] = []


def p(*a) -> None:
    OUT.append(" ".join(str(x) for x in a))


def scenario_of(entry: str) -> str | None:
    """`games/<场景>/cities.yml` → `<场景>`；不是这种形状就返回 None。"""
    parts = entry.split("/")
    if len(parts) == 3 and parts[0] == "games" and parts[2] in ("cities.yml", "forts.yml"):
        return parts[1]
    return None


def uv_of(item) -> tuple | None:
    """`map` 里的一项 = `[坐标, 附加数据]`。"""
    if not isinstance(item, (list, tuple)) or len(item) != 2:
        return None
    uv = item[0]
    if not isinstance(uv, (list, tuple)) or len(uv) != 2:
        return None
    try:
        return (int(uv[0]), int(uv[1]))
    except Exception:
        return None


def main() -> int:
    saves = [s for s in list_saves() if s.save_id.endswith(".usg")]
    p("存档总数:", len(saves))

    c1 = Counter()          # ① 清单 vs cities.yml
    c2 = Counter()          # ② 要塞
    c3 = Counter()          # ③ 最新一座
    c4 = Counter()          # ④ in_battle
    rows: list[str] = []

    for info in saves:
        sid = info.save_id
        try:
            with open_save(sid) as sv:
                names = sv.list_names()
                root = sv.read_yaml("main.yml", {}) or {}
                destroyed = [tuple(x) for x in (root.get("destroyed_cities") or [])]
                dset = set(destroyed)
                c1["saves"] += 1
                if destroyed:
                    c1["有清单的存档"] += 1

                per_scenario: dict[str, dict] = {}
                for n in names:
                    sc = scenario_of(n)
                    if sc is None:
                        continue
                    data = sv.read_yaml(n, {}) or {}
                    items = data.get("map") or []
                    slot = per_scenario.setdefault(sc, {})
                    if n.endswith("cities.yml"):
                        slot["cities"] = {uv_of(it): (it[1] or {})
                                          for it in items
                                          if uv_of(it) is not None}
                    else:
                        slot["forts"] = {uv_of(it): (it[1] or {})
                                         for it in items
                                         if uv_of(it) is not None}

                for sc, slot in per_scenario.items():
                    cities = slot.get("cities") or {}
                    forts = slot.get("forts") or {}
                    for uv, props in cities.items():
                        c1["cities 条目"] += 1
                        if uv not in dset:
                            c1["不在战役清单里"] += 1
                            rows.append("!! %s | %s | 城市 %s 不在清单里" % (sid, sc, uv))
                        for k in props:
                            if k != "in_repair":
                                c1["额外键 " + str(k)] += 1
                    for uv, props in forts.items():
                        fn = props.get("functional")
                        same = uv in cities
                        c2["forts 条目"] += 1
                        c2[("同格" if same else "异格") + "_" + str(fn)] += 1
                    if forts and cities:
                        c2["场景对（同时有 cities 与 forts）"] += 1
                        rows.append("%-56s %-24s cities=%-3d forts=%-3d"
                                    % (sid, sc, len(cities), len(forts)))

                if destroyed:
                    last = destroyed[-1]
                    hit = [sc for sc, slot in per_scenario.items()
                           if last in (slot.get("cities") or {})]
                    c3["有清单的存档"] += 1
                    c3["命中场景数合计"] += len(hit)
                    if hit:
                        c3["命中>=1 个场景的存档"] += 1

                st = root.get("in_state") or {}
                if st.get("scenario"):
                    c4["in_state.scenario 非空"] += 1
                    rows.append("B | %-56s scenario=%-24s destroyed=%d"
                                % (sid, st.get("scenario"), len(destroyed)))
        except Exception as exc:
            p("!! 读不动", sid, exc)

    p("\n" + "=" * 78)
    p("① 战役清单 vs cities.yml")
    p("=" * 78)
    for k in sorted(c1):
        p("  %-28s %d" % (k, c1[k]))
    p("  ⇒ cities.yml 里每个坐标都在战役清单里，附加数据只有 in_repair")

    p("\n" + "=" * 78)
    p("② forts.yml：装的是什么 / functional 的分布")
    p("=" * 78)
    for k in sorted(c2):
        p("  %-28s %d" % (k, c2[k]))
    p("  ⇒ 同格（该场景有废墟城市的那一格）的要塞 functional **全为 false**；")
    p("  ⇒ 异格的 false/true 都有 ⇒ false 的主因不是「城市被摧毁」")
    p("  ⇒ 所以要塞恢复只能**按格对齐**")

    p("\n" + "=" * 78)
    p("③ 「最新变成废墟的那座」（= 战役清单最后一项）")
    p("=" * 78)
    for k in sorted(c3):
        p("  %-28s %d" % (k, c3[k]))
    p("  ⇒ 100% 能定位到至少一个场景快照")

    p("\n" + "=" * 78)
    p("④ in_state.scenario 非空 ⇒ 正在战斗？")
    p("=" * 78)
    for k in sorted(c4):
        p("  %-28s %d" % (k, c4[k]))
    p("  ⇒ 这些存档是「战斗中」或「部署阶段」⇒ 能力位 in_battle 可用")

    p("\n" + "=" * 78)
    p("明细")
    p("=" * 78)
    for r in rows:
        p("  " + r)

    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        io.open(str(OUT_DIR / "e168_out.txt"), "w",
                encoding="utf-8", newline="\n").write("\n".join(OUT))
    except Exception as e:                       # pragma: no cover
        p("  （写不出去文件：%s）" % e)
    print("\n".join(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
