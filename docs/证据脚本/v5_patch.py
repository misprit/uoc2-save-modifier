# -*- coding: utf-8 -*-
"""V5: 补 §3.3 的运行时说明 + §4.1/§5.4 的 L5 联动规则"""
import io

P = r"D:\MiniMax\UOC2存档修改器-开发规范与Prompt.md"
t = io.open(P, encoding="utf-8").read()

REPL = []

# ---- §3.3：document/ 是运行时活层 ----
REPL.append((
"""### 3.3 `document/` = 游戏包的逐字节副本 ⚠️

`document/` 的内容 **等于** `<game>/_packages/base/data/campaigns/<campaign_id>.usc/`。
实测 west 战役：850 vs 850 个文件，**849 个字节级完全相同，只有 `units.yml` 不同**。""",
"""### 3.3 `document/` = 战役包副本，**但它是运行时活层** ⚠️⚠️

`document/` 的内容 **等于** `<game>/_packages/base/data/campaigns/<campaign_id>.usc/`。
实测 west 战役：850 vs 850 个文件，**849 个字节级完全相同，只有 `units.yml` 不同**。

> **⚠️ 它不是"只读副本"，而是运行时数据源（L5 层，见 §7.1）：**
> - **读**：每次读档时 `Campaign.load`（`campaign.pyc:166`）用
>   `read_serialization(...).subdirectory('document')` 把存档里的 `document/` 加载成 `CampaignDoc`。
>   `campaign_doc.get_doc_unit(id)`（`type` 的解析源）读的就是它。
> - **写**：游戏会往里写新造的单位（`campaign_doc.add_campaign_unit` → `_save_units_file`）。
> - **不在任何检查点里** ⇒ 改这里的东西**游戏内回退不掉**（§7.5）。
>
> **对比时必须先看 `main.yml` 的 `campaign_id`** —— 不同战役的包不同：
> `west-Husky.usg` 的 `document/` 与 `west.usc` 850 个文件全同；
> `campaigns\\Stalingrad.usg` 的 `document/` 是 **`barbarossa.usc`** 的副本（441 条目）。"""))

# ---- §4.1：补 L5 联动 ----
REPL.append((
"""> ⚠️ **更重要的联动规则**：对**出现在场景 `units.yml` 里的单位**，
> 战斗开始时 `type` 会被场景预设**覆盖**回 `document/units.yml[id].type`（§3.5.3）。
> **只改根 `units.yml` 的 `type` 是不够的，必须同时改 `document/units.yml` 里该 id 的 `type`。**""",
"""> ⚠️ **更重要的联动规则**：对**出现在场景 `units.yml` 里的单位**，
> 战斗开始时 `type` 会被场景预设**覆盖**回 `document/units.yml[id].type`（§3.5.3）。
> **只改根 `units.yml` 的 `type` 是不够的，必须同时改 `document/units.yml` 里该 id 的 `type`。**
>
> ⚠️ **这是唯一"游戏内回退不掉"的改动**（`document/` 不在检查点里）——
> 改之前必须单独备份并明确警告用户（§7.5）。
>
> 改 `document/units.yml` 时**只能改该 id 那一行的 `type`**，其余字段
> （`id` / `name_brief` / `name_full`）不要动 —— 它由 `doc_units_schema` 校验
> （`{id, type, name_brief, name_full}` 四个键，多一个键就报错）。"""))

# ---- §5.4：补 L5 回退提示 ----
REPL.append((
"""依据：`campaign_agree_on_unit`（`game_adjust_data.pyc:21`）在战斗初始化时执行 `u.type = unit.type`，
而 `unit.type` 对场景单位来说 = `document/units.yml[id].type`（§3.5.3）。""",
"""依据：`campaign_agree_on_unit`（`game_adjust_data.pyc:21`）在战斗初始化时执行 `u.type = unit.type`，
而 `unit.type` 对场景单位来说 = `document/units.yml[id].type`（§3.5.3）。

> ⚠️ **可撤销性**：`document/units.yml` **不在 `last_conference/` / `last_game/` 里**
> （实测 100 个检查点，0 个含 `document/`），
> 所以**改 `type` 是游戏内回退不掉的改动** —— 必须单独备份 + 明确告知用户（§7.2 W5、§7.5）。"""))

n = 0
for old, new in REPL:
    c = t.count(old)
    if c != 1:
        print(f"!! 匹配 {c} 次: {old[:40]!r}")
        continue
    t = t.replace(old, new)
    n += 1

io.open(P, "w", encoding="utf-8", newline="").write(t)
print(f"替换 {n}/{len(REPL)} 处")
