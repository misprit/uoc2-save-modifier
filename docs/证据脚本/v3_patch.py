# -*- coding: utf-8 -*-
"""V3: 批量替换交付文档中的旧"同步检查点"表述"""
import io

P = r"D:\MiniMax\UOC2存档修改器-开发规范与Prompt.md"
t = io.open(P, encoding="utf-8").read()
orig = t

REPL = []

# ---- 1) §6.2 战斗态同步清单 ----
REPL.append((
"""**战斗态下的同步清单**（改完根表后必须一起处理，详见 §3.4.4.7）：

| 目标 | 是否需要改 | 方式 |
|---|---|---|
| 根 `units.yml` | ✅ 必改 | 按 id 定位并修改 |
| `last_conference/units.yml` | 若存在 ✅ | 按 id 匹配 |
| `last_game/units.yml` | 若存在 ✅ | 按 id 匹配 |
| `games/<场景>/archive/<最后快照>/units.yml` | 若在战斗中 ✅ | 按 id 匹配 |
| `games/<场景>/archive/<最后快照>/campaign_units.yml` | 若该单位在其中 ✅ | 按 id 匹配（**它读档时会覆盖名册**） |
| `games/<场景>/units.yml`（ID 清单） | ❌ 不用改 | 只在**新增单位**时才加 id |
| `document/scenarios/*/units.yml` | ❌ 不要动 | 那是游戏包的场景预设，不是存档状态 |""",
"""**写入清单**（战斗态下改完根表还要处理什么，详见 §3.4.4.7 与 §7）：

| 目标 | 是否需要改 | 方式 |
|---|---|---|
| 根 `units.yml` / `hqs.yml` / `main.yml` / `cards.yml` / `store.yml` | ✅ **必改** | 按 id 定位并修改 |
| `last_conference/`、`last_game/` | ❌ **不要动** | 它们是玩家的游戏内撤销基线（§7.2 W3、§7.4） |
| `games/<场景>/archive/<最后快照>/*` | ❌ **不要动** | 历史 / 回放基线（§7.2 W4） |
| `games/<场景>/units.yml`（ID 清单） | ❌ 不用改 | 只在**新增单位**时才加 id |
| `games/<场景>/main.yml`、`ar_list.yml` | ❌ 不用动 | 战斗实时状态，由游戏自己维护 |
| `document/units.yml` | ⚠️ **仅"改 type"或"新增单位"时改** | 改了就**无法被游戏内回退撤销**，必须警告 + 单独备份（§7.5） |
| `document/scenarios/*/units.yml` | ❌ 不要动 | 那是游戏包的场景预设，不是存档状态 |"""))

# ---- 2) §3.4.4.7 第 4 条 ----
REPL.append((
"""4. `in_state.scenario` 非空 → 打开 `games/<场景>/archive/`，取**最后一个快照**：
   - 按 id 同步它的 `units.yml`；
   - 若该单位也在该快照的 `campaign_units.yml` 里，同样按 id 同步（它读档时会覆盖）。
5. `games/<场景>/units.yml`（ID 清单）**通常不用改**；只有**新增单位**时才要把新 id 加进去。
6. **不要**改 `document/scenarios/*/units.yml` —— 那是游戏包的场景预设，不是存档状态。""",
"""4. `in_state.scenario` 非空 → **不要动** `games/<场景>/archive/`（它是历史/回放基线，§7.2 W4）。
5. `games/<场景>/units.yml`（ID 清单）**不用改**；只有**新增单位**时才要把新 id 加进去。
6. **不要**改 `last_conference/`、`last_game/` —— 它们是玩家的游戏内撤销基线（§7.2 W3）。
7. **不要**改 `document/scenarios/*/units.yml` —— 那是游戏包的场景预设，不是存档状态。
8. **唯一例外**：`document/units.yml` —— 只有"改 type"或"新增单位"才需要动它，
   而它**不在检查点里**，所以这类改动**游戏内回退不掉**，必须警告 + 单独备份（§7.5）。"""))

# ---- 3) §10 坑清单第 10 条 ----
REPL.append((
"""10. **`last_conference/` / `last_game/` 会覆盖根级修改**（见 §7）。""",
"""10. **`last_conference/` / `last_game/` 会覆盖根级修改** —— 这是**预期行为**，是玩家的撤销基线。
    **不要去同步它们**（§7.4 的 R1–R4 风险）。"""))

# ---- 4) §11.1 验收项 ----
REPL.append((
"""- [ ] 改完根级文件后，**在游戏里点「退回会议」再读档**，确认修改仍在（验证 §7 方案 A）""",
"""- [ ] 改完根级文件后，**在游戏里点「退回会议」再读档**，确认修改**消失**（验证 §7.2 W1/W3：
      回退 = 整表替换根级修改，这正是期望行为）
- [ ] 改完根级文件后，**读档继续战斗**，确认修改**仍在**（读档不重算，§3.5.1）"""))

# ---- 5) §11.2b 最后一条 ----
REPL.append((
"""- [ ] 同上：改完后检查 **4 个位置**都已同步 —— 根 `units.yml`、`last_game/units.yml`、
      `archive/turn_05_phase_00_allies/units.yml`、以及 `archive/.../campaign_units.yml`（若含该 id）""",
"""- [ ] 同上：改完后确认 **只有根 `units.yml` 被写** —— `last_game/`、`archive/` 里的文件
      **字节级未变**（§7.2 W3/W4，可用 SHA256 校验）"""))

# ---- 6) §13 第 4 条 ----
REPL.append((
"""4. **写回时必须同步检查点**（§3.4.5.3）—— 这是最容易漏、后果最严重的一步：
   玩家点一次"重置会议"或"重打上一场"，没同步的修改就没了。
   同步时**按 id 匹配**，不要整表覆盖（检查点的单位集合比根表少）。
   **战斗态别忘了 `archive/<最后快照>/campaign_units.yml`** —— 它会覆盖名册（§3.4.4.5）。""",
"""4. **⚠️ 不要写任何回滚检查点**（§7）。`last_conference/` / `last_game/` 是玩家唯一的
   游戏内撤销基线；改了它玩家就再也回不到原版（§7.4 R1–R4）。
   默认只写根级文件 + 必要时写 `document/units.yml`（改 type / 新增单位时，且**不可撤销**、必须警告）。"""))

# ---- 7) §13 第 10 条（保留原文，只加一条新的） ----
REPL.append((
"""11. **内层 `archive` ZIP 原样复制**，不要解压重压（见 §11.4）。""",
"""11. **内层 `archive` ZIP 原样复制**，不要解压重压（见 §11.4）。
12. **每条改动都要能回答"游戏内回退能不能撤销它"**（§7.2 W6）。
    只有涉及 `document/units.yml` 的改动不能撤销 —— UI 上必须标出来。"""))

n = 0
for old, new in REPL:
    c = t.count(old)
    if c != 1:
        print(f"!! 匹配 {c} 次: {old[:48]!r}")
        continue
    t = t.replace(old, new)
    n += 1

io.open(P, "w", encoding="utf-8", newline="").write(t)
print(f"替换 {n}/{len(REPL)} 处，字符数 {len(orig)} -> {len(t)}")
