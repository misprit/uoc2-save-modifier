# -*- coding: utf-8 -*-
import io, re
P = r"D:\MiniMax\UOC2存档修改器-开发规范与Prompt.md"
t = io.open(P, encoding="utf-8").read()
orig = t
R = []

# C. §3.4.6 -> §3.4.5（能力矩阵）
R.append(("实现时应按 §3.4.6 的「能力矩阵」统一处理", "实现时应按 §3.4.5 的「能力矩阵」统一处理"))
R.append(("用 §3.4.6 的能力矩阵，任何**没见过的状态组合**", "用 §3.4.5 的能力矩阵，任何**没见过的状态组合**"))

# F. S0-S4 旧标签 -> §3.4.2 的新标签
R.append(("Stalingrad.usg   （S1 战斗进行中）", "Stalingrad.usg   （B1 战斗进行中）"))
R.append(("west-LastWar.usg （S2 刚进部署阶段）", "west-LastWar.usg （B2 刚进部署阶段）"))
R.append(("就能覆盖 S1/S2/S3/S4/S5 的绝大多数需求", "就能覆盖 B1/B2/M1..M5/S5 的绝大多数需求"))
R.append(("| **战斗中的**单位/总部（S1/S2） |", "| **战斗中的**单位/总部（B1/B2） |"))
R.append(("战役地图上的单位/总部（S3/S4） |", "战役地图上的单位/总部（M1..M5） |"))
R.append(("4. **S0（战役开局）没有根 `units.yml`**", "4. **战役开局（C0）没有根 `units.yml`**"))

# N. §6.2 状态判定引用
R.append(("- 用户打开存档时，先跑一遍 §3.4.2 的状态判定，把当前状态显示在界面上",
          "- 用户打开存档时，按 §3.4.6 的判定把当前阶段显示在界面上（**不要**按 §3.4.2 的状态标签写分支）"))

# M. 按钮叫法统一
R.append(("**在游戏里点「退回会议」再读档**", "**在游戏里点「重置会议」再读档**"))

# H. §5.3 表述
R.append(("存档中**没有**阵营/编制信息，真实上限来自 `entity_types/unit_types/<type>.yml`：",
          "存档里**有** `type`（实例字段），但**没有**战力/特种兵的上限 —— 上限来自 `entity_types/unit_types/<type>.yml`："))

# O. 里程碑计数
R.append(("`document/main.yml` 的 23 个里程碑（`do_not_take=True` 的 `success_90` 除外）：",
          "`document/main.yml` 的 **23 个**里程碑（其中 `success_90` 标记 `do_not_take=True`，UI 上不提供勾选）："))

# L. §10-5 粗体嵌套
R.append(("5. **`document/units.yml` 是 `type` 的权威源，但修改器**只读不写**（L5）。**",
          "5. **`document/units.yml` 是 `type` 的权威源，但修改器只读不写**（L5）。"))

for old, new in R:
    if old not in t:
        raise SystemExit("NOT FOUND: %r" % old[:70])
    t = t.replace(old, new)

io.open(P, "w", encoding="utf-8", newline="").write(t)
print("applied", len(R))
