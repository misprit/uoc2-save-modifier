# -*- coding: utf-8 -*-
"""V4: 替换 §6.2 的写入清单表"""
import io

P = r"D:\MiniMax\UOC2存档修改器-开发规范与Prompt.md"
t = io.open(P, encoding="utf-8").read()

i = t.find("**战斗态下的同步清单**")
j = t.find("**GUI 该怎么表现**", i)
assert i > 0 and j > i, (i, j)

new = (
    "**写入清单**（战斗态下改完根表还要处理什么，详见 §3.4.4.7 与 §7）：\n"
    "\n"
    "| 目标 | 是否需要改 | 方式 |\n"
    "|---|---|---|\n"
    "| 根 `units.yml` / `hqs.yml` / `main.yml` / `cards.yml` / `store.yml` | ✅ **必改** | 按 id 定位并修改 |\n"
    "| `last_conference/`、`last_game/` | ❌ **不要动** | 它们是玩家的游戏内撤销基线（§7.2 W3、§7.4） |\n"
    "| `games/<场景>/archive/<最后快照>/*` | ❌ **不要动** | 历史 / 回放基线（§7.2 W4） |\n"
    "| `games/<场景>/units.yml`（ID 清单） | ❌ 不用改 | 只在**新增单位**时才加 id |\n"
    "| `games/<场景>/main.yml`、`ar_list.yml` | ❌ 不用动 | 战斗实时状态，由游戏自己维护 |\n"
    "| `document/units.yml` | ⚠️ **仅「改 type」或「新增单位」时改** | 改了就**无法被游戏内回退撤销**，必须警告 + 单独备份（§7.5） |\n"
    "| `document/scenarios/*/units.yml` | ❌ 不要动 | 那是游戏包的场景预设，不是存档状态 |\n"
    "\n"
)

t = t[:i] + new + t[j:]
io.open(P, "w", encoding="utf-8", newline="").write(t)
print("ok, len =", len(t))
