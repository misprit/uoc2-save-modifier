# UOC2 存档修改器 GUI —— 开发规范与实现 Prompt

> 这份文档是**自包含**的。执行者不需要看到本对话，可直接据此实现。
> 文档中每一条结论都有实测证据（见文末「证据与复现」）。

> **本文件的位置**：它是本仓库的**唯一事实源**，与代码同版本管理
> （`docs/开发规范与Prompt.md`，随 Git 提交）。
> 配套的证据脚本在 `docs/证据脚本/`，终检脚本（`v6_check.py` / `v11_verify.py`）
> 也在那里，**按自身位置找本文件**，可以直接跑。
>
> **工程进度**另见 `docs/开发上下文.md`（与本文件冲突时**以本文件为准**）。

> **【2026-11-19 起 · 工作方式变更】GUI 视觉稿已冻结**
>
> 界面**直接在当前实现上改**（`src/save_modifier_web/web/index.html`，单文件前端），
> **不再拿 `docs/GUI视觉稿.html` 做对比，也不再更新它**。
>
> 视觉稿停在 **U42 前后** —— 老滚轮交互（悬停滚轮 / Ctrl+滚轮 ±10）、U9 残留的
> 卡牌图鉴、U43–U50 的新界面（对话框搜索框、战区资产候选卡、备选池定尺与分组折叠、
> 兵力卡两层滚轮、挂载合法性纠正……）**全都没进视觉稿**。
> 继续双向同步的收益已经低于成本：两边分叉十几个轮次，改一边要回填另一边，
> 而**行为**（游戏规则、字段约束）本来就写在《GUI设计规范.md》里，不依赖视觉稿。
>
> ⇒ 后续界面改动的**基准是 app 现状**；
> 《GUI设计规范.md》里描述**交互意图**的部分（§6.1b 两层滚轮、§7.3.2 挂载规则、
> §7.3.4 备选池……）**仍然是行为依据**，
> 但**布局 / 像素级**的视觉**以 app 为准**（视觉稿里的写法已过时，别照抄）。

---

## 目录

**上手顺序**：§0（任务、交付形态、接口）→ **§7**（写入策略：只写 L1）→ **§6**（三块功能怎么改）→ §4/§5（字段与约束）→ §8（打包）→ §10/§11（自查与验收）

| 章节 | 内容 | 什么时候看 |
|---|---|---|
| **§0** | 任务范围 + 交付形态 + 硬约束 | **必读** |
| **§0.2** | **核心库 8 个函数的接口定义** | **必读** —— 写代码时对着抄 |
| §1 | 环境事实（安装路径、存档目录） | 找文件时 |
| §2 | 存档容器格式（ZIP / 二层 ZIP / npz） | 写打包代码时 |
| §3 | 存档目录结构 | 了解文件在哪 |
| **§3.2b** | **战役 / 场景识别判据** | **必读** —— 认出这是哪个战役、哪个场景 |
| **§3.4** | 存档状态机（**能力矩阵**） | **必读** —— 决定"该改哪张表" |
| **§3.5** | 战斗初始化重组机制 | 理解"改了却不生效" |
| §4 | 精确字段定义 | 写解析器时 |
| §5 | 硬约束（数值范围、上限来源） | 写校验时 |
| **§6** | 三块功能的具体改法 | **必读** —— 实现主参考 |
| **§6.2b** | **总部兵库 + 战区资产**（L3 例外 ①） | **必读** |
| **§6.2c** | **作战标记**（L3 例外 ②） | **必读** |
| **§6.4** | **备份与撤销栈** | **必读** |
| **§7** | ⭐ **写入策略：只写 L1** | **必读** —— 写入总纲 |
| §8 | 写回规则（打包） | 写保存时 |
| **§8.1** | ⭐ **YAML 序列化必须复刻游戏自己的规则**（字节码实证） | **必读** —— 否则"没改的行"也会被改掉 |
| §9 | 参考目录（类型表） | 做下拉框时 |
| **§9.1** | **数据源分层：内置静态基线 + 增量覆盖 + 用户刷新** | **必读** —— 决定启动速度与 mod 兼容性 |
| §10 | 已知坑清单 | 收尾自查 |
| §11 | 验收清单 | 测试时 |
| §12 | 证据与复现（脚本表） | 想自己验证时 |
| §13 | 给实现者的最后提醒 | 收尾读一遍 |

**配套文档**（同一仓库，随 Git 提交）：

| 文档 | 内容 |
|---|---|
| **`docs/GUI设计规范.md`** | ⭐ **GUI 侧的事实源** —— 三条铁律、信息架构、视觉规范、贴图资产映射、交互规范、7 个功能页、GUI↔核心库调用时序、技术实现、实施路线 |
| `docs/GUI视觉稿.html` | GUI 视觉稿（浏览器打开；直接引用游戏真贴图） —— ⛔ **已冻结（2026-11-19）**：不再更新，**不再与实现比对**（见 §0 顶部声明） |
| `docs/核心库调用说明.md` | 8 个函数的精确签名 + 11 种 Edit + 能力位矩阵（写 GUI 必读） |
| `docs/开发上下文.md` | 工程进度、决策记录、踩过的坑 |

---

## 0. 任务

做一个面向《统一指挥 2》(Unity of Command II) 玩家的**傻瓜式存档修改器**：选存档 → 点选要改的东西 → 填数值 → 保存。不要求用户懂 YAML。

### 0.1 本文档交付什么

**交付物 = 核心库 + 调用说明。** 具体形态：

| 项 | 决定 | 理由 |
|---|---|---|
| **核心库形态** | **纯 Python 包**（`save_modifier_core`），**GUI 直接 `import`** 使用 | 不做 JSON/HTTP/子进程 CLI —— 少一层协议、少一层出错点，GUI 与核心库在同一进程里 |
| **对外接口** | **8 个函数**（`§0.2`） | 接口越少越不容易被误用，也越不容易漂移 |
| **GUI 归属** | ✅ **就在本仓库里做**（`src/save_modifier_gui/`）—— 原计划"并入静态查看器"，2026-11-17 改判：两个项目的**数据哲学与安全边界契约**不同，合并要跨仓库改契约；**先各自独立稳定，再做"外壳合并"** | GUI 的**设计**另见 `docs/GUI设计规范.md`（含 `docs/GUI视觉稿.html`）—— 那是 GUI 侧的事实源 |
| **开发顺序** | **先做无界面核心库**（可独立跑测试），**再在本仓库做 GUI** | 核心库能独立跑回归测试（往返无损），不用每次都点 GUI |
| **界面** | 必须是**傻瓜式 GUI**：不要求用户懂 YAML，不提供"跳过校验"入口 | §13；具体设计见 `docs/GUI设计规范.md` |
| **Python 运行时** | **随包分发**（`python/` 目录，含 CPython 3.14 运行时，**一并进 Git**） | 用户不装 Python 也能用；25 MB 一次性成本，之后不再改动 |
| **GUI 运行时** | 随包 runtime 是 **embeddable 版 CPython 3.14.3，不带 tkinter** ⇒ 做原生窗口须**补 tcl/tk**（+8.7 MB）：`python/{_tkinter.pyd,tcl86t.dll,tk86t.dll,zlib1.dll}` + `python/Lib/site-packages/tkinter/` + **`<包根>/lib/{tcl8.6,tk8.6}`**（Tcl 的 `<prefix>` 是包根，脚本库放这里才能被自动发现）。已端到端验证：补齐后 `Tk() OK patchlevel 8.6.15` | 见 `docs/GUI设计规范.md` §10.1 与证据脚本 `e141`~`e145`、`e144` |
| **成品形态** | **解压即用的 zip**（解压后双击 `run_gui.bat` 起图形界面；`run.bat` 是命令行自测入口） | 同上 |

> **阶段 4（并入静态查看器）的前置条件**：那个项目自己的「安全边界」契约目前明文禁止"修改存档"，
> **那份契约由用户自己修订**。本文档不越界去改那个仓库，只负责交付核心库与调用说明。

### 0.2 核心库对外接口（8 个函数）

```python
# ── 1) 列出存档 ──────────────────────────────────────────
list_saves() -> list[SaveInfo]
#     扫描 %LOCALAPPDATA%\.uoc2\save\ 下的**全部**存档。
#     ⚠️ 游戏自己只读 campaigns 与 games 两个目录；根下其它目录是**玩家自建的
#     归档区**（目录名叫什么都行）⇒ 修改器照样读，用 archived 标记区分。
#     返回 id / 路径 / 战役名 / 场景名 / 最后修改时间 / 是否独立场景。

# ── 2) 打开 ─────────────────────────────────────────────
open_save(save_id) -> Save
#     解析容器、算能力位（§3.4.5.1）、载入 L1 表。

# ── 3) 只读视图 ─────────────────────────────────────────
save.view() -> View
#     给 GUI 用的只读投影：能力位、当前阶段（§3.4.6）、
#     单位列表（含 max_st/max_spec）、总部列表、卡牌、商店、
#     历史战斗单位（只读）。
#
# save.ruined_cities() -> list[RuinedCity]   （§6.5 · U183）
#     战役里被摧毁的城市（废墟）清单 —— 坐标 / 影响哪些场景 /
#     是不是「最新变成废墟的那座」。**只读**：改它走 `city_restore`。

# ── 4) 规划编辑 ─────────────────────────────────────────
save.plan_edit(edits: list[Edit]) -> Plan
#     不碰磁盘。返回：将要改哪些文件、每个文件的 diff、
#     校验结果、警告（"进战斗会被重置"等）、以及是否可提交。
#     Edit 是 (target, id, field, value) 的结构化元组，
#     **不要接受 YAML 文本**（用户不写 YAML，工具也不该让用户写）。

# ── 5) 校验 ─────────────────────────────────────────────
validate(plan) -> ValidationResult
#     字段范围（§5.2）、type 合法性（§5.3）、枚举合法性、
#     数量级上限、未知键拦截（§5.1）。

# ── 6) 提交 ─────────────────────────────────────────────
save.commit(plan) -> CommitResult
#     顺序固定为：**备份 → 写临时文件 → 校验写回结果 → 原子替换**。
#     任何一步失败都必须完整回滚（不留半写坏的存档）。

# ── 7) 撤销 ─────────────────────────────────────────────
save.undo() -> UndoResult
#     修改器**自己的撤销栈**（内存 + 落盘）。
#     撤销 = 用上一次提交前的 L1 内容重新走一次 commit。
#     与游戏内的「重置会议」是**两套独立**的撤销机制。
#     落盘位置：存档旁边的 `<存档名>.undo.json`（§6.4.3）。
#     撤销前会**校验基准**，过期就拒绝，不硬改。
#
#     辅助（GUI 用来决定「撤销」按钮是否可点）：
save.undo_available() -> bool     # 栈里有没有东西可撤
save.undo_peek() -> str | None    # "可撤销：改了 1 个文件：单位 1 的 xp：314 → 77"

# ── 8) 目录查询 ─────────────────────────────────────────
catalog.units() / catalog.hq_types() / catalog.card_types()
catalog.spec_types() / catalog.fronts() / catalog.store_defaults()
#     下拉框数据源。**只做候选，绝不做白名单**（§9.1.3）。
```

> **另外还有一个异常类**：`SaveUnreadable` —— 存档**打不开**（文件损坏 / 不是 `.usg`）。
> 它带一句**人话**（提示玩家可以用 `bak` 里的 `_BACKUP.usg` 恢复），
> 服务端把它当 **400**（用户的文件坏了）而不是 500。

> **撤销栈是新需求**（原稿没有）：游戏自带的「重置会议 / 重打上一场」是**游戏内**的撤销，
> 但它会**整体回滚**玩家的整个存档状态 —— 用户只想撤销**刚才改的那一个数值**时，它帮不上忙。
> 因此修改器需要自己的**单步/多步撤销栈**（§6.4）。

### 0.3 本次范围（29 种编辑）

核心库一共支持 **29 种编辑**（`src/save_modifier_core/edits.py::EDIT_KINDS`），
**按写入目标**分组如下（`kind` 写错会直接报错，不会静默忽略）：

| 组 | 写入目标 | 编辑 kind（`EDIT_KINDS`） |
|---|---|---|
| 战役进度 | 根 `main.yml` | `progress`（声望 / 分数）、`level`（难度） |
| 单位 | 根 `units.yml` | `unit_field`、`unit_spec_add`、`unit_spec_remove`、`unit_spec_active` |
| 作战标记 ⭐ | **战斗层** `games/<场景>/main.yml`（独立场景 `game/main.yml`） | `unit_orders` —— **L3 例外 ②**（§6.2c） |
| 总部 | 根 `hqs.yml` | `hq_field`、`hq_trucks`、`hq_branch_level`、`hq_branch_suppressed`、`hq_branch_sp`、`hq_force_pool`、`hq_force_pool_add`、`hq_force_pool_remove` |
| 手牌 | 根 `cards.yml` | `card_add`、`card_remove`、`card_set` |
| 会议货架 | 根 `main.yml` 的 `card_store` | `card_store_set`、`card_store_add`、`card_store_remove` |
| 会议牌局 | 根 `main.yml` 的 `card_store` | `hand_restore`（读 L2 的检查点 → 写 L1） |
| 商店 | 根 `store.yml` | `store_set`、`store_remove`、`store_add` —— `store` 与 `elite_store` **两个子商店都支持**（§6.3） |
| 战区资产 ⭐ | **战斗层** `games/<场景>/main.yml`（独立场景 `game/main.yml`） | `theater_asset`、`theater_asset_add`、`theater_asset_remove` —— **L3 例外 ①**（§6.2b） |
| 废墟修复 ⭐ | 根 `main.yml` + **战斗层** `games/<场景>/cities.yml` 与 `forts.yml` | `city_restore` —— **L3 例外 ②**（§6.5） |

⚠️ **三个 L3 例外**：
① **战区资产**与②**作战标记**写的是**同一张文件**（当前战斗层那张 `main.yml`）：
战区资产改 `theater_assets`，作战标记改 `no_retreat_units` / `rearguard_units` / `elastic_defense_units`
三个 id 列表；该文件其余键原样搬运（§7.2 W8）。
③ **废墟修复**写的是**另外两张**：`games/<场景>/cities.yml` 与 `games/<场景>/forts.yml`
（场景级的废墟快照与同格要塞），并且**根 `main.yml` 的 `destroyed_cities` 也要一起改**（§6.5.3）。

🚫 **不做里程碑（milestones）相关的任何功能** —— 多数玩家不关心，而且它会削弱成就感；
技术上它还分成"存档内"和"Steam 全局统计"两套，改存档只能管着其中一半（§6.1b、§7.5）。

🚫 **不做"快速存读档"（原工具里的 AHK 热键方案）** —— 玩家已有"所见即所得 Mod"，
它直接透视了未来结果，频繁存读档是它的**下位替代**；而频繁存读档本身会污染存档历史、
让"改了什么"变得不可追溯（§7.5）。

### 0.4 贯穿全文的硬约束（务必先读 §7）

| 约束 | 含义 |
|---|---|
| **只写 L1** | 存档有 5 层，**可写的是根目录那 5 个 YAML**（实测它们**不一定都存在**，缺哪个就禁掉对应功能，**不要新建**）**+ 当前战斗层的那张 `main.yml`**（两个 L3 例外，见下一行）；检查点 / 战斗实时层的其它条目 / 回合历史 / 战役文档**全部只读** |
| **两个 L3 例外** | **当前进行中战斗**那张 `main.yml` 里的两处：**战区资产**（`theater_assets`）与**作战标记**（三个 id 列表）—— 读档即生效、且不是战报（§6.2b、§6.2c、§7.2 W8）。**历史战斗的快照一律不许写** |
| **四条硬拦** | ① 特种兵挂载：阵营相同 + 国籍相同或**单位国籍的父国籍**匹配（单向）；② **手牌槽位上限**（按难度 easy/normal 5、classic 4、hard 3）；③ **判重**：同一个商店 `(战线, 子商店)` 不许有重复条目、同一个总部的兵库不许有"同身份 + 同延迟"两条（§6.2、§6.2b、§6.3）；④ **空降 / 登陆卡不许直接加到手牌**（会召唤单位的那种 ⇒ 游戏读到会崩，§6.3、§4.5） |
| **写盘白名单** | 只允许改根层那五张表 + **当前战斗层**那张 `main.yml`；`document/`、`last_conference/`、`last_game/` 等只读条目**一律不许写**（§7.2 W9） |
| **`save_id` 边界** | 服务端只接受**游戏数据目录**（`<本地应用数据>/.uoc2`）之内的路径（`save/` 与 `modifier_imports/`），出去的一律拒绝（§7.2 W10） |
| **解析失败 ⇒ 整批不写盘** | 任一条目 YAML 解析失败 ⇒ 这一批**一个字节都不写**（不许把坏文件当"空表"写回去）（§7.2 W11） |
| **写盘互斥** | 同一个存档不许两个写盘同时进行（锁文件 `<存档名>.usg.lock`），临时文件名唯一（§7.2 W12） |
| **按下标删除排序** | 兵库删条目、商店下架这类"删第 N 项"的编辑必须**排在最后**，同组**按 index 降序**（§7.2 W13） |
| **不做四个高级功能** | ①改单位编制(`type`) ②新增单位/新增单位类型 ③改登陆进场特种兵 ④"跳到某会议" —— 前三个要写只读层、**游戏内回退不掉**，且玩家看不懂（§7.5）；第四个会让状态机不一致（§6.1） |
| **按能力位开关，不按状态** | 实测 70 个存档里同一功能在 8 个能力位上的可用性各不相同；**缺哪个文件就禁哪个功能**，不要写状态分支（§3.4.5） |
| **独立场景存档没有商店、没有卡牌** | 实测 3/3 的独立场景存档根目录只有 `main.yml`/`units.yml`/`hqs.yml`。这两块功能在独立场景上**整个禁用**（§3.2） |
| **不做里程碑功能** | 多数玩家不关心；它会削弱成就感；技术上"全局图鉴"那份在 Steam 统计里，改存档管不着（§6.1b、§7.5）。**但写回根 `main.yml` 时 `milestones` 字段必须原样保留** |
| **必须有备份 + 撤销** | 写回前自动生成 `<存档名>_BACKUP.usg`（放在 `<修改器目录>/bak/`，**绝不放在存档同目录**）；修改器自带撤销栈（§0.2、§6.4）。**这是产品的底线，不是可选项** |
| **改名直接写明文** | 不做"temp mod + 本地化"那套（§5.5、§7.5） |

---

## 1. 环境事实（本机实测）

| 项 | 值 |
|---|---|
| 游戏安装目录 | `D:\SteamLibrary\steamapps\common\Unity of Command 2` |
| 游戏数据目录 | `%LOCALAPPDATA%\.uoc2`（本机 `C:\Users\misprit\AppData\Local\.uoc2`） |
| 战役存档目录 | `%LOCALAPPDATA%\.uoc2\save\campaigns\*.usg` |
| 独立场景存档目录 | `%LOCALAPPDATA%\.uoc2\save\games\*.usg` |
| 玩家归档目录（**游戏不认**） | `%LOCALAPPDATA%\.uoc2\save\<任意目录名>\*.usg`（修改器照样读；目录名不挑） |
| 游戏原版包 | `<game>/_packages/{base,dlc1..dlc10}/`（base 必装，DLC 可选） |
| 战役定义（剧本） | `<game>/_packages/base/data/campaigns/<campaign_id>.usc/` |
| 实体类型定义 | `<game>/_packages/base/data/entity_types/{unit_types,hq_types,specialists,cards}/` |
| 本地化文本 | `<game>/_packages/base/localization/<locale>/strings.yml`（locale 默认 `chi`） |

`campaign_id` 取值（实测 15 个战役包）：`west` / `france` / `tutorial`（base）、`blitzkrieg`（dlc1）、
`barbarossa`（dlc2）、`moscow`（dlc3）、**`stalingrad`（dlc4）**、`don`（dlc5）、`desert`（dlc6）、
`fox`（dlc7）、`kursk` + `zitadelle`（dlc8）、`balaton` + `berlin`（dlc9）、`ardenes`（dlc10）。
⇒ **每个 DLC 一个或两个战役包**，包路径是 `_packages/<dlc>/data/campaigns/<campaign_id>.usc/`（目录）。

---

## 2. 存档容器格式

### 2.1 `.usg` 就是 ZIP

- **ZIP（deflate）**，无目录条目，**所有条目共用同一个时间戳**（= 存档写入时刻）
- `create_system=0`，`external_attr` 高 16 位 = `0600`（权限位，读取时无影响）
- 条目顺序 = 游戏写入顺序；游戏用 .NET `ZipArchive` **按名字查找**，**不依赖顺序**
- 内层文件全是 **UTF-8 YAML**（`.yml`），外加少量 **NumPy `.npz`** 二进制

> **实测结论**：解包 → 重新打包 → 954/954 条目内容 SHA256 完全一致，`zipfile.testzip()` 通过。
> 重打包安全。两处细微差异（每文件各自 mtime、`external_attr` 高位为 `0o100644` 而非 `0600`）实测不影响游戏加载，**建议仍按游戏约定写回**
> （统一时间戳 + `external_attr = 0o600 << 16`，即 **`0x01800000`** —— ⚠️ 不要写成 `0o1800000`，那不是合法八进制字面量）。

### 2.2 二层 ZIP：`games/<场景>/archive`

`games/<场景>/archive` **本身又是一个 ZIP**，内含**逐回合快照**：

```
deployment_phase_00_allies/      ← 部署阶段
turn_01_phase_00_allies/
turn_01_phase_01_axis/
turn_02_phase_00_allies/
...
turn_08_phase_01_axis/
```

命名规则（来自游戏字节码 `state/game/game.pyc`）：
- `deployment_phase_%02d_%s`
- `turn_%02d_phase_%02d_%s`（turn, phase, 阵营）

每个快照目录内含 **14~22 个文件**（实测 12071 个快照目录的分布：
14:66 / 15:409 / 16:1479 / 17:2743 / 18:3176 / 19:2838 / 20:1085 / 21:263 / 22:12），
**文件名并集共 22 种**：

```
ai_hints.yml  ar_list.yml  bridges.yml  campaign_units.yml  cards.yml  cities.yml
enroute_units.yml  forts.yml  fow.npz  hqs.yml  locale.yml  main.yml
objectives.yml  own.npz  playable.npz  prepositioned_assets.yml  store.yml
stragglers.yml  supply_hubs.yml  supply_sources.yml  units.yml  weather.npz
```

各文件出现次数（12071 个快照）：

```
units.yml / objectives.yml / playable.npz / locale.yml / fow.npz / store.yml
supply_sources.yml / weather.npz / own.npz / main.yml / hqs.yml      12071 （必有）
ar_list.yml                                                            12059
supply_hubs.yml                                                        11924
cards.yml                                                              11846
ai_hints.yml                                                           10395
bridges.yml                                                            10150
stragglers.yml                                                          8109
campaign_units.yml                                                      5974
enroute_units.yml                                                       5187
cities.yml                                                              3986
prepositioned_assets.yml                                               2153
forts.yml                                                              1367   （地图要塞坐标：map: [[坐标, {functional: true}], …]）
```

> ⚠️ **`ar_list.yml`（本回合已执行行动的列表）快照里也有**（12059/12071 = 99.9%）。
> **唯一的例外**：正在进行的战斗，其**最后一个快照**没有它（12 个）——
> 因为快照拍在回合边界，而"本回合行动列表"要到该回合产生行动后才写。
> ⚠️ 所以**不要**用"快照里有没有 `ar_list.yml`"来判断回合状态（这个错误本项目犯过一次，
> 见 §3.4.4.5 的更正说明）。
> 实时层的 `games/<场景>/ar_list.yml` 是**最新**的行动列表（实测 Husky 13 条、MonteCassino 35 条）。

**关键区分（已结束的战斗 vs 进行中的战斗）**：

| | `games/<场景>/units.yml` | `games/<场景>/main.yml` |
|---|---|---|
| **已结束的战斗**（`list[dict]`，691 个文件） | **完整对象列表** ≈ archive 最后快照的 `units.yml`（实测 conf3/avalanche 仅差 1 个单位的 `entr/ap/mp`，即最后一步行动结算差异；ahist2 完全一致） | 该场战斗的结算状态 |
| **进行中的战斗**（`list[int]`，12 战役 + 3 独立场景 = **15 个文件**） | **纯 ID 清单** `list[int]` | **实时状态**，实测**比最后快照新**（Husky `ar_ord` 190 vs 178） |

详见 §3.4.4。

### 2.3 三层 NumPy 二进制（`.npz`）

| 文件 | 键 | dtype | 形状 | 含义 |
|---|---|---|---|---|
| `own.npz` | `own` | uint8 | (508, 373) | 阵营控制图 |
| `fow.npz` | `fow_0`, `fow_1` | bool | (508, 373) | 双方战争迷雾 |
| `weather.npz` | `weather` | uint8 | (508, 373) | 天气 |

508×373 = 地图六边形格点。**修改器不需要碰这些。**

---

## 3. 存档目录结构

### 3.1 战役存档（`save/campaigns/*.usg`）

```
main.yml          units.yml       hqs.yml       cards.yml      store.yml
├── 战役当前状态 ─────────────────────────────────────────────────┘
document/                    ← 战役「剧本」层（见 §3.3）
games/<场景>/                ← 每场战斗各自的状态（存档里可同时存在几十个）
last_conference/             ← 上次会议的检查点（cards/hqs/main/store/units）
last_game/                   ← 上次战斗的检查点（cards/hqs/main/store/units）
```

### 3.2 独立场景存档（`save/games/*.usg`）

```
main.yml   units.yml   hqs.yml      ← 只有这三个根文件（没有 cards.yml / store.yml）
document/                            ← 只有 6 个条目
game/                                ← 注意是单数！该场战斗的状态
```

区分方式：根 `main.yml` 的 `standalone_scenario` 非空 → 独立场景（如 `normandy_breakout`）；否则战役。

> 战役的 `games/<场景>/` 与独立场景的 `game/` 是同一个概念，只是层级不同。**代码必须同时支持两种。**

**独立场景存档的实测细节（3/3 存档全同）**

| 位置 | 内容 |
|---|---|
| 根目录 | `main.yml` / `units.yml` / `hqs.yml` **只有这三个**；⚠️ **没有 `cards.yml`、没有 `store.yml`** |
| `document/` | 恰好 **6 个条目**：`fallback_prices.yml` / `hqs.yml` / `locale.yml` / `main.yml` / `medals.yml` / `units.yml` |
| `document/` 缺什么 | ⚠️ **没有 `scenarios/`、没有 `fronts/`、没有 `conferences/`、没有 `cinematics/`、没有 `restart_scenario.yml`** |
| `game/` | 15 个条目：`ai_hints.yml` `ar_list.yml` `bridges.yml` `fow.npz` `hqs.yml` `locale.yml` `main.yml` `objectives.yml` `own.npz` `playable.npz` `prepositioned_assets.yml` `supply_hubs.yml` `supply_sources.yml` `units.yml` `weather.npz`，外加 `archive`（二层 ZIP） |

**三个必须知道的后果**

1. **独立场景没有商店，也没有卡牌** —— 商店是**会议**机制，独立场景不走会议。
   ⇒ 修改器的「卡牌」「商店」两块功能在独立场景存档上**必须整个禁用**（不是"没数据"，是**这个模式本来就没有**）。
   实测根级文件存在性（70 存档）：战役 67 个里 `store.yml` **67/67 都有**、`cards.yml` **63/67 都有**（缺的 4 个 = 3 个战役开局 + 1 个战役结束）；
   独立场景 3 个里 `store.yml` **0/3**、`cards.yml` **0/3**。
2. **独立场景的场景预设不在存档里** —— 存档的 `document/` 没有 `scenarios/`。
   场景预设（默认兵力、目标、补给点、地图）只在**游戏安装目录**：
   `<game>/_packages/<dlc>/data/campaigns/<campaign_id>.usc/scenarios/<standalone_scenario>/`
   （实测 `unthinkable` 12 个文件；`normandy_breakout` 12 个文件 + `variants/breakout/`）。
   存档里的 `game/` 是**游戏重序列化过的运行时态**，与包里的文件**逐个都不同**（实测 12/12 不同）——
   `game/units.yml` 是 **ID 清单**（`list[int]`，213 个），包里是**完整对象**（54488 字节）；`game/main.yml` 多出运行时字段
   （`ar_ord` / `completed` / `end_data` / `factions` / `intel_markers` / `intel_positions`）。
   ⇒ **不要拿存档里的 `game/` 当成"场景预设"来用。**
3. **独立场景的 `document/` 6 个文件与游戏包同名文件语义等价** —— `yaml.safe_load` 后
   `units.yml` / `locale.yml` / `hqs.yml` / `fallback_prices.yml` **完全相同**；`main.yml` 只多 `security_unit_suffix` / `security_unit_type` 两个键。
   ⇒ 需要战役常量（里程碑、初始声望、`card_type_units`…）时，独立场景存档**同样读得到** `document/main.yml`。

### 3.2b 认出「这是哪个战役 / 哪个场景」

判据全部来自**根 `main.yml`**（L1，只读不写）+ 目录名，不需要加载游戏本体。

| 字段 | 含义 | 实测（70 存档） |
|---|---|---|
| `standalone_scenario` | **非空 ⇒ 独立场景**，值即场景 id | 3/70 非空：`normandy_breakout`×1、`unthinkable`×2 |
| `campaign_id` | 战役包 id | 70/70 都有；west 36 / stalingrad 9 / blitzkrieg 9 / barbarossa 8 / moscow 8 |
| `campaign_name` | 本地化 id，如 `id_campaign_name_c_stalingrad_p_dlc4` | 70/70 |
| `in_state.conference` | 当前会议 id（`c_42_07`） | **战役 67/67 非空**；独立场景 3/3 为空 |
| `in_state.scenario` | **当前战斗所在的场景 id**；非空 ⇔ 正在战斗中 | B1/B2 非空，其余为 `null` |
| `in_state.front` | 当前战线（`south`/`caucasus`/`france`/`italy`） | ⚠️ 与 `in_state.scenario` **完全等价**：70 个存档只有 (null,null) 与 (非空,非空) 两种组合 |
| `in_state.fronts[*].segment` | 当前段 id（`s_42_07_south`） | 战役 64/67 有（缺的 3 个是战役开局） |
| `in_state.variant` | 场景变体（变体战役时非空） | 战役 **2/67** 非空 |
| `in_state.completed` | 战役已通关 | 战役 6/67 为真 |
| `level` | 难度 | 战役 classic 38 / hard 29；独立场景 3/3 classic |

> **所有 70 个存档的根 `main.yml` 顶层都是 17 个键，一个不多一个不少**（`campaign_id` / `campaign_name` / `card_store` /
> `conference_start_state` / `destroyed_cities` / `in_state` / `level` / `milestones` / `num_buyed_turns` / `prestige` /
> `renamed_hqs` / `reverted_games` / `score` / `standalone_scenario` / `tokens` / `tokens_map` / `used_card_types_with_unit`）。

**场景名的四条取法（按可靠性排序）**

1. 正在战斗 → `in_state.scenario`
2. 独立场景 → `standalone_scenario`
3. 已结束的战斗 → **`games/<场景>/` 的目录名**
   ⚠️ **`games/<场景>/main.yml` 里没有 `scenario` 字段** —— 实测 64 个存档的该文件**全部不含此键**，场景名**只能从目录名拿**。
4. 补充：`last_game/main.yml` / `last_conference/main.yml` 是**根 `main.yml` 的完整副本**（实测键集 52/52 完全相同），
   其 `in_state.scenario` 给出"上一次战斗时"所在场景。

**战役包定位：`campaign_id` → 1:1，无歧义**（实测 5/5 唯一）

| `campaign_id` | 包目录 |
|---|---|
| `west` | `<game>/_packages/base/data/campaigns/west.usc/` |
| `blitzkrieg` | `<game>/_packages/dlc1/data/campaigns/blitzkrieg.usc/` |
| `barbarossa` | `<game>/_packages/dlc2/data/campaigns/barbarossa.usc/` |
| `moscow` | `<game>/_packages/dlc3/data/campaigns/moscow.usc/` |
| `stalingrad` | `<game>/_packages/dlc4/data/campaigns/stalingrad.usc/` |

⚠️ **场景 id 本身不唯一**：实测 `normandy_breakout` 在 **base 的 `france.usc` 和 `west.usc` 里都有**。
⇒ 独立场景存档的 `campaign_id` 决定用哪个包（实测 3 个独立场景存档 `campaign_id` 都是 `west` ⇒ 用 `west.usc`）。

**场景清单从哪读**

| 存档类型 | 场景清单来源 | 实测 |
|---|---|---|
| 战役存档 | 存档自带 `document/scenarios/` | west 44 / blitzkrieg 25 / stalingrad 24 / barbarossa 24 / moscow 11 |
| 独立场景存档 | ⚠️ 存档里**没有**，只能读游戏包 | 见下 |

**游戏包里场景预设的两处位置（⚠️ 必须都扫）**

```
<包>/data/campaigns/<campaign_id>.usc/scenarios/<场景>/    ← 战役包内（west 的 unthinkable 在这）
<包>/data/scenarios/<name>.usc/scenarios/<场景>/           ← 独立场景包（dlc4 的 seydlitz 在这）
```

实测独立场景包共 **11 个**：base 9 个（`kasserine_axis` `nordwind` `tutorial_5` `tutorial_6` `tutorial_7`
`tutorial_8` `tutorial_91` `tutorial_92` `wacht_am_rhein`）、dlc4 `seydlitz`、dlc6 `compass`。

⚠️ **还要扫用户包目录**（mod）：`<user>/_packages/<mod>/data/…`，**用户包优先级高于游戏包**
（游戏自己的 `paths.all_package_dirs()` 实测顺序）。本机实测存在 mod `fall_blau_2`
（`%LOCALAPPDATA%\.uoc2\_packages\fall_blau_2\data\scenarios\fall_blau_2.usc\`）——
它证明 mod 机制是活的，**只扫游戏包会漏掉 mod 的场景与新增类型**（§9.1.1）。

⇒ **场景名 → 场景预设** 的映射：战役存档用存档自己的 `document/`（L5，只读）；
独立场景存档用游戏安装目录 —— 若游戏未安装或对应 DLC 未拥有，则**该功能直接不可用**，不要瞎猜。

### 3.3 `document/` = 战役包副本，**但它是运行时活层** ⚠️⚠️

**战役存档**的 `document/` 内容 **等于** `<game>/_packages/<dlc>/data/campaigns/<campaign_id>.usc/`
（⚠️ `.usc` 是**目录**，不是压缩包）。

实测 5 个战役（逐文件 SHA256 比对，存档 `document/` ↔ 游戏包 `.usc/`）：

| `campaign_id` | 存档 `document/` 条目 | 包条目 | 字节级相同 | 不同 | 存档多出 | 存档缺 |
|---|---|---|---|---|---|---|
| `barbarossa` | 429 | 429 | **429** | 0 | 0 | 0 |
| `blitzkrieg` | 372 | 372 | **372** | 0 | 0 | 0 |
| `west` | 850 | 850 | **850** | 0 | 0 | 0 |
| `moscow` | 274 | 274 | 273 | **1**（`units.yml`） | 0 | 0 |
| `stalingrad` | 441 | 441 | 440 | **1**（`units.yml`） | 0 | 0 |

⇒ **除 `units.yml` 以外，`document/` 与游戏包逐字节相同**（合计 2364/2365）。
唯一的活文件是 `units.yml`（见下）。

（⚠️ **独立场景存档不成立** —— 3 个独立场景的 `document/` 只有 6 个条目，见 §3.2。）

> **⚠️ 它不是"只读副本"，而是运行时数据源（L5 层，见 §7.1）：**
> - **读**：每次读档时 `Campaign.load`（`campaign.pyc:166`）用
>   `read_serialization(...).subdirectory('document')` 把存档里的 `document/` 加载成 `CampaignDoc`。
>   `campaign_doc.get_doc_unit(id)`（`type` 的解析源）读的就是它。
> - **写**：游戏会往里写新造的单位（`campaign_doc.add_campaign_unit` → `_save_units_file`）。
> - **不在任何检查点里** ⇒ 改这里的东西**游戏内回退不掉**。
>
> ⇒ **修改器对 L5 只读、绝不写入**（§7.2 W5）。它只被读取，用于 §3.5 的重组预警判定。
>
> **对比时必须先看 `main.yml` 的 `campaign_id`** —— 不同战役的包不同：
> `campaigns\Stalingrad.usg` 的 `document/` 是 **`stalingrad.usc`（dlc4）** 的副本（441 条目，440 个字节级相同，
> 只差 `units.yml`；实测 `campaign_id` = `stalingrad`，与 `barbarossa.usc` 只有 8 个同名文件且全不相同）。

#### `document/units.yml` = 战役**名册**，它会随战役推进变长

它是唯一会变的文件，规律实测如下（存档条目数 vs 包条目数；**存档永远是包的超集，从不缺条目**）：

| 战役 | 包 | 存档条目数随进度的变化 | 存档多出 |
|---|---|---|---|
| `barbarossa` | 912 | 912 → 913 → 917 → **923** | 0 → 1 → 5 → 11 |
| `blitzkrieg` | 835 | 835（6 个存档不变）→ 837 → 843 | 0 → 2 → 8 |
| `moscow` | 1158 | 1158 → 1160 → 1164 → 1168 → 1173 → 1179 → **1185** | 0 → 2 → 6 → 10 → 15 → 21 → 27 |
| `stalingrad` | 785 | 785 → **789** | 0 → 4 |
| `west` | 846 | 846（10 个存档）→ 848 → 851 → 853 → **858** | 0 → 2 → 5 → 7 → 12 |

多出来的条目是**游戏运行时新造的单位**（战役推进时自动生成的警卫分遣队），id 接在包的最大 id 之后：

```
包里 846 个 → 存档里 851 个，新增 id 906..910
{'id': 906, 'name_brief': '1第德国警卫队', 'name_full': '1德国警卫分遣队', 'type': 'ger_inf_39'}
```

**⚠️ 名册与根表不是一回事（实测 12 个存档全部成立）**

| 关系 | 实测 |
|---|---|
| 根 `units.yml` ⊆ `document/units.yml` | **恒成立**（12/12） |
| `document/units.yml` ⊆ 根 `units.yml` | **恒不成立** |
| 同 id 的单位在两处的 `name_brief` 是否一致 | **完全一致**（12/12，0 处不同） |

⇒ `document/units.yml` 是**战役名册**（历史上出现过的全部单位，含已阵亡的），根 `units.yml` 是**当前活着的单位表**。

**字节码实证（谁写、谁读）**

| 动作 | 字节码位置 | 结论 |
|---|---|---|
| **读** 根 `units.yml` | `Campaign._load_campaign_objects`（`campaign.pyc`）：`load_yaml('units.yml', validation_schema=campaign_units_schema(self.campaign_doc))` | 根表用 `campaign_units_schema` 校验，**`campaign_doc`（名册）是校验依赖** |
| **写** 根 `units.yml` | `Campaign._save_campaign_files` → `UnitState.save(self.units, serialization)` | 根表 = 运行时对象，**直接序列化落盘** |
| **写** 名册 | `CampaignDoc._save_units_file` → `save_yaml('units.yml', sorted(self.units.values(), key=…))`（`campaign_doc.pyc`） | 名册由 `CampaignDoc.units` 写出，**是派生数据** |
| 名字的传递方向 | `Campaign._rename_hqs`：`c_hq = self.campaign_doc.get_doc_hq(hq.id); c_hq.name_brief = hq.name_brief` | **运行时对象 → 名册**（单方向） |

> **推论 1**：游戏自己造新单位时，**必须**同时写入 `document/units.yml`（CampaignDoc 名册），否则游戏不认这个 id。
> 这也正是 **`document/` 是运行时活层**的直接证据 —— 但**修改器不造单位**（§7.5），所以对它是**只读**。
> **推论 2**：单位名**可以直接写明文**（游戏自造的警卫队就是这么写的），不需要走本地化 id + temp mod 那一套。原版单位用 `id_unit_name_brief_...` 是因为它们来自游戏包，存档里改写成明文同样有效。
> **推论 3**（改名功能的正确性依据）：名字的流向是 **运行时对象 → 名册**，不是反过来。
> 所以**只改根 `units.yml` 的 `name_brief` / `name_full` 就是对的** —— 游戏读档时直接读根表（`_load_campaign_objects`），
> 下次存档时它会把新名字回写进名册。**不需要（也不应该）去动 `document/units.yml`。**

`document/` 下的**所有**文件（`main.yml`/`units.yml`/`hqs.yml`/`medals.yml`/`locale.yml`/`fallback_prices.yml`/`restart_scenario.yml`/
`scenarios/`/`fronts/`/`conferences/`/`cinematics/`）
对修改器都是**只读**（§7.2 W5）。它们只被读取，用于：查 `type` → 推 `max_st`/`max_spec`、判定 §3.5 的重组风险。
⚠️ 独立场景存档的 `document/` **只有前 6 个文件**，没有 `scenarios/`/`fronts/`/`conferences/`/`cinematics/`（§3.2）。

`document/main.yml` 里的战役常量（west 实测）：

| 字段 | 值/含义 |
|---|---|
| `prestige` | `100` —— **战役初始声望** |
| `score` | `0` —— 战役初始分数 |
| `player_faction` | `'allies'` —— 玩家扮演阵营 |
| `win_conference` | `'c_45_06'` —— 胜利会议 |
| `milestones` | 23 个里程碑的完整定义（见下） |
| `persistent_hqs` | `[21,13,25,5,14,22,24,16,14,44,34,33,27]` |
| `hq_renames` | `[[5,14,16],[27,33]]` |
| `card_type_units` | 卡牌类型 → `{unit_id, replacement_unit_id}` |
| `branching_token_char` | 分支令牌映射 |

`document/main.yml` 的 **23 个**里程碑（其中 `success_90` 标记 `do_not_take=True`，UI 上不提供勾选）：
`masters_of_the_north_african_shores, fascist_regime, slopes_of_st_benedict, early_fall_of_rome, fall_of_rome, a_second_front, according_to_plan, champagne_campaign, not_much_of_a_gap, professionals_study_logistics, success_90(do_not_take), fortress_buster, viennese_waltz, oath_of_kufra, I_ll_be_dam_med, nuts, conquest_of_the_ruhr, bohemia, to_the_moon, unter_den_linden, le_sang_vert, victory_in_the_west, a_third_front`

每个里程碑含 `{do_not_take, name_brief, scenario_name, objective}`。

---

### 3.4 存档状态机（决定"该改哪张表"）

#### 3.4.1 游戏自己的战役 API

从 `lib/uoc2/state/campaign/campaign.pyc` 反编译得到的接口：

| 函数 | 作用 | 触碰的存档路径 |
|---|---|---|
| `play_game(scenario_name, variant, ...)` | 进入一场战斗 | 写 `last_game/` |
| `continue_game(...)` | 继续当前战斗 | 读 `games/` |
| `revert_last_game(debug, remove_saved_game)` | 退回上一场战斗 | 读/写 `last_game/` |
| `revert_last_game_to_deployment(debug)` | **退回部署阶段**（重打本场） | 读/写 `games/`, `last_game/` |
| `set_conference(conference, save_revert_data)` | 进入会议 | 写 `last_conference/` |
| `revert_last_conference(debug)` | 退回上一个会议 | 读 `last_conference/` |
| `end_segment(check_next_segment)` | 本段结束 | 动 `last_conference/`, `last_game/` |
| `can_end_segment()` / `can_revert_to_last_conference()` | 决定 UI 显示哪些按钮 | — |
| `save(location, game, remove_savegames, as_zip, finished_game, rename_hqs)` | 写盘 | **`remove_directory('games'/in_state.scenario)` 后整个重写该目录** + 根文件 + `document/` |

**关键推论**：每次存档，**当前场景的 `games/<场景>/` 会被整个删除并重写**；其他 `games/<x>/` 原样保留（所以战斗目录只增不删）。

#### 3.4.2 可区分的存档状态（可观测签名版）

> ⚠️ **重要**：不要按"状态"写特判逻辑。70 个存档只是**样本**，不是全集。
> 下面这张表给的是**可观测签名**（修改器能直接读到的字段组合）+ **覆盖情况**，
> 实现时应按 §3.4.5 的「能力矩阵」统一处理，而不是为每种状态写分支。

本机 **70 个真实存档**实测（`%LOCALAPPDATA%\.uoc2\save` 下 6 个战役 + 3 个独立场景）的**精确签名分布**：

| 签名（card_store / 根units / last_game / last_conf / seg_finished / completed） | 数量 | 名称 | 样本 |
|---|---|---|---|
| `cards` / ✗ / ✗ / ✗ / F / F | 3 | **C0** 战役开局·第一次会议 | `west-Conference1-1`, `Moscow-Conference1`, `Stalingrad-Conference1` |
| `cards` / ✓ / **?** / **?** / F / F | **0** | **C1** 中途会议界面（已发牌，有单位） | ← **本机样本缺失，但必然可达** |
| `no-cards` / ✓ / ✓ / ✓ / **F** / F | 20 | **M1** 战役地图·本段还有场景 | `west-Conference2-2`, `barbarossa-Conference3-2` |
| `no-cards` / ✓ / ✓ / ✓ / **T** / F | 14 | **M2** 战役地图·本段场景已打完 | `west-Conference4-1`, `barbarossa-Conference3` |
| `no-cards` / ✓ / ✗ / ✓ / T / F | 5 | **M3** 已进入下一会议（跳过发牌） | `Blitzkrieg-Conference2`, `Blitzkrieg-historical-Conference3` |
| `no-cards` / ✓ / ✓ / ✗ / T / F | 3 | **M4** 战役地图·无会议检查点 | `barbarossa-Conference2`, `Moscow-Conference2`, `Stalingrad-Conference2` |
| `no-cards` / ✓ / ✓ / ✗ / F / F | 3 | **M5** 战役地图·第一段 | `Moscow-Conference1-3`, `west-Conference1-2`, `west-Conference1-3` |
| `no-cards` / ✓ / ✗ / ✗ / T / **T** | 6 | **F** 战役胜利（结束） | `barbarossa-fusg`, `west-ahistorical-fusg` |
| `no-cards` / ✓ / ✗ / ✗ / T / F | 1 | **F'** 战役结束但未标记完成 | `west-f.usg` |
| `in_state.scenario` 非空 + archive 有 `turn_NN_*` | 10 | **B1** 战斗进行中 | `Stalingrad.usg`, `west-Tunis` |
| `in_state.scenario` 非空 + archive 只有 `deployment_phase_00_*` | 2 | **B2** 战斗部署阶段 | `west-LastWar`, `west-first-try` |
| `standalone_scenario` 非空 | 3 | **S5** 独立场景 | `west_normandy_breakout` |

**从 70 个存档里学到的判定事实（全部实测）**

- `in_state.front` 与 `in_state.scenario` **完全等价**：70 个存档里只有 `(False,False)` 和 `(True,True)` 两种组合。
- `in_state.segment_finished` 只有 true/false 两值。
- **战役开局（C0）的存档没有根 `units.yml`**（还没生成任何单位），但根 `hqs.yml` 存在。
- `games/<场景>/archive` 的快照命名只有三种形态：`deployment_phase_00_<阵营>`、`turn_NN_phase_00_<阵营>`、`turn_NN_phase_01_<阵营>`。
  → **有没有 `turn_NN_*` 是区分 B1 / B2 的唯一可靠标志**（`games/<场景>/main.yml` 的 `turn` 字段在 B2 里也已经是 1，**不能用它判断**）。
- `card_store` 非空 ⇔ 玩家**正停在会议界面且已发牌**（`set_conference` 刚 `create_random_card_data` 完）。
  `card_store` 为空但 `last_conference` 在 → 会议已离开或被跳过。

#### 3.4.2b 已知可达但**样本未覆盖**的状态

用游戏的 API 反推（`state/campaign/campaign.pyc`）：

```
set_conference(conference, save_revert_data):
    in_state.conference = conference
    card_store = create_random_card_data(level)     # ← 发牌
    conference_start_state = <会议开始时的状态>
    prestige += extra_prestige_on_conference_start[level]
    _create_new_hqs(); _set_hqs_xp_target(); clear_stacks()
    save_revert_campaign_data('last_conference')    # ← 写会议检查点

end_segment(check_next_segment):
    _remove_revert_campaign_data('last_game')        # ← 删战斗检查点
    _remove_revert_campaign_data('last_conference')  # ← 删旧会议检查点
    in_state.segment_finished = False
    ... 求 next_conference ...
    set_conference(next_conference, True)             # ← 进下一个会议，重新写 last_conference

play_game(scenario, variant, ...):                   # ← 进战斗，写 last_game
game_finished():                                     # ← 战斗结束
    in_state.completed = outcome_status
    in_state.lost_scenario = in_state.scenario        # ← 输了
    ... segment_finished / situation_idx / milestones ...
```

由此可推出**必然可达、但本机 70 个存档里没有**的状态：

| 状态 | 为什么会产生 | 签名 | 修改器必须正确处理 |
|---|---|---|---|
| **C1 中途会议界面** | `end_segment` → `set_conference(c2)` 后玩家停在会议界面就存档 | `cards` / ✓units / ✗last_game / ✓last_conf / F | 正常改单位；**不要动 `last_conference/`**（那是玩家的游戏内撤销基线，§7.2 W2） |
| **L 刚输掉一场** | `game_finished()` 里 `in_state.lost_scenario = in_state.scenario` | `no-cards` / ✓units / ? / ? / ? | `lost_scenario` 非空 → 场景显示为"已失败"；**改单位不影响该场失败判定** |
| **C1 + `card_store` 被清空** | 会议界面点"开始会议"跳过发牌 | `no-cards` / ✓units / ✗last_game / ✓last_conf | 与 C1 同处理 |
| **R 回滚后** | `revert_last_game` / `revert_last_game_to_deployment` / `revert_last_conference` | 同被回滚到的目标状态 | 与目标状态同处理 |
| **F' 战役结束但未标记完成** | `west-f.usg` 已实测（1 例） | `no-cards` / ✓units / ✗ / ✗ / T / F | 与 F 同处理（= §3.4.2 的 **F'**） |

> **结论：不要用"状态枚举 + switch"的方式实现。**
> 用 §3.4.5 的能力矩阵，任何**没见过的状态组合**都会自然落到正确的行为上。

#### 3.4.3 每种状态下的"活着的单位表"在哪 ⚠️ 最容易搞错的地方

**实测结论（铁证）**

```
Stalingrad.usg   （B1 战斗进行中）
  根 units.yml                       354 个单位对象
  games/road_to_stalingrad/units.yml 86 个 int（ID 清单）
  archive 最后快照/units.yml          86 个单位对象
  → 根表里那 86 个参战单位 vs archive 快照：**逐字段完全一致，差异 0**
```

```
west-LastWar.usg （B2 刚进部署阶段）
  根 units.yml                       670 个单位对象
  games/unthinkable/units.yml         213 个 int（ID 清单）
  archive 唯一快照/units.yml          213 个单位对象
  → **逐字段完全一致，差异 0**
```

> **所以：根 `units.yml` 就是"实时单位表"。**
> 战斗中的单位**就在根 `units.yml` 里**（带实时 `uv`/`ap`/`mp`/`act_st`/`supply`）。
> `games/<当前场景>/units.yml` 只是 **ID 清单**（本场有哪些单位），不是实体数据。

#### 3.4.3b 根表装的是"**已经登场过**"的单位，不是战役全部单位 ⚠️

> 实测（`e86_root.py`，67 个战役存档全量普查）。**这决定"改单位"功能能改到哪些单位。**

| 战役 | 战役总场景 | 名册（`document/units.yml`） | 根表（`units.yml`）随进度的变化 | 战役通关时名册仍多出 |
|---|---|---|---|---|
| `barbarossa` | 24 | 912 | 0 → 262 → 451 → 560 → 664 → 810 → **875** | **48** |
| `stalingrad` | 24 | 785 | 0 → 130 → 282 → 299 → 323 → **354** | **435** |
| `moscow` | 11 | 1158 | 0 → 100 → 107 → 213 → 330 → 567 → **615** | **570** |
| `west` | 44 | 846 | 0 → 47 → 102 → 150 → 232 → 335 → 492 → **670** | **183** |
| `blitzkrieg` | 25 | 835 | 0 → 121 → 341 → 354 → 406 → **647** | **189** |

**三个实测结论：**

1. **战役开局（C0）根表是空的** —— 实测 3 个 C0 存档：根表 **0** 个单位，名册 785/846/1158。
   ⇒ 「战役一开始就写入了全部单位」**不成立**。
2. **根表随进度单调增长，但永远小于名册** —— 战役打完全部场景后，根表仍然只有名册的
   76%~95%（barbarossa 875/923、stalingrad 354/789、moscow 615/1185、west 670/853、blitzkrieg 647/835）。
   ⇒ **根表装的是"到当前进度为止已经登场过的单位"**；
   **未来场景才出现的单位只在名册里，没有运行时状态（无 `xp`/`act_st`/`uv`），改不了。**
   ⇒ **修改器的"改单位"列表 = 根表的内容**（不是名册！）。名册只用于查 `type` → `max_st`/`max_spec`。
3. **根表里同时有双方单位** —— 实测 `Stalingrad.usg` 根表 354 条：
   `uv` 非空（已部署到战役地图）191 条、`uv` 为 `null`（尚未部署）163 条，
   德国单位（`ger_jag_dlc4`/`ger_geb_dlc4`）与苏联单位（`sov_tank_dlc4`/`sov_cav_dlc4`）**同时存在**。
   ⚠️ 根表**没有 `faction` 字段**（19 个运行时字段 + `id`/`type`/`name_brief`/`name_full`/`specs`），
   阵营要靠 `type` 去 `entity_types/unit_types/` 反查。

> **对修改器的直接影响**：
> - 玩家能改的单位 = **根表里已有的那些**（已登场过的）。想改"还没登场"的单位是做不到的 —— 它们连运行时字段都没有。
> - UI 上"敌我单位"要靠 `type` 反查阵营，**不能假设根表只有玩家单位**。
> - ⚠️ **不要把名册（785~1185 条）当成可改单位列表展示** —— 那会让玩家以为能改未来场景的单位。

#### 3.4.3c 「下一场要打的场景」的单位，有多少已经能改？⭐

> 实测（`e87_next.py`）：对 67 个**战斗外**战役存档，取当前段的
> `document/fronts/<战线>/segments/<段>/data.yml` 的 `situations`，逐个场景比对
> `document/scenarios/<场景>/units.yml` 的 id 与根表的交集。

| 当前段场景的单位在根表里的比例 | 例数 |
|---|---|
| **全部已在根表**（100%） | **161** |
| 部分在（3.3% ~ 98.3%） | 54 |
| 完全不在（0%） | 3 |

**规律（看同一存档内不同场景的对比就一目了然）**：

- 进度靠后的存档 → 当前段里**所有**场景都是 100%（都打过了）；
- 进度靠前的存档 → **已经打过的场景是 100%，还没打的场景只有一部分**（实测 `bocage` 15.9%、
  `overlord` 3.3%、`normandy_breakout` 11.5%、`husky` 0%）；
- 同一个存档里，`west-ahistorical` 的 `wacht_im_nordrhein` 100% 而 `ljubljana_gap` 50%。

**为什么"未来的场景"也有一部分单位已在根表？**
⇒ **同一个单位 id 会跨场景复用**。一个德军单位在 `bocage` 出现过，它就"登场过"，
后面 `normandy_breakout` 里的同一个单位也已经在根表里了。

> **⭐ 所以真正的判据不是"这个单位属于哪一场战斗"，而是"这个单位 id 是否已经在根表里"。**

**三条直接可用的结论**

1. **不需要"先开始当前关卡"才能改下一场的单位** —— 只要那个单位 id 已经在根表里就行，
   而这在战役推进了一段之后是**常态**（161/218 例是 100%）。
2. **战斗外改 `xp` 对 A 类单位是有效的**（§3.5.8 矩阵）—— `xp` **不在**场景覆盖列表里，
   所以在战役地图上改完 xp，进战斗不会被 `Game.new` 冲掉。
   ⇒ **不需要一场一场地打才能"提前强化"**（这是最省事的批量强化路径）。
   ⚠️ 但**战斗中一旦补兵，xp 会被扣**（`deploy_calc_new_xp = max(100, xp − 缺口×cost)`，§3.5.6）。
3. **真正的硬限制只有一条**：**战役刚新建时根表是空的**（实测 C0 存档根表 0 条），
   此时**一个单位都改不了**。必须至少让第一批单位登场（打完一场，或让当前段的部队进入战场）。

**⇒ 给修改器产品的结论**

| 想做的事 | 可行性 |
|---|---|
| 战役刚建就"统一强化全军" | ❌ 做不到（根表为空，且未来场景的新单位还没登场） |
| 战役推进一段后，批量强化**已在根表**的单位 | ✅ **可以，而且不用进战斗**（改 `xp` / `act_st` / `specs` 列表 / 改名） |
| 强化某个**还没登场**的单位 | ❌ 做不到 —— 只能等它登场（打完一场戏）后改 |
| 给**全部**单位改名 | ⚠️ 只能改已登场的；且**改名是战斗内外都有效的字段**（§3.5.8），是最省心的一项 |
| 战斗外改完 → 玩家打下一场 | ⚠️ A 类单位：你的 `xp`/`act_st`/`specs` **保留**；<br>登陆/空降/增援单位（B/C 类）：`xp` 按缺口重算、`act_st` 被补到场景目标、`specs` 按 type 对账 |

**`games/<场景>/units.yml` 与 `hqs.yml` 有两种格式，规则是确定的：**

| 场景性质 | 格式 | 实测计数 |
|---|---|---|
| **当前活动场景**（`in_state.scenario == 场景名`） | `list[int]` —— ID 清单 | 战役 12 个存档 × 2 文件 = 24 |
| **已结束的存档战斗**（历史，可回放） | `list[dict]` —— 完整对象 | 691 |
| 独立场景的 `game/units.yml` | `list[int]` —— ID 清单 | 3 个存档 × 2 文件 = 6 |

> 全部 70 个存档里 **ID 清单出现恰好 30 次**（12 个战役存档的 `units.yml`+`hqs.yml` = 24，
> 加 3 个独立场景的 `game/units.yml`+`game/hqs.yml` = 6），与上表**完全吻合**，无一例外。
> **根 `units.yml` / `hqs.yml` / `last_conference/*` / `last_game/*` 永远是完整对象**（67/70、70/70、48/48、51/52）。
>
> ⚠️ **解析时必须用 `yaml.safe_load` 判断类型，不能靠文本形态** ——
> 实测**有 8 处** `games/<场景>/hqs.yml` 用的是**流式单行写法**（`[2, 11, 12, 23]\n`），
> 其余 698 处是块式（`- 12\n- 13\n…`）。按「首行是不是 `- ` 开头」来判类型会在这 8 处出错。

**因此，修改器该改哪张表：**

| 玩家想改的东西 | 状态 | 改这里 |
|---|---|---|
| 战斗中的单位/总部 | B1 / B2 | **根 `units.yml` / `hqs.yml`**（按 ID 找） |
| 战役地图上的单位/总部 | M1..M5 | **根 `units.yml` / `hqs.yml`** |
| 已结束战斗里的单位（历史存档 / 回放） | 任意 | 🔒 **只读** —— `games/<场景>/units.yml`（完整对象格式）属于 L3，**不改**（§7.2 W3） |
| 独立场景里的单位 | S5 | **根 `units.yml` / `hqs.yml`**（`game/units.yml` 是清单） |

> **推论**：修改器**永远只改根 `units.yml` / `hqs.yml`**（L1），就能覆盖 B1/B2/M1..M5/S5 的绝大多数需求。
> 历史战斗里的单位**可以查看、不可修改** —— 它们属于 L3（战斗实时层）/ L4（回合历史），
> 改那些等于伪造战报（§7.4 R5）。
> **解析代码必须同时支持 ID 清单与完整对象两种格式**，否则会在 15/706 的文件上炸掉。

#### 3.4.4 战斗中单位数据的确切机制 ⚠️ 字节码 + 实测双重验证

> **一句话回答"战斗中的单位数据在哪"：**
> 战斗中每个单位的信息**在全局只有一份**，就在**根 `units.yml`（战役名册总表）**里；
> `games/<当前场景>/units.yml` **一个数值都不存**，它只是"本场有哪些单位"的 **ID 清单**；
> `games/<当前场景>/archive/<快照>/units.yml` 是**回合边界的历史快照**，比总表**旧**。

##### 3.4.4.1 各层文件的职责（本节最重要的产出）

| 文件 | 层 | 存什么 | 谁写的（字节码实证） | 与根表的关系 | **修改器能写吗** |
|---|---|---|---|---|---|
| **根 `units.yml`** | L1 | **全部单位实例的完整状态**（19 字段） | `Campaign._save_campaign_files` → `UnitState.save(self.units, serialization)` | **权威源**。战斗中的单位就在这里，且是最新的 | ✅ **写** |
| **根 `hqs.yml`** | L1 | 全部总部实例 | 同上 → `HQState.save(self.hqs, serialization)` | 权威源 | ✅ **写** |
| **根 `main.yml`** | L1 | 战役当前状态（声望/分数/里程碑/会议号/`card_store`） | `Campaign._save_campaign_main_file` | 权威源 | ✅ **写** |
| **根 `cards.yml`** | L1 | 持久卡牌库存 | `Campaign._save_campaign_game_files` | — | ✅ **写** |
| **根 `store.yml`** | L1 | 商店库存 | 同上 | — | ✅ **写** |
| `games/<场景>/units.yml` | L3 | **纯 ID 清单** `list[int]` | `Gamelike._save_gamelike` → `save_yaml_check_empty(list(self.units.keys()), UnitState.FILENAME)` | 只有索引，**没有任何数值** | ❌ 只读 |
| `games/<场景>/hqs.yml` | L3 | 纯 ID 清单 | 同上 | 同上 | ❌ 只读 |
| `games/<场景>/main.yml`（独立场景是 `game/main.yml`） | L3 | **战斗实时元数据**：`turn/phase/ar_ord/scores/supply/theater_assets/…` | `Game._save` → `serialization.save_yaml(data, 'main.yml')` | **实测比最后快照新** | 🔶 **只写 `theater_assets` 与三个作战标记 id 列表**（当前战斗层；§7.2 W8），其余只读 |
| `games/<场景>/ar_list.yml` | L3 | 本回合已执行行动列表 | `Game._save` | **实时层最新**；快照里也有同名文件（累计到该回合边界），但**进行中战斗的最后一个快照没有它** | ❌ 只读 |
| `games/<场景>/enroute_units.yml` | L3 | 行军 / 待部署单位定义 | `Gamelike._save_gamelike` | 实时层（70 存档里 5 个有） | ❌ 只读 |
| `games/<场景>/archive/<快照>/units.yml` | L4 | **回合边界的完整对象**（参战单位全量，含已阵亡） | `Game._game_data_snapshot` | **比根表旧** | ❌ 只读 |
| `games/<场景>/archive/<快照>/main.yml` | L4 | 回合边界的战斗元数据 | 同上 | **比 `games/<场景>/main.yml` 旧** | ❌ 只读 |
| `games/<场景>/archive/<快照>/campaign_units.yml` | L4 | **还能被用到的战役单位**的完整对象 | `Campaign._save_campaign_units(serialization, self._get_unit_ids_that_can_be_used())` | 根表的一个**子集**。⚠️ 若被加载会覆盖根表，但**实测读档路径上不会加载它**（§3.4.5.3） | ❌ 只读 |
| `games/<场景>/archive/<快照>/enroute_units.yml` | L4 | 行军单位定义 | `Gamelike._save_gamelike` | 与实时层同源 | ❌ 只读 |
| `document/units.yml` | L5 | **战役文档名册**：`{id, name_brief, name_full, type}`（Stalingrad 存档里 789 个） | 游戏包 + 游戏运行时 | **`type` 的唯一权威来源** | ❌ 只读 |
| `document/scenarios/<场景>/units.yml` | L5 | **场景预设单位**，**没有 `type` 字段** | 游戏包（静态） | 键：`act_st, entr, hq_id, id, name_brief, specs, sup_st, supply, uv, xp` | ❌ 只读 |
| `document/scenarios/<场景>/enroute_units.yml` | L5 | 场景预设的行军单位 | 游戏包（静态） | 键：`on_turn, positions, unit{act_st, hq_id, id, specs, sup_st, xp}` | ❌ 只读 |

##### 3.4.4.2 为什么总表和战斗是同一批对象（字节码）

加载侧（`Gamelike._load_entities`）：

```python
if scenario_data:                       # 场景 / 独立场景模式
    HQState.load(...) ; UnitState.load(...)       # 直接用场景文件里的完整对象
elif not archive:                      # 没有历史快照
    serialization.load_yaml('units.yml')          # 读出 ID 清单
    -> campaign.allocate_unit(unit_id, self)       # 从【战役名册】取出该单位对象
    -> self._set_unit(...)
else:                                  # 有 archive 的战斗读档
    UnitState.load(..., validation_schema=campaign_units_schema(campaign_doc))
```

**关键**：战斗里的单位对象是从战役名册（根表）里"取"出来的**同一批对象**；游戏在战斗中改的就是名册里的那一份。

写回侧（对称的两段）：

```python
Campaign._save_campaign_files(serialization):
    self._save_campaign_main_file(serialization)   # 根 main.yml
    UnitState.save(self.units, serialization)      # 根 units.yml ← 名册，含实时状态
    HQState.save(self.hqs, serialization)          # 根 hqs.yml
    self._save_campaign_game_files(serialization)  # cards.yml + store.yml

Gamelike._save_gamelike(serialization, complete_data):
    if IS_GAME:
        serialization.save_yaml_check_empty(list(self.units.keys()), 'units.yml')  # 只写 ID！
        serialization.save_yaml_check_empty(list(self.hqs.keys()),  'hqs.yml')
    else:
        UnitState.save(self.units, ...)            # 场景模式才写完整对象
```

##### 3.4.4.3 实测验证（三个存档逐字段比对）

| 存档 | 根表 | 参战清单 | 最后快照 | 清单⊆快照 | 根表 vs 快照**有差异的单位数** | 差异样例 |
|---|---|---|---|---|---|---|
| `Stalingrad.usg`（T1 部署后） | 354 | 86 (`list[int]`) | 86 个对象 | 86/86 | **0** | — |
| `west-Husky.usg`（T5 战斗中） | 100 | 21 | 23 个对象 | 21/23 | **5** | `uv [190,274]→[190,275]`、`mp 0→3`、`ap 1→3`、spec 激活位变化 |
| `west-MonteCassino.usg`（T6 战斗中） | 133 | 20 | 23 个对象 | 20/23 | **13** | `xp 328→329`、`uv` 移动、`act_st` 变化 |

- 清单里比快照少的 id（Husky `136,166`；MonteCassino `187,189,200`）= **本回合阵亡被移除的单位**，它们只留在历史快照里。
- 根表里多出来的差异**全部是战斗实时量**（`uv` 移动、`ap`/`mp` 消耗、`xp` 增长、`specs` 激活）→ **总表是"当前"，快照是"回合边界"**。
- `Stalingrad` 差异为 0，是因为它正好停在回合 1 边界，根表和快照是同一时刻。

`games/<场景>/main.yml` 同样是实时的（比快照新）：

| 存档 | `games/<场景>/main.yml` | 最后快照 `main.yml` |
|---|---|---|
| `west-Husky.usg` | `turn 5 / phase 0 / ar_ord 190`，`supply.trucks=[1]`，`tow_sup` 非空，`scores.enemy_kia 36` | `ar_ord 178`，`trucks=[2]`，`tow_sup` 空，`enemy_kia 34` |
| `west-MonteCassino.usg` | `turn 6 / phase 0 / ar_ord 282`，`scores.enemy_kia 63` | `ar_ord 248`，`enemy_kia 54` |
| `Stalingrad.usg` | `turn 1 / phase 0 / ar_ord 29` | 同（正好在回合边界，一致） |

而且 `games/<场景>/ar_list.yml` 在 Husky 有 13 条、MonteCassino 有 35 条行动记录。
⚠️ **快照里也有 `ar_list.yml`**（内容 = 累计到该回合边界的行动），
只是**进行中战斗的最后一个快照没有它**（12/12071）—— 本项目曾因此得出"快照里没有 ar_list.yml"的错误结论，
见 §3.4.4.5 的更正说明。

##### 3.4.4.4 参战单位的来源（四类）

| 来源 | 判据 | Stalingrad | Husky | MonteCassino |
|---|---|---|---|---|
| 场景预设单位 | id ∈ `document/scenarios/<场景>/units.yml` | 86（全来自预设） | 5 | 13 |
| 战役带入 / 上局幸存 | 在参战清单里但不在预设里 | 0 | 16 | 7 |
| 行军 / 待部署 | 出现在该快照的 `enroute_units.yml`（**快照时点还没抵达战场的**） | 2（id 20, 95；`on_turn` 2 / 3） | 6 | 3 |
| 卡牌提供的单位 | `used_card_types_with_unit` | — | 1（id 570） | 1（id 570） |

##### 3.4.4.5 `campaign_units.yml` 的确切语义（⚠️ 本节更正了初稿的说法）

初稿曾把它写成"本场中来自战役名册的单位"。**那是错的。**

字节码实测：

```python
Game._get_unit_ids_that_can_be_used(self):
    unit_ids  = {行军单位 id}
    unit_ids |= {前置资产(pp_assets)携带的单位 id}
    if campaign.card_deck:
        for c in campaign.card_deck.values():
            unit_id = c.unit_id or campaign_doc.get_card_type_unit_id(c.card_type)
            if unit_id: unit_ids.add(unit_id)          # 卡牌引用的单位
    for obj in self.objectives.values():              # 目标奖励卡引用的单位
        if obj.reward_type == 'card': ...
    return unit_ids
```

即 **`campaign_units.yml` = "还能被用到的、来自战役名册的单位"的完整状态**，
来源 = 行军单位 ∪ 卡牌引用的单位 ∪ 目标奖励卡引用的单位。
随着卡牌被打出、行军单位抵达战场，这个列表**单调变短**（实测 `7→7→4→4→3→3→2→2→2→2→1→1→1→1→0`）。

实测 id 集合（`west-Husky.usg`）：

```
turn_01_phase_00_allies  enroute=[519,178,156,520,5,157]   campaign_units=[46,94,95,570]
turn_01_phase_01_axis    enroute=[519,178,156,520,5,157]   campaign_units=[570]
turn_02_phase_01_axis    enroute=[178,156,520,157]         campaign_units=[570]
turn_04_phase_00_allies  enroute=[178]                     campaign_units=[570]
turn_05_phase_00_allies  enroute=(无)                      campaign_units=[570]
```

`46/94/95` 是**卡牌引用的战役单位**（卡被打出后从列表消失），`570` 是卡牌
`tactical_naval_assault_us` 携带的单位（根 `main.yml` 的 `used_card_types_with_unit: {tactical_naval_assault_us: [570]}`）。

> **为什么这个文件对修改器重要**：加载侧 `Campaign._load_campaign_units(serialization)` 会把
> `campaign_units.yml` **读回 `campaign.units[id]`** —— 也就是说**它能覆盖根表里的同名单位**。
> 所以如果某个单位也出现在某份 `campaign_units.yml` 里，那份文件里的旧值**理论上会盖掉你的修改**。
>
> **但按 §7 的策略，修改器不写这些文件**，理由三条：
> 1. **读档路径上它不会被加载** —— `Game._load` 的序列化对象是 `games/<场景>/`，
>    而 `games/<场景>/campaign_units.yml` **在全部 70 个存档的所有场景目录里 0 次出现**
>    （对照：`enroute_units.yml` 出现 97 次）；它只存在于 `archive/` 快照里。
> 2. `archive/` 是**历史/回放基线**，写它属于污染历史（§7.2 W4）。
> 3. 真要覆盖时，是**回退**路径（整表替换）覆盖的 —— 那是玩家的安全网，属预期行为。
>
> ⇒ **只写根 `units.yml` 即可**；不要动任何 `campaign_units.yml`。
**文件分布实测（70 个存档全普查）**：

```
games/<当前场景>/units.yml 是 ID 清单的存档          15 / 15  （当前场景目录里 0 个是完整对象）
games/<当前场景>/campaign_units.yml 存在              0 / 15  （只出现在 archive 快照里）
games/<当前场景>/enroute_units.yml 存在              5 / 15
archive 最后快照含 units.yml                         15 / 15
archive 最后快照含 campaign_units.yml                10 / 15
archive 最后快照含 enroute_units.yml                  5 / 15
archive 最后快照含 ar_list.yml                        0 / 15   ← ⚠️ 这个数字是【口径造成的假象】，见下
```

> ⚠️⚠️ **⚠️ 本项目犯过的一个错：把"快照里没有 `ar_list.yml`"当成了结论。**
>
> **错在哪**：上面那行 `0 / 15` 只抽了**当前场景的最后那个快照**，
> 而"进行中战斗的最后一个快照"恰好**总是没有** `ar_list.yml`
> （快照拍在回合边界，本回合行动列表还没写）—— 于是 15 个样本**全中**这个例外。
>
> **真相**（12071 个快照目录全普查）：
> `ar_list.yml` 出现在 **12059/12071 = 99.9%** 的快照里；
> 只有 **12 个**没有 —— 正好是本机"正在进行的战斗"的最后快照。
>
> **教训**：**不要用"最后一个快照"抽样做存在性普查** ——
> 它恰好是所有快照里最特殊的那一个。要下结论，就得全量普查。

##### 3.4.4.6 `type` 从哪来（**只读参考** —— 修改器不改 `type`）

```
document/units.yml            : {id, name_brief, name_full, type}   ← 789 个，type 的唯一权威来源
document/scenarios/*/units.yml : 【没有 type 字段】
根 units.yml                   : 有 type（属于实例字段）
```

- 场景预设单位**不带 `type`**，游戏是靠 id 去 `document/units.yml` 解析类型的。
- 实测链路：`document/units.yml` id=2 → `type: ger_jag_dlc4` → 根表 id=2 → `type: ger_jag_dlc4` ✓
- **因此修改器把 `type` 当只读信息展示**，并据此推导 `max_st` / `max_spec`（§5.4、§7.5）。
- `specs[].type` 同理，必须能在 `entity_types/specialists/`（375 个）里找到 —— **这个是玩家可改的，必须校验**。

##### 3.4.4.7 修改器在"战斗中"的正确做法（可执行清单）

1. 改单位 → **写根 `units.yml`**（权威源）。
2. **不要**改 `last_conference/`、`last_game/` —— 它们是玩家的游戏内撤销基线（§7.2 W2）。
3. `games/<场景>/` 下**除当前战斗那张 `main.yml` 的白名单键外**，其余都**不要动** ——
   `archive/` 是历史/回放基线（§7.2 W4），`ar_list.yml` 是回合流程状态（§7.2 W3）；
   `main.yml` 只有 `theater_assets` 与三个作战标记 id 列表可改（§7.2 W8、§6.2b、§6.2c）。
   ⚠️ 独立场景的战斗层是**单数目录 `game/`**（`game/main.yml`），规则相同。
4. **不要**改 `games/<场景>/campaign_units.yml`（实测该路径根本不存在，读档也不会加载它）。
5. `games/<场景>/units.yml`（ID 清单）**不用改** —— 修改器**不提供新增单位**（§7.5）。
6. **不要**改 `document/`（含 `units.yml` 与 `scenarios/*`）—— 战役文档层只读（§7.2 W5）。

##### 3.4.4.8 本节未能完全验证的部分（如实标注）

- `Game._load` 在**有 archive** 分支里用 `UnitState.load(..., campaign_units_schema)` 读**完整对象**，
  但**这个序列化对象究竟取自"最后快照目录"还是别的目录，本次没跑通完整调用链**。
  不过这**不影响写入策略**：无论它读的是哪一份，L2/L3/L4/L5 都**只读**（§7.2 W2–W5），
  写它们的风险（见 §7.4 R1–R6）远大于"可能丢一次修改"的收益。
- `Game._save` 里 `campaign._save_campaign_units(serialization, ...)` 写向哪个 `serialization`，
  **未逐字节验证**；这里只依据"实测 `games/<场景>/campaign_units.yml` 不存在、只存在于快照里"反推。
- `games/<场景>/units.yml` 这个 ID 清单**在读档时是否被读取**、还是仅用于存档展示，**未实测**
  （读档走的是"快照"与"名册"两条路）。
- 以上三点**不影响**"改单位 = 改根 `units.yml`"这个主结论 —— 它有实测逐字段比对 + 字节码双向支撑。

#### 3.4.5 能力矩阵（**实现方式：按能力，不按状态**） ⭐

> **这是整个修改器的核心设计原则。**
> 70 个存档只是样本，真实玩家会遇到样本里没有的组合（比如"会议发牌后立刻存档"）。
> 如果按"状态枚举 + switch 分支"实现，遇到没见过的组合就会出错。
> 如果按下面的**能力矩阵**实现，任何组合都会自然落进正确的行为。

##### 3.4.5.1 解析阶段：算出 8 个能力位

打开一个存档后，只计算这 8 个布尔量，**不要**试图给存档"贴状态标签"：

| 能力位 | 怎么算 | 含义 |
|---|---|---|
| `has_root_units` | 根 `units.yml` 存在？ | 有没有战役名册可以改单位（实测 **67/70** 个存档有） |
| `has_root_hqs` | 根 `hqs.yml` 存在？ | 有没有总部可以改（实测 **70/70**，恒存在） |
| `has_root_cards` | 根 `cards.yml` 存在？ | 有没有卡牌库存可改（实测 **63/70**；3 个独立场景 + 4 个战役存档没有） |
| `has_root_store` | 根 `store.yml` 存在？ | 有没有商店可改（实测 **67/70**；3 个独立场景没有） |
| `has_card_store` | 根 `main.yml` 的 `card_store` 非空？ | 玩家是否正停在会议界面（已发牌） |
| `cp_conference` | `last_conference/` 存在？ | 有没有会议回退基线。**只用于 UI 提示与"恢复牌局"，不参与任何写入决策**（§7.2 W2） |
| `cp_game` | `last_game/` 存在？ | 有没有战斗回退基线。同上，**只读不可写**（§7.2 W2） |
| `in_battle` | **当前战斗目录存在？**（战役 `games/<场景>/main.yml`；独立场景 `game/main.yml`） | 是否在战斗里（决定要不要显示"当前战斗"信息）。⚠️ **独立场景存档的 `in_state.scenario` 恒为 null**，只看它会误判成"不在战斗"（`container.py::battle_dir`） |

再加两个**仅用于展示**的量（不参与决策）：
`battle_turn`（从 `games/<scenario>/main.yml` 读）、`battle_phase`（部署阶段 / 战斗中）。

##### 3.4.5.2 编辑能力矩阵

| 要改的东西 | 写入目标 | 依赖的能力位 | 不可用时 |
|---|---|---|---|
| 声望 / 分数 | 根 `main.yml` | 恒可用（实测 70/70 都有） | — |
| 🚫 里程碑 | — | — | **不提供任何入口**（§6.1b、§7.5）；写回时该字段**原样保留** |
| 卡牌（库存） | 根 `cards.yml` | `has_root_cards` | 禁用 + 提示"该存档没有卡牌库存数据"（实测 7/70 个存档无此文件） |
| 会议手里的牌（**编辑已有手牌**） | 根 `main.yml` 的 `card_store` | `has_card_store` | 禁用 + 提示"当前不在会议界面"（见下一行的「恢复牌局」） |
| 会议手里的牌（**恢复上次会议的牌局**） | 根 `main.yml` 的 `card_store` | `cp_conference` | 禁用 + 提示"该存档没有会议检查点，无法恢复牌局" |
| 商店 | 根 `store.yml` | `has_root_store` | 禁用 + 提示"该存档没有商店数据"（实测 3/70 个存档无此文件） |
| 单位 | 根 `units.yml` | `has_root_units` | **禁用** + 提示"该存档还没有可编辑的单位" |
| 总部 | 根 `hqs.yml` | `has_root_hqs` | 禁用 |
| **总部兵库（存货）** | 根 `hqs.yml` 的 `force_pool[].quantity` | `has_root_hqs` | 禁用（§6.2b） |
| **战区资产** ⭐ | 🔶 `games/<当前场景>/main.yml` 的 `theater_assets` | `in_battle` **且** 该场景目录存在 | 禁用 + 提示"当前不在战斗中，战区资产由场景在开打时计算"（§6.2b、§7.2 W8） |
| **作战标记** ⭐ | 🔶 `games/<当前场景>/main.yml`（独立场景 `game/main.yml`）的三个 id 列表 | `in_battle` **且** 当前战斗目录存在 | 禁用 + 提示"当前不在战斗中，作战标记是战斗里的命令"（§6.2c、§7.2 W8） |
| 改名 | 随单位/总部 | 同上 | 禁用 |
| 历史战斗里的单位（回放） | 🔒 **只读** `games/<场景>/units.yml` | 无（存在即显示） | 只读展示，灰显不可编辑（§7.2 W3） |
| 历史战斗的战区资产 | 🔒 **只读** `games/<场景>/archive/<快照>/main.yml` | 无 | 只读展示，**永远不可编辑**（§6.2b） |

##### 3.4.5.3 检查点会在哪些路径上覆盖根级修改（**⚠️ 旧的“写回时同步检查点”建议已被 §7 推翻**）

> **前一版文档在这里建议"把改动同步进 `last_conference/` 和 `last_game/`"，
> 经复核这是错的** —— 它会摧毁玩家唯一的游戏内撤销能力。
> **现行策略见 §7：只写 L1（根状态），其余各层一律只读。**

保留本节是因为"检查点会在哪些路径上覆盖根级修改"这个知识仍然有用：

```
若玩家点了「重置会议」/「重打上一场」：
    根级修改  →  被检查点整体替换  →  消失（这是预期行为，是玩家的安全网）
若玩家读档继续战斗：
    根级修改  →  保留（Game._load 不重算，§3.5.1）
```

**检查点的文件清单（实测 70 个存档、100 个检查点）**：

```
last_conference/ 与 last_game/ 里各只有 5 个文件：
    cards.yml  hqs.yml  main.yml  store.yml  units.yml
（99/100 是这 5 个；1 个只有 hqs/main/store）
检查点里【不含】document/（0/100）    ← 所以改 document/ 的东西回退不掉
检查点里【不含】games/                ← 战斗状态不在检查点里
```

> **对照事实**：`games/<场景>/archive/<最后快照>/campaign_units.yml` 会被
> `Campaign._load_campaign_units()` 读回名册（§3.4.4.5）。
> 但读档时 `Game._load` 的序列化对象是 `games/<场景>/`（由 `revert_last_game_to_deployment`
> 的 `serialization.subdirectory(game_dir)` 与 `load_zip('archive')` 证实），
> 而 **`games/<场景>/campaign_units.yml` 在全部 70 个存档的所有场景目录里 0 次出现**
> → 读档路径上它不会被加载。
> **即便如此，也不要写它**（W3/W4：L3/L4 只读，它是历史）。

**旧建议（已作废，留档对比）**：
"同步 `last_*/units.yml`（按 id 匹配）、`last_*/main.yml`（只覆盖 prestige/score/milestones）、
`last_*/cards.yml`、`last_*/store.yml`、`archive/<最后快照>/{units.yml, campaign_units.yml}`"。
**作废理由见 §7.4 的 R1–R6 六条风险。**

##### 3.4.5.4 未覆盖状态的自动正确性

用能力矩阵回头检查 §3.4.2b 里那几个"样本里没有"的状态：

| 状态 | has_root_units | has_card_store | cp_conference | cp_game | 行为是否正确 |
|---|---|---|---|---|---|
| **C1 中途会议界面** | ✓ | ✓ | ✓ | ✗ | 改单位→根表 ✓；`last_conference` 不动 ✓；不动不存在的 `last_game` ✓ |
| **L 刚输掉一场** | ✓ | ✗ | ? | ? | 改单位→根表 ✓；检查点一律不动 ✓ |
| **R 回滚后** | 与目标状态一致 | 同 | 同 | 同 | 自动继承目标状态的行为 ✓ |
| **C0 战役开局** | ✗ | ✓ | ✗ | ✗ | 单位功能禁用 ✓；其余照常 ✓ |
| **B1/B2 战斗中** | ✓ | ✗ | ✓ | ✓ | 改单位→根表（即战斗内单位）✓；两个检查点都不动 ✓ |

> **一句话**：只要实现遵守能力矩阵，**新增状态不需要改任何代码**。

#### 3.4.6 状态判定仅用于 UI 展示

如果要在界面上显示"当前处于什么阶段"，用下面的判定（**只用于显示，不得用于决定改哪张表**）：

```
if standalone_scenario 非空                     -> "独立场景"
elif in_state.scenario 非空:
    archive 有 turn_NN_* ?  -> "战斗中（第 N 回合）" : "准备/部署阶段"
elif card_store 非空           -> "会议界面（已发牌）"
elif in_state.completed        -> "战役已完成"
elif in_state.lost_scenario    -> "刚结束一场（失败）"
elif in_state.segment_finished -> "本段场景已打完"
else                            -> "战役地图"
```

#### 3.4.7 旧版状态对照表（仅供理解，已被 §3.4.5 能力矩阵取代）

| 操作 | 战役开局 | 战斗中 | 部署阶段 | 场景打完 | 段打完 | 独立场景 |
|---|---|---|---|---|---|---|
| 改声望/分数 | 根 main.yml | 根 main.yml | 根 main.yml | 根 main.yml | 根 main.yml | 根 main.yml |
| 改单位数值/改名 | **无单位可改**（无根表） | 根 units.yml | 根 units.yml | 根 units.yml | 根 units.yml | 根 units.yml |
| 改总部 | 根 hqs.yml | 根 hqs.yml | 根 hqs.yml | 根 hqs.yml | 根 hqs.yml | 根 hqs.yml |
| 加卡牌 | 根 cards.yml + main.yml.card_store | 同左 | 同左 | 同左 | 同左 | 同左 |
| 改商店 | 根 store.yml | 同左 | 同左 | 同左 | 同左 | 同左 |
| 回滚基线（**只读，勿写**） | 无 last_* | last_game 存在且=当前战斗 | 同左 | last_conference 存在 | 两者都可能存在 | 无 |

**战役开局特别说明**：根 `units.yml` 不存在、没有 `games/`、没有 `last_*`。
此时修改器：
- 改声望/分数/卡牌/商店 → 正常
- 改单位 → **必须禁用**（并提示"该存档处于战役开局，尚未生成单位"）
- （修改器不提供"新增单位"，所以这里没有别的可做）

> 顺带一提：战役名册是在**第一场战斗开始时**由游戏从 `document/` 重建的。
> 这也是我们**不做"新增单位"**的原因之一 —— 手写的根 `units.yml` 在开局阶段会被重建覆盖。

---

---

### 3.5 战斗初始化重组机制 ⚠️⚠️ **决定"改单位"到底改不生效**

> 本节回答一个最容易踩坑的问题：
> **"我在战役地图上改了一个单位，进战斗后游戏把它改回去了 —— 为什么？"**
>
> 答案：游戏在**新开一场战斗**（`Game.new`）时会执行一次**初始化重组**，
> 把部分字段按**场景预设**重算一遍。战斗外改的部分字段因此会"失效"。
>
> **本节全部结论有字节码 + 实测双重支撑**，与 §3.4（存档布局）是两件不同的事：
> §3.4 讲"数据存在哪"，本节讲"**游戏什么时候会把它改回去**"。

#### 3.5.1 时序：重组只发生在"新开一场战斗"这一刻

```
战役地图 / 会议（战斗外）
      │
      │  玩家点「开始这场战斗」
      ▼
Campaign.play_game()                    campaign.pyc:1235   ← Game.new 的唯一调用者
      │
      ├─ save_revert_campaign_data(..., 'last_game')     ← 存"重打上一场"检查点
      ▼
Game.new(...)                           game.pyc:185
      │
      ├─ line 223  _adjust_hqs_between_situations()      ← 总部也有一套同样的重组
      └─ line 224  adjust_units_between_situations()     ← ★ 单位的重组在这里
                        │
                        ▼
              （在内存里改写 campaign.units 里的单位对象）
                        │
                        ▼
      战斗进行 → 存档 → Campaign._save_campaign_files() → 根 units.yml（重组后的值）
```

**其它所有路径都不会重算**（`Game._load` 里没有 `adjust_units_between_situations`）：

| 玩家操作 | 代码路径 | 是否重算重组 |
|---|---|---|
| **新开一场战斗**（战役地图上点开始） | `Campaign.play_game` → `Game.new` | ✅ **会重算** |
| 读档继续已有战斗 | `Game._load` | ❌ 不重算 |
| 「重打上一场」`revert_last_game` | `_load_revert_campaign_data('last_game')`（campaign.pyc:1493） | ❌ 不重算（但玩家再点开始战斗就会重算） |
| 「回到部署阶段」`revert_last_game_to_deployment` | `Game._load` + `apply_action_record`（campaign.pyc:1522） | ❌ 不重算 |
| 「重置会议」`revert_last_conference` | `_load_revert_campaign_data('last_conference')`（campaign.pyc:1558） | ❌ 不重算 |
| 独立场景（standalone） | `adjust_units_between_situations` 第 150-152 行**直接 return** | ❌ 不重算 |

> **⭐ 这是整节最重要的一句话：**
> **"战斗中存档后修改"是安全的**（读档走 `_load`，不重算）；
> **"战斗外修改"是不安全的**（下次开打时会被重算覆盖）。
>
> 修改器的主战场应该是**战斗中的存档**；战斗外修改必须做风险提示（§3.5.7）。

##### 3.5.1b 两个容易搞混的时点 ⚠️

**误解①："空降登陆的执行环节在选择场景/战役的一瞬间就完成了"**

**不对。** 执行点是 **`Game.new`**，也就是玩家在战役地图上点「**开始这场战斗**」的那一刻：

```
Campaign.play_game()  →  Game.new()  →  adjust_units_between_situations()
                                            ├─ A 类：campaign_agree_on_unit  → 场景覆盖
                                            ├─ B/C 类：_take_force_for_lci   → 登陆/空降对账
                                            └─ 全体：supply=3 / sup_st 清零 / specs.active 重置
```

⚠️ **登陆空降只是重组的一部分**。**A 类的场景覆盖、`supply`/`supplied_by` 强制 3/0、
`sup_st` 清零加回 `act_st`、`specs[].active` 全部重新激活，都在同一个时刻发生**（§3.5.8 矩阵）。
⇒ "战斗外改单位" 的风险**远不止**空降登陆那一条。

**误解②："战役已经开始 ⇒ 编辑安全"**

要分清两个"开始"：

| | 判定 | 重组会不会重算 |
|---|---|---|
| **战役已经开始**（战役地图上，已打过若干场，当前停在会议/准备阶段） | `in_state.scenario` 为空 | 🚫 **会**（下次开打时重算） |
| **这场战斗已经开始**（战斗内，含**部署阶段 = 回合零**） | `in_state.scenario` 非空 / 有 `games/<场景>/` | ✅ **不会**（`Game.new` 已跑过） |

⇒ **安全边界是「这场战斗已经开始」，不是「战役已经开始」。**
⇒ 部署阶段（B2）**是安全的**：`Game.new` 已经执行过，之后读档走 `Game._load`（不重算），
「退回部署阶段」`revert_last_game_to_deployment` 也走 `_load`（不重算）。
⚠️ 但「重打上一场」`revert_last_game` 会用检查点**整表替换**根表 ⇒ **战斗外改的东西会被抹掉**（§7.3、§10 第 10 条）。

#### 3.5.2 三类参战单位，走三条不同的路

`adjust_units_between_situations`（`game_adjust_data.pyc:145`）把参战单位分成三类。
**判据是"这个 id 出现在哪个场景文件里"**：

| 类别 | id 出现在哪 | 走哪段代码 | 受不受登陆规则影响 |
|---|---|---|---|
| **A. 场景初始单位** | `document/scenarios/<场景>/units.yml` | 第 167-185 行 → `campaign_agree_on_unit` | ❌ 不走 lci，但**部分字段被场景覆盖** |
| **B. 登陆/空降承载单位** | `document/scenarios/<场景>/prepositioned_assets.yml` 里 `type != 'bb'` 的资产 | 第 189-223 行 → `_take_force_for_lci` | ✅ **走 lci 对账** |
| **C. 增援单位** | `document/scenarios/<场景>/enroute_units.yml` | 第 226-249 行 | ⚠️ **只有 `on_turn ≤ 4` 且场景有 lci/para 才走 lci** |

> **实测确认三类的 id 互不相交**（Husky / MonteCassino / Stalingrad 三个存档全部验证）：
> `资产承载 id ∩ 场景初始 id = []`，`增援 id ∩ 场景初始 id = []`。
> **这很重要**：B/C 类单位**不经过** `campaign_agree_on_unit`，
> 所以它们的 `type` / `uv` / `entr` **不会被场景覆盖**；A 类才会。

#### 3.5.3 A 类（场景初始单位）：哪些字段被场景覆盖

`campaign_agree_on_unit(campaign, unit, gamelike, set_in_campaign)`（`game_adjust_data.pyc:14`）：

```python
u = campaign.units.get(unit.id)              # 17
if u and not set_in_campaign:                # 18  ← 玩家单位走这里
    u.uv              = unit.uv              # 20  ← 场景位置覆盖
    u.type            = unit.type            # 21  ← 场景类型覆盖
    u._type           = unit._type           # 22
    u.hq_id           = unit.hq_id           # 23  ← 场景所属总部覆盖
    u.entr            = unit.entr            # 24
    u.losses          = unit.losses          # 25
    u.retreated       = unit.retreated       # 26
    u.hidden_defense  = unit.hidden_defense  # 27
    unit = u                                # 28  ← 之后继续用【旧对象】
else:                                        # 30  AI 单位：整个换成场景对象
    campaign.units[unit.id] = unit
unit.supply      = 3                         # 32  ← 强制满补给
unit.supplied_by = 0                         # 33
```

**场景单位的 `type` 从哪来？** —— `UnitState.__init__`（`unit.pyc:63`）第 73-86 行：

```python
if type:                       # 73  实例里带了 type（战役名册单位）
    self.type = type
    self.name_brief = name_brief
    self.name_full = name_full
else:                          # 79  场景文件里没有 type（场景预设单位）
    c_unit, _ = gamelike.campaign_doc.get_doc_unit(id, segment_obj=...)   # 79-82
    self.type       = c_unit.type        # 84
    self.name_brief = c_unit.name_brief  # 85
    self.name_full  = c_unit.name_full   # 86
```

**实测印证**：`units_schema(gamelike, from_scenario_data=True)` = `Schema([scenario_unit_schema])`，
而 `scenario_unit_schema` **只有 10 个字段**（`id, name_brief, uv, act_st, sup_st, xp, entr, supply, specs, hq_id`），
**没有 `type`**。所以场景预设单位的类型**只能**来自战役文档名册 `document/units.yml`（按 id）。

> **⚠️ 由此得到一条对修改器很重要的推论：**
> **"改单位 `type`"是一个做不成的功能** —— 只改根 `units.yml` 没用，
> 对 A 类单位（出现在场景 `units.yml` 里），进战斗时 `type` 会被重置为
> `document/units.yml[id].type`；而要改 `document/units.yml` 就得写 L5，
> 而 L5 **游戏内回退不掉**。
> ⇒ **修改器不提供"改编制"功能**（§7.5），只把 `type` 当作**只读信息**展示
> （玩家想看这个单位是什么编制，改 `act_st` 和 `specs` 即可）。

**A 类单位还有两个无条件副作用**（对**玩家阵营**的存活单位，第 178-179 行）：

```python
unit.apply_recovery_steps()     # 178  ← sup_st 全部转回 act_st
unit.apply_recovery_specs()     # 179  ← specs 全部重新激活
```

`apply_recovery_steps`（`unit.pyc:572`）：`steps = self.sup_st; if steps: self.sup_st -= steps; self.act_st += steps`
`apply_recovery_specs`（`unit.pyc:581`）：把至多 `len(specs)` 个未激活的特种兵置为 `active=True`

> 所以**战斗外把 `sup_st` 调高、或把某个特种兵设为 inactive，进战斗后都会被清掉**。

#### 3.5.4 B/C 类（登陆 / 空降 / 早期增援）：`_take_force_for_lci` 的完整规则

**触发条件**（`game_adjust_data.pyc:188-201` + `243`）：

```python
has_ppas = False                                     # 188
for ppa in self.pp_assets.values():                  # 189
    if ppa.type == 'bb':      continue               # 190  炮舰（bb）不算
    if not ppa.unit['id']:   continue                # 193
    has_ppas = True                                  # 201  ← 只要有一个 lci/para 就置位
...
# 早期增援（第 243 行）
if has_ppas and en_unit.on_turn <= 4:                # 243  ★ 第 4 回合含，第 5 回合不含
    _take_force_for_lci(...)
```

**B 类（资产承载单位，第 202-223 行）：**

```python
unit = campaign.units.get(ppa.unit['id'])            # 202
if not unit: continue                                # 203  名册里没有 → 跳过
if unit.faction != player_faction:                   # 204
    campaign.units.pop(unit.id); continue            # 205  敌方单位不受影响
unit.hq_id = ppa.unit['hq_id']                       # 208  ← 所属总部被覆盖
num_steps = ppa.unit['act_st'] + ppa.unit['sup_st']  # 212  ← 目标战力
specs     = ppa.unit['specs']                        # 213  ← 目标特种兵清单
if ppa.type == 'para_plane' and unit.specs:          # 216  ★ 空降专用
    unit.specs = {}                                  # 217  旧特种兵全清
    specs     = []                                   # 218  目标清单也清空
_take_force_for_lci(self, brief, unit, num_steps, specs, alive_units)   # 220
if ppa.type == 'para_plane':                         # 222
    unit.xp = max(100, unit.xp)                      # 223
```

**C 类（增援单位，第 232-249 行）：**

```python
unit = campaign.units.get(en_unit.unit['id'])        # 232
if not unit: continue                                # 233
if unit.faction != player_faction:                   # 234
    campaign.units.pop(unit.id); continue
unit.hq_id = en_unit.unit['hq_id']                   # 238  ← 所有增援的 hq_id 都被覆盖
num_steps = en_unit.unit['act_st'] + en_unit.unit['sup_st']   # 240
specs     = en_unit.unit['specs']                    # 241
if has_ppas and en_unit.on_turn <= 4:                # 243
    _take_force_for_lci(...); continue               # 244
if unit.kia: _take_force_for_kia(...)                # 246
else: unit.apply_recovery_steps(); unit.apply_recovery_specs()   # 248-249
```

**`_take_force_for_lci`（`game_adjust_data.pyc:101`）本身：**

```python
strengthen = False
if unit.kia:                                          # 104  阵亡分支
    unit.act_st = num_steps                           # 106  战力 = 场景目标
    unit.sup_st = 0                                   # 107
    unit.specs = {}                                   # 108  特种兵全清
    unit.xp   = 100                                   # 109  ★ XP 绝对重置为 100
    take_steps_for_recovery(self, brief, unit, num_steps)   # 110
    strengthen = True
else:                                                 # 存活分支
    num_steps = max(0, num_steps - unit.tot_st)       # 113  ★ 缺口 = 目标 - 当前总战力
    if num_steps > 0:                                 # 114
        unit.act_st += num_steps                      # 115  补兵
        unit.deploy_calc_xp(num_steps)                # 116  ★ XP 会被重算（见 §3.5.6）
        take_steps_for_recovery(self, brief, unit, num_steps)   # 117
        strengthen = True
    unit.apply_recovery_steps()                       # 120  压制恢复

hq = self.get_hq(unit.hq_id)                         # 123
# —— 特种兵对账 ——
for s in list(unit.specs.values()):                  # 125  遍历单位现有特种兵
    for i, spec in reversed(list(enumerate(specs))):  # 126  倒序找同 type 的目标需求
        if s.type == spec['type']:                    # 127
            specs.pop(i)                              # 128  消耗一份目标需求
            s.active = True                           # 129  保留并激活
            break
    else:                                             # ★ 没匹配上
        hq.force_pool.add(s.nationality, s.type, delay=0)   # 133  退回总部兵库
        unit.remove_specialist(s.idx)                 # 134  从单位上移除
# —— 补齐场景目标 ——
for spec in specs:                                   # 136
    unit.add_specialist(spec['type'], active=True)   # 138
    take_spec_for_recovery(self, brief, unit, spec['type'], alive_units)   # 139
```

#### 3.5.5 特种兵对账规则（最关键的一条）

**场景目标清单是"按 type 的多重集"，不是集合去重。**

| 情况 | 结果 |
|---|---|
| 单位有的 spec，**目标清单里同 type 也有** | **保留**并激活（消耗一份目标需求） |
| 单位有的 spec，**目标清单里没有**（或该 type 的份数已用完） | ❌ **从单位上移除，退回当前总部兵库（delay=0）** |
| 目标清单里还有剩余需求 | **自动添加并激活**，来源：总部兵库 → 其它存活单位 → 凭空（"from the thin air!"） |
| 单位 `specs` 是空的 | 全部目标需求都会被补上 |
| 资产是 `para_plane`（空降） | **旧 specs 全清 + 目标清单清空** → 该单位**一个特种兵都不会有** |

> **含义：战斗外给登陆/空降单位加的特种兵，进入战斗时会被"对账"掉。**
> 目标清单里没有的 type 会被剥离并塞进总部兵库 —— **特种兵没消失，但换了位置**。

`take_spec_for_recovery`（`game_adjust_data.pyc:62`）的补给来源顺序：

1. **当前总部的兵库**：`hq.force_pool.deploy_with_delay(None, cumulative=True)`（累计扣取，不是只取 delay=0）
2. **其它存活单位**：`alive_units` 里同 type 的候选，排序键 **`(u.tot_specs, u.tot_st)`**（第 79 行 lambda，已确认；
   旧 PDF 写的 `key=lambda u: u.xp` 是**过时资料**，以字节码为准）
3. **都没有** → 日志 `"from the thin air!"`（凭空给）

> `alive_units` = **开局地图上存活的玩家单位**（第 180 行收集），
> 所以**普通初始单位也可能是登陆单位的特种兵供给方**。

#### 3.5.6 ⚠️ XP 的隐藏规则：补兵反而会**降** XP

`deploy_calc_xp(steps)`（`unit.pyc:606`）→ `deploy_calc_new_xp(steps, elite=False)`（`unit.pyc:596`）：

```python
if self.exp >= 1:                       # 600  该类型是"经验兵"（老兵）
    cost = consts.unit_exp_step_loss_elite if elite else consts.unit_exp_step_loss_standard
    return max(100, self.xp - steps * cost)     # 603  ★ 补 N 步兵 → XP 扣 N*cost
else:
    return self.xp                       # 604
```

> **这是"战斗外改 XP"最隐蔽的坑**：
> 登陆/空降单位在初始化时被补兵 → **XP 会被重算成 `max(100, 原XP - 补兵数 × cost)`**。
> 你把 XP 调到 400，进战斗后可能变成 `400 - 缺口×cost`。
> 而且 `exp < 1` 的普通兵种根本不会扣。
> `unit_exp_step_loss_standard` / `_elite` 的具体数值在游戏常量表里（本次未取到确切数字）。

**XP 的三种硬重置**：

| 情形 | XP 结果 | 代码位置 |
|---|---|---|
| 登陆/空降单位**阵亡** | `xp = 100`（绝对值） | `game_adjust_data.pyc:109` |
| 空降单位（para_plane） | `xp = max(100, xp)` | `game_adjust_data.pyc:223` |
| 场景初始单位**阵亡**（走 `_take_force_for_kia`） | `xp = min(100, xp)`、`act_st = 3`、`specs = {}` | `game_adjust_data.pyc:93-98` |

#### 3.5.7 实测验证（铁证 + 对照组）

**被登陆/空降规则命中的单位，战力被精确补齐到场景目标。**
（`west-Husky.usg`，当前战斗 `husky`；目标 = 资产里的 `act_st + sup_st`）

| 资产 | 类型 | unit | 场景目标战力 | 根表 `act_st+sup_st` | 场景目标 specs | 根表 specs |
|---|---|---|---|---|---|---|
| 2 | lci | 147 | 6 | **6** | `[us_armx_42, us_towed_arty_42]` | `[us_armx_42, us_towed_arty_42, us_towed_arty_42]` |
| 3 | para_plane | 146 | 5 | **5** | `[]` | `[]` |
| 4 | lci | 1 | 6 | **6** | `[us_towed_arty_42, us_at_42, us_spec_42]` | ✅ 一致 |
| 5 | lci | 46 | 6 | **6** | `[us_spec_42, us_spec_42, us_eng_42]` | ✅ 一致 |
| 7 | lci | 95 | 6 | **6** | `[uk_recon_42, uk_towed_arty_42]` | `[…, uk_towed_arty_42]`（多一个） |
| 8 | para_plane | 167 | 6 | **6** | `[]` | `[]` |
| 9 | lci | 94 | 6 | **6** | `[uk_recon_42, uk_eng_42]` | `[…, uk_towed_arty_42]`（多一个） |
| 10 | lci | 173 | 6 | **6** | `[uk_spec_42, uk_towed_arty_42]` | ✅ 一致 |
| 11 | lci | 159 | 4 | **4** | `[uk_eng_42, uk_spec_42, uk_spec_42_opt]` | ✅ 一致 |
| 12 | lci | 168 | 6 | **6** | `[uk_spec_42_opt, uk_towed_arty_42]` | `[…, uk_eng_42]`（多一个） |

**10/10 命中，战力全部精确等于场景目标。**

**对照组（同一存档里**不**走 lci 的场景初始单位）：**

```
非资产单位中『场景战力 == 根表战力』的: 1 / 25
```

> **对照组 1/25 vs 命中组 10/10** —— 这就是"只有登陆/空降单位被补齐"的直接实证。
> （对照组那一例是巧合：未部署单位根表 `uv` 为 `None`。）

**"多出来的那一个 spec"是怎么来的？**
初始化时它会被**剥离**（退回总部兵库），但玩家在战斗里又通过商店/卡牌买了回来。
例如 MonteCassino 的 unit 112：场景目标是 `[uk_recon_42, uk_spec_42, uk_towed_arty_42]`，
根表当前是 `[uk_spec_42, uk_heavy_43, uk_arty_42]` —— **明显的后期改动痕迹**。
这恰好说明：**初始化对账确实发生过，之后玩家又改了。**

**变体（variant）也要注意**：场景可能有 `document/scenarios/<场景>/variants/<变体>/` 覆盖
`units.yml` / `enroute_units.yml` / `prepositioned_assets.yml`。
实测 MonteCassino 当前变体是 `frosinone_and_pescara`，但该变体目录**没有** `prepositioned_assets.yml`，
所以资产仍取基础文件。**修改器解析场景预设必须"变体优先、基础兜底"。**

#### 3.5.8 修改器对策：字段级存活性矩阵 ⭐

**这张表是本节的核心产出。** 列 = 修改器改动生效的场景；行 = 字段。

| 改的字段 | 战斗中改（存档后修改） | 战斗外改 · A 类单位<br>（在场景 `units.yml` 里） | 战斗外改 · B/C 类单位<br>（登陆承载 / 增援） |
|---|---|---|---|
| `xp` | ✅ 生效 | ✅ 生效 | ⚠️ **会被重算**：`max(100, xp-缺口×cost)`；阵亡→`100`；空降→`max(100,xp)` |
| `name_brief` / `name_full` | ✅ 生效 | ✅ 生效 | ✅ 生效 |
| `type`（🔒 **只读，不提供编辑**） | —（不可改） | ❌ **会被场景覆盖**（= `document/units.yml[id].type`） | —（不可改） |
| `uv` | 🚫 **不可改**（U94 已删除该字段） | — | — |
| `hq_id` | 🚫 **不可改**（从未实现） | — | — |
| `entr` / `losses` / `retreated` / `hidden_defense` | ✅ 生效 | ❌ **被场景覆盖** | ✅ 保留 |
| `supply` / `supplied_by` | ✅ 生效 | ❌ 强制 `3` / `0` | ❌ 强制 `3` / `0` |
| `sup_st` | ✅ 生效 | ❌ **清零并加回 `act_st`** | ❌ 同左 |
| `specs[].active` | ✅ 生效 | ❌ **全部重新激活** | ❌ 同左 |
| `specs` 列表内容 | ✅ 生效 | ✅ 保留 | ⚠️ **按 type 对账**：多的剥离退回总部，少的自动补上；空降全清 |
| `act_st` | ✅ 生效 | ✅ 保留 | ⚠️ **被补到场景目标（只增不减，超出的不削）** |

**直接回答"那应该怎么改"：**

| 用户想要 | 正确做法 |
|---|---|
| 改 XP / 改名 | 战斗内外都安全 ✅ |
| 改编制（`type`） | ❌ **修改器不提供这个功能**（§7.5）—— 要生效就得改 L5，而 L5 回退不掉 |
| 改位置（`uv`） | 🚫 **不提供** —— `uv` 已从可改字段里删掉（U94） |
| 改特种兵 | 普通单位：战斗外可改（但 `active` 会被重置）。<br>**登陆/空降/早期增援单位：战斗外改无效** —— 只能在**战斗中**改（§3.5.1） |
| 改战力（`act_st`） | 战斗外改对普通单位有效；对登陆单位，**低于场景目标的值会被抬上去** —— 想固定就调到 ≥ 场景目标 |
| 想让登陆单位带着自定义特种兵进场 | ❌ **修改器不提供这个功能**（§7.5）—— 唯一根治办法是改 L5 场景预设的回退不掉。<br>**替代方案：在"战斗中"的存档里改**（战斗中改不会被对账） |

#### 3.5.9 修改器应当实现的功能（按优先级）

> 注意：下列功能**全部只写 L1**（§7.2 W1）。重组机制的存在**不改变**这一点 ——
> 它只影响"哪些改动有效、哪些需要预警"，不改变"改到哪一层"。

1. **【高】重组预警**：打开一个"战斗外"的存档时，读取
   `document/scenarios/<下一场场景>/{units.yml, prepositioned_assets.yml, enroute_units.yml}`（变体优先），
   算出：
   - 哪些单位会被 **lci 对账**（B 类：资产里 `type != 'bb'` 的 `unit.id`；C 类：`on_turn ≤ 4` 的增援，且场景存在 lci/para）
   - 哪些单位会被 **字段覆盖**（A 类：在场景 `units.yml` 里）
   然后在 UI 上对每个单位标注 `⚠️ 进战斗时会被重置` / `⚠️ 特种兵会被对账`，并列出**具体会被重置的字段**。
2. **【高】"在战斗中改"的推荐位**：UI 顶部提示
   「当前是战斗中的存档，此处修改**不会被游戏初始化覆盖**，推荐在此修改。」
   （依据：`Game._load` 不重算。）
3. **【中】对账差异预览**：对每个 B/C 类单位，显示
   `当前 specs` vs `场景目标 specs` 的 diff，并标出"会被剥离退回总部"的那些。

> **❌ 明确不做**（完整清单见 §0 的「不做四个高级功能」）：场景预设编辑器、「改 `type` 联动」、新增单位。
> 这三个都要写 L5/L3，**改动游戏内回退不掉**，而且用户摸不着头脑。

#### 3.5.10 本节未能验证的部分（如实标注）

- `unit_exp_step_loss_standard` / `unit_exp_step_loss_elite` 的**确切数值**未取到
  （它们在游戏常量表里，本次没定位到赋值处）。所以"补兵降多少 XP"只能给出公式形式。
- `tot_st` 的**定义**未定位到代码对象（疑似父类/描述符实现），
  按语义推断为 `act_st + sup_st`（与实测数据一致，但未直接读到定义）。
- `unit_replacements`（ID 替换映射）的**来源与规则**未研究
  （`Campaign.get_unit_replacements()`）。它会影响"哪个 id 对应哪个单位"，本次不展开。
- `_adjust_hqs_between_situations`（总部侧的同类重组，`game.pyc:223`）**未研究**，
  本节只覆盖单位侧。
- `campaign_agree_on_unit` 里 `uv` 覆盖的**实测**证据不足
  （实测的对照组单位多为"未部署"状态，根表 `uv` 为 `None`，无法直接对比），
  该结论**仅来自字节码第 20 行**。
- "初始化后玩家又加回来的那一个 spec"是**推断**（剥离 → 商店/卡牌买回），
  未逐帧回放验证。

---

## 4. 精确字段定义

### 4.1 单位实例（19 个字段）

> ⚠️ **容器有两种格式**（详见 §3.4.3、§3.4.4）：
> `games/<场景>/units.yml` 可能是 **ID 清单**（`list[int]`）也可能是 **完整对象**（`list[dict]`）；
> 根 `units.yml` / `hqs.yml` 永远是完整对象。
> 下面是**单位对象本身**的字段定义。

根 `units.yml`、`games/<场景>/units.yml`、`archive/<快照>/units.yml` **字段集完全一致**：

```yaml
- id: 1
  type: us_inf_42
  name_brief: id_unit_name_brief_3_dot__US_ID       # str | null，可写明文
  name_full: id_unit_name_full_3rd_US_Infantry_Division__singlequote_Marne_singlequote_
  hq_id: 16            # null | int ≥ 0
  xp: 316              # int 0..399  ← 硬上限（游戏的**逻辑**上限）
  act_st: 6            # 活跃战力(int ≥ 0)，上限见 §5.2
  sup_st: 0            # 被压制战力(int ≥ 0)
  ap: 0                # 行动点 0..3
  mp: 0                # 移动力 ≥ 0
  entr: 0              # 堑壕等级 0..2
  supply: 3            # 补给 0..3
  losses: 0
  retreated: 0
  supplied_by: 0       # ∈ {0,1,2,3}
  ap_start_turn: false
  hidden_defense: true
  uv: [195, 247]       # [列,行] 两个非负 int，或 null
  specs:               # 特种兵列表，长度 0..3
    - {type: uk_engineer_42, active: true, captured: false, idx: 0}
```

`document/units.yml` 是**另一种结构**（只有 4 个字段，是名册不是实例）：
```yaml
- {id: 906, name_brief: 1第德国警卫队, name_full: 1德国警卫分遣队, type: ger_inf_39}
```
> ⚠️ 这个文件是 **`type` 的唯一权威来源**（§3.4.4.6、§3.5.3）。
> `document/scenarios/<场景>/units.yml` 里**没有 `type`**（实测 `scenario_unit_schema` 只有 10 个字段：
> `id, name_brief, uv, act_st, sup_st, xp, entr, supply, specs, hq_id`），
> 游戏是按 id 去这里解析的（`UnitState.__init__` 第 79-86 行 → `campaign_doc.get_doc_unit(id)`）。
>
> ⚠️ **对**出现在场景 `units.yml` 里**的单位**，战斗开始时 `type` 会被场景预设
> **覆盖**回 `document/units.yml[id].type`（§3.5.3）。
>
> ⇒ **修改器不提供"改编制 `type`"功能**（§7.5）：要让它真正生效就得写 `document/units.yml`，
> 而 L5 **游戏内回退不掉**（`document/` 不在任何检查点里，实测 100 个检查点 0 个含 `document/`）。
>
> > **本节的 `document/units.yml` 只用于"读取"**：了解一个单位的编制是什么、
> > 判定 §3.5 的重组风险。**绝不写入**（§7.2 W5）。

### 4.2 总部表（26 个字段）

根 `hqs.yml` 与 `games/<场景>/hqs.yml` 结构相同：
`branch_levels, branches, cp, fixed_movement, fixed_range, force_pool, general, id, intels_revealed, loss_count, max_cp, motor_pool_flag, moved, name_brief, name_full, name_super_brief, overrun, persistent, prisoners, supply, template, trucks, turn_disbanded, uv, xp, xp_target`

- `branch_levels`: `{force_pool, intel, operations, logistics, engineering}`，每项 `{level, suppressed}`
- `branch_levels` 之和 **> 3 会报错**（游戏校验）
- `max_cp`: `hq_min_max_cp=3` ~ `hq_max_cp=9`；上限取自 `template`（如 `uk_hq_mid_hard` 的 `max_cp: 5`）
- `force_pool`: `[{delay, nationality, quantity, spec? | equipment?}]`
  —— ✅ **可改（L1）**。这就是玩家口中的"存货 / 兵库"：**每个 HQ 各自一份**，
  记着该 HQ 手头存了多少兵力/装备，可以往单位上部署（§6.2b）。
  **游戏在任何重组路径上都不重算它**（§12 的 `e112` / `e113` 字节码证据）。
- `general`: 将军 id 或 null

`document/hqs.yml` 是名册：`{id, name_brief, name_full, name_super_brief, nationality, number_of_xs}`

**总部里哪些字段能改**（`handlers.py::HQ_FIELD_ALLOWED`）：

| 能改 | 说明 |
|---|---|
| `cp` / `max_cp` | 0–9 / 3–9 —— 游戏的**硬范围**，超范围**存档直接打不开** |
| `supply` | 0–3（硬范围） |
| `trucks` | 1–5（硬范围）；另有专用编辑 `hq_trucks` |
| `prisoners` / `loss_count` / `intels_revealed` | 游戏自己累计的统计值，改了不会被重算 |
| `name_brief` / `name_full` | 直接写明文（与单位改名同一套口径） |
| `xp` / `xp_target` | 🚫 **不可改**（U94 硬拦）—— 经验目标是游戏按战役规模**每次推进都重算**的，手改会被覆盖；想升级请直接改**分支等级 / 技能专精**（`handlers.py::HQ_XP_FIELDS`） |

另有专用的总部编辑：`hq_trucks`（补给卡车）、`hq_branch_level`（分支等级）、
`hq_branch_suppressed`（被压制的等级数）、`hq_branch_sp`（技能专精次数）、
以及兵库三件套 `hq_force_pool` / `hq_force_pool_add` / `hq_force_pool_remove`（§6.2b）。

### 4.3 战役根 `main.yml`（17 个字段）

```yaml
campaign_id: west
campaign_name: id_campaign_name_c_west_p_base
level: hard | classic | normal | easy
prestige: 320                # ← 当前声望（可改）
score: 2980                  # ← 当前分数（可改）
milestones: [masters_of_the_north_african_shores, fascist_regime]   # ← 🔒 **只读、原样保留**（不做里程碑功能，§6.1b）
num_buyed_turns: 0
card_store: null             # null | [卡牌列表]  当前会议发到手里的牌
conference_start_state: null # {} | dict
destroyed_cities: [[203,252], ...]
renamed_hqs: {5: 14, 14: 16}
reverted_games: []
standalone_scenario: null
tokens: [[avalanche, coast], ...]
tokens_map: [[avalanche, ortona, A, id_objective_name_brief_Ortona], ...]
used_card_types_with_unit: {tactical_naval_assault_us: [570]}
in_state:
  completed: false
  conference: c_43_09       # 当前会议
  front: null               # 当前战斗所属战线（france/italy）；**非战斗时为 null**，与 scenario 恒等（§10 第 18 条）
  scenario: null            # 当前战斗场景名
  variant: null             # 当前战斗变体
  segment_finished: true
  lost_scenario: null
  fronts:
    france: {approved_plan, played_segments, segment, situation_idx, supply_value, tmp_approved_plan}
    italy:  {同上}
```

> ⚠️ **`milestones` 是只读字段 —— 修改器一个字都不改。**
> 它是游戏在战斗结算时自动写入的（`Campaign.game_finished`），**修改器重写根 `main.yml` 时必须原样搬运**：
> 丢掉这个键，游戏 schema 会当成空列表（`Required('milestones', default=list())`，**不报错**），
> 于是本局已达成的里程碑与战役奖章**静默消失**（直到玩家用游戏内的「重置会议」回退为止 ——
> 检查点 `last_conference/main.yml` 里也带 `milestones`，实测确认）。
> 详见 §6.1b。

### 4.4 战斗 `games/<场景>/main.yml`（独立场景是 `game/main.yml`）

> 🔒 **基本只读**（L3，§7.2 W3）。列出来是为了让实现者知道"战斗实时状态"长什么样、
> 以及能从里面读出 `turn` / `ar_ord` 等**展示用**信息。
>
> ⚠️ **两个例外**：**战区资产**（`theater_assets`）与**作战标记**
> （`no_retreat_units` / `rearguard_units` / `elastic_defense_units`）——
> 它们在**当前进行中战斗**里**可写**，且写的是**同一张文件**；理由与边界见 §6.2b、§6.2c、§7.2 W8。
> 其余所有字段（`ar_ord` / `turn` / `scores` / `start_data` / `end_data` / …）仍然**一律只读**。
>
> ⚠️ 独立场景存档的战斗层是**单数目录 `game/`**（`game/main.yml`）——
> 判定与写入都按 `container.py::battle_dir()` 的结果，不要写死 `games/`。
>
> ⚠️ 这是**实时**的战斗元数据，**比 `archive/<最后快照>/main.yml` 新**（§3.4.4.3 有实测对比）。
> 快照里的 `main.yml` 额外带 `turn_prestige` / `turn_score` / `used_card_types_with_unit` /
> `destroyed_cities` / `in_state_front` 五个键，实时层没有。

```
ar_ord, base_num_turns, brilliant_victory, camera_position, command_authority,
completed, decisive_victory, deployment, end_data, entrenched_units, env,
factions, flags, map_name, no_retreat_units, outcome_status, phase,
playable_area, rearguard_units, salt, score_multiplier, scores, start,
start_data, supply, supply_dump_units, theater_assets, tow_sup, turn,
turn_len, turn_seq, victory_level, weather_hint
```

- `turn`: 当前回合数；`turn_seq: [allies, axis]`；`phase`: 当前阶段
- `ar_ord`: 当前行动序号（实测实时 190 / 快照 178 —— 差值 = 本回合已执行的动作数）
- `theater_assets`: `[[{asset, to_use, to_use_not_used, uses_total, uses_turn}], []]` —— **战区资产**的可用次数
  —— 🔶 **仅在当前进行中的战斗里可写**（§6.2b、§7.2 W8）；历史战斗快照里的同名键**只读**。
  ⚠️ **它和"总部兵库"（`hqs.yml` 的 `force_pool`）是两个完全不同的东西，别混**（§6.2b 开头）。
- `scores`: `{casualties, destruction, enemy_kia, general, objectives, prisoners}`
- `start_data` / `end_data`: 战斗开始/结束时的 `{prestige, score, supply_value, units{...}}`
- `rearguard_units` / `supply_dump_units` / `no_retreat_units` / `entrenched_units`: **单位 ID 列表**（不是对象）
- 同目录的 `ar_list.yml` = 本回合已执行行动的列表（**实时层最新**；快照里也有同名文件，内容是累计到该回合边界的行动，
  但**进行中战斗的最后一个快照没有它** —— 见 §2.2 的更正说明）

### 4.5 卡牌 `cards.yml`

```yaml
- {card_type: air_attack_allies, is_free: true, position: 1, unit_id: null, used: false}
```
- `card_type` 必须是 `entity_types/cards/` 里存在的类型（共 39 种）
- `position` = 槽位号（1 起）
- `unit_id`: null 或 int（带单位的卡指向该单位）
  ⚠️ **U187**：**带单位的卡（空降 / 登陆）根本进不了手牌** ⇒ 手牌里的 `unit_id` 恒为 `null`
  （`unit_id` 只在「上架 / 换牌」写 `main.yml` 的 `card_store` 时才出现）
- `used`: 是否已使用

**两处不同，别混**：
- `cards.yml` = 战役**持久卡牌库存**（改这里＝给玩家加牌）
- `main.yml` 的 `card_store` = **当前会议发到手里的牌**（null 表示当前不在会议界面）
- `last_conference/main.yml` 的 `card_store` = 上次会议发过的牌

### 4.6 商店 `store.yml`

```yaml
france:
  elite_store: null
  store:
    - {equipment: infantry, nationality: uk, price: 5, quantity: 20}
    - {equipment: armor,    nationality: us,  price: 5, quantity: 10}
    - {nationality: uk, price: 25, quantity: 2, spec: uk_towed_arty_42}
```
- 顶层键 = **战线名**（`france` / `italy` / `south` / `caucasus` / …）
  ⚠️ 实测它**是游戏包 `fronts/` 目录名的子集**（= 当前已激活的战线），实测 5 个战役：
  `barbarossa` 包 `{north,south}` = 存档 `{north,south}`；`moscow` 包 `{north,south}` = 存档 `{north,south}`；
  `stalingrad` 包 `{caucasus,south}` = 存档 `{caucasus,south}`；`west` 包 `{france,italy}`，存档有 `{france,italy}` / `{italy}` 两种；
  `blitzkrieg` 包 `{balkans,eur,scandi}`，存档有全量 / `{eur,scandi}` / `{eur}` 三种。
  ⇒ **只能往存档已有的战线键下面加东西，不要凭空新建战线键**；
  **不是** `document/main.yml` 的 `fronts_sorting_order`（那只是排序用）。
- 条目**只有两种形态**（实测 5 个战役包、44 个会议文件，键组合只有这两种）：
  | 形态 | 键 |
  |---|---|
  | 通用装备 | `{equipment, nationality, price, quantity}`（`equipment` ∈ `infantry` / `armor`） |
  | 特种兵 | `{spec, nationality, price, quantity}` |
  （`elite_store` 恒为 `null`，实测 5/5 战役包的全部会议文件）
- `price` = **单价**。**`price: 0` 是「免费商品」** —— 游戏正常产生的状态，不是任何特殊标记
  （实测 70 个存档：`price: 0` 的条目 **43 条**，单条战线最多 7 条；`quantity: 0` 的条目 **0 条**）
- `quantity` = **库存数量**（这一条还剩多少可买）。字节码实证 `ForcePool.deploy_store`（`force_pool.pyc:711`）
  按 `quantity` 部署、按 `price` 计价（`add_nat_equipment(..., price=…)` / `add_specs(..., num_specs=…, price=…)`）
- ⚠️⚠️ **游戏里没有「已售罄」这个标记**：库存买完后，**该条目直接从 `store.yml` 里消失**。
  实测 70 个存档的 **1659 条**商店条目里，`quantity: 0` 的**一条都没有** —— 游戏从不产生这种状态。
- ⇒ **修改器禁止把 `quantity` 设成 0**：那会造出一个游戏自己从不产生的状态 ——
  条目仍会出现在商店列表里，但点下去什么也拿不到（典型的「改了却像没改」）。
  **要清掉某个商品，正确做法是把该条目从 `store.yml` 里删掉。**

#### 4.6.1 商店的"买空"机制（实测，含两种不同表现）

拿 `campaigns\Stalingrad.usg`（当前会议 `c_42_07`）和它自己的检查点 `last_conference/store.yml` 对比，
再和游戏包 `fronts/south/conferences/c_42_07.yml` 的默认清单三方比对：

```
包 c_42_07 south 默认 19 条
存档根 store.yml south   13 条
last_conference/store.yml south  19 条   ← 上次会议的检查点（未购买状态）
```

| 条目类型 | 购买后的表现 | 实测 |
|---|---|---|
| **通用装备**（`equipment`） | 条目**保留**，`quantity` **递减** | german infantry `20 → 19`、german armor `10 → 6`、slovak infantry `3 → 1` |
| **特种兵**（`spec`） | **整条条目消失** | 6 条 spec（`ger_towed_arty_42` / `ger_towed_at_dlc3` / `ger_eng_dlc4` / `ger_recon_41` / `ger_asg_dlc4` / `ger_asg_dlc4_opt`）全部从 `store.yml` 消失 |

⇒ **统一规则**：`quantity` = 该条目剩余可买数量；玩家购买后 `quantity` 递减；
**`quantity` 归零时条目被移除**（所以存档里看不到 `quantity: 0` 的条目 —— 这就是"游戏从不产生 quantity: 0"的真正原因）。

全存档普查（存档根 `store.yml` vs 游戏包当前会议默认清单，67 个战役存档）：

| 状态 | 条目数 |
|---|---|
| 与包默认完全相同 | 974 |
| 包里有、存档里**条目已移除**（买空/售罄） | 325 |
| `quantity` **少于**默认（已购买递减） | 173 |
| 价格与包默认不同 | 277 |
| 存档里有但包里没有 | 214 |

⚠️ **⚠️ 价格不总是等于包里的静态清单**：stalingrad 实测 `caucasus` 战线 **19/19 条价格与包 `c_42_07.yml` 完全一致**，
但 `south` 战线有 **3 条价格被上调**（`ger_towed_at_dlc3` 15→25、`ger_towed_at_dlc4_opt` 30→35、`ger_at_dlc4` 30→35），
且同一战线的不同会议文件价格互不相同（`south/c_42_06.yml` 17/19 匹配、`south/c_42_07.yml` 16/19 匹配）。
**上调的确切原因未定位**（难度加成 / 进度加成 / 其它结算，均未跑通调用链）—— ⚠️ **如实标注：未验证**。
⇒ **因此：修改器只能改存档里的实际值，绝不能拿游戏包的静态清单去"纠正"存档。**

**商店的默认清单在哪（给 GUI 做"重置商店"基线用）**

```
<game>/_packages/<dlc>/data/campaigns/<campaign_id>.usc/fronts/<战线>/conferences/<会议>.yml
```
顶层键：`{card_probability_scales, elite_store, store, tracks}`；`store` 就是上面的条目列表。
⚠️ **商店清单不在场景目录里**（`scenarios/<场景>/` 里没有 `store.yml`），
⚠️ 也在 `document/conferences/<会议>.yml` 里（那个文件只有 `card_probabilities` / `date` / `period`，**没有商店**）。
战役存档的 `document/fronts/<战线>/conferences/<会议>.yml` 是同一个文件（`document/` = 战役包副本，§3.3）。
⚠️ **独立场景存档拿不到它** —— 独立场景没有商店（§3.2）。

---

## 5. 硬约束（写坏了会怎样）

> 来源：游戏自带校验器 `lib/uoc2/state/**/data_validation/*.pyc`（voluptuous），可直接反汇编读取。

### 5.1 不允许新增未知键 ⚠️⚠️

voluptuous 的 `Schema` 默认 `extra=PREVENT_EXTRA`。实测：

```
给单位加一个 'foo_bar' 键 → MultipleInvalid: extra keys not allowed @ data['id']
```

**含义**：修改器**只能改已有字段的值**，绝不能往 YAML 里塞自定义字段。所有「元数据」（比如 UI 上显示的备注）必须存在修改器自己的数据库里，不能写进存档。

### 5.2 数值范围（单位）

| 字段 | 约束 |
|---|---|
| `xp` | **0..399**（超了游戏拒绝载入；400 是 schema 的校验上限，但会被游戏 `_repair_data` 修回 399） |
| `entr` | 0..2 |
| `supply` | 0..3 |
| `ap` | 0..3 |
| `supplied_by` | ∈ {0,1,2,3} |
| `uv` | 恰好 2 个非负 int，或 null（但**不可改**，U94） |
| `specs` | 长度 0..3 |
| `act_st` / `sup_st` / `mp` / `losses` / `retreated` | ≥ 0（schema 无上限，但**游戏逻辑有**） |
| `store[].quantity` | **≥ 1** —— `0` 是非法值（游戏无售罄标记，实测 1659 条条目里 0 条为 0）；下架请删条目（§4.6） |
| `store[].price` | ≥ 0（**`0` = 免费商品**，是正常值，实测 43 条） |

### 5.3 战力上限不在存档里，在类型定义里

存档里**有** `type`（实例字段），但**没有**战力/特种兵的上限 —— 上限来自 `entity_types/unit_types/<type>.yml`：

```yaml
us_inf_42:  {faction: allies, nationality: us, movement: infantry, attack: 2,
              defense: 3, armor: 0, max_st: 6, max_spec: None, ...}
ger_inf_39: {faction: axis, nationality: german, movement: infantry, attack: 3,
              defense: 2, armor: 1, max_st: 7, max_spec: 2, ...}
```

- `max_st` 分布（全 627 个类型）：`3:4, 4:9, 5:83, 6:108, 7:245, 无:178`
- `max_spec` 分布：`1:233, 2:314, 3:25, 无:55`
- **`max_spec` 为 None 的类型表示"该类型没有此字段"，按 schema 的 3 处理，但实际能挂几个要看 `type` 的定义**
- 战力上限 ≈ `max_st`；**普通部队（活跃 + 被压制）合计不得超过 `max_st`** ——
  U96 起**自动配平并改写输入值**（先从 `sup_st` 扣、不够再截 `act_st`），同时给出警告；
  **不是"软警告照写"**（`handlers.py::_unit_field`）。
  ⚠️ 特种兵**不占**这个名额（游戏读档时也只查这两项）
- 特种兵上限 = `min(3, max_spec or 3)`

> ⚠️ **不要相信朋友工具里的硬编码「轴心 7 / 盟军 6」**——那只是粗糙近似。以 `max_st` 为准。

### 5.4 `type` 是**只读信息** —— 修改器不改编制

校验器不是裸函数——它接收一个携带类型数据库的上下文对象：

```
campaign_data_validation : unit_types ×4, card_types ×3, nationality_types ×2
hq data_validation       : hq_types ×1
card data_validation     : card_types ×2
```

也就是说 `unit.type`、`specs[].type`、`card_type`、`hq.template` 都是**通过类型表解析**的，
写一个不存在的字符串不会得到「未识别的类型」而是**直接载入失败**。

> 实测限制：这些校验函数需要完整的 `entity_types` 装载链（见 §12 末尾），本次只成功导入了
> 字段级 schema，**未执行到"未知 type"的报错分支**。因此修改器**不要依赖游戏报错**来兜底，
> 必须自己校验。

`unit_types/` 下 627 个类型文件（base + 10 个 DLC 合并）。`type` 写错 → 游戏载入失败。
`specs[].type` 必须在 `specialists/` 下（375 个）。
`card_type` 必须在 `cards/` 下（39 个）。

**但修改器不提供"改编制 `type`"这个功能**（§7.5），原因是它**做不成**：

| 单位类别 | 只改根 `units.yml` 的 `type` | 要真正生效需要 |
|---|---|---|
| 出现在 `document/scenarios/<场景>/units.yml` 里（**A 类**） | ❌ **进战斗后会被改回去** | 改 `document/units.yml`（L5，**回退不掉**） |
| 只作为登陆/空降承载或增援出现（B/C 类） | ✅ 生效 | 不必 |
| 不参加下一场战斗 | ✅ 生效 | 不必 |

依据：`campaign_agree_on_unit`（`game_adjust_data.pyc:21`）在战斗初始化时执行 `u.type = unit.type`，
而 `unit.type` 对场景单位来说 = `document/units.yml[id].type`（§3.5.3）。
要覆盖它就得写 `document/units.yml`，而那个文件**不在 `last_conference/` / `last_game/` 里**
（实测 100 个检查点，0 个含 `document/`）→ **游戏内回退不掉**。

> ⇒ **GUI 里 `type` 只作为只读标签展示**，并顺带显示它推导出的
> **`max_st`（战力上限）与 `max_spec`（特种兵上限）** —— 这两个才是玩家真正需要的。
> 想让单位更强，就调 `act_st` 和 `specs`（§6.2）。
>
> **同理，修改器也不提供"新增单位"**：新 id 必须注册进 `document/units.yml`（L5），
> 且还要写 `games/<场景>/units.yml` 的参战清单（L3）—— 涉及 **L1 / L5 / L3 三层**，且回退不掉（§7.5）。

### 5.5 单位名的两种形态

- `id_xxx_xxx`：本地化 id，需要 `<game>/_packages/base/localization/chi/strings.yml` 里有对应键
- **明文**：`'1第德国警卫队'` —— 直接可读可写

改名的正确做法：**直接写明文**到 `name_brief` / `name_full`，改完存 `.usg` 即可生效，**不需要重启游戏**，也不需要写任何 temp mod（`<game>/_packages/` 与 `%LOCALAPPDATA%\.uoc2\_packages\` 两个位置都不用碰）。
（`name_brief` 允许 `null`；`name_full` 允许 `null`。）

⚠️ **U148（2026-11-21）**：改名要**两份表都写** ——
存档里有**两份**单位/总部表：

| 表 | 内容 | 谁在显示 |
|---|---|---|
| 根 `units.yml` / `hqs.yml` | **已经登场过**的（实测 354 / 23 条） | **战斗中**（`game_world`） |
| `document/units.yml` / `document/hqs.yml` | **整场战役的全部**（实测 835 / 47 条） | **战役地图 / 主界面**（`main_screen`） |

两份表的 id 是**同一套编号**、同 id 的 `name_brief` **完全一致**（实测 9 个存档 100% 一致）。

* 战役地图：`campaign_doc._load` → `add_campaign_unit(unit_id, type, name_brief, name_full)`
  ⇒ 名字来自**名册**，**原样**带进去（**不**按 id 反查）；
* 战斗中：`gamelike._load_entities` → `HQState.load` / `UnitState.load` ⇒ 来自**根表**；
* 显示时统一 `app.locale.get(name_brief)`（`unit_sheet.py:101` / `scalables.py:601` /
  `campaign_ctrl.py:1784`）；`LocalizationManager.get`（`tools/localization.py:198`）
  对**不以 `id_`/`idp_` 开头**的字符串**原样返回** ⇒ 明文可用；
* **游戏自己的改名**（`campaign.py::_rename_hqs`）改的正是**名册**那份 ⇒ 佐证。

⇒ **只改根表 ⇒ 战役地图上完全看不到变化**（朋友 2026-11-21 反馈"改名没生效"）。

---

## 6. 三块功能的具体改法

### 6.1 战役进度

| 想改 | 改哪里 | 注意 |
|---|---|---|
| 声望 | 根 `main.yml` 的 `prestige` | 是**预算**，会被战斗消耗（实测有升有降） |
| 分数 | 根 `main.yml` 的 `score` | |
| 🚫 里程碑 | — | **不做**（§6.1b、§7.5）。改声望/分数时该字段**原样保留**，不要增删 id |
| ~~跳到某会议~~ | ~~根 `main.yml` 的 `in_state.conference`~~ | 🚫 **不在本次范围（§0），默认不提供**。见下方说明 |

> **为什么"跳到某会议"不做**：它虽然只改 L1，但会把状态机改**不一致** ——
> 会议号变了，而 `in_state.fronts[*].segment` / `situation_idx` / `milestones` / `card_store`
> 都还停在原来的会议。游戏读档时可能直接报错，或跳到一个半成品战役。
> 这属于"改了却像没改、甚至崩"的典型，**与傻瓜式修改器的定位相反**。
> 本次范围只做**声望 / 分数**（§0）。

**声望/分数的语义（实测 16 档进度序列）**

```
存档文件                 root.prestige  root.score | last_conference | 战斗 start→end
west-Conference1-1.usg        100           0  |   (无)          | -
west-Conference2-1.usg        375        1550  |   375 / 1550    | -
west-Conference3-1.usg        320        2980  |   375 / 1550    | avalanche
west-Conference4-2.usg        520        8360  |   270 / 6641    | gothic_line
west-Conference6-2.usg        835       16952  |   970 / 14268   | po_valley
```

- 根 `main.yml` = **当前状态**（玩家在界面上看到的数）
- `last_conference/main.yml` = 上一次会议时的检查点
- `last_game/main.yml` = 上一次战斗时的检查点
- `games/<场景>/main.yml` 的 `start_data.prestige` / `end_data.prestige` = 该场战斗前后的声望

> 战斗会**消耗**声望（`end_data.prestige` 可小于 `start_data.prestige`），所以把 `prestige` 调高等于给玩家更大的行动预算。

#### 6.1b 🚫 不做里程碑（milestones）相关的任何功能

**结论：里程碑一个字都不改，UI 上也不提供任何入口。**

理由三条，前两条是产品判断，第三条是技术事实：

1. **多数玩家不关心。** 真正被反复使用的是声望、分数、单位强度、商店；里程碑是次要的收藏项。
2. **它削弱成就感。** 里程碑与战役奖章是"打赢一场"的正反馈载体。把它变成一个可勾选清单，
   等于替玩家把成就感也一起拿走了 —— 这与"傻瓜式修改器"的定位相反。
3. **技术上它分成两套，改存档只管得着其中一半。** 详见下表 —— 做了必然"改了却像没改"。

**第 3 条的机制（供实现者理解，不需要实现）**

游戏里有**三处**显示里程碑，数据源互不相同：

| 显示位置 | 数据源 | 改存档能影响吗 |
|---|---|---|
| 战役内战略侧边栏的里程碑列表 | 存档根 `main.yml` 的 `milestones` ∩ `document/main.yml` 的 `milestones` 定义表 | ✅ 能 |
| 战役内的战役奖章 | `document/medals.yml` 的 `milestones` ⊆ 存档根 `milestones` | ✅ 能 |
| 主菜单「里程碑」图鉴（跨战役的全局页） | **Steam UserStats 统计 `ms_<campaign_id>_<milestone_id>`** | ❌ 不能 |

全局那一份**不在任何游戏本地文件里，而在 Steam 账号的统计里**：

- 读：`state/campaign/campaign_info.pyc :: MilestoneInfo.__init__` → `app.steam_api.get_stat_value('ms_<campaign>_<id>')`；
  取值 `0` = 未解锁 / `1` = 刚首次达成（发光挂饰 + "首次达成"提示）/ `≥2` = 早已解锁。
- 写：唯一写入点 `state/campaign/campaign.pyc :: Campaign.game_finished` →
  `self.milestones.append(id)`（存档）+ `app.steam_api.inc_stat('ms_...')` + `store_stats()`（Steam），
  后者经 `lib/tools/steam_api.pyc` → `lib/tools/steamworks.pyc` → `SteamUserStats.SetStat` / `StoreStats`。
- 主菜单图鉴读的"定义"来自**战役包** `<包>/data/campaigns/<战役>.usc/main.yml`
  （`paths.pyc :: _Paths.init_packages` 动态生成的 `campaign_doc_dir_abs`）。
- 旁证：`settings.yml` 全文无里程碑字段；Steam Cloud 的 `remotecache.vdf` 只登记 `.uoc2/save/**/*.usg`，
  **没有任何 `ms_*` 条目**；`userdata\<id>\809230\remote`（UserStats 本地缓存）本机不存在。

⇒ 就算要做，**也只能做战役内那一半**，主菜单的全局图鉴仍然不会亮。所以：**不做。**

**唯一必须遵守的规则（不是功能，是写回纪律）**

改声望/分数必然要重写根 `main.yml`，此时 **`milestones` 字段必须原样保留**：

- 丢掉它 ⇒ 游戏 schema 会当成空列表（`Required('milestones', default=list())`，**不报错**），
  于是本局已达成的里程碑与战役奖章**静默消失**，直到玩家用游戏内的「重置会议」回退
  （检查点 `last_conference/main.yml` 里也带 `milestones`，实测确认）。
- 也不要新增或删除其中任何一个 id。

> 同一条纪律适用于根表其余字段 —— `card_store` / `tokens` / `tokens_map` / `renamed_hqs` /
> `reverted_games` / `used_card_types_with_unit` 等：
> **除非本次功能明确要改它，否则一律原样搬运**（§7.2 W2）。
> "悄悄丢一个键"是比"写了非法值"更难发现的破坏。

**证据脚本**：`e88_achieve.py` ~ `e92_setup.py`（入口搜索）、`e93_globalms.py`、`e94_msdetail.py`、
`e95_globalstore.py`、`e96_firsttime.py`（`MilestoneInfo.__init__` → `ms_*` 读法）、
`e97_steamapi.py` / `e98_write.py`（`Campaign.game_finished` 发放链）、`e99_apiimpl.py`、
`e100_docdir.py`、`e101_census.py` / `e102_census2.py`（70 存档里程碑普查：
根表 ⊆ 定义表 **70/70**、奖章 **79/249** 已满足、15 个战役包的定义表条数）、
`e103_globals.py`、`e104_exe.py`、`e105_steamapi2.py`（`lib/tools/steam_api.pyc` 完整反汇编）。

> ⚠️ **诚实边界**：本机**没有读出任何 `ms_*` 统计的真实数值** —— 它在 Steam 客户端的 UserStats 里，
> 需要 Steam 客户端在运行才能通过 `SteamUserStats.GetStat` 读到。
> 上面关于 `ms_*` 读写链的结论来自**字节码链路**与**游戏日志**（每次启动都打印
> `Steamworks initialized!` 与 `Steam user stats and achievements successfully fetched`），
> **不是**读到了真实统计值。

### 6.2 单位

**要改哪个表？** 这是最容易出错的地方 —— ⚠️ **初稿曾写错，此处为实测更正**。

> **根 `units.yml` / `hqs.yml` 就是实时单位表。**
> 战斗中的单位**就在根表里**，带着实时的 `uv`/`ap`/`mp`/`act_st`/`supply`。
> `games/<当前场景>/units.yml` **只是 ID 清单**（本场有哪些单位），不是实体数据。
> 证据见 §3.4.3（`Stalingrad.usg`：根表中 86 个参战单位与 archive 快照**逐字段完全一致**）
> 与 §3.4.4（字节码：战斗的单位对象就是从名册里取出来的同一批对象）。

| 玩家想改的东西 | 改这里 |
|---|---|
| **战斗中的**单位/总部（B1/B2） | **根 `units.yml` / `hqs.yml`**（按 `id` 定位） |
| 战役地图上的单位/总部（M1..M5） | **根 `units.yml` / `hqs.yml`** |
| 已结束战斗里的单位（历史存档 / 回放） | 🔒 **只读** —— `games/<场景>/units.yml`（完整对象格式），L3 不改（§7.2 W3） |
| 独立场景（S5） | **根 `units.yml` / `hqs.yml`** |

**当前活动场景的判定**：`games/<场景>/units.yml` 的内容是 `list[int]` → 这是 ID 清单（数据在根表）；
是 `list[dict]` → 完整对象（已结束的战斗）。
**解析器必须先判断这个，再决定怎么读。**
（实测：70 个存档里，**当前活动场景的 `units.yml` 15/15 全是 ID 清单，0 个是完整对象**。）

**写入清单**（战斗态下改完根表还要处理什么，详见 §3.4.4.7 与 §7）：

| 目标 | 是否需要改 | 方式 |
|---|---|---|
| 根 `units.yml` / `hqs.yml` / `main.yml` / `cards.yml` / `store.yml` | ✅ **可写**（唯一的常规写入面） | 按 id 定位并修改（§7.2 W1） |
| `last_conference/`、`last_game/` | ❌ **不要动** | 玩家的游戏内撤销基线（§7.2 W2、§7.4 R1–R3） |
| `games/<场景>/main.yml`（独立场景是 `game/main.yml`） | 🔶 **只有两个键可改** | `theater_assets`（战区资产）与三个作战标记 id 列表；其余键（`ar_ord` / `turn` / `scores` …）**不要动** —— 回合流程状态由游戏自己维护（§6.2b、§6.2c、§7.2 W8） |
| `games/<场景>/ar_list.yml` | ❌ **不要动** | 本回合已执行行动列表（§7.2 W3） |
| `games/<场景>/archive/<最后快照>/*` | ❌ **不要动** | 历史 / 回放基线（§7.2 W4、§7.4 R5） |
| `games/<场景>/units.yml`（ID 清单） | ❌ **不要动** | 修改器不提供新增单位（§7.5） |
| `games/<场景>/campaign_units.yml` | ❌ **不要动** | 实测该路径根本不存在，读档也不会加载它 |
| `document/`（含 `units.yml`、`scenarios/*`） | ❌ **不要动** | 战役文档层只读；写它回退不掉（§7.2 W5、§7.4 R6） |

**GUI 该怎么表现**：
- 用户打开存档时，按 §3.4.6 的判定把当前阶段显示在界面上（**不要**按 §3.4.2 的状态标签写分支）（"战斗中：Tunis 第 4 回合" / "本段场景已完成，等待会议" …）。
- 展示单位列表时，**永远从根 `units.yml` 读**。
- 如果用户想看"某场已结束战斗里的单位"，从 `games/<场景>/units.yml` 读，并标明这是**历史存档（只读，不可编辑）**。
- **不要**给用户"战役名册 / 战斗内"这种需要用户自己判断的作用域选择框 —— 结构上根本不存在两张表。
- 在战斗态下，UI 可以额外显示该单位的**实时战场状态**（`uv` 位置、`ap`/`mp`、补给、压制战力），
  这些值就来自根表，不需要另读一份。

**可改项**

| GUI 项 | 字段 | 约束 |
|---|---|---|
| 经验 | `xp` | 0..399 |
| 活跃战力 | `act_st` | ≥0；**普通部队（活跃 + 被压制）超类型上限 `max_st` 时自动配平并改写输入值**（§5.3、§6.2） |
| 被压制战力 | `sup_st` | ≥0；同样参与上面的自动配平 |
| 编制/类型 | `type` | 🔒 **只读展示**（灰显）。同时显示它推导出的 `max_st` / `max_spec`（§5.4、§7.5） |
| 特种兵 | `specs[]` | 增删 `{type, active, captured, idx}`；`type` 下拉 375 个；上限 `min(3, max_spec or 3)`；`idx` 填空闲槽位 0..2；**挂载合法性硬拦**：阵营相同 + 国籍相同或**单位国籍的父国籍**匹配（单向）（`handlers.py::_unit_spec_add`） |
| 改名 | `name_brief` / `name_full` | **直接写明文**；`name_full` 允许 null |
| **所属总部的兵库（存货）** | 根 `hqs.yml` 的 `force_pool[].quantity` | ✅ **可改**；≥0；见 §6.2b |
| 所属总部 | `hq_id` | 🚫 **不可改** —— **从未实现**，一点就报错（`handlers.py::_unit_field`） |
| 位置 | `uv` | 🚫 **不可改**（U94 已删除该字段，有护栏测试） |
| 堑壕/补给/行动点 | `entr`/`supply`/`ap` | 见 §5.2 |

**改 `type` 的副作用**：~~`act_st` 可能超过新类型的 `max_st`~~ —— 不适用，修改器不改 `type`（§5.4）。

#### ⚠️ 6.2.1 最重要的一件事：改动的"生效时机" ⚠️

**游戏在"新开一场战斗"时会重算一部分字段**（§3.5）。
这意味着**同一个改动，在战斗中改和在战斗外改，结果不同**。

| 改动的时机 | 结果 |
|---|---|
| **战斗中（存档后修改）** | ✅ **全部生效**。读档走 `Game._load`，**不重算** |
| **战斗外（战役地图 / 会议）** | ⚠️ **部分字段会在下次开打时被覆盖** |

**逐字段的存活性矩阵见 §3.5.8**（⭐ 核心表）。摘要：

| 改什么 | 战斗外改的结果 |
|---|---|
| `xp` / 改名 | ✅ 安全（登陆单位例外，见 §3.5.6） |
| `uv` / `entr` / `hq_id` | ❌ 对**场景初始单位**会被场景预设覆盖<br>（`uv` 这一条的依据**仅来自字节码**，未见实测 —— 见 §3.5.10 第 5 条） |
| `sup_st` / `specs[].active` | ❌ 会被重置（压制恢复 / 全部重新激活） |
| `specs` 列表内容 | ⚠️ 对**登陆/空降/早期增援单位**会被"按 type 对账"，多余的剥离退回总部 |
| `act_st` | ⚠️ 对**登陆/空降/早期增援单位**会被补到场景目标（只增不减） |

> **UI 决策**：这些字段**不禁用**，但必须打上 `⚠️ 进战斗时会被重置` 的徽标，
> 点击时给一句说明（例如"这是场景初始单位，改它的位置会在下次开打时被场景预设覆盖"）。
> **禁用反而更糟** —— 玩家会以为修改器坏了。给警告 + 允许改，符合"傻瓜式"定位。

**修改器应当做的三件事**（详见 §3.5.9）：

1. **在战斗中时，UI 顶部明确标注**：「当前是战斗中的存档，此处修改**不会被游戏初始化覆盖**，推荐在此修改。」
2. **在战斗外时，对将被重组的单位给出预警**，并列出**具体会被重置的字段**：
   - 判定方法：读 `document/scenarios/<下一场场景>/{units.yml, prepositioned_assets.yml, enroute_units.yml}`（**变体优先、基础兜底**）
   - 资产里 `type != 'bb'` 且有 `unit.id` → 该 id 是**登陆/空降承载单位**
   - 存在任一这样的资产 → `on_turn ≤ 4` 的增援也是**早期增援**
   - 在场景 `units.yml` 里的 id → **A 类**，字段会被覆盖
3. **❌ 不提供"场景预设编辑"** —— 登陆单位的特种兵要对账，唯一根治办法是改
   `document/scenarios/<场景>/prepositioned_assets.yml` 的 `unit.specs`（对账基准），
   那是 **L5 写入**，**游戏内回退不掉**，而且用户完全摸不着头脑（§7.5）。
   **替代方案**：引导用户在"战斗中"的存档里改（§3.5.1：战斗中改不会被对账）。

> **一句话给产品负责人**：
> **"改单位"这个功能有两个战场——战斗中的存档（安全）和战役地图（会被游戏重算）。**
> 界面必须让用户一眼看出自己在哪个战场，以及哪些字段会被覆盖。

#### 6.2b 总部兵库与战区资产 —— 两个常被混为一谈的东西

玩家口中的"存货"其实有**两个不同的东西**，存储位置、生命周期、可改性都不一样。**先分清，再实现。**

| | **总部兵库**（玩家说的"存货"） | **战区资产**（游戏内部术语 `theater_assets`） |
|---|---|---|
| 存哪 | 根 `hqs.yml` 的 `force_pool[]`，**每个 HQ 各一份** | `games/<当前场景>/main.yml` 的 `theater_assets`，**每个场景一份** |
| 是什么 | 该 HQ 手头存的兵力/装备**存量**（`{delay, nationality, quantity, spec 或 equipment}`） | 战场层面的一次性**资源额度**（`{asset, to_use, to_use_not_used, uses_total, uses_turn}`） |
| 谁在用 | 会议/商店界面把兵从 HQ 部署到单位上 | 场景内的特殊行动（空投、登陆、特殊事件等）的可用次数 |
| 游戏什么时候算 | **从不重算** —— 只在玩家花掉或补货时变化 | **每次开一场新战斗时按场景重新计算**（`Game.new`） |
| 改它安不安全 | ✅ **L1，可随时改**，改完读档即生效 | ⚠️ **仅在当前进行中的战斗里安全**；战斗外改会被下次开打覆盖 |
| 层级归属 | **L1**（正常可写层） | **L3** —— §7.2 W8 的**白名单例外 ①**（另一个例外是作战标记，§6.2c） |

##### 总部兵库（L1，随时可改）

**字节码证据**（见 §12 的 `e112_hqinherit.py` / `e113_hqadjust.py`）：

- `Game._adjust_hqs_between_situations`（总部侧的重组函数）会重建 `self.hqs`、
  调用 `campaign.agree_on_hq(hq, self)`、`hq.unsuppress_branch_levels()`、`self._set_hq(hq)`、`hq_routes_clear()`
  —— **全程没有 `force_pool`**。
- `Campaign.agree_on_hq` 处理的是 `persistent / campaign_id / uv / supply / overrun / turn_disbanded /
  general / sp_data / disable_action / reduce_action_cost / level`
  —— **`'force_pool' in co_names` = False**。
- `Campaign._rename_hqs` 的常量表只有 `1, 'id', 'general', None, 'hq_id'`
  —— 只改 id / 将领 / 关联，**内容整体继承**（含兵库、含升级）。

⇒ **HQ 兵库的 `quantity` 是 L1 可写字段，且游戏在任何重组路径上都不重算它。**
改完读档即生效，玩家在会议/商店界面直接看到新的存量。

约束：

- `quantity` 必须是 **≥ 0 的整数**。
- `delay` 是"冷却回合"（这个部队等几个回合才能部署）—— **GUI 里必须可填**
  （它是游戏里的真实机制，GUI 设计规范同样要求可填）；但必须是**非负整数**
  （游戏的 `force_pool_schema` 硬范围，负数会让存档打不开）。
- **判重**：同一个总部里**同身份 + 同延迟**不许并存（延迟不同可以共存 = 分批上线）
  —— 硬拦（`handlers.py::_hq_force_pool_add`）。
- 条目的 `spec?` / `equipment?` 是**二选一**：既不要同时写两个，也不要写第三个键（PREVENT_EXTRA，§5.1）。
- 改 `quantity` **不改变**该条目的 `nationality` / `spec` / `equipment`。

##### 战区资产（L3，白名单例外 ①）

玩家的判断是对的，而且可以说得更精确：

- `Game.new`（**玩家点「开始这场战斗」的那一刻**）才会重置战区资产：
  `ta.to_use = ta.uses_turn; ta.to_use_not_used = None`。
- `Game._load`（**读档继续战斗**）按 `game_main_schema` 读 `games/<场景>/main.yml` 之后执行
  `self.__dict__.update({k: data[k] for k in copy_fields})`，而 **`copy_fields` 含 `theater_assets`**
  ⇒ **读档不重算**，直接采用存档里的值。
- `Game.hard_set_state_on_ar_ord` 的 `copy_fields` 同样含 `theater_assets` ⇒ 这条路径同样不重算。

⇒ **在"当前进行中的战斗"的存档里改 `theater_assets`，读档后立刻生效，游戏不会把它冲掉。**
这就是 §7.2 W8 那个 L3 白名单例外的全部理由。

**但边界必须说清楚**：

| 情形 | 可否改 | 说明 |
|---|---|---|
| 当前正在战斗中（`in_state.scenario` 非空，且 `games/<场景>/` 存在） | ✅ 可改 `games/<当前场景>/main.yml` 的 `theater_assets` | 读档即生效 |
| 战斗外（战役地图 / 会议界面） | ❌ **不可改** | 下次开打时 `Game.new` 会按场景重算，改了等于没改 —— 典型"改了却像没改" |
| 已结束战斗的快照（`games/<场景>/archive/<快照>/main.yml`） | ❌ **永远不可改** | 那是历史战报（§7.4 R5） |

补充事实（避免误解）：

- **游戏写盘时会覆盖它**（`Game._save` 把当前的 `theater_assets` 写回 `games/<场景>/main.yml`）——
  这没问题：修改器改完存档、玩家读档继续打，游戏接手后按自己的状态写回，逻辑自洽。
- **游戏内的「重置会议」撤不掉它**（会议回退走 `Campaign._load_revert_campaign_data`，
  整表替换根级 L1 文件，**不碰** `games/<场景>/main.yml`）。
  ⇒ 这正好说明**修改器必须有自己的撤销栈**（§6.4）：游戏内回退救不了这一项。
- **战斗外改战区资产是禁止的**，不是因为会损坏存档，而是因为**会白改** ——
  游戏下次开打时按场景重算，玩家的修改直接消失。这违反"改了就一定看得见"的第一原则。

**写回时的实现要求**：战区资产与作战标记（§6.2c）是本策略下**仅有的两个**需要写 L3 的功能，
而且写的是**同一张文件** ⇒ `save.commit` 要能同时处理"根目录 L1 文件"与
"当前战斗层那张 `main.yml`"两个来源，但**只允许改那几个键**。
正确做法：解析该文件 → 只替换 `theater_assets`（及三个作战标记 id 列表）这几个键 →
其余键（`ar_ord` / `turn` / `scores` / …）**原样搬运** → 写回。
**不要用整表替换** —— 那会丢掉实时字段的当前值。
⚠️ 独立场景存档的战斗层是**单数目录 `game/`**（`game/main.yml`）——
路径要按 `container.py::battle_dir()` 取，不要写死 `games/<场景>/main.yml`。

#### 6.2c 作战标记（L3，白名单例外 ②）

**单位身上的三种"命令"**（HQ 技能）：**死守**（`no_retreat_units`）、**后卫部队**（`rearguard_units`）、
**反击**（`elastic_defense_units`）—— 写在**当前战斗层**那张 `main.yml` 里
（战役 `games/<场景>/main.yml`，独立场景 `game/main.yml`）。

- ⚠️ 这是**第二个 L3 例外**（第一个是战区资产，§6.2b）—— 两者写的是**同一张文件**，
  该文件其余键原样搬运（§7.2 W8）。
- 三个标记**互斥**：一个单位同时只能有一个（游戏的 `UnitSetFlags._set_flags` 先全清再加一个，
  三个 `can_make_*` 都要求该单位没有别的标记）⇒ 硬拦。
- 「**反击**」只允许**装甲机动单位**（有 `armor`、不是 `armor_def`、`movement = mobile`）⇒ 硬拦。
- 命令**敌方下一回合结束前有效** ⇒ 游戏回合开始会清掉（`Game.start_turn_clear`）⇒ 只对当前回合有效。
- 单位必须**在这场战斗里**（当前战斗的单位 id 名单），否则报错。
- ⚠️ 游戏**开着**时改盘 ⇒ 退出时的自动保存会覆盖你的改动 ⇒ 改之前先退出游戏。
- 实现：`handlers.py::_unit_orders`（kind = `unit_orders`）。
- **写回时**：与战区资产共用同一条路径 —— 只替换这三个 id 列表，该文件其余键原样搬运
  （§7.2 W8、§7.6）。

---

### 6.3 卡牌与商店

**加卡**：往根 `cards.yml` 追加条目
```yaml
- {card_type: air_attack_allies, is_free: true, position: 3, unit_id: null, used: false}
```
- `position` 建议用现有最大 position + 1，避免重复
- ⚠️ **手牌槽位有上限**（按难度 easy/normal 5、classic 4、hard 3 —— `card_deck_limit`）：
  超限的槽位**游戏读不到**（游戏按槽位索引读手牌）⇒ **硬拦**；槽位已被占用也拦
  （`handlers.py::_card_add`）
- `card_type` 从 39 个卡牌类型里选
- ⛔ **U187：带单位的卡（`has_unit: true` = 空降 / 登陆）一律不许直接加到手牌** —— 硬拦。
  **理由**：这类卡用的时候要召唤单位，而本战役为它登记的那个单位 id
  （`document/main.yml.card_type_units`）**可能已经被召唤过**（`used_card_types_with_unit`）
  ⇒ 有**重复召唤同一个单位**的风险 ⇒ **游戏读到会崩**
  （2026-11-25 实测：给「霸王行动」加 82 空降师 ⇒ 崩）。
  ⚠️ **崩溃的具体触发点没能离线定位** —— 游戏自己的存档里**也有**同样形态的
  召唤卡（`e169` 实测）⇒ 这是一条**保守兜底**（整类掐掉），不是「已定位根因」。
  ⇒ 手牌这一侧**一刀切禁掉**，不判断「用没用过」（用户 2026-11-25 拍板：最保险）。
  - **存档里原本就有的不检测** —— 读路径一行不改，照常显示。
  - **卡牌商店（货架）那侧不受影响** —— 上架 / 换牌走 `card_whitelist`
    （那里本来就把「已召唤过 / 已在手牌 / 预留单位阵亡」排除掉了），
    而**游戏自己本来就会把召唤卡发上货架**。

**"当前会议手里的牌"（`main.yml` 的 `card_store`）—— 分三种情况**：

| 情况 | 能力位 | 修改器怎么做 |
|---|---|---|
| 玩家正停在会议界面（已发牌） | `has_card_store` | **可编辑**手里那几张牌的 `card_type` / `is_free` / `unit_id`（写 L1） |
| 玩家不在会议界面 | — | **不提供"凭空造牌局"** —— 写 `card_store` 会让游戏认为你在会议界面，但 `in_state.fronts` / `segment` / `milestones` 都没跟着变，状态机会不自洽 |
| 「**恢复上次会议的牌局**」 | `cp_conference` | ✅ **提供这个动作**：读 `last_conference/main.yml` 的 `card_store` → 原样写进根 `main.yml` 的 `card_store`。<br>**读 L2、写 L1，完全符合 §7 的写入策略**（检查点只读） |

> 「恢复牌局」是很实用的一步操作：玩家错过一次会议后，可以把上次的牌面原样恢复到手里。
> 它也顺带演示了 §7 的策略为什么成立 —— **读**检查点没问题，**写**才是问题。

**改商店**：根 `store.yml`
```yaml
store:
  - {equipment: infantry, nationality: us, price: 5, quantity: 20}
```
- 改 `price` → 改单价。**`price: 0` = 免费商品**（游戏正常状态，实测 70 个存档里有 43 条）
- 改 `quantity` → 改库存，**必须 ≥ 1**。⚠️ **不要把它设成 0** —— 游戏里没有「已售罄」标记，
  买完是**把条目删掉**；`quantity: 0` 是游戏自己从不产生的状态（实测 1659 条条目里 0 条），
  写进去会让条目留在列表里却买不到东西。**要下架某商品，请删除该条目。**
- 想加条目 → 复制格式追加；`equipment` ∈ {infantry, armor}，或用 `spec:` 挂特种兵
- **顶层的战线键必须用游戏包 `fronts/` 里已有的战线名**，且**只写在存档已有的键下面**
  （存档的键是包 `fronts/` 的**子集** = 当前已激活战线；实测 west 有 `{france,italy}` 与 `{italy}` 两种、
  blitzkrieg 有三种）。**不要凭空新建战线键**，也不要按 `document/main.yml` 的 `fronts_sorting_order` 猜。
- `elite_store`（精英商店）**同样支持**：改价 / 改量 / 下架 / 上架**三种商店编辑都覆盖
  `store` 与 `elite_store` 两个子商店**（`handlers.py::STORE_SUBS`）—— 实测战役包里它恒为 `null`，
  但存档里出现就照改
- **判重**：同一个 `(战线, 子商店)` 里**不许出现重复条目**（同 spec/equipment + 同国籍）
  —— 硬拦（`handlers.py::_store_add`）；要改就直接改那一条，别再上一份
- 条目只有**两种**形态：`{equipment, nationality, price, quantity}` 与 `{spec, nationality, price, quantity}`（§4.6）
- ⚠️ **不要拿游戏包的静态商店清单去"纠正"存档** —— 实测存档价格可能与包默认不同（277 条），原因未定位（§4.6.1）。
  修改器只改存档里的实际值。

**「补货」的正确做法（实测机制，§4.6.1）**

| 玩家想要 | 修改器怎么做 | 为什么 |
|---|---|---|
| 把某个商品补满 | 改**该条目的 `quantity`**（调大） | `quantity` 就是"剩余可买数量"，游戏买的时候按它扣 |
| 让某个商品变成无限量 | `quantity` 设一个**足够大的整数**（如 99） | 游戏不校验上限，但别设成 0 |
| 下架某个商品 | **删掉该条目** | `quantity: 0` 是游戏从不产生的状态（条目会留在列表里却买不到） |
| 让某个商品免费 | `price: 0` | 这是游戏正常状态（实测 43 条） |
| 加一个新商品 | 复制现有条目改字段后追加 | 键集合只有两种，别自创键（§5.1 PREVENT_EXTRA） |

---

### 6.4 备份与撤销栈 ⭐（产品底线，不是可选项）

玩家改存档最怕两件事：**改坏了**、**改错了想反悔**。游戏自带的「重置会议 / 重打上一场」
只能**整体回滚**，救不了"只想改回刚才那个数字"的场景 —— 而且它**根本撤不掉战区资产**（§6.2b）。
所以修改器必须自带两件东西。

#### 6.4.1 备份（写回前自动生成）

- 写回前，把**原始 `.usg` 整体复制**为 `<存档名>_BACKUP.usg`，
  **放在 `<修改器目录>/bak/`**（U109：`paths.py::backup_dir`）。
  - 命名沿用**游戏自己的约定**（`main_screen/ctrl.pyc` 里就是这个命名），玩家认得出来。
  - 同名备份**已存在时不要直接覆盖** —— 用带序号的后缀（`<存档名>_BACKUP_2.usg`），
    否则第二次修改会把第一次的救命备份冲掉。
- 备份必须是**原文件的整体字节拷贝**，不是"重新打包" —— 必须与原文件**字节级一致**。
  （重新打包会改变 ZIP 条目顺序/时间戳，虽然游戏能读，但就不是"原件"了。）
- 🚫 **绝不放在存档同目录** —— 游戏只扫存档目录里的 `*.usg`，
  备份放那儿会被**游戏当成存档**列出来（U109 的教训）。
- `bak/` 建不出来 / 不可写时（例如整个修改器装在 Program Files 下）⇒ 退到
  **`<游戏数据目录>/bak/`**（U132：`paths.py::fallback_backup_dir`）；
  两处都不行 ⇒ **宁可拒绝写盘**（没有备份就不写），也绝不把备份丢给游戏
  （`writer.py::make_backup`）。

#### 6.4.2 修改器自己的撤销栈

- 每次 `save.commit` 成功前，把"本次改动涉及的 L1 内容"（以及**战区资产 + 作战标记**那几处 L3 内容）压入**撤销栈**。
- `save.undo()` 弹出栈顶，把**上一次提交前的值**重新写回去 ——
  同样走完整的"备份 → 写临时文件 → 校验 → 原子替换"流程，**不复用**任何简化的写路径。
- 撤销栈要**落盘**（例如 `<存档名>.undo.json`，或程序目录下的 `undo/`），
  否则关掉程序就撤不回来了。
- 撤销粒度是**"一次 commit"**，不是"一个字段" —— 一次 commit 里改了 3 个单位，就一起撤销。
  更细的粒度对傻瓜式 GUI 反而更难用。
- 撤销栈与游戏内回退**互不干扰**：两个都能用，谁先谁后都可以。
  ⚠️ 唯一要处理的是：**游戏内回退后，撤销栈的基准可能已经过期** ⇒
  撤销前必须**重新校验基准**（例如"该单位现在的 `xp` 是 320，而不是你改之前的 100"），
  基准不符就**拒绝执行并明确提示**，不要硬改。

> **一句话**：游戏内回退是"整体回到过去"，撤销栈是"退回我上一步改的那个数"。
> **两个都要有。**

#### 6.4.3 撤销栈的落地格式（实现参考）

下面是核心库已实现的形态（`save_modifier_core/undo.py`），照此实现即可满足 §6.4.2。

**栈文件位置**：存档旁边的 `<存档名>.undo.json`
（游戏只扫 `*.usg`，`.undo.json` 不会被它当成存档；玩家备份存档目录时一起带上）。

```json
{
 "version": 1,
 "records": [
  {
   "id": "8f14e45fceea167a5a36dedd4bea2543",
   "time": "2026-11-17T23:26:48",
   "summary": "改了 1 个文件：单位 1 的 xp：314 → 77",
   "entries": [
    {"entry": "units.yml", "codec": "zlib+b64",
     "before": "H4sIAAAAAAAA...", "after_sha256": "3f2a...（64 位十六进制）"}
   ]
  }
 ]
}
```

| 字段 | 作用 |
|---|---|
| `before` | 被改条目的**改前原始字节**（zlib 压缩 + base64）—— 撤销时逐字节写回 |
| `after_sha256` | 被改条目**改后内容**的 SHA256 —— **这就是基准** |
| `summary` / `time` | 给 GUI 显示的一行说明（"可撤销：…"） |

**撤销流程**：

1. 读栈顶；
2. **校验基准** —— 读当前存档里那几个条目的内容，算 SHA256，
   与记录的 `after_sha256` 逐条比对；
   **对不上就拒绝执行**，明确说明"存档在你改完之后又被动过"，
   并提示玩家可以直接把 `_BACKUP.usg` 复制回去；
3. 走**和 commit 完全相同**的写回管线（备份 → 临时文件 → 校验 → 原子替换），
   把条目还原成 `before` 字节；
4. 成功后**弹出栈顶**并落盘。

**容量**：最多 20 条记录 / 32 MB，超了从**最旧的**开始丢。

⚠️ **拒绝撤销时不能弹栈** —— 否则玩家就永远撤不回来了。

**顺带一条守卫**：规划之后如果存档被别人改过（多半是玩家在游戏里手动改的），
`commit` 也应当**拒绝写入** —— 别把人家的改动覆盖掉。

---

### 6.5 废墟修复（city_restore）⭐

> ✅ **状态**：设计已拍板（用户 2026-11-24），U183（只读 API）→ U184（写入）→ U185（界面）**全部落地**。
> * **U183**：`Save.ruined_cities()` + `/api/campaign-detail` 的 `ruins` 字段。
> * **U184**：`city_restore` 写入路径 + 写盘白名单已放开（§7.2 W9）。
> * **U185**：战役页的「废墟」块（§6.5.8）。
> * ⛔ **只剩实机验证**：改一座城市后让游戏读一遍（§11.8 最后一条）。

#### 6.5.1 为什么需要它

城市被打成废墟后，**废墟状态是战役级的、只增不减**（机制见 `docs/开发上下文.md` §5.1bn / §5.1bo）：

* 战役根 `main.yml` 的 `destroyed_cities` 是**权威清单**（`[[x, y], …]`，顺序 = 摧毁时间序）；
* 每场**新开**的战斗开局时（`Game.new`）把清单**重新注入**当前场景
  ⇒ 上一场打废的城市，下一场仍然是废墟。

⇒ 废墟天然挡在关键城市前面。修改器要做的事只有一件：**让某一座废墟城市重新变回完好**。

#### 6.5.2 范围（用户 2026-11-24 拍板：保守）

**做**（就这三样）：

1. 战役页显示**最近变成废墟的那一座**（= 清单最后一项）—— 坐标 + 它出现在哪些场景；
2. 一个「修复这一座」按钮；
3. 折叠区列出**其它废墟**，可点选修复（**一次一座**）。

**不做**（明确排除）：

| 不做 | 为什么 |
|---|---|
| 添加废墟 / 把城市打成废墟 | 反方向的功能，风险不对称，也没有玩法诉求 |
| 批量 / 全部恢复 | 使用者通常只需要修 1 座；批量会一次动多个场景快照，改了什么看不清 |
| 城市总表（地图上所有城市 + 名字） | 游戏包里**没有城市坐标清单** —— 城市位置来自**运行时 vector map 的地形码 `CTY`**（`assets.yml: cities: {terrain: CTY, terrain_method: one_hex}`），不随包发布（`data/maps/<图>/` 只有 `map.yml` / `assets.yml` / `assets/*.yml` / `editor_data/` / `__cache__/`）⇒ 要做总表就得反解 `.npz` 地形码，代价远大于收益 |
| 城市名 | 存档里只有 `document/scenarios/<场景>/objectives.yml` 给**有目标**的城市起名，绝大多数城市没有名字 ⇒ 只能显示坐标 |

#### 6.5.3 写入目标：三处必须一起改 ⭐

「修复一座城市」= **三处同时改**。漏掉任何一处都会留下**永久残留**（§6.5.6 R1）：

| # | 条目 | 改什么 | 为什么必须改 |
|---|---|---|---|
| ① | **根 `main.yml`** → `destroyed_cities` | 删掉该坐标的**所有出现**（清单里可能有重复坐标） | 权威清单。不删 ⇒ 下一场**新开**的战斗又注入它 |
| ② | **`games/<场景>/cities.yml`** → `map` | 删掉含该坐标的条目（**遍历所有场景**） | 场景级快照。不删 ⇒ 该场景仍是废墟；而且**清单已无、快照还在 ⇒ 以后再也注入不回来 ⇒ 永久残留** |
| ③ | **`games/<场景>/forts.yml`** → `map` | 同格要塞的 `functional` 改回 `true` | `set_destroyed_cities` 摧毁城市时会把**同格要塞**置 `functional=False` |

**②③ 的落点怎么找**：**只按存档里 `games/*/cities.yml` 的实际内容定位**（哪些场景的快照里有这座城市），
**不要**用 `playable.npz` 反查，也**不要**用 `document/scenarios/<场景>/main.yml` 的 `playable_area` 多边形
（实测 bbox / 多边形判定误判 43 处 —— 多边形是凹的）。

**③ 只改「同格」的那一条**：实测 68 个存档里，废墟格上的要塞条目共 28 条，
**`functional` 全部为 `false`（28/28，0 例外）**；而不在废墟格上的要塞 423 条里 False/True 都有
（271 `false` / 152 `true`）⇒ **`functional=false` 的主因不是「城市被摧毁」**，
只有**按格对齐**才不会误伤「城市没被摧毁、但要塞被单独打掉」的格子。

#### 6.5.4 数据格式（字节码 + schema 实证）

| 文件 | 结构 | schema（`state/gamelike/map_objects.pyc`） |
|---|---|---|
| 根 `main.yml` → `destroyed_cities` | `[[x, y], …]` | `campaign_schema`：`Required('destroyed_cities'): List(uv_schema)`；`uv_schema` = 两个非负整数的序列 |
| `games/<场景>/cities.yml` | `map: [[x, y], {in_repair: false}]` | `_cities_schema` = `Schema(Dict({Required('map', default=[]): ExactSequence(uv_schema, Namespace({Required('in_repair', default=False): bool}))}))` |
| `games/<场景>/forts.yml` | `map: [[x, y], {functional: true}]` | `_forts_schema` 同上，但附加数据是 `Namespace({Required('functional'): bool})` —— **没有默认值 ⇒ 必须写** |

**加载路径（字节码实证）**：`MapObjects.__init__`（L75-77）→ `map_additional[ft] = dict(data['map'])`
⇒ `map` 是「`[坐标, 附加数据]` 对」的列表；voluptuous 的 `uv_schema` 会把坐标**转成 tuple**
（否则 `dict(...)` 会因 list 不可哈希而炸）。

**保存路径**：`MapObjects.save`（L123-131）→ `data['map'] = [(uv, {k: v for k, v in ns.__dict__ if not k.startswith('_')}) …]`
→ `serialization.save_yaml_check_empty('<ft>.yml', data)` ⇒ **空表不写文件**。

> **证据脚本**：`docs/证据脚本/e167_ruins_mapobjects.py`（本节全部字节码）、
> `docs/证据脚本/e168_ruins_survey.py`（本节全部统计数字）。

#### 6.5.5 三条硬约束

1. **战斗中不许修**（能力位 `in_battle` = `in_state.scenario` 非空 ⇒ 直接报错）。
   理由：`Campaign.save` 每次存档都**删掉并重写** `games/<当前场景>/`，根 `main.yml` 也从内存重写
   ⇒ **我们在磁盘上的修改会被游戏覆盖回去**（改了等于没改）。
   实测 68 个存档里 `in_state.scenario` 非空的 9 个**全部**是「战斗中」或「部署阶段」，无误判。
2. **不写 L2 检查点**（`last_game/`、`last_conference/`）—— §7.2 W2 不变。
   代价：游戏里点「重置会议 / 重打上一场」会用检查点覆盖战役清单 ⇒ 可能把这处修改回退
   ⇒ 界面必须提示「要撤销请用本工具的『撤销』」。
3. **不改其它坐标**：只删目标坐标的条目，其它坐标与其它键**原样搬运**（§7.2 W2）。

#### 6.5.6 风险

| 风险 | 说明 | 对策 |
|---|---|---|
| **R1 残留** | 只删了根清单、漏了某场景的 `cities.yml` ⇒ 该场景仍是废墟，而清单已无 ⇒ 以后**永远**不会再注入 ⇒ **永久残留**（比不改更糟：玩家以为修好了） | ② **遍历所有** `games/*/cities.yml`，按实际内容删 |
| **R2 被游戏覆盖** | 战斗中改 ⇒ 游戏存档时从内存重写 ⇒ 白改 | 战斗中**禁用**（§6.5.5-1） |
| **R3 坐标不是城市** | `set_destroyed_cities` 按坐标匹配当前图的 `cities` 类型，不匹配就**静默丢弃** | 本功能**只修清单里已有的坐标** ⇒ 它必然曾是城市（否则当初也不会进清单）⇒ 风险被范围收敛消掉 |
| **R4 清单有重复坐标** | 「重打上一场」后再摧毁一次会 append 第二次 | ① 删**所有**出现 |
| **R5 误伤要塞** | 把「城市没被摧毁、但要塞被单独打掉」的格子也复活 | ③ 只改**同格**且**该场景 `cities.yml` 里确实有这座城市**的那一条 |
| **R6 游戏内回退覆盖** | 「重置会议」用检查点整表替换根 `main.yml` | 不写检查点；界面提示用本工具的『撤销』 |

#### 6.5.7 删空之后怎么办

`cities.yml` 的某一条被删光 ⇒ 文件会变成空表。
游戏的 `save_yaml_check_empty` 的规矩是「空表不写文件」，而 `packing.py` 目前**没有删除 ZIP 条目的能力**。

⇒ **第一版：把整个文件内容替换成 `map: []`**。
这与「文件不存在」**完全等价**（字节码实证）：
`MapObjects._read_data_file`（L116-121）在文件不存在时返回 `schema(dict())` ⇒ `{'map': []}`；
文件存在但内容是 `map: []` 时 `load_yaml` 也得到 `{'map': []}`
⇒ 两种情况都让 `map_additional['cities'] = dict([]) = {}`。

⚠️ **第一版不做「删掉整个 ZIP 条目」** —— 若实机验证发现 `map: []` 有问题，再上删除能力。

#### 6.5.8 界面（战役页新增「废墟」块）

战役页现在是**只读页**（§7 的写入总纲下，只读页不能有编辑入口）⇒ 加了这块之后，
那句「这一页是只读的」要改成「除『废墟修复』外，这一页是只读的」。

```text
┌ 废墟 ─────────────────────────────────────────────┐
│ ⚠ 最近变成废墟：坐标 (380, 208)                     │
│   影响场景：edelweiss、fall_blau_2                  │
│   ⚠ 这座废墟不在当前场景里（对当前战斗无影响）        │
│   [ 修复这一座 ]                                   │
│ ▸ 其它废墟（3 座）                                    │
└────────────────────────────────────────────────────┘
```

* 「影响场景」**用存档里 `games/*/cities.yml` 的实际内容算**（不是可玩区反查）。
* 「在不在当前场景」由界面判定：当前战斗场景（`in_state.scenario`）或当前会议的**可选场景**里有没有它 —— 核心库只给事实，不给结论。
* 「其它废墟」默认折叠，点开可点选任意一座修复（一次一座）。
* **不显示城市名**（游戏没给，见 §6.5.2）。
* 最新那座不在当前场景时：**仍然给按钮**，但标黄提示「对当前战斗无影响」（用户 2026-11-24 拍板）。
* **位置（U188）**：废墟块在**路线图块的正下方**（= 战役页第二行），**不在页面最底下**。
  用户 2026-11-25 原话：「目前修改废墟功能埋在战役最低下，太难发现了。
  把这个功能调整到战役第二行，也就是路线图下面」。
  ⚠️ 搬位置要**同时改两处**，少改一处就有一半界面没搬：
  ① `index.html` 的 `pageCampaign()` 里的 L2 模板；
  ② `i18n.json` `ui` 段里那份**整页模板**（英文界面渲染的是词表那份，不是源码那份）。
  ⚠️ `L2()` 按**占位符下标**替换（`{12}`）⇒ 搬 `{12}` **不用重排编号**；
  但**中英两版模板必须逐行对应** —— 换行位置不一致会让占位符错位。

#### 6.5.9 核心库接口

| 东西 | 位置 | 说明 |
|---|---|---|
| 只读清单 | `Save.ruined_cities()` → `list[RuinedCity]` | 每项含 `uv`（坐标）/ `scenarios`（影响哪些场景）/ `index`（第几座被摧毁）/`latest`（是不是最新那座）/ `occurrences`（清单里重复了几次）|
| 编辑 | `Edit.city_restore(uv, restore_forts=True)` | `kind = "city_restore"`；`uv` = 地图坐标 `(x, y)`；一次只修一座 |
| 写盘白名单 | 放开 `games/*/cities.yml` 与 `games/*/forts.yml` | §7.2 W9 的新例外（U184 同步） |

---

## 7. ⭐ 写入策略：只写 L1，其余各层一律只读

> **本节是整个修改器的写入总纲，也是唯一的写入授权清单。**
>
> **一句话：修改器只写存档根目录下的 5 个 YAML 文件
> + 当前战斗层的那一张 `main.yml`
> + 废墟快照那两张（`games/<场景>/cities.yml` 与 `games/<场景>/forts.yml`）；
> 其他一切（检查点、战斗实时层里的其它条目、回合历史、战役文档、游戏包）一律只读、绝不触碰。**
>
> ⚠️ **三个 L3 例外**：
> ① **战区资产**（`theater_assets`）与②**作战标记**（三个 id 列表，`unit_orders`）
> 写的是**同一张文件** —— **当前进行中战斗**的 `main.yml`；它们读档即生效、且不是战报
> （§6.2b、§6.2c、§7.2 W8）。
> ③ **废墟修复**（`city_restore`）写的是**另外两张** —— `games/<场景>/cities.yml`
> 与 `games/<场景>/forts.yml`（§6.5.3、§7.2 W9）。
> **除此之外，L3 里没有任何东西可写。**

### 7.1 存档有 5 个层，修改器只碰第 1 层（+ 三个 L3 例外）

| 层 | 位置 | 内容 | 游戏什么时候读 | 游戏内回退会撤销吗 | **修改器能不能写** |
|---|---|---|---|---|---|
| **L1 根状态** | `main.yml` `units.yml` `hqs.yml` `cards.yml` `store.yml`<br>（**最多 5 个**，实测 63 个存档全有，缺的按下表禁用） | 战役当前状态 | 每次读档 | ✅ **会**（被检查点整体替换） | ✅ **可写**（唯一的常规写入面） |
| **L2 检查点** | `last_conference/{cards,hqs,main,store,units}.yml`<br>`last_game/{cards,hqs,main,store,units}.yml` | 玩家可回退的基线 | 点「重置会议」/「重打上一场」 | ❌ 它自己就是回退源 | ❌ **只读** |
| **L3 战斗实时层** | `games/<场景>/{main.yml, ar_list.yml, units.yml(清单), enroute_units.yml, hqs.yml, …}`（独立场景是 `game/`） | 战斗当前状态 | 读档继续战斗 | ⚠️ 部分（回退到部署阶段会重写） | ❌ **只读**（⛔ **三个例外**：① 当前战斗 `main.yml` 的 `theater_assets` 与三个作战标记 id 列表（§7.2 W8）；② `games/<场景>/cities.yml` 与 `forts.yml`（废墟快照，§7.2 W9 / §6.5.3）） |
| **L4 回合边界历史** | `games/<场景>/archive/<快照>/*` | 每个 phase 边界的历史快照 | 回放 / 回退到部署阶段 | ❌ 不会 | ❌ **只读** |
| **L5 战役文档** | `document/`（= 对应战役包的副本） | 名册 `units.yml`、场景预设、战役常量 | **每次读档都会加载**（`Campaign.load`） | ❌ 不会 | ❌ **只读** |

另有 **L0 游戏包**（`<game>/_packages/base/data/campaigns/<campaign_id>.usc/`）：
只在**新建**战役时作为模板，**不要动**（它是共享文件，影响该战役的所有存档）。

**为什么 L3 也不写？** 战斗实时层由游戏自己维护（`ar_list.yml` 记回合动作顺序、`main.yml` 记回合数）。
而**战斗中的单位数据就在 L1 根 `units.yml`**（§3.4.3 铁证：战斗中参战单位的根表值与 archive 快照
逐字段完全一致）—— **改 L1 就等于改到了战斗里的单位**。
L3 里剩下的都是"回合流程状态"，改它们只会让存档内部不自洽，却不会让玩家看到任何好处。

> **⚠️ L5 是个容易被当成"只读副本"的陷阱** —— 它其实**是运行时活数据**，
> 游戏会往里写新造的单位。
> 所以"我们不写它"**不等于**"它没用"：**它必须被读取**
> （用于 §3.5 的重组预警判定），只是**绝不写入**。
> 实测：`west-Husky.usg` 的 `document/` 与游戏包 `west.usc` **850 个文件逐字节全同**；
> 而 `campaigns\Stalingrad.usg` 的 `document/` 是**另一个战役包**（**`stalingrad.usc`，dlc4**）的副本
> —— **对比时必须先看 `main.yml` 的 `campaign_id`**（实测该存档的 `campaign_id` 就是 `stalingrad`）。

### 7.2 写入规则（修改器必须遵守）

| 规则 | 内容 | 理由 |
|---|---|---|
| **W1** | **只写 L1**（根目录**最多** 5 个 YAML：`main.yml` `units.yml` `hqs.yml` `cards.yml` `store.yml`）。**文件不存在就禁用对应功能，绝不新建**（实测 7/70 个存档无 `cards.yml`、3/70 无 `store.yml`） | 唯一被授权的写入面。所有玩家想改的数据都在这里 |
| **W2** | **只读 L2**（检查点） | 检查点就是玩家的游戏内撤销基线。改它 = 把基线换成"修改后的状态"，玩家再也回不到原版（§7.4 R1） |
| **W3** | **只读 L3**（战斗实时层） | 回合流程状态由游戏维护；单位数据在 L1，改 L3 只会造成存档内部不自洽（§7.1） |
| **W4** | **只读 L4**（回合历史） | 它是回放/复盘的历史记录，改它等于伪造历史（§7.4 R5） |
| **W5** | **只读 L5**（战役文档） | 唯一**回退不掉**的层；写它等于给玩家留一个无法撤销的改动（§7.4 R6） |
| **W6** | **只读 L0**（游戏包） | 共享文件，会影响该战役的所有存档 |
| **W7** | **重打包时 L2/L3/L4/L5 必须字节级原样保留** | 唯一合法的例外是"重新打包"，不是"改内容"。内层 `archive` ZIP 要**整条目原样复制**（§11.4） |
| **W8** | ⛔ **两个 L3 例外（同一张文件）：当前进行中战斗的 `theater_assets`（战区资产）与作战标记三个 id 列表可写** | 只写 `games/<当前场景>/main.yml`（**独立场景是 `game/main.yml`**）的**这几个键**，其余键原样搬运。生效条件：当前战斗目录存在（`save.battle_dir()`；独立场景的 `in_state.scenario` 恒为 null，见 §3.4.5.1）。**历史战斗的快照一律不许写**（§6.2b、§6.2c） |
| **W9** | ⛔ **写盘白名单：只允许改根层那五张表 + 当前战斗层那张 `main.yml` + 废墟快照那两张** | 根层 = `main.yml` / `units.yml` / `hqs.yml` / `cards.yml` / `store.yml`；战斗层 = 当前战斗的 `main.yml`（战役 `games/<场景>/main.yml`、独立场景 `game/main.yml`）；废墟快照 = 存档里**真实存在**的 `games/<场景>/cities.yml` 与 `games/<场景>/forts.yml`（**U184 新增**，§6.5.3 —— 修复城市必须同时改这两张，否则留下**永久残留**）。`document/`、`last_conference/`、`last_game/`、`games/**` 的其它条目、历史战斗目录等**只读条目一律不许写** —— 白名单外的条目会让整批计划失败（`plan.py::ROOT_WRITABLE` / `RUIN_SNAPSHOT_RE` / `writable_entries`） |
| **W10** | ⛔ **`save_id` 边界：服务端只接受游戏数据目录之内的路径** | 边界 = **游戏数据目录**（`<本地应用数据>/.uoc2`）：`save/` 与 `modifier_imports/` 之内；出去的一律拒绝 —— 否则 HTTP 请求里塞个绝对路径就能读/复制任意文件（`web/server.py::_save_id_checked`） |
| **W11** | ⛔ **YAML 解析失败 ⇒ 整批不许写盘** | 任一条目解析失败就记一条错误、**这一批一个字节都不写** —— 绝不把坏文件当成"空表"写回去（那会造出残缺存档）（`plan.py::Work.table` 的 `parse_errors`） |
| **W12** | ⛔ **写盘互斥 + 唯一临时文件名** | 同一个存档不许两个写盘同时进行：锁文件 `<存档名>.usg.lock`（不是 `*.usg`，游戏不会当存档）；临时文件 `<存档名>.usg.<pid>.<随机>.new`（`writer.py::_SaveLock` / `_temp_path_for`） |
| **W13** | ⛔ **按下标删除的编辑必须排在最后，同组按 index 降序** | 兵库删条目、商店下架删的是"列表第 N 项"；删了会让后面的下标整体前移 ⇒ 先改数量就会改错行（`plan.py::order_edits`） |

### 7.3 为什么"只写 L1"是安全的 —— 回退是**整表替换**

这是本策略成立的关键。`Campaign._load_revert_campaign_data(in_dir)`（`campaign.pyc:317`）：

```python
with read_serialization(self.location) as main_ser:
    serialization = main_ser.subdirectory(in_dir)                        # 320
    data = serialization.load_yaml('main.yml', validation_schema=campaign_schema(self.campaign_doc))  # 322
    self.__dict__.update(data)                                           # 323
    self.units = {}                                                      # 325  ← 清空
    self.hqs   = {}                                                      # 326  ← 清空
    self._load_campaign_objects(serialization)                           # 327  ← 用检查点的 units.yml/hqs.yml 重新装载
    if self.card_store is not None:
        self.card_store = [CardState.load_from_data(self, d, False) for d in self.card_store]   # 328-329
```

> **回退 = 用检查点的 `units.yml` / `hqs.yml` / `main.yml` 整体替换当前状态。**
>
> ⇒ 只写 L1 ⇒ 玩家点回退 ⇒ **完整回到修改前的状态**（干净的两态，不会有"半生效"）。
> ⇒ 反之，若**曾经**把改动同步进检查点 ⇒ 玩家点回退 ⇒ 回到"部分被改过的状态"（更糟，见 R2）
> —— 这正是旧建议被推翻的原因。

### 7.4 为什么不碰其余各层（六条风险）

| 风险 | 层 | 说明 |
|---|---|---|
| **R1 摧毁安全网** | L2 | 检查点是玩家唯一的游戏内撤销基线。改它 = 把基线替换成修改后的状态，玩家再点「重置会议」也回不到原始状态。这与"傻瓜式修改器"的理念相反 |
| **R2 混合态** | L2 | 检查点的单位集合**比根表少**（实测 conf3：根 138 / last_conference 102 / last_game 121）。按 id 匹配只能改交集 → 未同步的部分保持原值 → 回退后得到"一半新一半旧"的**非存档状态**，比不同步更糟 |
| **R3 手里的牌会丢** | L2 | 检查点的 `main.yml` 里有 `card_store`（上次会议发到手里的牌）。若整表覆盖 `main.yml`，会把 `card_store` 变成 `null` 或旧值 → 玩家点「重置会议」**丢失手里的牌** |
| **R4 无法预验** | L2 / L3 | 检查点与战斗层会被 `_load_campaign_objects` 整体重载，改动后的单位集合与名册不匹配时，游戏内部的一致性检查可能直接报错。修改器无法在写回前预知游戏会不会崩 |
| **R5 伪造历史** | L4 | `archive/<快照>/` 是每个回合边界的历史记录，改它等于伪造战报/复盘，并且会破坏"回退到部署阶段"所依赖的基准 |
| **R6 不可撤销的改动** | L5 | L5 **不在检查点里**（实测 100 个检查点，0 个含 `document/`），所以写 L5 的任何改动**游戏内回退不掉**。玩家改错了只能靠手动备份恢复 |

**L0（游戏包）**不在上表，因为它不是存档的一层，而是**跨存档共享**的：
改它会影响该战役的**所有**存档（不只是当前这个），所以同样只读。

> **结论**：写 L2/L3/L4/L5 的收益（"修改不被回退撤销" / "一次改到位"）远小于风险。
> **而且第一个收益本身就不是用户想要的** —— 用户想要的是"改过头了能反悔"，不是"改了就锁死"。

### 7.5 由此砍掉的功能 ⭐

因为**只写 L1**，那些"必须联动多层"的需求**直接不存在**。
修改器**明确不做**下面这些事（"跳到某会议"写在 §6.1，同样不做）：

| 不做的功能 | 为什么不做 | 引导玩家改什么 |
|---|---|---|
| **改单位编制 `type`** | 要真正生效必须同时改 L5 `document/units.yml`（§3.5.3），而 L5 回退不掉；玩家也分不清"编制"这个概念，改了还常被场景预设覆盖 | 改**战力（`act_st`）**与**特种兵（`specs`）**，视觉效果相同 |
| **新增单位** | 要同时写 L1 + L5（注册 id/type/name）+ L3（参战清单），涉及三层；新 id 还会被 §3.5 的重组逻辑改写 | **加强现有单位** |
| **新增单位类型 / 新增特种兵类型**（`create-type` / `create-spec`） | 要往**游戏包或 L5 名册**里注册新类型 —— 跨存档共享、**回退不掉**；而且玩家要的是"把这支部队变强"，不是"造一种新兵种" | 改 `act_st` / `specs` / `name_brief`（**同一个单位想叫什么都行**，§5.5） |
| **改登陆/空降单位的进场特种兵** | 唯一根治办法是改 L5 场景预设的 `prepositioned_assets.yml`（对账基准），同样回退不掉 | **在"战斗中"的存档里改**（§3.5.1：战斗中改不会被对账） |
| **里程碑 / 奖章** | ①多数玩家不关心 ②它会削弱成就感（里程碑是"打赢一场"的正反馈载体）③技术上"全局图鉴"那份在 Steam 统计里，改存档管不着，只能做一半 ⇒ 典型"改了却像没改" | **什么都不用改** —— 里程碑是游戏自动结算的，正常打就有（§6.1b） |
| **用 temp mod + 本地化做改名** | 要往 `%LOCALAPPDATA%\.uoc2\_packages\` 与游戏包两处写临时包，污染玩家环境、还要清理 | **直接写明文**到 `name_brief` / `name_full` —— 游戏自己就在写明文（§5.5，证据链 `e107`~`e109`） |
| **快速存读档**（原工具里的 AHK 热键方案） | 玩家已有"所见即所得 Mod"，它**直接透视未来结果**，频繁存读档是它的**下位替代**；而且频繁存读档会污染存档历史，让"到底改了什么"变得不可追溯 | **不做**。修改器只管"改"和"撤销"（§6.4），不管"存档节奏" |

> **为什么砍掉**：前几个功能都要动 L5 或 L3，**用户摸不着头脑**
> （"我的编制怎么没变？""我加的单位呢？"），而且产生的改动**游戏内无法撤销**；
> 里程碑则是**多数人不关心**、而且**削弱成就感**，做了只会让修改器变成"替你把成就也打了"的工具；
> 快速存读档则是**功能重复** —— 玩家已经有更强的替代品了。
>
> 傻瓜式修改器的第一原则是：**改了就一定看得见、错了一定能反悔。**
> 宁可功能少，也不要做出"改了却像没改"的界面。

### 7.6 落地建议

- **写回流程**：只改 L1 里**实际存在**的那些 YAML（最多 5 个）→ 校验 → 预览 diff →
  备份 `<存档名>_BACKUP.usg`（放 `<修改器目录>/bak/`）→ 重打包。
- **重打包时**：L2/L3/L4/L5 的条目**原样复制**；内层 `games/<场景>/archive` ZIP **整条目原样复制，不解压重压**（§11.4）。
- **战斗层的写回**是例外路径（两个功能共用同一张文件）：只替换 `games/<当前场景>/main.yml`
  （**独立场景是 `game/main.yml`**）里的 `theater_assets` 与三个作战标记 id 列表这几个键，
  该文件其余键原样搬运（§6.2b、§6.2c、§7.2 W8）。
- **每次写回后**，UI 提示一行（**按能力位分支，不要写成无条件承诺**）：
  - 有 `cp_conference` 或 `cp_game`：
    > 「修改已写入。游戏中点『重置会议』或『重打上一场』可撤销本次修改。」
  - 两者都没有（如战役开局 C0）：
    > 「修改已写入。该存档没有游戏内回退点，**无法在游戏里撤销** —— 请保留修改器生成的 `_BACKUP.usg`。」
  - 因为只写 L1，所以**只要存在回退点，那句话就成立**；不存在时必须说清楚。
  - ⚠️ **如果本次改动里包含战区资产**，上面那句话**不成立**（游戏内回退撤不掉它）——
    必须额外补一句：「战区资产无法通过游戏内回退撤销，可在此界面用『撤销』还原。」
  - ⚠️ **如果本次改动里包含废墟修复**，也要补一句 —— 游戏里的「重置会议 / 重打上一场」
    会用检查点覆盖战役清单 ⇒ 可能把这处修改回退：
    「要撤销这处修改，请用本工具的『撤销』。」
- **不提供**"同时写入回滚检查点"的开关 —— 旧版本有过这个建议，已作废（§7.4 R1–R6）。
- **备份与撤销**必须无条件生效，不做成可选项（§6.4）。

### 7.7 核心库与 GUI 的职责切分

| 层 | 负责 | 不负责 |
|---|---|---|
| **核心库**（`save_modifier_core`） | 解析容器、算能力位、校验、生成 plan、备份、撤销栈、写回与打包 | **不做任何界面**；**不接受 YAML 文本**；**不启动子进程** |
| **GUI**（静态查看器那一侧） | 下拉框、表格、diff 展示、能力位驱动的启用/禁用、用户确认 | **不直接碰存档文件**；不自己解析 YAML；不自己打包 |

- GUI 只通过 §0.2 的 **8 个函数**与核心库交互。
- 核心库**不依赖 GUI 框架**（不 import tkinter），以便**无界面地跑回归测试**（§11.5 的 SHA256 比对就是无界面的）。
- 核心库**不依赖游戏进程**，只依赖文件系统与（可选的）游戏包目录。

### 7.8 本轮新增的写盘安全护栏（2026-11-21）

除了 §7.2 的 W1–W8（**写入面**），这一轮又补了五条**必须照做**的护栏 ——
它们不改变"改什么"，只保证"改坏了不会毁存档、服务端不会越界"：

| 护栏 | 规则 | 为什么（代码依据） |
|---|---|---|
| **写盘白名单** | 只有根层那五张表 + 当前战斗层那张 `main.yml` 能被改写；白名单外的条目会让**整批计划失败** | 以前理论上能往存档里写**任意条目**（`document/`、`last_conference/`、`last_game/` …）—— 那些是**只读**层（`plan.py::ROOT_WRITABLE` / `writable_entries`） |
| **`save_id` 边界** | 服务端只接受**游戏数据目录**（`<本地应用数据>/.uoc2`）之内的路径（`save/` 与 `modifier_imports/`），出去的**一律拒绝** | `save_id` 来自 HTTP 请求 ⇒ 传绝对路径就能把任意文件当存档打开/复制（`web/server.py::_save_id_checked`） |
| **YAML 解析失败 ⇒ 整批不写** | 任一条目解析失败就记一条错误，**这一批一个字节都不写** | 原来把解析失败的条目当成"空表"再写回去 = 造出**残缺存档**（`plan.py::Work.table` 的 `parse_errors`） |
| **写盘互斥 + 唯一临时名** | 同一个存档不许两个写盘同时进行；临时文件名带进程号与随机串 | 服务端是多线程 ⇒ 连点两次"应用更改"就会撞车（`writer.py::_SaveLock` / `_temp_path_for`；锁文件 `<存档名>.usg.lock`） |
| **按下标删除排序** | 兵库删条目、商店下架这类"删第 N 项"的编辑**排在最后**，同组**按 index 降序** | 删了会让后面的下标整体前移 ⇒ 先改数量就会改错行（`plan.py::order_edits`） |

---

## 8. 写回规则（打包）

```python
# 解包（可选：只读时直接在 ZIP 里读，不必解包）
with zipfile.ZipFile(usg_path, "r") as zf:
    zf.extractall(work_dir)

# 改 YAML —— 序列化必须复刻游戏自己的规则（见 §8.1）

# 重新打包 —— 关键：保持游戏写入约定
with zipfile.ZipFile(usg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for name in original_entry_order:          # 用解包时的原始顺序
        zi = zipfile.ZipInfo(name, date_time=save_timestamp)   # 全部条目同一时间戳
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o600 << 16          # = 0x01800000，与游戏一致
        zi.create_system = 0
        zf.writestr(zi, data)
```

**必须遵守**
1. **不写目录条目**（游戏写的是纯文件条目）
2. **所有条目共用一个时间戳**
3. `external_attr = 0x01800000`、`create_system = 0`
4. **只重写改过的文件，其余条目用原始字节原样复制**（不要解包再压缩再打包全部——虽然实测无损，但原样复制更快更安全）
5. 解包时先清空工作目录（上次残留会被打包回去）

> 最低可行做法（朋友工具的做法）：全量解包 → 改 → 全量重打包。**实测 954/954 条目内容 SHA256 一致，`testzip()` 通过**。但推荐上面的"只重写改过的条目"方案。

**写回前必做**
- 备份：`<存档名>.usg` → `<存档名>_BACKUP.usg`（游戏自己也用这个命名，`main_screen/ctrl.pyc` 里有 `_BACKUP.usg`），
  放在 `<修改器目录>/bak/`（兜底 `<游戏数据目录>/bak/`），**绝不放在存档同目录**（§6.4.1）
- 校验：所有 YAML 能被 `yaml.safe_load` 解析；所有数值在 §5.2 范围内；
  所有**可写**的类型字段（`specs[].type`、`card_type`）在类型表里存在；
  `unit.type`（只读）也要能解析出 `max_st` / `max_spec`，解析不了就跳过该单位并记录

---

### 8.1 YAML 序列化：必须复刻游戏自己的规则 ⭐（字节码实证）

**只重写改过的条目**还不够 —— 改过的那**一个文件内部**，没改的行也不该被顺手改掉。
实测：用通用的 `yaml.safe_dump` 写回 `units.yml`，改一个 XP 会让 **780 行**产生 diff
（因为整个文件被重新格式化了一遍）。

游戏的规则在 `lib/tools/yaml_.pyc`（`tools/yaml_.py`）里，字节码还原如下：

```python
class _Dumper(yaml.CDumper):                    # ← 基于 C emitter
    def check_short_list(self, l):               # 1 <= len(l) < 5 且全是标量 ⇒ 流式
        s = 1 <= len(l) < 5 and all(isinstance(e, (int, float, str)) for e in l)
        return self.represent_sequence('tag:yaml.org,2002:seq', l, flow_style=s)
    def set_representer(self, l):                # set ⇒ sorted
        ...
    def str_representer(self, data):             # len > 100 ⇒ 块样式 '|'
        ...
    def float_representer(self, data):            # str(float(data))
        ...

_Dumper.add_representer(list,  _Dumper.check_short_list)
_Dumper.add_representer(str,   _Dumper.str_representer)
_Dumper.add_representer(float, _Dumper.float_representer)
_Dumper.add_representer(bool,  _Dumper.bool_representer)
_Dumper.add_representer(int,   _Dumper.int_representer)

yaml.dump(obj, Dumper=d, default_flow_style=False)   # ← 没传 allow_unicode！
```

**四个容易踩错的点**：

| 点 | 值 | 说明 |
|---|---|---|
| 短列表的门槛 | **1..4 个**（不是 1..5） | 5 个标量的列表在游戏里是**块样式** |
| `allow_unicode` | **False**（默认值） | 游戏**没传这个参数** ⇒ 中文写成 `"1\u7B2C\u82CF\u8054\u8B66\u536B\u961F"`（双引号 + 大写十六进制） |
| `default_flow_style` | **False** | 字典与长列表一律块样式 |
| 键序 | 保持文件原样 | 游戏自己写的文件本来就是字母序；手改过的文件不该被我们重排 ⇒ 用 `sort_keys=False` |

**实测收益**（70 个存档 / 337 个 L1 条目，解析 → 重新序列化 → 比对字节）：

| 序列化方式 | 字节一致 |
|---|---|
| 通用 `yaml.safe_dump`（`allow_unicode=True`） | **281 / 337** |
| 复刻游戏 dumper（`allow_unicode=False`） | **337 / 337** ✅ |

⇒ 改一个 XP，diff 里**只剩 XP 那一行**；其余 400 多行一个字节都不动。
这直接兑现了 §0.4 的铁律「写回时未改动的一切原样搬运」。

> ⚠️ 顺带修正一处旧说法：本节原先写的是「dump 时 `allow_unicode=True`」——
> 那是**推断**，不是实证。**字节码证明游戏用的是默认的 `False`**，
> 真实存档里 **含原始非 ASCII 字节的 L1 条目 0 个、含 `\uXXXX` 转义的 40 个**。

---

## 9. 参考目录（给 GUI 做下拉用的数据源）

全部来自 `<game>/_packages/base/data/entity_types/`（+ DLC 覆盖）：

| 目录 | 数量 | 关键字段 | 用途 |
|---|---|---|---|
| `unit_types/*.yml` | 627 | `faction, nationality, movement, attack, defense, armor, max_st, max_spec, equipment, name_brief` | 把单位的 `type` 翻译成 **`max_st` / `max_spec`**（只读展示 + 数值校验，§5.4） |
| `hq_types/*.yml` | 213 | `faction, nationality, max_cp, trucks, branches, init_levels, fp_max_steps` | 读 `template` → `max_cp` |
| `specialists/*.yml` | 375 | `faction, nationality, attack, defense, armor, artillery, flags`（flags: `at`106 `towed`104 `arty`102 `recon`38 `engineers`35 `special`32 `lci`20 `ski`2） | **特种兵下拉**（可写，必须校验） |
| `cards/*.yml` | 39 | `cost, faction, has_unit, meta_type, recoup, persistent, title, subtitle` | **卡牌下拉**（可写，必须校验） |

**卡牌费用表**（39 种，节选高频）：
`long_range_recon_* 10 | power_hq_axis 20 | sabotage_* 20-30 | store_* 20 | truck_* 25 | air_supply_* 30 | arty_prep_soviet 30 | espionage_* 30 | air_attack_* 40 | flying_artillery_axis 40 | saturation_strike_allies 40 | naval_bombardment_* 45 | air_hq_axis 50 | tactical_naval_assault_uk/us 50 | air_fleet_axis 60 | precision_bombing_axis 75 | tactical_para_* 75 | divisional_para_allies_* 120`

**卡牌元类型**（决定卡牌作用，GUI 分组用）：
`long_range_recon, divisional_para, power_hq, sabotage, store, truck, air_supply, arty_prep, espionage, air_attack, flying_artillery, saturation_strike, naval_bombardment, air_hq, tactical_naval_assault, air_fleet, precision_bombing, tactical_para`

**本地化**：`entity_types` 里的 `name_brief` 是 id（如 `id_us_inf_42_brief`），显示中文要查
`<game>/_packages/base/localization/chi/strings.yml`（+ 同目录 `ui.yml`）。
**多个包同名键时，后加载的包覆盖先加载的**；按包名自然序加载（`dlc2` 先于 `dlc10`）。

### 9.1 场景预设 / 商店默认清单 / 静态整理数据 —— 数据源怎么分层

> **这一节的结论来自实测（脚本 `e74_bench.py` / `e75_mod.py` / `e76b_paths.py` / `e77_datadirs.py`），
> 实现者不要凭感觉设计这一层。**

#### 9.1.0 先看事实：慢的不是 I/O，是 YAML 解析

> ⭐ **2026-11-17 补充实测：换成 libyaml 的 C 解析器（`yaml.CSafeLoader`）快 6.6 倍。**
> 上表的耗时都是**纯 Python 的 `SafeLoader`** 测出来的。换成 `CSafeLoader` 之后：
> 解析一个存档的 `view()` 从 **357 ms → 54 ms**；627 个 `unit_types` 全量解析 **1072 ms → 94 ms**。
> ⇒ **实现时务必用 `CSafeLoader`**（前提是随包分发的 PyYAML 带 `_yaml` C 扩展）。
> ⚠️ **写回仍必须用纯 Python 的 `safe_dump`** —— C 版 `CSafeDumper` 的输出格式与纯 Python 版**不一样**。

| 操作 | 实测耗时 |
|---|---|
| **只 listdir**（`entity_types/`，1573 个文件，不解析） | **1.5 ms** |
| 解析一个存档（解 ZIP + 解析根 + `document/*.yml`） | 413 ms |
| 解析 `entity_types/specialists/`（375 个 yml） | 173 ms |
| 解析一个场景目录（11 个 yml） | 56 ms |
| 解析 `entity_types/` **全量**（1568 个 yml） | **1072 ms** |
| 解析整个战役包（`west.usc` 710 个 yml） | **2751 ms** |
| 解析整个战役包（`stalingrad.usc` 379 个 yml） | 2099 ms |
| 解析整个战役包（`moscow.usc` 230 个 yml） | 982 ms |
| 解析 `localization/chi/`（只有 2 个 yml，但极大） | **893 ms** |

**⚠️ 「每次启动全量遍历游戏文档」的代价（`e80_traverse.py` 实测）**

规模：全游戏包 **14372 个 yml / 18.9 MB**（`data/maps` 8076 / `data/campaigns` 4570 / `data/entity_types` 1573 / `data/scenarios` 153 / 本地化 46）。

| 做法 | 实测耗时 | 结论 |
|---|---|---|
| **全量 YAML 解析全部 14418 个 yml** | **36 096 ms（36 秒）** | 🚫 **绝对不能放进启动流程** |
| 同上，但排除 `data/maps/`（8076 个，修改器根本不需要） | ≈ **16 秒** | 🚫 仍然太慢 |
| **只解析 `specialists/`（375 个）= "更新特种兵库"** | **153 ms** | ⚠️ 可接受 |
| **只 stat 375 个特种兵文件**（mtime+size，不解析） | **1.4 ms** | ✅ 几乎免费 |
| stat + 全文 SHA256（375 个） | 28.8 ms | ✅ 更保险 |
| `os.walk` 全部（40353 个文件，只列目录） | 100 ms | ✅ |
| **stat 全部 14418 个 yml**（不解析） | **54 ms** | ✅ |
| **增量：stat 全部 + 只解析"变了"的文件** | **52 ms** | ✅ **推荐方案** |
| 全树 (path,mtime,size) 指纹 | 312 ms | ✅ 一次性判断"有没有任何变化" |
| **读预编译 JSON 再 `json.loads`（内置基线加载）** | **0.6 ms** | ✅ **最快** |
| 读预编译 pickle 再 `loads` | 0.5 ms | ✅ |

⇒ **「检查更新」和「执行更新」必须分开**：
**检查** = stat/mtime 比对（1.4 ~ 54 ms）；**执行** = 只解析变了的文件（没变就是 0）。
**不要每次启动都重新解析** —— 那就是 36 秒。

> **首次运行没有快照**，必须全量解析一次（36 秒）⇒ 首次运行要**放后台线程 + 进度条**，或改为"按需解析"（用户打开哪个类型才解析哪个）。
> ⚠️ 上表是**本机、OS 文件缓存已热**的数字；冷缓存会增加 I/O，但主导项是 CPU 上的 YAML 解析，结论不变。

⇒ **"每次启动全量读一遍游戏包"确实是坏设计（约 3~4 秒）**，
但 **"完全不读游戏包"同样是坏设计**（见 §9.1.2 的三条事实）。
真正的解法是**分层 + 懒加载 + 增量**，不是二选一。

#### 9.1.1 三条决定架构的事实

1. **`data/entity_types/` 只有 `base` 包有** —— 实测 11 个游戏包里**只有 base** 带 `data/entity_types/`
   （dlc1..dlc10 的 `data/` 里只有 `campaigns` / `scenarios`）。
   ⇒ **原版游戏里类型表（627 单位 + 375 特种兵 + 39 卡牌 + 213 总部 + 304 将领 + 10 换皮 = 1568 个 yml）永不变化**。
   ⇒ **类型表完全适合做成随修改器内置的静态快照**（内置一次，永远命中）。
2. **游戏会从两个位置加载包，用户包优先** —— 直接问游戏自己的 `uoc2.paths._Paths`（实测）：

   ```python
   paths.all_package_dirs()
   # ['C:\\Users\\misprit\\AppData\\Local\\.uoc2\\_packages',      ← 用户包（mod）在前
   #  'D:\\SteamLibrary\\steamapps\\common\\Unity of Command 2\\_packages']  ← 游戏包在后
   paths.all_non_game_package_dirs()   # ['C:\\...\\.uoc2\\_packages']
   paths.get_editable_packages()       # {'fall_blau_2'}   ← 本机实测存在的 mod
   paths.get_non_editable_packages()   # {'base','dlc1'..'dlc10'}  ← 只含玩家有 Steam 授权的
   ```

   ⇒ mod 装在 `%LOCALAPPDATA%\.uoc2\_packages\<mod名>/data/…`，**游戏会自动加载它**。
   ⇒ 修改器若只扫游戏包目录，**mod 新增的特种兵/场景就会漏掉**。
3. **包内 `data/` 有三个并列子目录**（字节码 `paths.pyc` 里的 `'entity_types'` / `'campaigns'` / `'scenarios'`）：

   ```
   <包>/data/entity_types/{unit_types,hq_types,specialists,cards,generals,card_reskins}/
   <包>/data/campaigns/<campaign_id>.usc/      ← 战役包（scenarios/ fronts/ conferences/ cinematics/ …）
   <包>/data/scenarios/<name>.usc/             ← 独立场景包（结构同战役包）
   ```

   实测独立场景包共 **11 个**：base 9 个（`kasserine_axis` `nordwind` `tutorial_5` `tutorial_6` `tutorial_7`
   `tutorial_8` `tutorial_91` `tutorial_92` `wacht_am_rhein`）、dlc4 `seydlitz`、dlc6 `compass`。
   ⇒ **定位场景预设时必须同时扫 `data/campaigns/*/scenarios/<id>/` 和 `data/scenarios/*/scenarios/<id>/`**
   （`unthinkable` 在 `west.usc` 里，而 `seydlitz` 在 `dlc4/data/scenarios/seydlitz.usc/` 里）。
   ⇒ 用户 mod 包（本机 `fall_blau_2`）用的正是 `data/scenarios/fall_blau_2.usc/`。

#### 9.1.2 推荐架构：内置静态基线 + 增量覆盖 + 用户主动刷新

```
┌─ 层 A：随修改器内置的静态基线（随发布打包，0 启动成本）
│    entity_types 的 1568 个类型（单位/总部/特种兵/卡牌/将领/换皮）+ 本地化字符串
│    —— 因为事实①：原版游戏的类型表永不变化
│
├─ 层 B：运行时增量覆盖（只在需要时读，读多少算多少）
│    ① 打开存档时读存档自带的 document/（权威，永远对得上）—— 战役存档自带全部场景预设
│    ② 名册 document/units.yml 里出现、内置表没有的 type → 只去 entity_types/unit_types/ 找那一个文件
│    ③ 独立场景存档 → 只读那一个场景目录（实测 56 ms）
│    ④ mod 包：按 all_package_dirs() 的顺序扫（用户包优先），发现内置表没有的类型就补进来
│
└─ 层 C：用户主动刷新（一次性全量扫描，写回本地 overlay）
     「重新扫描游戏包」按钮 → 全量扫两个包目录 → 写进 %LOCALAPPDATA%\<修改器>\overlay.json
     下次启动直接用 overlay，不用再扫
     ⚠️ 全量重扫 ≈ 36 秒（§9.1.0）⇒ 必须放后台线程 + 进度条，不能卡 UI
```

**启动流程（把上面的成本落到实际时序上）**

| 阶段 | 主线程耗时 | 说明 |
|---|---|---|
| 加载内置基线（预编译 JSON/pickle） | **0.6 ms** | 直接可用 |
| 变更检测（stat 全部 14418 个 yml，比对快照） | **54 ms** | 只 stat，**不解析** |
| 只解析"变了"的文件 | **0 ~ N ms** | 没变化就是 0 |
| 打开存档（解 ZIP + 解析根 yml） | 400 ~ 900 ms | 躲不掉，但**只在用户选存档时**发生 |
| **启动总增量** | **≈ 55 ms** | 🚫 而不是 36 秒 |

⚠️ **首次运行没有快照** ⇒ 要么放后台线程做一次全量（36 秒，带进度条），要么改"按需解析"（用户点开哪类才解析哪类）。

**这套架构同时满足三个诉求**：

| 诉求 | 怎么满足 |
|---|---|
| **启动快** | 层 A 直接用（0.6 ms）；层 B 是增量（只 stat 不解析，实测 52~54 ms） |
| **新 DLC 可见** | 层 B③ + 层 C：DLC 带来的是**战役/场景数据**（本来就从存档 `document/` 或游戏包按需读），不是类型表 |
| **mod 作者新增的特种兵可见** | 层 B④ + 层 C：扫到用户包里的 `data/entity_types/specialists/*.yml` 自动补进候选列表 |

#### 9.1.3 ⚠️ 一条不可让步的原则：静态表只做**候选**，绝不做**白名单**

**内置表 / overlay 过期时，绝不能把玩家锁死。**

- 下拉框里没有某个特种兵 ⇒ **允许玩家手输 type id**（并提示"未在数据表中，请确认 id 正确"）；
- 校验 `max_spec` 时，表里查不到 ⇒ **只提示、不拦截**（仍然写入，让游戏自己判）；
- 存档里出现一个表里没有的 `type` ⇒ **照常显示**（用 `type` 原文 + 未知标记），**不要抛异常**。

理由：静态表是快照，会过期（游戏更新、新 DLC、mod）。
如果它成了白名单，过期一次玩家就**完全无法修改对应的单位** —— 这正是本项目最忌讳的
**「改了却像没改」/「界面禁用得莫名其妙」**。
**表驱动的是"方便"，不是"能不能"。**

#### 9.1.4 各数据的权威来源与取数顺序

| 数据 | 权威来源（优先级从高到低） | 实测位置与口径 |
|---|---|---|
| **单位/总部 `type` → `max_st`/`max_spec`** | ① 存档 `document/units.yml`（名册，含 `type`）→ ② 内置 `entity_types/unit_types/` → ③ 游戏包 `entity_types/unit_types/` | 名册条目只有 4 个键（`id`/`type`/`name_brief`/`name_full`，见 `CampaignUnit.__init__`）；`max_st` 在类型库里 |
| **场景默认兵力配置** | ① 战役存档 `document/scenarios/<场景>/units.yml`（**存档自带**）→ ② 游戏包 `data/campaigns/*/scenarios/<场景>/units.yml` → ③ 游戏包 `data/scenarios/*/scenarios/<场景>/units.yml` | 场景目录固定 12~16 个文件：`ai_hints.yml` `hqs.yml` `locale.yml` `main.yml` `objectives.yml` `own.npz` `playable.npz` `supply_hubs.yml` `supply_sources.yml` `units.yml` + 可选 `bridges.yml` `enroute_units.yml` `prepositioned_assets.yml` `stragglers.yml` `forts.yml` `variants/` |
| **商店默认清单** | ① 游戏包/存档 `…/fronts/<战线>/conferences/<会议>.yml` 的 `store` → ② 存档根 `store.yml`（运行时态，L1 可写） | 详见 §4.6.1。⚠️ **不在场景目录里**，也**不在 `document/conferences/<会议>.yml` 里** |
| **兜底价格** | 存档 `document/fallback_prices.yml` | `{armored_step, infantry_step, infantry_step_by_type, specs:{...}}`；战役 **33/67** 有、独立场景 3/3 有 |
| **战役常量** | 存档 `document/main.yml` | `prestige`/`score`/`milestones`/`persistent_hqs`/`hq_renames`/`card_type_units`/`branching_token_char` |
| **卡牌类型 / 特种兵类型 / 卡牌费用** | ① 内置静态表（层 A）→ ② 游戏包 `entity_types/`（层 B） | 39 种卡牌 / 375 种特种兵；卡牌费用见 §9 |

⚠️ **独立场景存档拿不到第 2、3 行**（它的 `document/` 没有 `scenarios/`、没有 `fronts/`），
只能回退到游戏安装目录；游戏没装或 DLC 没买 ⇒ **该数据源不可用，GUI 必须显示"不可用"而不是空白或猜测值**。

#### 9.1.5 mod 覆盖（override）的正确读法 ⭐

> **实测依据**：`e82_modsave.py`（三方比对）、`e83_patch.py`（`.patch.yml` / `addable` 机制）、
> `e84_tri.py`（包优先级）、`e85_chain.py`（读写链路字节码）。

**① 存档里已经是 mod 生效后的数据 —— 修改器不用去追 mod**

游戏的链路（字节码实证）：

```
新建存档：CampaignDoc 从「包」加载场景与名册（按包优先级取，见 ③）
              ↓  mod 覆盖在这里生效
保存：CampaignDoc._save → save_yaml / save_yaml_check_empty 写进存档的 document/
              ↓  ← 存档里从此就是 mod 版本
读档：Campaign.load → read_serialization(...).subdirectory('document')
              ↓  ← ★ 直接读存档里的 document/，不再回查包
```

`CampaignDoc._load` 读的字符串常量 = `main.yml` `fallback_prices.yml` `medals.yml` `locale.yml`
`restart_scenario.yml` `units.yml` `hqs.yml` `scenarios`；
`CampaignDoc._save` 写的 = `restart_scenario.yml` `fronts` `scenarios`；
`CampaignDoc.scenario_serialization` 的常量 = `scenarios` `variants`。

**实证**：存档的 `document/units.yml` 会**随战役推进变长**（§3.3，实测 5 个战役 0~27 个新增单位），
这证明 `document/` 是**运行时快照**而不是包目录的拷贝。
⇒ **存档自带的就是 mod 生效后的版本**；玩家事后升级/卸载 mod，**不影响已有存档**（游戏自己也不回查包）。

⇒ **修改器只读存档，就能正确反映 mod 的场景/名册改动 —— 零额外成本。**

**② 唯一还要读包的地方：`entity_types/`（它不在存档里）**

mod 对 `entity_types/` 的影响有两种，都必须从**用户包**读：

| mod 行为 | 修改器怎么取 |
|---|---|
| **新增**特种兵类型（用户包里多一个 `data/entity_types/specialists/xxx.yml`） | 扫用户包 → 发现新文件 → 加进候选列表 |
| **覆盖**已有特种兵定义（用户包里同名文件，改了 `max_st` / `flags` / `name_brief`） | ⚠️ **必须取用户包那份**，不能取 base —— 否则显示的上限/标签是原版的，**与游戏实际不符** |
| **新增**特种兵 **flag**（用户包 `flags:` 里出现没见过的名字） | **原样取、不做白名单**（`catalog.spec_type()` 只做 `tuple(str(f) for f in flags)`）⇒ **自动纳入**，不报错 |

**flag 的中文名**走 locale 键 `id_sheet_spec_flag_<flag>`
（`server._catalog_payload()`：`spec_flags.setdefault(_f, cn("id_sheet_spec_flag_" + _f, _f))`）——
**查不到就退回 flag 原文**（中文名的来源规则见《GUI设计规范.md》§5.7，绝不自己翻译）
⇒ mod 新增的 flag 自带 locale 键就有中文名，没有就显示原文，**两种都不报错**。

⚠️ **flag 名还要过游戏侧那道门**：`state/entity_types/specialist_types.pyc` 的模块级
`_specialists_flags`（`aa/at/engineers/no_retreat/recon/towed/arty/special/lci/ski`）
是游戏校验 `flags` 字段的硬白名单 ⇒ **只改包不改游戏代码，新 flag 会被游戏拒掉**；
**修改器这边照收不误**（它只认包里写了什么，§9.1.3「只做候选，绝不做白名单」）。

**⚠️ 这是一个真实的实现陷阱**：直接去 `<game>/_packages/base/data/entity_types/` 读，
在装了 mod 的机器上会拿到**错的值**。必须按「用户包 → 游戏包」顺序取，与游戏一致。

**③ 包的优先级（游戏自己的实现，实测）**

```python
paths.all_package_dirs()
# ['C:\\Users\\misprit\\AppData\\Local\\.uoc2\\_packages',       ← 用户包（mod）在前
#  'D:\\SteamLibrary\\steamapps\\common\\Unity of Command 2\\_packages']
paths.get_editable_packages()   # {'fall_blau_2'}  ← mod 列表
```

`_Paths._build_package_list`（字节码）先遍历 `all_non_game_package_dirs()`（= 用户包目录），
再遍历 `_game_packages`；`get_yml(path)` **遍历 `_packages` 取第一个存在的文件** ⇒ **用户包优先命中**。

**④ 还有两套覆盖机制存在但当前没人用**（实测磁盘：游戏包 0 个、用户包 0 个）

| 机制 | 位置 | 说明 |
|---|---|---|
| `.patch.yml` | 与目标文件同目录，`foo.yml` → `foo.patch.yml` | `get_yml` 找不到 `path` 时会去找 `os.path.splitext(path)[0] + '.patch.yml'` |
| `addable` 目录 | `<包>/data/addable/` | `cache_addables` 扫描它，构造 `_<资产名>` 形式的覆盖名（`addable_dir` 用 `'{package}_{asset_name}'` / `'{asset_name}'` 两种键） |

⇒ 这两套如果将来被 mod 用上，**修改器当前的两处扫描不会自动覆盖它们**：
`entity_types/` 扫描要按「同名覆盖 + `.patch.yml` + `addable/`」三种方式各找一遍（成本仍是毫秒级）。

**⑤ 成本**

| 动作 | 实测 |
|---|---|
| 扫用户包 + base 的 `entity_types/specialists/`（stat，不解析） | **1.4 ms** |
| 解析 `specialists/` 375 个（更新特种兵库） | **153 ms** |
| 增量（mtime+size 比对，只解析变化的） | ≈ **0 ms**（没变化时） |

⇒ **"mod 改了东西 ⇒ 更新一下"确实是一个极轻量的动作**（§9.1.0）。
⇒ 而且按 §9.1.3，**即使某个 type 在表里查不到，也只提示不拦截** ——
mod 新增的类型还没被扫到时，玩家仍然可以手输 id 完成修改。

#### 9.1.6 外部静态整理数据（"所有场景的静态表"）的定位

如果实现方手里已经有一份**离线整理**的静态数据（每个场景的默认兵力配置 / 商店出售的类型数量价格 / 全部特种兵数据），
它就是**层 A 的现成素材** —— 不用重新扫一遍游戏包去生成，直接转成内置基线即可。
但要记住三点：

| 能不能用 | 结论 | 理由 |
|---|---|---|
| 当**层 A 内置基线**？ | ✅ **推荐** | 它就是"静态基线"本身 |
| 当**权威源**、直接覆盖存档实际值？ | ❌ **不要** | 静态表是某次游戏版本的快照，会过期 —— 过期数据会导致"改了却像没改" |
| 当**校验器**（存档实际值 vs 静态默认值）？ | ✅ **推荐** | 用来判断"这个商店条目是原装的还是被玩家买过的"、"这个单位是不是场景初始单位" |

**静态表与存档的关系（实测）**：战役存档的 `document/` 就是整个战役包副本（§3.3，实测 2364/2365 条目字节级相同），
所以"静态表 = 战役包内容的人工整理" —— 两者**信息量等价**。
静态表的增量价值有三点：

1. **独立场景的兜底** —— 存档里确实没有 `document/scenarios/`；
2. **免去运行时解析游戏包** —— UI 启动即可用，不必扫描 `_packages/`（但游戏包读不到时要能优雅降级）；
3. **跨场景横向视角** —— 同一特种兵在哪些场景出场、同一单位类型在各战役的分布 —— 游戏包本身没这个视角。

**⚠️ 静态表最容易踩的三个坑**

| 坑 | 说明 |
|---|---|
| 把"商店默认清单"当成"存档当前商店" | 存档根 `store.yml` 是**运行时态**（玩家买空的条目已消失、`quantity` 已递减、**价格还可能与包默认不同**，§4.6.1）；默认清单在 `fronts/<战线>/conferences/<会议>.yml`。两者**不是一回事** |
| 把"场景默认兵力"当成"存档当前单位" | 存档根 `units.yml` 是**活着的单位表**（含 `xp`/`act_st`/`uv`…），场景预设只是**出场时的初始值**（§3.5） |
| 把静态表当成 `type` 的权威源 | `type` 的权威是**存档 `document/units.yml` 名册**（`get_doc_unit(id)`），静态表里没有 id 映射 |

---

## 10. 已知坑清单

1. **`games/<场景>/` vs `game/`**：战役是复数+场景层，独立场景是单数。代码必须都支持。
2. **单位的 `units.yml` 有两种格式**：`list[int]`（当前活动场景的 ID 清单，**15/706**）与 `list[dict]`（已结束战斗的完整对象，**691/706**）。**必须先判类型再解析**。
   （口径：**706** = `games/<场景>/units.yml` 的 703 个 + 3 个独立场景的 `game/units.yml`；其中 ID 清单 15 个、完整对象 691 个。
   另见 §3.4.3 的 **30** —— 那是把 `units.yml` + `hqs.yml` 一起数、跨战役与独立场景的口径。两个数不要混用。）
3. **根 `units.yml` 就是实时单位表** —— 战斗中的单位也在根表里。**不要**去 `games/<场景>/units.yml` 找战斗单位。
   ⚠️ 但根表**只装"已经登场过的单位"**（C0 时 0 条，随进度单调增长，战役通关后仍小于名册 785~1185 条）——
   **未来场景才出现的单位改不了**，UI 也不要把名册当可改列表展示（§3.4.3b）。
4. **战役开局（C0）没有根 `units.yml`** —— 改单位功能必须禁用，不能当异常处理。
5. **`document/units.yml` 是 `type` 的权威源，但修改器只读不写**（L5）。
   修改器不提供"新增单位"与"改编制"（§7.5）。
6. **不要往存档里加任何自定义字段**（PREVENT_EXTRA）。
7. **`xp` 上限 399**（游戏逻辑上限；schema 是 400 但会被 `_repair_data` 修回来），`entr` 上限 2，`supply` 上限 3。
8. **战力上限看 `max_st`，不是硬编码 6/7**。
9. **⚠️ 商店的 `price: 0` 是「免费商品」，不是「已售罄」** —— 实测 70 个存档里 `price: 0` 有 43 条，
   全是正常的免费条目。游戏**没有售罄标记**：库存买完就把**条目删掉**。
   实测 1659 条商店条目里 `quantity: 0` 的**一条都没有** —— 所以 **`quantity: 0` 是非法值**（§4.6、§6.3）。
10. **`last_conference/` / `last_game/` 会覆盖根级修改** —— 这是**预期行为**，是玩家的撤销基线。
    **不要去同步它们**（§7.4 的 R1–R6 风险）。
11. **`card_store`（当前会议）≠ `cards.yml`（持久库存）**。`card_store` 非空 ⇔ 玩家正停在会议界面已发牌。
12. **商店的顶层键必须匹配战线名**，而且**只写存档已有的键** —— 存档的键是游戏包 `fronts/` 的**子集**
    （= 当前已激活战线；实测 west 有 `{france,italy}` / `{italy}` 两种，blitzkrieg 有三种）。
    **不要凭空新建战线键**（§4.6、§6.3）。
13. **不要用 temp mod + 本地化做改名**——直接写明文。
14. **🚫 `uv`（单位坐标）不可改**（U94 已删除该字段，有护栏测试）—— 它是地图格坐标，
    写错会让存档**直接打不开**（游戏的 `uv_schema` 要求 `[int, int]`）。
15. `store.yml` / `cards.yml` 里 `nationality` 是国籍 id（`uk`/`us`/`german`/…），不是阵营。
16. `games/<场景>/` 目录**只增不删**——每打赢一场就多一个场景目录，这是正常的。
17. **区分"战斗中"与"部署阶段"不能看 `games/<场景>/main.yml` 的 `turn`** —— 部署阶段时它也已经是 1。只能看 archive 里有没有 `turn_NN_*` 快照。
18. **⚠️ 判断"在不在战斗中"要看战斗目录，不是只看 `in_state.scenario`** ——
    战役存档里 `in_state.front` 与 `in_state.scenario` 恒等，但**独立场景存档的 `in_state.scenario` 恒为 null**
    （场景名在 `standalone_scenario`）⇒ 独立场景的战斗层是 `game/`，判据是 `game/main.yml` 在不在
    （`container.py::battle_dir`）。
19. **不要**去"补写"任何 `campaign_units.yml`（根目录、`games/<场景>/` 或 `archive/` 里的）——
    它在读档路径上**不会被加载**（实测 `games/<场景>/campaign_units.yml` 在 70 个存档的所有场景目录里 0 次出现，且 `Game._load` 的
    序列化对象是 `games/<场景>/`），写它只污染历史、零收益（§3.4.4.5、§7.2 W4）。
20. **`document/scenarios/<场景>/units.yml` 里没有 `type`** —— 场景预设的类型是按 id 去
    `document/units.yml` 解析的。所以 `type` 在 UI 上只能**只读展示**（§5.4、§7.5）。
21. **`campaign_units.yml` 不是"参战单位名单"** —— 它是"还能被用到的战役单位"（行军 + 卡牌引用），
    会随卡牌打出而变短。别把它当成参战清单用（§3.4.4.5）。
22. **⚠️ `ar_list.yml`（行动列表）实时层与快照里都有**，但**进行中战斗的最后一个快照没有它**
    （快照拍在回合边界，行动列表还没写）。**别用"快照里有没有它"判断回合状态**（本项目踩过这个坑，§2.2 / §3.4.4.5）。
23. **⚠️ 战斗外改单位，部分字段会在开打时被游戏重算覆盖**（§3.5）。
    重组只在 `Game.new`（**玩家点「开始这场战斗」的那一刻**）时发生，读档不重算。
    ⚠️ 风险**不只是**登陆/空降 —— A 类的场景覆盖、`supply` 强制 3/0、`sup_st` 清零、`specs.active` 重置同时发生（§3.5.1b）。
    ✅ **但 `xp` / `act_st` / `specs` 列表 / 改名对 A 类单位是战斗外也生效的** ——
    所以"提前强化"不必一场一场地打，战役地图上直接改已在根表的单位即可（§3.4.3c）。
24. **⚠️ 登陆/空降/早期增援单位的特种兵会"按 type 对账"**：
    场景目标清单里没有的 spec 会被**从单位上剥离并退回总部兵库**；空降单位（`para_plane`）**旧 spec 全清**。
25. **⚠️ 补兵会扣 XP**：`deploy_calc_new_xp` = `max(100, xp - steps * cost)`（`unit.pyc:603`）。
    登陆单位被补兵后，战斗外调高的 XP 会被重算掉一部分。
26. **⚠️ 改 `type` 是做不成的功能** —— A 类单位（出现在场景 `units.yml` 里）进战斗时
    `type` 会被重置为 `document/units.yml[id].type`（§3.5.3）；要覆盖它就得写 L5，而 L5 回退不掉。
    **修改器因此不提供"改编制"功能**（§5.4、§7.5）。
27. **⚠️ 场景预设的变体会覆盖基础文件** —— 解析 `document/scenarios/<场景>/` 里的
    `units.yml` / `prepositioned_assets.yml` / `enroute_units.yml` 时，
    必须**变体优先（`variants/<in_state.variant>/`）、基础兜底**。
28. **`adjust_units_between_situations` 对独立场景直接 return**（第 150-152 行）——
    独立场景存档不受重组影响。
29. **⚠️ 存档里的 `document/` 不一定对应你以为的战役包** —— 必须先读根 `main.yml` 的 `campaign_id`
    再定位。实测 `campaigns\Stalingrad.usg` 的 `campaign_id` = `stalingrad`，其 `document/` 是
    **`stalingrad.usc`（dlc4）** 的副本（440/441 字节级相同），**不是 `barbarossa.usc`**（同名 8 个全不同）。
    读错包 = 预警判错、重组风险算错（§7.1、§12 `e49_pkgtree.py`）。
30. **⚠️ 只写 L1 + 当前战斗层那张 `main.yml`** —— L2/L3 的其余条目/L4/L5 全部只读
    （两个 L3 例外：战区资产、作战标记，§6.2b、§6.2c）。重打包时这些层的条目必须**字节级原样保留**，
    内层 `archive` ZIP 整条目原样复制（§7.2 W7–W13、§11.4）。
31. **⚠️ 别用"最后一个快照"抽样做存在性普查** —— 它恰好是最特殊的那一个
    （进行中战斗的最后快照没有 `ar_list.yml`）。本项目据此得出过错误结论（§2.2 / §3.4.4.5）。
32. **⚠️ 判 YAML 格式要用 `yaml.safe_load`，别看文本形态** —— 实测有 8 处
    `games/<场景>/hqs.yml` 是流式单行 `[2, 11, 12, 23]`，其余是块式 `- 12`（§3.4.3）。
33. **⚠️ 同一个场景在不同存档里 `units.yml` 的格式可能不同** —— 实测 9 个场景
    （`husky` / `monte_cassino` / `tunis` / `unthinkable` / `advance_on_antwerp` 等）
    在部分存档里是 `list[int]`、在另一些里是 `list[dict]`。**每个存档都要重新判类型**。
34. **⚠️ 独立场景存档没有商店、没有卡牌** —— 实测 3/3 的根目录只有 `main.yml`/`units.yml`/`hqs.yml`，
    **没有 `store.yml`、没有 `cards.yml`**（战役 67 个里 `store.yml` 67/67 有）。
    「卡牌」「商店」两块功能在独立场景上**必须整个禁用**（§3.2）。
35. **⚠️ `document/units.yml` ≠ 根 `units.yml`** —— 前者是**战役名册**（历史上出现过的全部单位），
    后者是**当前活着的单位表**。实测 12 个存档：**根表 ⊆ 名册**（恒成立），且同 id 的 `name_brief` 完全一致。
    名字的流向是「运行时对象 → 名册」（`Campaign._rename_hqs` 字节码），所以**改名只改根表就够**（§3.3）。
36. **⚠️ 商店的"买空"有两种表现** —— 通用装备（`equipment`）是 `quantity` **递减**、条目保留；
    特种兵（`spec`）是**整条消失**。`quantity` 归零 ⇒ 条目被移除，所以存档里永远看不到 `quantity: 0`（§4.6.1）。
37. **⚠️ 存档里的商店价格可能与游戏包默认清单不同** —— 实测 277 条（stalingrad `south` 战线有 3 条被上调）。
    原因未定位。⇒ **不要拿游戏包去"纠正"存档**，只改存档实际值（§4.6.1）。
38. **⚠️ `games/<场景>/main.yml` 里没有 `scenario` 字段** —— 实测 64/64 个存档的该文件都不含此键。
    场景名**只能从 `games/<场景>/` 的目录名**取（§3.2b）。
39. **⚠️ 场景 id 本身不唯一** —— `normandy_breakout` 在 `france.usc` 和 `west.usc` 里都有。
    必须用 `campaign_id`（不是场景名）来定位战役包（§3.2b）。
40. **⚠️ 独立场景的场景预设不在存档里** —— 存档 `document/` 没有 `scenarios/`。
    存档的 `game/` 是游戏重序列化过的运行时态（实测与包内文件 12/12 全不同，`units.yml` 是 ID 清单而非完整对象）。
    **别拿 `game/` 当场景预设用**（§3.2）。
41. **⚠️ 外部静态整理数据是缓存不是权威源** —— 它是某次游戏版本的快照，会过期。
    正确用法：① 独立场景兜底 ② 离线校验器 ③ 跨场景横向对比。
    **优先级永远是「存档 `document/` → 游戏包 → 静态表」**（§9.1.6）。
42. **⚠️ 别在启动时全量解析游戏包** —— 实测 `entity_types/` 全量 1072 ms、战役包整树 982~2751 ms、
    `localization/chi/` 单目录 893 ms。但 **listdir 只要 1.5 ms** ——
    **慢的是 YAML 解析，不是读文件**。⇒ 用「内置静态基线 + 增量读差集 + 用户主动刷新」（§9.1.2）。
43. **⚠️ `data/entity_types/` 只有 base 包有** —— 实测 11 个游戏包里只有 base 带它
    （dlc1..dlc10 的 `data/` 只有 `campaigns`/`scenarios`）。
    ⇒ **原版游戏的类型表永不变化**，适合做成内置静态快照；**新 DLC 带来的是战役/场景数据，不是新类型**。
44. **⚠️ 游戏从两个位置加载包，用户包优先** —— 实测 `paths.all_package_dirs()` =
    `['%LOCALAPPDATA%\.uoc2\_packages', '<game>\_packages']`。
    ⇒ 只扫游戏包目录**会漏掉 mod**（本机实测有 mod `fall_blau_2`）。
    ⇒ `get_editable_packages()` 返回的就是 mod 列表（实测 `{'fall_blau_2'}`）。
45. **⚠️ 场景预设在包里有两处位置** —— `data/campaigns/*/scenarios/<id>/` **和** `data/scenarios/*/scenarios/<id>/`。
    实测独立场景包 11 个（base 9 个、dlc4 `seydlitz`、dlc6 `compass`）。**两处都要扫**。
46. **⚠️ 静态表 / 内置表只做"候选"，绝不做"白名单"** —— 表里没有某个 type 时，
    **允许手输 id、只提示不拦截、照常显示存档里的未知 type**。
    否则内置表过期一次，玩家就完全改不了对应的单位 —— 这是"界面禁用得莫名其妙"的根源（§9.1.3）。
47. **⚠️ 读 `entity_types/` 必须按「用户包 → 游戏包」顺序取** —— 否则装了 mod 的机器上会拿到**原版的**特种兵定义，
    显示的上限/标签与游戏实际不符。存档里的 `document/` **已经是 mod 生效后的版本**（读档不回查包），不用追 mod（§9.1.5）。

48. **⚠️ 不要把商店条目的 `quantity` 设成 0** —— 它不是「售罄」，而是游戏从不产生的非法状态。
    下架商品请**删除条目**（§4.6、§6.3、第 9 条）。
49. **🚫 不要动 `milestones`** —— 里程碑功能**整个不做**（§0、§6.1b、§7.5）。
    技术原因（供理解，不必实现）：游戏里里程碑分两套 —— 战役内的列表与奖章读**存档根 `main.yml` 的 `milestones`**，
    而主菜单那个跨战役的**全局里程碑图鉴读 Steam UserStats 的 `ms_<campaign_id>_<milestone_id>`**，
    **不在任何本地文件里**。改存档只能管着前一半 ⇒ 做了必然"改了却像没改"（§6.1b）。
50. **⚠️ 写回根 `main.yml` 时 `milestones` 必须原样保留** —— 游戏 schema 是
    `Required('milestones', default=list())`：**丢掉这个键不会报错**，会被当成空列表，
    于是本局已达成的里程碑与战役奖章**静默消失**（直到玩家用「重置会议」回退 ——
    检查点 `last_conference/main.yml` 里也带 `milestones`）。
    同一条纪律适用于根表其余字段（`card_store` / `tokens` / `tokens_map` / `renamed_hqs` /
    `reverted_games` / `used_card_types_with_unit`）：**除非本次功能明确要改它，否则一律原样搬运**（§7.2 W2）。
51. **⚠️⚠️ 随包分发的 Python 运行时必须自带 PyYAML —— 现在这个包是跑不起来的**（实测）：
    现有 `uoc2-save-modifier` 的 `python/python314._pth` 里写着 `Lib\site-packages`，
    但 **`python/Lib/site-packages/` 目录根本不存在**，`python314.zip`（标准库）里也没有 yaml
    ⇒ `run.bat` 直接 `ModuleNotFoundError: No module named 'yaml'`。
    **打包时必须把 PyYAML 放进 `python/Lib/site-packages/`**：
    实测可用版本 = **PyYAML 6.0.3**（含 `_yaml.cp314-win_amd64.pyd`，ABI 与 CPython 3.14 一致）。
    ⚠️ 别用 `*.pyd` 通配去忽略文件 —— 那个 `.pyd` 正是必需的 C 扩展（§0.1、§11.4）。
52. **⚠️ "战区资产"和"总部兵库"是两个完全不同的东西** ——
    战区资产 = `games/<场景>/main.yml` 的 `theater_assets`（战场级的一次性额度）；
    总部兵库 = 根 `hqs.yml` 的 `force_pool[]`（每个 HQ 一份的存货存量）。
    **写错地方 ⇒ 改了却像没改**（§6.2b）。
53. **⚠️ 战区资产只有"当前进行中的战斗"里能改** —— `Game.new`（点「开始这场战斗」）会
    `ta.to_use = ta.uses_turn` 重置它；`Game._load` 与 `hard_set_state_on_ar_ord` 的 `copy_fields`
    含 `theater_assets` ⇒ **读档不重算**。所以战斗外改 = 白改（§6.2b、§7.2 W8）。
54. **⚠️ 改 HQ 兵库不会被任何重组重算** —— `_adjust_hqs_between_situations` / `agree_on_hq`
    **全程不碰 `force_pool`**（`'force_pool' in co_names` = False）；`_rename_hqs` 只改 id/将领/关联，
    内容整体继承。⇒ 兵库的 `quantity` 是安全的 L1 可写字段（§6.2b）。
55. **⚠️ 写回战区资产时不要整表替换 `games/<场景>/main.yml`** ——
    只替换 `theater_assets` 这一个键，其余键（`ar_ord` / `turn` / `scores` / …）原样搬运。
    整表替换会丢掉实时字段的当前值（§6.2b）。
56. **⚠️ 改名直接写明文，不要 temp mod** —— 游戏包原件 12061 条单位里就有 **24 条非 id 名**
    （`unit_53` 等），70 个存档的 84462 条单位条目里有 **746 条明文 `name_brief`**（去重 73 组，
    如 `'1第德国警卫队'`）⇒ **游戏自己就在写明文**，明文一定能正确显示（§5.5，证据 `e107`~`e109`）。
57. **⚠️ 游戏内的「重置会议」撤不掉战区资产** —— 会议回退走 `Campaign._load_revert_campaign_data`，
    整表替换根级 L1 文件，**不碰 `games/<场景>/main.yml`**。
    ⇒ 这正是**修改器必须自带撤销栈**的原因（§6.4）。
58. **⚠️ 撤销栈要落盘，且撤销前要校验基准** —— 否则关掉程序就撤不回来；
    而且玩家可能在游戏里回退过，撤销栈里的"改前值"已经过期 ⇒ 撤销前必须重新比对当前值，
    不符就**拒绝并提示**，不要硬改（§6.4.2）。
59. **⚠️ 备份不要覆盖同名备份** —— 写回前生成 `<存档名>_BACKUP.usg`，
    同名已存在时用带序号的后缀（`_BACKUP_2.usg`），
    否则第二次修改会把第一次的救命备份冲掉（§6.4.1）。
60. **⚠️ `force_pool` 的条目里 `spec` 与 `equipment` 是二选一** ——
    既不要同时写两个，也不要写第三个键（PREVENT_EXTRA，§5.1）。`delay` **在 GUI 里必须可填**
    （它是真实机制：延迟几回合才能部署），但必须是非负整数（§6.2b）。
61. **⚠️ `_packages/` 是「包容器」，不是「包」** ——
    游戏侧 `_packages/base` `_packages/dlc1` … `_packages/dlc10`，
    用户侧 `_packages/<mod名>/`；每个包的数据在 **`<包>/data/…`**。
    把容器当包去读 `data/entity_types/` ⇒ **一条类型都读不到**（实测：静默返回 0 条）。
62. **⚠️ `fronts` 是「每个战役包各有一份」，不是全局表** ——
    位置是 `<包>/data/campaigns/<战役>.usc/fronts/<战线>/`（实测 15 个战役包各有一份：
    west → france/italy，stalingrad → caucasus/south）。
    存档 `store.yml` 的顶层键必须是它的**子集**（当前已激活的战线），**不要凭空新建战线键**。
63. **✅ 打包验收口径是「条目内容逐条 SHA256 一致」，不是「整个文件字节一致」** ——
    实测：保真打包器产出的整个 `.usg` 与游戏自己写的**字节级一致 47/70**；
    其余 23 个差约 **0.2%**（游戏对部分条目用了不同压缩级别），但**条目内容 70/70 完全一致**。
    ⇒ 写回前后的比对**以条目内容为准**，文件级字节一致只是额外加分项。
64. **⚠️⚠️ 写回时用的 YAML 序列化器必须复刻游戏自己的，否则"没改的行"也会被改掉** ——
    游戏的规则在 `lib/tools/yaml_.pyc` 里：`yaml.dump(obj, Dumper=_Dumper, default_flow_style=False)`，
    `_Dumper` 基于 `yaml.CDumper` 且注册了 5 个自定义 representer
    （短列表 1..4 个标量 ⇒ 流式；str > 100 字符 ⇒ 块样式 `|`；float ⇒ `str(float(x))`）。
    ⚠️ 游戏**没传 `allow_unicode`** ⇒ 用的是默认的 **False** ⇒
    **中文写成 `"1\u7B2C\u82CF\u8054\u8B66\u536B\u961F"`**（双引号 + 大写十六进制）。
    实测：70 个存档的 L1 条目里**含原始非 ASCII 字节的 0 个、含 `\uXXXX` 转义的 40 个**。
    ⇒ 用通用 `safe_dump`（`allow_unicode=True`）写回，**56/337 个 L1 条目会被整体改写**；
    复刻游戏 dumper 后是 **337/337 字节一致**（§8.1）。
65. **⚠️ 短列表的门槛是「1..4 个」不是「1..5 个」** —— 5 个标量的列表在游戏里是**块样式**
    （`played_segments` / `milestones` 正好 5 个时就是块样式）。
    写成 `<= 5` 会让这 16 个条目往返不一致（§8.1）。
66. **⚠️ 撤销栈的基准是「改后内容的 SHA256」，不是「改前值」** ——
    撤销前要拿**当前存档**的内容算 SHA256 与记录比对；
    对不上说明玩家在游戏里动过 ⇒ **拒绝撤销并说明原因**，不硬改（§6.4.3）。
    ⚠️ 拒绝时**不能弹栈** —— 否则玩家永远撤不回来。
67. **⚠️ 规划之后存档被别人改过 ⇒ `commit` 要拒绝写入** ——
    玩家可能在游戏里手动改了同一个存档；按旧计划写下去会覆盖掉人家的改动（§6.4.3）。

---

## 11. 验收清单

实现完成后，逐条验证：

### 11.1 字段级
- [ ] 打开 `west-Conference3-1.usg`（副本），改根 `units.yml` 里某单位 `xp` 为 399 → 重打包 → 校验 954 条目内容除该文件外全部一致
- [ ] 改一个单位 `xp` 为 400 → **必须被拦截**（提示上限 399），而不是写进去让游戏崩溃
- [ ] 往单位里加一个 `foo` 字段 → **必须被拦截**
- [ ] 把 `specs[].type` 改成不存在的特种兵类型 → **必须被拦截**（必须在 `specialists/` 的 375 个里）
- [ ] UI 上 `type` 是**只读**的（灰显、不可点）—— 修改器不提供"改编制"（§5.4、§7.5）
- [ ] 给单位加第 4 个特种兵 → **必须被拦截**（上限 3，且受 `max_spec` 约束）
- [ ] 改 `name_brief` 为明文「我的部队」→ 存盘 → 游戏内读档 → 显示中文名，**且无需重启游戏**
- [ ] 改根 `prestige` → 读档 → 声望变化生效
- [ ] 往 `cards.yml` 加一张 `air_attack_allies` → 读档 → 战役界面卡牌数 +1
- [ ] 改 `store.yml` 某条目 `price` → 读档 → 商店价格生效
- [ ] 改完根 `main.yml` 的 `prestige` / `score` 后，**该文件的 `milestones`（以及 `tokens` / `tokens_map` /
      `renamed_hqs` / `reverted_games` / `used_card_types_with_unit` / `card_store`）与改前逐字节一致**
      —— 悄悄丢一个键比写非法值更难发现（§10 第 50 条）
- [ ] 改 `store.yml` 某条目 `price` 为 **0** → 读档 → 该商品显示为**免费**（**不是**下架）
- [ ] 把 `store.yml` 某条目 `quantity` 改成 **0** → **必须被拦截**（提示「游戏无售罄标记，请删除该条目」）
- [ ] 删除 `store.yml` 里某个条目 → 读档 → 该商品从商店列表里消失（下架的正确做法）
- [ ] 改完根级文件后，**在游戏里点「重置会议」再读档**，确认修改**消失**（验证 §7.2 W1/W2：
      回退 = 整表替换根级修改，这正是期望行为）
- [ ] 改完根级文件后，**读档继续战斗**，确认修改**仍在**（读档不重算，§3.5.1）
- [ ] 保存前自动生成 `<存档名>_BACKUP.usg`
- [ ] **第二次修改后，第一份 `_BACKUP.usg` 仍在**（没有被覆盖），第二份写成 `_BACKUP_2.usg`
- [ ] 生成的 `_BACKUP.usg` 与修改前的原文件**字节级一致**（SHA256 相同），不是"重新打包"的产物
- [ ] 改名走**明文**：改 `name_brief` 为明文 → 读档 → 显示中文名，**且不产生任何 temp mod 目录**
      （`%LOCALAPPDATA%\.uoc2\_packages\` 与游戏包 `_packages/` 都不该有新增/改动）
- [ ] **改 HQ 兵库**（根 `hqs.yml` 的 `force_pool[].quantity`）→ 读档 → 会议/商店界面看到新的存量
- [ ] **改战区资产**（当前战斗的 `games/<场景>/main.yml` 的 `theater_assets`）→ 读档 → 生效，
      且 `games/<场景>/main.yml` 的**其余键**（`ar_ord` / `turn` / `scores`）逐字节未变

### 11.2 状态机级（每个状态各测一遍）
- [ ] **战役开局·第一次会议** `west-Conference1-1.usg`：能打开；单位列表正确显示为"无单位（战役开局）"而不是崩溃；改声望/卡牌/商店有效
- [ ] **战斗中** `Stalingrad.usg`：单位列表读的是**根 `units.yml`**；改某参战单位的 xp → 读档 → **战斗内立刻生效**
- [ ] **部署阶段** `west-LastWar.usg`：状态显示"准备阶段"；改单位 xp → 读档 → 生效
- [ ] **战役地图·本段还有场景** `west-Conference2-2.usg`：状态显示正确；改单位生效
- [ ] **战役地图·本段场景已打完** `west-Conference2-1.usg`：状态显示"本段已完成，等待会议"；改单位生效
- [ ] **独立场景** `west_normandy_breakout.usg`：能打开能改能存；单位列表读根 `units.yml`
- [ ] **已结束战斗的单位**：`west-Conference3-1.usg` 的 `games/avalanche/units.yml` 是完整对象格式，能解析并**只读展示**（不可编辑，§7.2 W3）

### 11.2b 战斗态专项（§3.4.4 的回归测试，**最容易做漏的一组**）
- [ ] `west-Husky.usg`（T5 战斗中）：改**参战单位**（如 id 1）的 `xp` → 读档 → 战斗内该单位 xp 生效
- [ ] 同上：改完后确认 **只有根 `units.yml` 被写** —— `last_conference/`、`last_game/`、
      `games/`（含 `archive/`）、`document/` 里的文件**字节级未变**（§7.2 W2–W5，可用 SHA256 校验）
- [ ] 同上：读档后该单位的 `uv` 位置与改动前一致（**没被快照里的旧位置覆盖**）
- [ ] 同上：改一个**已阵亡**单位（id 136，Husky 快照里有、总表里已不在参战清单）的 `xp` → 不报错、
      不污染总表（它不在根表里就跳过）
- [ ] `Stalingrad.usg`：两个**行军单位**（id 20 / 95，同时出现在 `enroute_units.yml` 和
      `campaign_units.yml` 里）改 xp → 读档 → 生效（验证行军单位这条路径）
- [ ] `Stalingrad.usg`：`games/road_to_stalingrad/enroute_units.yml` **未被修改器改动**（它不是可改目标）
- [ ] 改动后重打包 → **archive 内层 ZIP 仍可正常打开**（`zipfile.ZipFile(BytesIO(zf.read("games/<场景>/archive")))` 不报错）
- [ ] 改 `west-Husky.usg` 的单位后，`games/husky/main.yml` 的 `ar_ord` 与 `ar_list.yml` **未被改动**

### 11.2c 重组机制专项（§3.5 的回归测试，**决定"改单位"功能是否真的有效**）
- [ ] **战斗中的存档**（`west-Husky.usg`，T5 战斗中）：改 id 1 的 `xp` / `name_brief` / `act_st` / `specs`
      → 读档 → **全部生效**（`Game._load` 不重算）
- [ ] **战斗外的存档**：拿一个"战役地图"状态的存档，改一个**场景初始单位**（A 类）的 `uv`（设成别的坐标）
      → 进战斗 → **预期** `uv` 被场景预设覆盖
      ⚠️ 这一条**尚未有实测支撑**（结论仅来自字节码 `game_adjust_data.pyc:20`，见 §3.5.10 第 5 条）——
      所以它的验收含义是"**如果实测不符，就说明 §3.5.10 第 5 条待补实测**"，而不是"必须被覆盖"
- [ ] 同上，UI 对该单位显示 `⚠️ 进战斗时会被重置` 徽标，并列出被覆盖的字段
- [ ] 同上，改 A 类单位的 `sup_st`（设成 3）→ 进战斗 → **`sup_st` 变 0、`act_st` 相应增加**
- [ ] 同上，把 A 类单位某个 spec 的 `active` 设成 `false` → 进战斗 → **该 spec 被重新激活**
- [ ] **登陆单位**（Husky 的 id 46，资产 5，`lci`，目标 6 步 / 3 个 spec）：
      - 根表 `act_st+sup_st` 应**等于 6**（实测 10/10 成立）
      - 改它的 `act_st` 到 2 → 进战斗 → **被补回 6**
      - 改它的 `act_st` 到 9 → 进战斗 → **保持 9**（只增不减）
      - 加一个场景目标里没有的 spec → 进战斗 → **该 spec 从单位上消失（退回总部兵库）**
- [ ] **空降单位**（Husky 的 id 146，资产 3，`para_plane`）：给它加任何 spec → 进战斗 → **specs 全空**
- [ ] **早期增援**（Husky 的 id 178，`on_turn=4`）→ 进战斗 → 走 lci 对账；
      同场景 `on_turn=5` 的单位（若存在）→ **不走** lci
- [ ] **无登陆资产的场景**（`Stalingrad.usg` 的 `road_to_stalingrad`，`has_ppas=False`）
      → 它的 2 个增援单位（id 20 / 95）**不走** lci 对账
- [ ] 修改器能自己算出"哪些单位会被重组"，且与上面的人工判定一致
- [ ] 重组预警文案列出的"会被重置字段"，与 §3.5.8 矩阵一致

### 11.3 覆盖盲区级（**本机样本里没有、但必然存在的状态**）
- [ ] **C1 中途会议界面**（`card_store` 有 5 张牌 + 有根 `units.yml` + 有 `last_conference/`、无 `last_game/`）：
  - 构造方法：拿 `west-Conference2-1.usg` 的副本，把根 `main.yml` 的 `card_store` 填成
    `last_conference/main.yml` 里那 5 张牌，`conference_start_state` 填 `{}`
  - 改单位 → 读档 → 生效
  - 改声望 → 读档 → 在游戏里点"重置会议" → **声望回到修改前的值**（修改被回退撤销，
    这是**预期行为**，正是玩家的安全网；验证 §7.2 W1/W2 + §7.3 的整表替换）
- [ ] **L 刚输掉一场**：把某存档根 `main.yml` 的 `in_state.lost_scenario` 设为某场景名 → 修改器能正常打开、不报错、不误判成战斗中
- [ ] **R 回滚后**：对 `last_game` 做过修改的存档，在游戏里点"重打上一场" → 修改**消失**
      （被回退撤销，预期行为；验证 §7.3 整表替换）
- [ ] **未知组合**：手工把 `card_store`、`last_game/`、`last_conference/` 组合成样本里没有的样子 → 修改器**不崩溃**、行为符合能力矩阵

### 11.4 格式兼容级
- [ ] `games/<场景>/units.yml` 两种格式都能解析：`list[int]`（ID 清单）与 `list[dict]`（完整对象）
- [ ] 解析 `list[int]` 时**不会**把它当成单位列表直接展示（要回根表取对象）
- [ ] 遍历全部 70 个真实存档，无解析异常
- [ ] **把能力矩阵的 8 个能力位对 70 个存档全部枚举一遍**，每种组合都能给出合理的编辑能力（可用/禁用），没有"未识别"分支
- [ ] **7 个没有 `cards.yml` 的存档**（3 个独立场景 + 4 个战役存档）与 **3 个没有 `store.yml` 的存档**
      → 对应功能**禁用且不崩溃**；写回后**没有新建**这些文件（§3.4.5.2、§7.2 W1）
- [ ] 内层 `games/<场景>/archive` ZIP：改外层 `.usg` 时**原样复制**这个条目，不要解压重压（内容必须逐字节一致）
- [ ] `games/<场景>/enroute_units.yml` 存在时能解析（键：`on_turn` / `positions` / `unit{…}`），但**不作为可改目标**
- [ ] **流式写法**：`games/road_to_stalingrad/hqs.yml`（内容 `[2, 11, 12, 23]`）能被正确解析成 ID 清单
      —— 用 `yaml.safe_load` 后判类型，不靠文本形态（§10 第 32 条）
- [ ] **同一场景不同存档格式不同**：`husky` 在不同存档里分别是 `list[int]` 与 `list[dict]`，
      修改器对两者都能正确处理（不缓存上一份的判断结果）

### 11.5 分层写入专项（§7 的回归测试，**决定"会不会把存档改坏"**）
- [ ] 对 `west-Husky.usg` 做任意修改后，把外层 ZIP 的**全部条目**逐个 SHA256 比对：
      **只有 L1 的目标文件变了，其余条目（含 `last_game/`、`document/`、历史战斗目录）字节级完全一致**
      （⚠️ **当前战斗层那张 `main.yml` 除外** —— 战区资产 / 作战标记就写在那里，§7.2 W8）
- [ ] 同上，但**内层** `games/<场景>/archive` ZIP 的每个成员也逐个 SHA256 一致
- [ ] 修改器代码里**不存在**任何写 `last_conference/` / `last_game/` / `document/` / 历史战斗目录的路径；
      写 `games/` **只允许写当前战斗层那张 `main.yml`**（战役 `games/<场景>/main.yml`、独立场景 `game/main.yml`），
      且只改 `theater_assets` 与三个作战标记 id 列表
      （可 grep 实现代码里的 `save_yaml` / `writestr` 调用点自查；白名单见 §7.2 W9）
- [ ] 规划一批会改到 `document/` 的编辑 ⇒ **整批报错、不产生任何改动**（写盘白名单，§7.2 W9）
- [ ] 把某个根表 YAML 故意写坏 ⇒ 那一批**整批不许写盘**（不是把坏文件当空表写回去，§7.2 W11）
- [ ] 连点两次"应用更改" ⇒ 第二次被锁挡住（`<存档名>.usg.lock`），存档不被写坏（§7.2 W12）
- [ ] 同一批里既改商店某条目的数量、又下架另一条 ⇒ 下架排在最后且**删的是指定那条**（§7.2 W13）
- [ ] 写回后外层 ZIP 的条目**数量与顺序**与原存档一致（游戏按名字查找，但保持一致更安全）
- [ ] 在游戏里点「重置会议」→ 根级修改**整体消失**（回到修改前），且**没有出现"一半新一半旧"的混合态**
      （把 `last_conference/units.yml` 单独打开比对，确认它仍是改前的值）
- [ ] **目标文件内部也没改的行也不变**：改一个 XP → 该文件的 diff 里**只有 XP 那一行**
      （不是整份文件被重新格式化 —— §8.1、§10 第 64 条）
- [ ] 把 70 个存档的 L1 条目（337 个）逐个"解析 → 重新序列化 → 比对字节" → **337/337 完全一致**

### 11.6 备份与撤销专项（§6.4）
- [ ] 改一次 → **`<修改器目录>/bak/`** 里出现 `<存档名>_BACKUP.usg`，且与改前的原文件 **SHA256 相同**
      （**存档目录里不得出现备份** —— 游戏只扫存档目录里的 `*.usg`，§6.4.1）
- [ ] 再改一次 → `_BACKUP.usg` **内容不变**（还是第一次改前的版本），新增 `_BACKUP_2.usg`
- [ ] 在修改器里点「撤销」→ 存档内容**精确回到这次修改前**（不是回到最初，是回到上一次提交前）
- [ ] 撤销栈**落盘**：关掉程序、重新打开 → 「撤销」仍可用
- [ ] 撤销栈是**按 commit 粒度**的：一次改了 3 个单位 → 一次撤销全回退
- [ ] **基准过期时拒绝撤销**：先改一次 → 在游戏里手动改同一个存档 → 回修改器点「撤销」
      → 修改器**检测到当前值与记录不符**，**拒绝执行并明确提示**，而不是硬改回去
- [ ] 撤销走的是**完整写回流程**（备份 → 校验 → 原子替换），与 `commit` 完全同一条代码路径
- [ ] 写回过程中途失败（模拟磁盘满 / 目标文件被占用）→ **原存档完好无损**，不留下半写坏的文件

### 11.7 兵库与战区资产专项（§6.2b）
- [ ] 改 HQ 兵库 `force_pool[].quantity` → 读档 → 生效；**进战斗后仍然生效**（不被重组清掉）
- [ ] 改 HQ 兵库后，`document/hqs.yml`（名册）**未被修改**
- [ ] 战斗**外**的存档：战区资产功能**禁用**，并给出提示"当前不在战斗中"
- [ ] 战斗**中**的存档：战区资产功能**可用**
- [ ] 改战区资产后，`games/<场景>/main.yml` 里**只有 `theater_assets` 这一个键变了**
      （其余键逐字节一致，`ar_ord` / `turn` / `scores` 全部原样）
- [ ] 改战区资产后，**`games/<场景>/archive/<快照>/main.yml` 未被修改**（历史战报不可写）
- [ ] 在游戏里点「重置会议」→ 战区资产**不消失**（游戏内回退撤不掉它），
      但修改器的「撤销」能撤掉 → 验证 §10 第 57 条
- [ ] `force_pool` 条目里同时写 `spec` 与 `equipment` → **必须被拦截**（§10 第 60 条）

### 11.8 废墟修复专项（§6.5）

- [x] 修复一座城市后：根 `main.yml` 的 `destroyed_cities` 里**没有**这个坐标
- [x] 同一次修复后，**所有** `games/<场景>/cities.yml`（原先含这个坐标的那些）里也**没有**它了
      —— 漏一个就是**永久残留**（清单已无 ⇒ 以后不再注入 ⇒ 那份快照再也清不掉，§6.5.6 R1）
- [x] 同格要塞的 `functional` 改回 `true`；**异格**要塞（城市没被摧毁、但要塞被单独打掉）**不动**
      （实测同格 28/28 全是 `false`，异格 271 条 `false` / 152 条 `true`，e168）
- [x] `restore_forts` 关掉时，要塞**一个字节都不动**
- [x] 清单里同一个坐标**出现两次**时，两次**都**被删掉
- [x] 删空之后 `cities.yml` 的内容是 `map: []`（与「文件不存在」等价，e167 字节码）
- [x] **战斗中**的存档：废墟修复**被拦截**，并说明「游戏会从内存重写、改了会被覆盖回去」
- [x] 坐标不在清单里 / 坐标形状不合法（负数、字符串、只有一个数）⇒ **必须被拦截**
- [x] 修复后，**除了** `main.yml` 与那几张 `cities.yml` / `forts.yml`，
      **其它条目逐字节不变**（含 `document/**`、`last_game/**`、`last_conference/**`、战斗层 `main.yml`）
- [x] 战役页显示**最新变成废墟的那一座**（坐标 + 影响场景）+「修复这一座」按钮
- [x] 其它废墟**默认折叠**，展开后每行一个「修复」按钮（一次一座）
- [x] 不在当前场景时**仍然给按钮**，并加黄色提示「对当前战斗无影响」
- [x] 界面改动的连带影响：前端 L2 模板变了 ⇒ **i18n `ui` 词表同步**（`test_ui_table_covers_every_l_call` 守着）
- [ ] 修复后**读档继续战斗**、**新开一场战斗** ⇒ 那座城市**显示为完好城市**（⛔ 这一条**只能实机验证**）

---

## 12. 证据与复现

本机实测脚本**随仓库分发**：`docs\证据脚本\`（181 个取证 / 校验脚本 + 4 个共用辅助模块 + README）。
原件仍在 `D:\MiniMax\_analysis\`；仓库里那份是**逐字节拷贝**，路径仍是本机绝对路径
（它们是"取证现场"，故意没改）。

| 脚本 | 作用 |
|---|---|
| `a1_structure.py` | `.usg` ZIP 顶层结构 |
| `a2_extract.py` | 解包 + 根 YAML |
| `a3b_schemas.py` | 单位/总部字段集 |
| `a5_binaries.py` | archive 二层 ZIP、npz 内容 |
| `a8_progress.py` | 16 档进度序列 diff |
| `a9_roundtrip.py` | ZIP 打包往返无损验证 |
| `b10_validate.py` | 加载游戏类型数据库 + max_st/max_spec 统计 |
| `b16_final.py` | 全存档字段字典（数据驱动） |
| `b17_flow.py` | 声望/分数流转 + 卡牌/特种兵目录 |
| `b18_final_details.py` | 战役常量、各层字段集 |
| `pyc.py` / `pyc_scan.py` | 从游戏 `.pyc` 提取 schema 字符串 |
| `c1_states.py` / `c2_classify.py` | 70 个存档的状态分类（§3.4.2 的判据来源） |
| `c3_fingerprints.py` | 各状态指纹交叉表（card_store / segment_finished / front / scenario） |
| `c4_bytecode.py` / `c6_transitions.py` | 游戏战役状态机 API（§3.4.1） |
| `c8_formats.py` | `units.yml`/`hqs.yml` 两种格式普查（30 vs 691） |
| `c9_live.py` | 证明"根表即实时战斗表"（逐字段比对） |
| `d1_combos.py` | 组合空间覆盖分析（笛卡尔积 + 未覆盖组合清单） |
| `d2_cardstore.py` | `card_store` / `conference_start_state` 的读写点 |
| `d3_reachable.py` | 从游戏 API + UI 反推可达状态 |
| `d4_final.py` | 战役完成态签名、`set_conference` 调用点 |
| `e1_battle_units.py` | 战斗中单位数据的三个位置（总表 / 参战清单 / 快照）逐字段比对 |
| `e2_campaign_units.py` | 参战单位来源拆分（场景预设 / 战役带入 / 行军） |
| `e3_layers.py` | 各层文件职责 + `enroute_units.yml` / `campaign_units.yml` 结构（§3.4.4.1） |
| `e4_fields.py` | 场景预设 / 行军单位 / `campaign_units.yml` 的**精确键集** |
| `e5_types.py` | `type` 的来源链、`document/units.yml` 与根表的关系、`games/<场景>/main.yml` 全文 |
| `e6_type.py` | `_load_campaign_objects` / `_save_campaign_units` / `load_repair_specs` 反汇编 |
| `e7_loading.py` | `Game._load` / `Game._save` 的调用图与引用清单 |
| `e8_gameload.py` | `Game._load` / `Game._save` / `Gamelike._load_entities` 完整反汇编 |
| `e9_paths.py` | `Gamelike._save_gamelike` / `Campaign._save_campaign_files` 反汇编（写入路径实证） |
| `e10_snapshot.py` | archive 快照文件清单 + `games/<场景>/main.yml` 与快照的差异对比 |
| `e11_cardunits.py` | `_get_unit_ids_that_can_be_used` 精确实现（`campaign_units.yml` 的真实语义） |
| `e12_enroute.py` | `enroute_units` 与 `campaign_units` 的 id 集合关系 |
| `e13_census.py` | 70 个存档里各关键路径的存在性普查 |
| `e14_adjust.py` | **复核 `game_adjust_data.pyc`**：四个关键函数完整反汇编（§3.5.3-3.5.5） |
| `e15_timing.py` | `adjust_units_between_situations` 的调用者（只有 `Game.new`）、`apply_recovery_*` 语义 |
| `e16_xp.py` | `deploy_calc_new_xp` / `take_steps_for_recovery` / `_take_force_for_kia`（§3.5.6） |
| `e17_consts.py` | `tot_st` 定位、`unit_exp_step_loss_*` 常量、存档里各场景的 `prepositioned_assets` 普查 |
| `e18_empirical.py` | **登陆/空降承载单位的根表值 vs 场景目标**（10/10 铁证，§3.5.7） |
| `e19_variant.py` | 变体覆盖检查 + **对照组**（非资产单位 1/25，§3.5.7） |
| `e20_revert.py` | `Game.new` 的唯一调用者、回滚路径是否重算（§3.5.1） |
| `e21_out.txt` | `adjust_units_between_situations` 完整反汇编（452 行） |
| `e22_fields.py` | A/B/C 三类 id 互不相交的实证 + type/uv/hq 覆盖对比 |
| `e23_schema.py` | `units_schema` 反汇编（场景单位 vs ID 清单两种 schema） |
| `e24_scenario_schema.py` | **`scenario_unit_schema` 导入**（10 字段，无 `type`） |
| `e25_scenload.py` | `Scenario._load` / `_set_unit_data`（场景单位如何拿数据） |
| `e26_out.txt` | `UnitState.__init__` / `Entity.__init__`（**type 来自 `get_doc_unit(id)`**） |
| `e27_doc.py` / `e27_out.txt` | `document/` 是运行时数据源还是包副本：`CampaignDoc` 加载链反汇编（§3.3、§7.1 的 L5） |
| `e28_out.txt` | `CampaignUnit.__init__` 反汇编（4 键：`id` / `type` / `name_brief` / `name_full`） |
| `e29_out.txt` | `campaign_ctrl.pyc` 调用点：`get_read_serialization` / `campaign_doc_dir_abs` / `list_conference_files`（证明 `document/` 每次读档都被加载） |
| `e30_out.txt` | `Campaign.__init__` 反汇编（`load_types` / `CampaignDoc` 初始化链） |
| `e31_live_doc.py` / `e31_out.txt` | **`document/` 是运行时活层**：存档 `document/` vs 战役包 `.usc` 逐字节比对（§7.1 的 L5 实测） |
| `e32_checkpoint.py` / `e32_out.txt` | **检查点普查**：70 存档 / 100 检查点，检查点只有 5 个文件、**0 个含 `document/`**（§7.1、§7.4） |
| `e33_out.txt` | **`_load_revert_campaign_data` 完整反汇编**（`campaign.pyc:317`）—— **回退 = 整表替换**（§7.3 的核心证据） |
| `e35_schema.py` / `e35_out.txt` | `campaign_units_schema` / `_id_unit_schema` / `doc_units_schema` 的 voluptuous 结构（§3.4.4.6 的 4 键） |
| `e36_docpkg.py` / `e36_out.txt` | 存档 `document/` 的初步比对（⚠️ 此脚本的结论**有一处是错的**，见 `e49_pkgtree.py`） |
| `v1_check.py` / `v1_check.txt` | 交付文档自检（表格列数 / 代码块闭合 / 章节引用） |
| `v2_check.py` / `v2_check.txt` | 交付文档自检 v2（追加坏字符扫描与标题层级） |
| `v3_patch.py` / `v4_patch.py` / `v5_patch.py` | 文档改写脚本（批量替换旧"同步"表述 / 重写 §6.2 写入清单表 / 补 §3.3 与 §4.1 §5.4 的 L5 规则） |
| `v6_check.py` / `v6_check.txt` | **交付文档终检**：表格列数 / 代码块闭合 / 坏字符 / 章节引用落点 / 关键锚点 / **旧策略残留扫描** / 顶层章节连续性 |
| `v7_patch.py` | 文档改写脚本（引用错位、旧标签 S0–S4、措辞与粗体的批量修正） |
| `e37_root.py` / `e37_root.txt` | **根级文件普查**（70 存档）：根目录**最多** 5 个 YAML（5 个:63 / 4 个:1 / 3 个:6）—— 支撑「L1 **最多** 5 个文件」 |
| `e38_arlist.py` / `e38_arlist.txt` | **`ar_list.yml` 全量普查**（12071 个快照目录）—— 推翻旧结论的关键证据（§2.2） |
| `e39_census.py` / `e39_census.txt` | 快照文件数分布（14~22）+ 快照内 22 种文件名 + 出现次数 |
| `e41_final.py` / `e41_final.txt` | **存档去重**（70 个 .usg → 68 个唯一）与去重后的格式普查 |
| `e42_raw.py` / `e42_raw.txt` | 未去重口径的格式普查（691/703、ID 清单 30 次） |
| `e43_bug.py` / `e43_out.txt` | **旧普查口径的复现**（说明"0/15"是怎么来的） |
| `e44_last.py` / `e44_last.txt` | 「字典序最后一个快照」与「时间上最后一个快照」的差异（口径陷阱的证据） |
| `e45_misc.py` / `e45_misc.txt` | **流式单行 YAML 写法普查**（8 处 `hqs.yml`）+ `forts.yml` 内容样例 |
| `e46_forts.py` / `e46_forts.txt` | `forts.yml`（地图要塞坐标）样例 |
| `e47_cu.py` / `e47_cu.txt` | 实时层 `campaign_units.yml` / `enroute_units.yml` 普查（前者 0 次、后者 97 次） |
| `e48_pkg.py` / `e48_pkg.txt` | 商店 `price` / `quantity` 普查（`price:0` 43 条、`quantity:0` **0** 条）与战役包清单 |
| `e49_pkgtree.py` / `e49_pkgtree.txt` | **存档 `document/` ↔ 15 个战役包的全量 SHA256 比对** —— 确认 Stalingrad 对应 `stalingrad.usc`（§3.3、§7.1） |
| `e50_store.py` / `e50_out.txt` | 扫描全部 `.pyc`，定位含 `store` / `quantity` / `price` 的模块 |
| `e51_store.py` / `e51_out.txt` | **`ForcePool.deploy_store` 反汇编**（`force_pool.pyc:711`）—— 按 `quantity` 部署、按 `price` 计价（§4.6） |
| `e52_store.py` / `e52_out.txt` | 商店 UI（`hq_ctrl.pyc`）与 `campaign_store_schema` —— UI **不过滤** `quantity == 0` |
| `e53_store.py` / `e53_out.txt` | `Game.store_deployable_to_unit` / `_to_hq` —— 条目筛选靠 `ForcePoolInfo`，**没有 sold-out 概念** |
| `e54_store.py` / `e54_out.txt` | `Campaign.conference_deploy_store` / `Conferences.get_store` —— 商店是纯数据，**没有移除空条目的专用路径** |
| `e55_ident.py` / `e55_out.txt` | **战役 / 场景识别普查**（70 存档）：`campaign_id` / `standalone_scenario` / `in_state.*` / `document/scenarios` 场景数（§3.2b） |
| `e56_standalone.py` / `e56_out.txt` | **独立场景存档的完整条目树**：`document/` 恰好 6 个条目、`game/` 15 个条目、`main.yml` 17 键 |
| `e57_equiv.py` / `e57_out.txt` | **存档 `document/` ↔ 游戏包 `.usc` 逐文件 SHA256**（5 战役）：只有 `units.yml` 会变（§3.3） |
| `e58_diff.py` / `e58_out.txt` | 上述差异的**定性**：YAML 格式重写 vs 语义差异；独立场景 `game/` 与包的逐文件比对 |
| `e59_store_src.py` / `e59_out.txt` | **会议默认商店的真正位置** `fronts/<战线>/conferences/<会议>.yml`；存档 vs 包 `units.yml` 的语义等价性 |
| `e60_units_diff.py` / `e60_out.txt` | **`document/units.yml` 名册随进度增长**的全量表（5 战役，存档 ⊇ 包，从不缺条目） |
| `e61b_rename.py` / `e61_out.txt` | 根表 ⊆ 名册（12/12 恒成立）；同名单位在两处的 `name_brief` 完全一致 |
| `e62_rename_bc.py` / `e62_out.txt` | `CampaignDoc._save_units_file` / `add_campaign_unit` / `Campaign._rename_hqs` 反汇编（**名字流向：运行时 → 名册**） |
| `e63_final.py` / `e63_out.txt` | `_load_campaign_objects` / `_save_campaign_files` 反汇编（**根 `units.yml` 是权威载入源**）+ 场景名可获取路径 |
| `e64_census.py` / `e64_out.txt` | **根级文件存在性普查**：战役 67 个 `store.yml` 67/67、`cards.yml` 63/67；独立场景 3 个 `store.yml`/`cards.yml` **0/3** |
| `e65_quick.py` | `in_state.conference`/`variant`/`segment`/`completed`/`level` 计数；`main.yml` 顶层恒 17 键 |
| `e66_store.py` / `e66_out.txt` | 5 个战役包会议文件的 `store` 统计（**条目只有两种形态**；`elite_store` 恒 `null`） |
| `e67_conf.py` / `e67_out.txt` | 存档根 `store.yml` 顶层键 = 包 `fronts/` 目录名；`document/conferences/*.yml` **不含商店** |
| `e68_soldout.py` / `e68_out.txt` | **"买空"机制三方比对**（包默认 / 存档根 / `last_conference`）—— 装备递减、特种兵整条消失（§4.6.1） |
| `e69_store_stat.py` / `e69_out.txt` | 全存档商店库存机制普查（974 相同 / 325 移除 / 173 递减 / 277 价格不同 / 214 存档独有） |
| `e70_price.py` / `e70_out.txt` | 同战役不同存档的价格向量对比（价格差异**不随存档状态变化**） |
| `e71_which.py` / `e71_out.txt` | 定位运行时商店价格的来源：caucasus 19/19 匹配包 `c_42_07.yml`，south 16/19（**原因未定位**） |
| `e72_noseg.py` | 无 `in_state.fronts[*].segment` 的 3 个战役存档 = 3 个战役开局（C0） |
| `e73_fronts.py` / `e73_out.txt` | 商店顶层键 vs 包 `fronts/`：**子集关系**（west 2 种、blitzkrieg 3 种） |
| `e74_bench.py` / `e74_out.txt` | **读取游戏包的实测耗时**（§9.1.0）：listdir 1.5ms / specialists 173ms / entity_types 全量 1072ms / 战役包整树 982~2751ms / localization/chi 893ms |
| `e75_mod.py` / `e75_out.txt` | **mod 目录实测**：`%LOCALAPPDATA%\.uoc2\_packages\fall_blau_2\`（`data/scenarios/fall_blau_2.usc/`）的内容与结构 |
| `e76b_paths.py` / `e76_out.txt` | **直接问游戏自己的 `uoc2.paths`**：`all_package_dirs()`（用户包在前）/ `all_non_game_package_dirs()` / `get_editable_packages()` / `get_non_editable_packages()` |
| `e77_datadirs.py` / `e77_out.txt` | 包内 `data/` 子目录约定（`entity_types` / `campaigns` / `scenarios`）与各包实际内容 |
| `e78_cost.py` / `e78_out.txt` | **各战役包静态清单规模**（15 包 5371 文件 / 292 场景 / 184 变体覆盖）+ **分支逻辑的字节码量**（15 函数 779 条指令） |
| `e79_align.py` / `e79_out.txt` | 段图 / `required_tokens` / `variants` 的**机器可对齐性**（west 24 个变体 100% 被 `required_tokens.variant` 声明） |
| `e80_traverse.py` / `e80_out.txt` | **「每次遍历游戏文档」的精确成本**（§9.1.0）：全量解析 36.1 s / 增量 52 ms / stat 54 ms / 预编译基线 0.6 ms |
| `e81_breakdown.py` | 全包 yml 构成拆解（`maps` 8076 / `campaigns` 4570 / `entity_types` 1573 / `scenarios` 153，共 18.9 MB） |
| `e82_modsave.py` / `e82_out.txt` | **mod 场景在存档里的可读性**（`fall_blau_2` 三方比对）；`paths.pyc` 的 addable 机制 |
| `e83_patch.py` / `e83_out.txt` | **`.patch.yml` / `addable` 机制**在磁盘上的实际情况（游戏包 0 个、用户包 0 个）+ `get_yml` 完整逻辑 |
| `e84_tri.py` / `e84_out.txt` | **base vs mod vs save 三方比对**（⚠️ 本机这个 mod 内容与原版相同，**不构成覆盖**）+ 包优先级实跑 |
| `e85_chain.py` / `e85_out.txt` | **`document/` 的读写链路字节码**（`_load` 读什么 / `_save` 写什么 / `scenario_serialization` 含 `variants`） |
| `e86_root.py` / `e86_out.txt` | **根表装的是"已登场过的单位"**（§3.4.3b）：C0 根表 0 条、根表随进度单调增长但永小于名册、根表同时含敌我双方单位 |
| `e87_next.py` / `e87_out.txt` | **「下一场场景」的单位有多少已在根表**（§3.4.3c）：161 例 100% / 54 例部分 / 3 例 0%；跨场景复用是部分覆盖的原因 |
| `e88_achieve.py` / `e89_glob.py` / `e90_union.py` | **全局里程碑的入口搜索**：`achieve` / `milestone` / `medal` 在全部 `.pyc` 里的分布；`main_screen` 相关模块的函数清单 |
| `e91_selms.py` / `e91_out.txt` | `MainScreenCtrl.on_enter__main_selector` 反汇编（`_sel_milestones` 状态容器的来源） |
| `e92_setup.py` / `e92_out.txt` | `main_screen/setup.pyc` 全部函数名 + `CampaignSetup.__init__` 反汇编（战役包 vs 存档 `document/` 的取法） |
| `e93_globalms.py` / `e93_out.txt` | `CampaignSetup.__init__` / `usg_campaign_info` / `paths.addable_dir` / `paths.get_yml` 完整反汇编 |
| `e94_msdetail.py` / `e94_out.txt` | **`_cr_prepare_milestones_selectors` / `Campaign.get_achieved_milestones` / `get_campaign_medal` / `usg_campaign_info` 完整反汇编**（§6.1b） |
| `e95_globalstore.py` / `e95_out.txt` | `CampaignDoc.get_milestones` 反汇编（读 `main.yml` 的 `milestones` 定义表）+ `MilestoneInfo` / `MedalInfo` 类定义 |
| `e96_firsttime.py` / `e96_out.txt` | **`MilestoneInfo.__init__` 全量反汇编** —— 全局解锁状态读自 `ms_<campaign>_<ident>`（§6.1b 的核心证据） |
| `e97_steamapi.py` / `e97_out.txt` | 全库定位 `steam_api` / `get_stat_value` / `inc_stat` / `store_stats` 的使用点 |
| `e98_write.py` / `e98_out.txt` | **`Campaign.game_finished` 全量反汇编** —— 里程碑发放链：写存档 + `inc_stat` + `store_stats`（§6.1b） |
| `e99_apiimpl.py` / `e99_out.txt` | `lib/` 目录结构普查（发现 `lib/tools/steam_api.pyc` 在 `lib/uoc2/**` 之外） |
| `e100_docdir.py` / `e100_out.txt` | `campaign_doc_dir_abs` 定位 + `paths.init_paths()` 实跑 + 存档根 `milestones` 格式实测（内联列表） |
| `e101_census.py` / `e101_out.txt` | 里程碑三元组普查初版（发现 `document/main.yml` 的定义表是**块状映射**） |
| `e102_census2.py` / `e102_out.txt` | **修正后的里程碑普查**（YAML 精确解析）：根表 ⊆ 定义表 **70/70**；奖章 79/249 满足；**15 个战役包的定义表条数**（§6.1b） |
| `e103_globals.py` / `e103_out.txt` | `_Paths.init_packages` 反汇编 → `campaign_doc_dir_abs` 的根目录是 `data/campaigns` |
| `e104_exe.py` / `e104_out.txt` | `uoc2.exe` 字符串扫描 + 游戏目录下的 steam DLL 清单 |
| `e105_steamapi2.py` / `e105_out.txt` | **`lib/tools/steam_api.pyc` + `lib/tools/steamworks.pyc` 完整反汇编**（`inc_stat`/`set_stat`/`store_stats`/`get_stat_value`/`DummySteamAPI`） |
| `e107_plainname.py` / `e107_out.txt` | **「直接写明文」可行性**：本地化回退行为 + **游戏包 12061 条单位里 24 条非 id 名** + **70 存档 84462 条单位条目里 746 条明文 `name_brief`**（去重 73 组，如 `'1第德国警卫队'`）（§5.5） |
| `e108_plainsrc.py` / `e108_out.txt` | **明文名的来源**：`LocalizationManager.is_str_id`（`id_` / `idp_` 前缀）与 `get()` 的三条回退分支（不在语言表 + 非 str_id → **原样返回**）（§5.5） |
| `e109_display.py` / `e109_out.txt` | **单位名显示走 `get` 还是 `get_unformatted`** —— `get_unformatted` 全库仅被 `tools/localization.pyc` 自身与离线工具调用，**运行时 UI 不用它** ⇒ 明文不会显示为空（§5.5） |
| `e110_theater.py` / `e110_out.txt` | **战区资产读写链路**：`Game.new` 的 `ta.to_use = ta.uses_turn` 重置 vs `Game._load` / `hard_set_state_on_ar_ord` 的 `copy_fields` 含 `theater_assets` ⇒ **读档不重算**（§6.2b） |
| `e111_out.txt` | 上述战区资产相关的完整反汇编输出 |
| `e112_hqinherit.py` / `e112_out.txt` | **HQ 侧的继承**：`Campaign.agree_on_hq` 的 `co_names`（**`'force_pool' in co_names` = False**）与 `_rename_hqs` 的常量表（`1,'id','general',None,'hq_id'`）⇒ 兵库与升级**内容整体继承**（§6.2b） |
| `e113_hqadjust.py` / `e113_out.txt` | **HQ 侧重组**：`Game._adjust_hqs_between_situations` 全量反汇编 —— **全程不碰 `force_pool`** ⇒ 兵库是 L1 安全可写字段（§6.2b） |
| `e114_out.txt` | 上述 HQ 重组/继承的补充输出 |
| `e115_yaml.py` | **游戏的 YAML 序列化器**：`lib/tools/yaml_.pyc` 反汇编 —— `_Dumper` 的基类（`yaml.CDumper`）、5 个自定义 representer、`yaml.dump(obj, Dumper=d, default_flow_style=False)`（§8.1） |
| `e116_dumper.py` / `e116_dumper.txt` | `check_short_list` / `set_representer` / `str_representer` / `float_representer` 的**逐条反汇编** —— 短列表门槛是 **1..4**（`< 5`），不是 1..5 |
| `e117_dumps.py` | `yaml_dump` / `yaml_dumps` 的反汇编 —— 确认**没有传 `allow_unicode`**（⇒ 默认 False） |
| `e119_gamedumper.py` | **复刻游戏 dumper 的全量字节回归**：337 个 L1 条目，`allow_unicode` / `sort_keys` 四种组合的对比（281/337 vs 337/337） |
| `e122_exact.py` | 修正短列表门槛后的**最终字节回归**：**337/337 完全一致** |
| `e125_core_dump.py` | 核心库 `yamlio.dump()` 的字节回归（**337/337**） |
| `e126_unicode.py` | 真实存档里中文的存储形态普查：**含原始非 ASCII 字节的 0 个、含 `\uXXXX` 转义的 40 个** |
| `e127_esc.py` | 转义字符串的确切写法：`name_brief: "1\u7B2C\u82CF\u8054\u8B66\u536B\u961F"`（双引号 + 大写十六进制） |
| `e120_ser.py` / `e123_base.py` / `e124_base2.py` | `tools/serialization.pyc` 的 `save_yaml` → `yaml_dumps` 调用链，以及 `_Dumper` 基类确认 |
| `e135_assetmap.py` / `e135_assetmap.md` | **GUI 贴图资产全盘点**：629 个单位类型目录 / 379 个特种兵目录（378 真有图 + `generic` 空目录）/ 11 张 step / 44 张战区资产（11×4 态）/ status 55 / icon 211 —— 尺寸全部由 PNG IHDR 直读，**不靠文件名猜** |
| `e136_fphelper.py` | `hq_ctrl.pyc::HQCtrl._fp_helper` 全量反汇编 ⇒ **战力阶梯（step）语义**：`'steps/step{}'` 的拼法、`id_n_steps_*` 的三选一分支、步数 `n` 的来源（§《GUI设计规范》§5.4） |
| `e137_scan_pyc.py` | 全量 `.pyc` 字符串扫描 ⇒ 定位 `n_steps` / `force_pool` / `img_ident` 的定义方（`state/entities/force_pool.pyc`、`state/entities/unit.pyc`） |
| `e138_nsteps.py` | `n_steps` 出现在哪些类/方法里 |
| `e139_stepalgo.py` | **战力阶梯算法**：`UnitState.use_from_deploy` → `num_steps = max_st − tot_st`；`get_num_nationality_steps` / `get_unit_equipment_steps` 逐条反汇编 |
| `e140_equipcombo.py` | 627 个单位类型的 `(equipment, equipment_q)` 组合分布 ⇒ 日常只会用到 `step.png` / `step_armor_1.png` / `step_armor_2.png` 三张阶梯图 |
| `e141_tkprobe.py` / `e142_tkreal.py` | tkinter / PhotoImage / PNG 能力探测；**"能 import" ≠ "能开窗"** 的实测（`Tk()` + `ttk.Style` + `PhotoImage`） |
| `e143_tcllib.py` | Tcl 脚本库位置（`info library` / `auto_path`） |
| `e144_tktest.py` | **给随包 runtime 补 tcl/tk 的端到端验证**：补齐 7 项后 `Tk() OK patchlevel: 8.6.15`、`clam` 主题可用、`PhotoImage` 可用 |
| `e145_peimports.py` | PE 导入表解析（纯标准库）⇒ 定位缺失依赖：**`tcl86t.dll` 依赖 `zlib1.dll`**，缺了必然 `DLL load failed` |
| `e146_edge.py` | 两个真实坑：`specialist/generic` 是**空目录**；`unit/ger_pz_dlc7/` 里是 **`sheet_l.png`（小写 L）** ⇒ 图标查找必须大小写不敏感 |
| `e147_sheetlr.py` / `e148_sheetbranch.py` | **`sheet_L` / `sheet_R` 语义**：战斗面板进攻方用 `sheet_L`、防守方用 `sheet_R`；单位详情面板**永远用 `sheet_L`** |
| `e149_picktypes.py` | 真实单位类型的 `movement` / `equipment` / `max_st` / `max_spec`（视觉稿与测试用） |
| `e150_speccheck.py` | 特种兵目录逐个复查（**只有 `generic` 空**，其余 378 个 7 图齐全） |
| `e151_checkrefs.py` | 视觉稿引用的每一个贴图路径逐个核对（**缺失 0**） |

> `e135` ~ `e151` 这一组是 **《GUI设计规范》§5「游戏贴图资产映射」与 §10「技术实现」的证据链**：
> 它们把"GUI 能用哪些游戏贴图、step 图标到底怎么选、贴图怎么缩放、GUI 跑在什么运行时上"
> 从**猜测**变成了**字节码 + 实测**。
> ⚠️ 其中 `e144` 是**唯一一条结论会影响成品打包**的证据链：随包 CPython 3.14.3（embeddable 版）
> **不带 tkinter**，不补 `tcl/tk` 就做不了原生窗口。

> `e88` ~ `e105` 这一组是 **§6.1b「不做里程碑功能」那个决定的证据链** ——
> 它们回答的是"全局里程碑状态到底存在哪里"，而不是"怎么改它"。
> 保留它们是为了让后来者**不必重新挖一遍**就能复核这个取舍；实现者不需要照着实现任何里程碑功能。
>
> `e107` ~ `e114` 这一组是 **§5.5 / §6.2b 的证据链**：
> `e107`~`e109` 证明"**直接写明文**"这条路是通的（游戏自己就在写明文），
> `e110`~`e111` 证明"**战区资产在当前战斗里读档即生效**"，
> `e112`~`e114` 证明"**HQ 兵库不会被任何重组重算**"。
>
> `e115` ~ `e127` 这一组是 **§8.1「YAML 序列化要复刻游戏」的证据链**：
> 它们把"游戏到底怎么写 YAML"从**推断**变成了**字节码实证**，
> 并给出可量化的收益（**337/337 字节一致**，改一个 XP 只产生一行 diff）。

**另一个证据源：实现仓库自己的自动化测试**

规范里的很多断言，在实现阶段被固化成了**可重复运行的回归测试**（随实现一起交付）：

```
<实现仓库>\tests\        标准库 unittest（内置解释器没有 pip，装不了 pytest）—— 共 167 项
  test_runtime.py        内置解释器 / PyYAML / libyaml C 扩展 / 明文往返
  test_packing.py        保真打包器：合成存档 8 项 + 真实存档全量回归
  test_core.py           70 个存档全部打开成功、8 个能力位逐条对账、能力矩阵自洽
  test_catalog.py        类型表数量、max_st/max_spec 分布与 §5.3 一字不差、未知类型不拦截
  test_editing.py        plan 不碰磁盘 / 改动的只有目标条目 / 备份字节一致 / 拒绝坏计划
  test_units.py          xp / 战力 / 改名明文；改编制被拒；改名不产生 temp mod
  test_specs_and_pool.py 特种兵类型合法性 + max_spec 封顶 + 总部兵库
  test_cards_store.py    卡牌与商店（price:0 免费 / quantity:0 被拦 / 下架=删条目）
  test_theater_assets.py 战区资产（唯一 L3 例外）：战斗外禁用 / 不新增资产 / 快照不写
  test_undo.py           撤销栈：落盘 / 精确还原 / commit 粒度 / 多步 LIFO / 基准过期拒绝
  test_yamlio.py         YAML 序列化规则逐条 + 真实存档往返 337/337 字节一致（§8.1）
  test_api_contract.py   8 个函数的签名与返回结构**冻结**（接口漂移立刻失败）
```

运行方式：

```
python\python.exe -m unittest discover -s tests -t .
```

⇒ **实现者若改了任何一处写回逻辑，先跑这一套** —— 它覆盖了"不改坏存档"这个底线。

**权威来源**：游戏把核心逻辑以 Python 3.14 字节码装在
`<game>/lib/uoc2/**/*.pyc`。校验 schema 在
`lib/uoc2/state/**/data_validation/*.pyc`（voluptuous）。可用 `marshal` 直接读取常量：

```python
import marshal, types
code = marshal.loads(open(path, "rb").read()[16:])   # .pyc 头部 16 字节
# 递归收集 co_consts 里的字符串 → 就是 schema 的键名与类型
```

更进一步的验证方式（已验证可行）：

```python
import sys, numpy, yaml
sys.frozen = True
sys.executable = r"<game>\uoc2.exe"       # 让游戏认为自己是 frozen app
sys.path.append(r"<game>\lib")
import importlib
paths = importlib.import_module("uoc2.paths")
paths.init_paths()                          # 成功解析出 root_dir / settings_file
um = importlib.import_module("uoc2.state.entities.data_validation.unit")
# um.campaign_unit_schema 就是字段字典；um.units_schema(gamelike, from_scenario_data) 需要上下文
```

> 注：`game_data_validation` / `scenario_data_validation` / `campaign` 等模块导入时会拉起
> `load_types`，需要完整的 `entity_types` 装载链（本次未完全跑通）。
> **但字段级 schema（unit / hq / card / campaign_unit_schema）已成功导入并用于实测。**

**§3.4.4 里明确标注"未验证"的三点**（不影响"改单位 = 改根 `units.yml`"这个主结论）：
1. `Game._load` 有-archive 分支的序列化对象究竟取自"最后快照目录"还是别处 —— 调用链未跑通。
2. `Game._save` 里 `_save_campaign_units` 写向哪个 `serialization` —— 未逐字节验证，
   只依据"实测 `games/<场景>/campaign_units.yml` 不存在、只存在于快照里"反推。
3. `games/<场景>/units.yml` 这个 ID 清单在读档时是否被读取 —— 未实测。

**§3.5 里明确标注"未验证"的五点**（不影响"战斗中改 = 安全 / 战斗外改 = 部分字段会被重算"这个主结论）：
1. `unit_exp_step_loss_standard` / `_elite` 的确切数值未取到 —— 只给出公式形式。
2. `tot_st` 的定义未定位到代码对象，按语义推断为 `act_st + sup_st`（与实测一致）。
3. `unit_replacements`（ID 替换映射）的来源与规则未研究。
4. ~~总部侧的同类重组 `_adjust_hqs_between_situations`（`game.pyc:223`）未研究。~~
   ✅ **已补完**（`e112` / `e113`）⇒ 它**不碰 `force_pool`**，
   `agree_on_hq` 的 `co_names` 里也没有 `force_pool`，`_rename_hqs` 只改 id/将领/关联、内容整体继承
   ⇒ **HQ 兵库是 L1 安全可写字段**（§6.2b）。
5. `campaign_agree_on_unit` 中 `uv` 覆盖缺实测证据（对照组单位多为未部署状态），
   该结论**仅来自字节码 `game_adjust_data.pyc:20`**。

**§6.1b 里明确标注"未验证"的一点**（不影响"里程碑功能整个不做"这个主结论）：
- **本机没有读出任何 `ms_*` 统计的真实数值** —— 它在 Steam 客户端的 UserStats 里，
  需要 Steam 客户端在运行、且有一个能调用 `SteamUserStats.GetStat` 的宿主进程才能读到。
  关于 `ms_*` 读写链的结论来自**字节码**（`campaign_info.pyc` 读、`campaign.pyc` 写、
  `lib/tools/steam_api.pyc` 的 `inc_stat`/`set_stat`/`store_stats`/`get_stat_value`）与
  **游戏日志**（`log.txt` / `clog.txt` 每次启动都打印 `Steamworks initialized!` 与
  `Steam user stats and achievements successfully fetched`）。
  ⇒ 另有一项**流程性事实**：`userdata\<id>\809230\remote`（SteamUserStats 本地缓存）**在本机不存在**，
  所以"本地缓存里能不能改"这条路**连样本都没有**，更没有实测过改它是否有效。

**§5.5 / §6.2b 里明确标注"未验证"的三点**（不影响"改名走明文"与"兵库 L1 可写"这两个主结论）：
1. **明文名的显示没有"实机截图"级证据** ——
   `e107`~`e109` 是**字节码 + 存档数据**双证据（`get()` 的回退分支 + 游戏自己写的 746 条明文），
   但**没有真的进游戏看一眼**。判定"明文能正确显示"的依据是：
   `is_str_id` 只认 `id_`/`idp_` 前缀 ⇒ 明文**根本不会被送进本地化表**，
   `get()` 对"不在语言表 + 非 str_id"**原样返回**；
   并且运行时 UI 用的是 `get`，而不是对缺失键返回空串的 `get_unformatted`。
   ⇒ 这条链是完整的，**但仍建议实现者实测一次**（改个名字 → 读档 → 看一眼）。
2. **HQ 兵库改完后，游戏界面上的确切表现没有实机截图** ——
   结论来自 `_adjust_hqs_between_situations` / `agree_on_hq` / `_rename_hqs` 三处字节码
   （**都不碰 `force_pool`**）。**未做"改 500 → 进战斗 → 看兵库"的端到端实测。**
3. **战区资产"改完读档生效"没有实机截图** ——
   结论来自 `Game._load` / `hard_set_state_on_ar_ord` 的 `copy_fields` 含 `theater_assets`。
   ⚠️ 同时**未验证**"改完后游戏写盘会不会把它冲掉"这一步的**具体值** ——
   字节码上 `Game._save` 会写回当前值，所以理论上游戏接手后按自己的状态走（§6.2b）。

---

### 12.1 本文档里的"产品决策"与"实证结论"的区分 ⚠️ 请实现者注意

下面几条**不是**从游戏里测出来的，而是**产品取舍**。它们同样有效，但理由不同，不要试图去"验证"它们：

| 决策 | 性质 | 理由 |
|---|---|---|
| **只写 L1，其余四层只读** | 产品决策（基于实测的 R1–R6 风险） | 玩家要的是"改过头能反悔"，不是"改了就锁死" |
| **两个 L3 例外：当前进行中战斗的 `theater_assets`（战区资产）与作战标记**（同一张文件） | ✅ **实证结论**（`e110` 字节码）+ 边界取舍属产品决策 | `Game._load` 的 `copy_fields` 含它 ⇒ 读档即生效；且它不是战报。作战标记是战斗里的"命令"（U89 批准）。其余 L3 一律只读（§6.2b、§6.2c、§7.2 W8） |
| **HQ 兵库 `force_pool[].quantity` 可写（L1）** | ✅ **实证结论**（`e112` / `e113` 字节码） | 三处重组/继承路径**都不碰 `force_pool`** ⇒ 改完不会被重算（§6.2b） |
| **"战区资产"与"总部兵库"是两个不同的东西** | ✅ **实证结论** | 存储位置、生命周期、可改性全都不同；混了就会"改了却像没改"（§6.2b、§10 第 52 条） |
| **改名直接写明文**（不做 temp mod + 本地化） | ✅ **实证结论**（`e107`~`e109` 字节码 + 70 存档 746 条明文）· 兼产品决策 | `is_str_id` 只认 `id_`/`idp_` ⇒ 明文原样返回；**游戏自己就在写明文**（§5.5、§7.5） |
| **不提供改编制 / 新增单位 / 场景预设编辑器** | 产品决策 | 要写 L5/L3 → 游戏内回退不掉；且玩家看不懂 |
| **历史战斗里的单位只读** | 产品决策 | 它们属于 L3/L4，改它等于伪造战报 |
| **"跳到某会议"不做** | 产品决策 | 会让状态机不一致，属于"改了却像没改"（§6.1） |
| **重组预警用徽标而不是禁用字段** | 产品决策 | 禁用会让玩家以为修改器坏了 |
| **回退 = 整表替换** | ✅ **实证结论**（`campaign.pyc:317` 字节码） | 策略成立的基础 |
| **重组只发生在 `Game.new`** | ✅ **实证结论**（字节码 + 10/10 对照组） | 决定"战斗中改是安全的" |
| **检查点只有 5 个文件、不含 `document/`** | ✅ **实证结论**（100 个检查点普查） | R1/R6 的依据 |
| **"恢复上次会议的牌局"**（读 L2 的 `card_store` → 写 L1） | 产品决策 | 读检查点不违反 §7 —— 这是策略能成立的一个正例 |
| **商店 `price: 0` = 免费商品；`quantity: 0` 是非法值** | ✅ **实证结论**（`force_pool.pyc:711` 字节码 + 70 存档 1659 条条目全普查） | 修改器必须禁止 `quantity = 0`（§4.6、§5.2、§6.3、§10 第 9/34 条） |
| **"买空"有两种表现**：装备 `quantity` 递减、特种兵整条消失；`quantity` 归零 ⇒ 条目移除 | ✅ **实证结论**（包默认 / 存档根 / `last_conference` 三方比对 + 67 存档全普查） | 这才是"游戏从不产生 `quantity: 0`"的真正原因（§4.6.1） |
| **存档里的商店价格可能与游戏包默认清单不同** | ✅ **实证结论**（277 条）· ⚠️ **原因未定位** | 因此**不能拿游戏包去"纠正"存档**（§4.6.1、§10 第 37 条） |
| **战役包默认商店清单在 `fronts/<战线>/conferences/<会议>.yml`** | ✅ **实证结论**（5 战役 44 个会议文件） | 不在场景目录里，也不在 `document/conferences/<会议>.yml` 里（§4.6.1） |
| **战役/场景可从根 `main.yml` 精确识别** | ✅ **实证结论**（70 存档全普查） | `standalone_scenario` / `campaign_id` / `in_state.*` 四个字段足够（§3.2b） |
| **独立场景存档没有商店、没有卡牌** | ✅ **实证结论**（3/3） | 两块功能在独立场景上整个禁用（§3.2、§3.4.5） |
| **写回用的 YAML 序列化器要复刻游戏自己的**（`yaml.CDumper` + 5 个自定义 representer + `allow_unicode=False`） | ✅ **实证结论**（`e115`~`e127` 字节码 + 337/337 字节回归） | 游戏自己就那么写 ⇒ 照着写才能"没改的行一个字节都不动"（§8.1、§10 第 64/65 条） |
| **根 `units.yml` ⊆ `document/units.yml`；名字流向是「运行时 → 名册」** | ✅ **实证结论**（12 存档 + `campaign.pyc` 字节码） | 改名**只改根表就够**，不需要动 L5（§3.3） |
| **外部静态整理数据当缓存用，不当权威源** | 产品决策（基于"静态表会过期"） | 优先级：存档 `document/` → 游戏包 → 静态表（§9.1.1） |
| **快照里有 `ar_list.yml`（99.9%）** | ✅ **实证结论**（12071 个快照全普查） | ⚠️ 本文档**前一版曾写反**（说"快照里没有"）—— 教训见 §2.2 |
| **游戏里的里程碑分两套**：战役内列表与奖章读存档根 `main.yml` 的 `milestones`；主菜单的**全局图鉴读 Steam UserStats `ms_<campaign_id>_<milestone_id>`** | ✅ **实证结论**（`campaign_info.pyc` + `campaign.pyc` + `lib/tools/steam_api.pyc` 字节码链 + 游戏日志） | 全局那一份**不在任何本地文件里** ⇒ 改存档点不亮它 ⇒ **里程碑功能整个不做**（§6.1b、§7.5） |
| **里程碑发放只发生在 `Campaign.game_finished`，且 `if m_ident in self.milestones: continue`** | ✅ **实证结论**（字节码） | 说明"改存档只能管着战役内那一半"的机制来源（§6.1b） |
| **根表 `milestones` ⊆ `document/main.yml` 的定义表；奖章判据是 `medal.milestones` ⊆ 根表** | ✅ **实证结论**（70/70 存档；249 条奖章中 79 条已满足） | 支撑"里程碑是游戏自动结算的，玩家正常打就有"（§6.1b） |
| **"里程碑 / 奖章"整个不做** | **产品决策** | ①多数玩家不关心 ②削弱成就感 ③技术上只能改一半，是"改了却像没改"的典型（§6.1b、§7.5） |
| **修改器自带备份 + 撤销栈** | **产品决策** | 游戏内回退只能**整体**回滚，救不了"只想改回刚才那个数"；而且它**根本撤不掉战区资产**（§6.4、§10 第 57 条） |
| **不做"快速存读档"（原工具的 AHK 热键方案）** | **产品决策** | 玩家的"所见即所得 Mod"已能透视未来结果，频繁存读档是它的**下位替代**（§7.5） |
| **新增单位类型 / 新增特种兵类型（`create-type` / `create-spec`）不做** | **产品决策** | 要写游戏包或 L5 名册 → 跨存档共享、**回退不掉**（§7.5） |
| **核心库 = 纯 Python 包、8 个函数、GUI 直接 `import`** | **产品决策** | 少一层协议、少一层出错点；核心库能**无界面**跑回归测试（§0.1、§0.2、§7.7） |
| **Python 运行时随包分发并一并进 Git** | **产品决策** | 用户不装 Python 也能用；25 MB 是一次性成本，之后不再改动（§0.1、§10 第 51 条） |
| **GUI 在本仓库独立开发**（不并入静态查看器） | **产品决策**（2026-11-17 改判） | 两个项目的**安全边界契约**不同（静态项目 D-033 明文禁止改存档），合并要跨仓库改契约；先各自稳定再"外壳合并" |
| **GUI 技术栈 = Tk 8.6 + ttk** | **产品决策**（基于实测） | 与静态查看器同栈 ⇒ 配色/主题代码可复用，未来"外壳合并"成本最低；原生窗口对玩家最傻瓜 |
| **随包 runtime 必须补 tcl/tk（+8.7 MB）** | ✅ **实证结论**（`e141`~`e145`） | embeddable 版 CPython 3.14.3 **不带 tkinter**；补齐后 `Tk() OK patchlevel 8.6.15`（§0.1、GUI 设计规范 §10.1） |
| **GUI 贴图运行时从游戏目录读，不打包** | **产品决策**（基于实测） | `assets/surfaces` 全部约 **180 MB**；改存档的人一定装了游戏 |
| **"战力阶梯"（step）= 离满战力还差几步** | ✅ **实证结论**（`e136` / `e139` 字节码） | `use_from_deploy`：`num_steps = max_st − tot_st`；图标按 `equipment` / `equipment_q` 选 `steps/step*`（GUI 设计规范 §5.4） |
| **单位头像用 `sheet_L`**（`sheet_R` 只在"进攻方 vs 防守方"对阵时用） | ✅ **实证结论**（`e147` / `e148` 字节码） | 战斗面板：攻方 `sheet_L` / 守方 `sheet_R`；单位详情面板永远 `sheet_L`（GUI 设计规范 §5.3） |
| **战区资产图标有 4 态变体**（neutral/hover/down/disabled） | ✅ **实证结论**（`e135` 全盘点） | 11 个资产 × 4 = 44 张，120×120 ⇒ GUI 可直接复用游戏现成的四态（GUI 设计规范 §5.5） |
| **特种兵图鉴主图用 `hq_action_icon.png`（160×160）** | **产品决策**（基于实测尺寸） | `sheet_large.png` 只有 52×68，名字骗人（GUI 设计规范 §5.2、§12.3） |

> **给实现者的一条方法论**：
> 本项目在这份文档上犯过两次同类错误 —— ①用"最后一个快照"抽样做存在性普查，
> ②把两个不同总体（`games/<场景>/units.yml` 的 703 个文件 vs 所有层里 ID 清单的 30 次）混在一个分母里。
> **写进规范的每个数字，都应该是全量普查或明确标注口径的。**

---

## 13. 给实现者的最后提醒

1. **按能力实现，不要按状态实现。** 真实玩家的存档组合比任何样本都多。
   用 §3.4.5 的 8 个能力位 + 能力矩阵，**新增状态不需要改任何代码**。
   状态判定（§3.4.6）只用于界面显示。
2. **先做一个只读的"存档浏览器"**，把 §4 的结构 + §3.4.6 的当前阶段显示出来，确认能正确解析两类存档，再加编辑功能。
3. **任何写入都要走"校验 → 预览 diff → 备份 → 写回"四步**，不要提供"跳过校验"的入口。
4. **⚠️ 只写 L1 + 当前战斗层那一张 `main.yml`，别的都不要写**（§7）。存档有 5 层（L1 根状态 / L2 检查点 /
   L3 战斗实时层 / L4 回合历史 / L5 战役文档），**只有 L1 可写，其余四层全部只读**。
   写 L2 会摧毁玩家唯一的游戏内撤销基线（§7.4 R1–R3），写 L4 是伪造历史（R5），
   写 L5 的改动游戏内回退不掉（R6）。
   ⛔ **两个例外**（同一张文件）：**当前进行中战斗**的 `theater_assets`（战区资产）
   与三个作战标记 id 列表 —— 这是 §7.2 W8 那个白名单，**只写这几个键**，其余 L3 内容照旧只读（§6.2b、§6.2c）。
   ⛔ 另外 §7.2 **W9–W13** 是本轮加的硬护栏（写盘白名单 / `save_id` 边界 / 解析失败整批拒写 /
   写盘互斥 / 按下标删除排序），**别绕过它们**（§7.8）。
5. **单位数据只有一个来源：根 `units.yml`。** 不要去 `games/<场景>/units.yml` 找数值（那里只有 id），
   也不要把 archive 快照当成"当前状态"（那是回合边界的历史）。见 §3.4.4。
6. **⚠️ 告诉用户"改单位"有生效时机之分**（§3.5）：
   战斗中改 = 全部生效；战斗外改 = 部分字段会在下次开打时被游戏重算覆盖。
   **这个区别必须在 UI 上说清楚**，否则用户会认为修改器没生效。
7. **优先把下拉数据源**（卡牌类型/特种兵类型）从游戏包读出来，而不是硬编码。
   `unit_types/`（627 个）用来把 `type` 翻译成 `max_st` / `max_spec` 供展示与校验（§5.4）。
8. **数值改动一律带上上限校验**（xp≤399、specs≤min(3,max_spec) 硬拦；
   act_st/sup_st 超 `max_st` ⇒ **自动配平并改写输入值**，不是只给个软提示，§5.3）。
9. 存档是玩家唯一的存档，**默认行为应该是"备份后再写"**，且写回失败要能完整回滚。
10. **解析器要容错**：遇到不认识的文件/字段组合，**跳过并记录**，不要抛异常中断整个存档的加载。
11. **内层 `archive` ZIP 原样复制**，不要解压重压（见 §11.4）。除了 L1 的目标文件与
    **当前战斗层那张 `main.yml` 的白名单键**（战区资产 / 作战标记），其余条目都要**字节级原样保留**。
12. **功能要少而确定**。`type`（编制）、新增单位、场景预设编辑器、「跳到某会议」这四个功能**明确不做**
    （权威清单见 §0，理由见 §7.5 / §6.1）—— 它们要么写 L5/L3（**回退不掉**），要么让状态机不自洽。
    **宁可少做一个功能，也不要做出「改了却像没改」的界面。**
13. **⚠️ 数据源要分层，不要"每次全量读游戏包"，也不要"只认内置表"**（§9.1.2）。
    - 内置静态基线（类型表 + 本地化）→ 0 启动成本；
    - 运行时增量（只读差集、只读当前场景）→ 实测几十~几百 ms；
    - 用户主动刷新 → 写本地 overlay；
    - **⚠️ 表只做候选，不做白名单**（§9.1.3）：表里没有的 type 要能手输、要照常显示。
    - **⚠️ 别忘了扫用户包目录**（`%LOCALAPPDATA%\.uoc2\_packages`）—— 那里有 mod，
      游戏会加载它（用户包优先级更高），只扫游戏包会漏掉 mod 新增的特种兵与场景。
14. **🚫 不要顺手加"里程碑/奖章解锁"** —— 这是**明确砍掉的功能**（§0、§6.1b、§7.5）。
    理由：多数玩家不关心；它削弱成就感；技术上"全局图鉴"那份在 Steam 统计里，改存档管不着。
    **但也别把 `milestones` 字段弄丢** —— 写回根 `main.yml` 时一律原样搬运（§10 第 50 条）。
15. **⚠️ "战区资产" ≠ "总部兵库"** —— 前者在 `games/<场景>/main.yml`，后者在根 `hqs.yml`。
    **写错地方 = 改了却像没改**（§6.2b、§10 第 52 条）。
16. **⚠️ 战区资产只在"当前进行中的战斗"里可改** —— 战斗外改会被 `Game.new` 重算覆盖。
    UI 必须**禁用**它并说明原因，而不是让用户白改（§6.2b、§7.2 W8）。
17. **⚠️ 备份与撤销栈是底线，不是可选项**（§6.4）—— 写回前自动生成 `<存档名>_BACKUP.usg`
    （放 `<修改器目录>/bak/`，**绝不放在存档同目录**；不覆盖同名备份），
    撤销栈落盘、撤销前校验基准。**游戏内回退撤不掉战区资产**，只有自己的撤销栈能撤。
18. **⚠️ 打包时别忘了 PyYAML** —— 随包分发的 `python/` 必须自带 `python/Lib/site-packages/yaml/`，
    否则 `run.bat` 直接起不来（§10 第 51 条）。
19. **改名就写明文** —— 不要为了改名去写 temp mod 或本地化包（§5.5、§7.5）。
