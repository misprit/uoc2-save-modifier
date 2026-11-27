"""e170 —— 战斗中能不能修废墟？取证的四个关键事实。

**背景**：玩家 2026-11-27 问「战斗中不小心造成废墟，能不能立即修复」。
现有实现禁止战斗中修复（`handlers._city_restore` 里 `w.require(not w.caps.in_battle, ...)`），
理由只写了半句「游戏会覆盖回去」。本脚本把那半句**用字节码钉死**。

**四个关键事实（全部来自字节码，不是推断）**

| # | 事实 | 出处 |
|---|---|---|
| ① | **废墟是「开一场新战斗」时注入的**：`Game.new` 里 `map_objects.set_destroyed_cities(self.destroyed_cities)` —— 参数是**战役级**的 `destroyed_cities`（清单） | ① |
| ② | **战斗存档会把内存里的 `destroyed_cities` 写回**：`Game._save` 的字段表里有 `destroyed_cities` ⇒ 战斗中磁盘上的清单改动会被内存值覆盖 | ② |
| ③ | **游戏存档会删掉重写 `games/` 与 `document/`**：`Campaign.save` ⇒ `remove_directory('games')` + `remove_directory('document')` + `_save_main_files`（根 `main.yml` 从内存重写） | ③ |
| ④ | **战斗中写盘的触发点很多**：每回合开始（`Game.save_archive_start_turn`）、回合结束（`GameWorldCtrl._cr_end_turn` / `slot_save`）、离开战斗（`CampaignCtrl.on_leave__active`、`MainScreenCtrl._cr_world_suspend`） | ④ |

⇒ **结论**：战斗中改盘**必然被游戏覆盖**，而且**改不了当前这局**
（废墟在 `Game.new` 时就进了内存的地图对象）⇒ 详见
`docs/战斗中修复废墟-可行性研究.md`。

**跑法（仓库根目录）**：
    .\\python\\python.exe docs\\证据脚本\\e170_battle_ruins_restore.py
"""

from __future__ import annotations

import dis
import io
import marshal
import os
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core.paths import CorePaths                     # noqa: E402

LIB = Path(str(CorePaths.discover().game_dir)) / "lib"
OUT: list[str] = []


def p(*a) -> None:
    OUT.append(" ".join(str(x) for x in a))


def load_pyc(path: Path):
    """游戏 .pyc 的头是 magic(4)+flags(4)+mtime(4)+size(4) = 16 字节。"""
    return marshal.loads(path.read_bytes()[16:])


def find_class(code, cls_name):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            if k.co_name == cls_name:
                return k
            got = find_class(k, cls_name)
            if got is not None:
                return got
    return None


def find_func(code, func_name):
    for k in code.co_consts:
        if isinstance(k, types.CodeType) and k.co_name == func_name:
            return k
    return None


def walk_code(code, prefix=""):
    yield prefix, code
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield from walk_code(k, prefix + code.co_name + ".")


def all_pyc():
    for dirpath, _dirs, files in os.walk(LIB):
        for f in files:
            if f.endswith(".pyc"):
                yield Path(dirpath) / f


def names_of(code):
    return ", ".join(code.co_names)


def strings_of(code):
    return [c for c in code.co_consts if isinstance(c, str)]


def main() -> int:
    game = load_pyc(LIB / "uoc2/state/game/game.pyc")
    camp = load_pyc(LIB / "uoc2/state/campaign/campaign.pyc")

    gcls = find_class(game, "Game")
    new = find_func(gcls, "new")
    gsave = find_func(gcls, "_save")
    ccls = find_class(camp, "Campaign")
    csave = find_func(ccls, "save")

    p("=" * 72)
    p("① Game.new —— 废墟在**开新战斗**时注入")
    p("=" * 72)
    p("  名字：", names_of(new))
    p("  含 set_destroyed_cities：", "set_destroyed_cities" in new.co_names)
    p("  含 destroyed_cities：", "destroyed_cities" in new.co_names)
    buf = io.StringIO()
    dis.dis(new, file=buf)
    for ln in buf.getvalue().splitlines():
        if "set_destroyed_cities" in ln or "destroyed_cities" in ln:
            p("   ", ln.strip())

    p("")
    p("=" * 72)
    p("② Game._save —— 战斗存档把**内存里的** destroyed_cities 写回")
    p("=" * 72)
    p("  名字：", names_of(gsave))
    p("  含 destroyed_cities：", "destroyed_cities" in gsave.co_names)

    p("")
    p("=" * 72)
    p("③ Campaign.save —— 存档时删掉重写 games/ 与 document/")
    p("=" * 72)
    p("  名字：", names_of(csave))
    p("  字符串常量：", strings_of(csave))
    buf = io.StringIO()
    dis.dis(csave, file=buf)
    for ln in buf.getvalue().splitlines():
        if ("remove_directory" in ln or "'games'" in ln or "'document'" in ln
                or "_save_main_files" in ln or "_save_campaign_files" in ln):
            p("   ", ln.strip())

    p("")
    p("=" * 72)
    p("④ 战斗中写盘的触发点（谁调 save）")
    p("=" * 72)
    hits = []
    for pyc in all_pyc():
        rel = pyc.relative_to(LIB).as_posix()
        if not rel.startswith("uoc2/"):
            continue
        try:
            code = load_pyc(pyc)
        except Exception:
            continue
        for prefix, c in walk_code(code):
            names = set(c.co_names)
            if ("save" in names and c.co_name not in ("save",)) or (
                    c.co_name in ("save_archive_start_turn", "_cr_end_turn",
                                  "slot_save", "on_leave__active",
                                  "_cr_world_suspend", "_save_current_game")):
                hits.append((rel, prefix + c.co_name))
    for rel, where in sorted(set(hits)):
        p("  %-46s %s" % (rel, where))

    print("\n".join(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
