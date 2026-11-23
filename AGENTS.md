# AGENTS.md —— 《统一指挥 2》存档修改器

> **给 AI 协作者的工作指令**，不是产品文档。
> 产品与技术的事实源是 `docs/开发规范与Prompt.md`；这里只放**纪律、命令与环境事实**，不复述规范。

> ⚠️ **作用域守卫**：本文件对**开发会话**生效（工作目录在仓库根或 `src/` `tests/` `docs/` `tools/` 下）。
> 如果你的工作目录是 `.review/` ⇒ 你是**审阅者**，改读 `.review/AGENTS.md`（那份是只读审阅协议），
> 下面的要求不适用于你 —— 尤其：**不 commit、不 push、不改源码**。

## 0. 项目一句话

《统一指挥 2》(Unity of Command II) 的**存档修改器**：Web 界面（HTML/CSS + 本机 127.0.0.1 服务）
+ Python 核心库 `save_modifier_core`，自带 Python 运行时，解压即用，不联网。
平台：**Windows + Edge only**（用户拍板）。

## 1. 事实源（先读，再动手）

| 内容 | 文件 |
|---|---|
| 产品与技术的**唯一事实源** | `docs/开发规范与Prompt.md` |
| 工程上下文 / 进度 / 每次改动的来龙去脉 | `docs/开发上下文.md`（§7 工作方式；§5.1x 是逐次改动记录） |
| 发版清单与自检口径 | `docs/发布清单.md` |
| GUI 行为与交互规范 | `docs/GUI设计规范.md` |
| 核心库对外 API（签名被测试冻结） | `docs/核心库调用说明.md` |

## 2. 动手前的纪律

- **一改动一个 commit**；commit message 写清「症状 → 根因 → 改法 → 实测」。
- **改仓库文件一律用 Python 脚本**（脚本放 `.scratch/`），用 `rep(old, new, n)` 命中断言；
  写文件用 `io.open(..., encoding="utf-8", newline="")` ⇒ **无 BOM、LF、不 CRLF**
  （本仓库 `core.autocrlf=false` ⇒ git 不转换行尾，写进去是什么就是什么）。
- **临时产物只放 `.scratch/`**（已 gitignore，不进成品包）；**会话结束前清空**。
  同一用途的浏览器 profile / 隔离 appdata **固定一个目录反复用**
  （`tools/ui_audit.py` 用 `.scratch/ui_audit_profile`），要干净状态就**先删目录再跑** ——
  别每次新建带随机名的目录（实测教训：131 个 Edge profile = 4.16 GB）。
- **交付物一律进 git**，不要留在 `.scratch/`。

## 3. 改代码的硬性检查

- **i18n**：`L()` / `L2()` 里的中文字面量**必须**在 `src/save_modifier_web/web/i18n.json`；
  改 `L2` 模板 = 改 key ⇒ 词表要同步、**占位符名与顺序要一致**。
- **注释风格**：留＝游戏/系统硬约束、不变量、「为什么这样写」的依据（字节码证据指针、
  实测数据、会导致存档打不开的后果）；删＝历史叙述（「U94 之前…」「2026-11-20 审查…」）、
  决策汇报、复述代码、重复别处已有的约定。
- **只改注释的改动必须自证零行为变更**：剥离注释与 docstring 后比较代码 token 是否逐字符相同。
- **API 签名**：`docs/核心库调用说明.md` 的签名被 `tests/test_api_contract.py` 冻结 ⇒ 改签名要同步。

## 4. 命令

```powershell
# 全量测试（必须绿）
.\python\python.exe -m unittest discover -s tests -t .
# 单个测试文件
.\python\python.exe -m unittest discover -s tests -t . -p "test_x.py"
# i18n 词表审计
.\python\python.exe tools\i18n_audit.py
# 发版前自检（6 项）
.\python\python.exe tools\release_check.py --clean
```

⚠️ 第②项「成品 zip 与当前代码逐字节一致」在**发布之后 main 领先于 tag** 时会红 —— 那是**预期状态**
（已发布的包与 tag 的树逐字节一致，可复现）⇒ **不要**为了消这个红项去动已发布的 tag 或重传资产。

## 5. 起服务与界面巡检

```powershell
# 起服务（隔离 appdata，别碰玩家真存档）
$env:UOC2_APPDATA = "$PWD\.scratch\appdata\.uoc2"
.\python\python.exe -u -m save_modifier_web.server --serve --no-window --no-browser
#   ⇒ 打印 [OK ] GUI 服务已启动：http://127.0.0.1:<端口>/?t=<token>（token 每次随机，URL 必须带 ?t=）

# 界面全盘巡检（要**系统 Python**，随包 python 没 pip、装不了 websocket-client）
#   第 3 个参数 = 要打开的存档 id（默认 "campaigns%2Fwest.usg"）
#   ⇒ 用隔离 appdata 时**必须显式传**，否则会去开一个不存在的存档 ⇒ 误报「存档不存在」
python tools\ui_audit.py http://127.0.0.1:<端口>/?t=<token> 9401 "campaigns%2F<存档名>.usg"
#   退出码 0 = 没有异常；1 = 有异常。
#   ⚠️ 工具**不过滤 favicon** ⇒ 界面干净时也会是「共 1 条异常(favicon.ico 404)」+ 退出码 1。
#   判据：**除 favicon 外没有别的异常** 就算通过（要看清单，别只看退出码）。
```

## 6. 边界

- **不要自行打包 / 发版**：只有用户明确说「打包 / 出包」才跑 `tools/build_dist.py`；
  发布走 `tools/release_publish.py`（tag → release → 上传 → 双重校验一条命令）。
- **`.review/` 是只读审阅通道**：不提交、不清理、不改。
- **独立审阅报告要自己核验**：每条都用真实存档 / 真实代码 / 只读探针确认属实才改；
  不属实的要说明为什么不改。报告在 `.review/outbox/REVIEW-<commit>.md`，
  待裁决清单是 `.review/STATUS.md`。
- **真实存档不可写**：验证一律用副本（`tests/_fixtures.py` 的 `make_save`，
  或复制到 `.scratch/appdata/`）。玩家存档在 `%LOCALAPPDATA%\.uoc2\save`，**不要动**。

## 7. 本机环境事实（已实测，别再踩）

- **编码**：系统 **ACP=936(GBK)**。当前会话的 shell 是 **pwsh 7.7.0**（控制台 UTF-8），
  但 **Windows PowerShell 5.1 仍在**
  （`%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`），
  它的裸 `Get-Content` 读 UTF-8 中文会乱码
  （实测「中文」→「涓<U+E15F>枃」，中间那个是私用区码位）。
  ⇒ 读文件优先用 `read`/`grep` 工具（Node UTF-8），其次 `[System.IO.File]::ReadAllText($p)`；
  用 cmdlet 必须显式 `-Encoding UTF8`；**禁裸 `Get-Content` / `Out-File` / `>`**。
  读到「锟斤拷」「烫烫屯」就换 UTF-8 重读，别逐个编码试探。
- **代理**：全局 `git config --global http.proxy https.proxy http://127.0.0.1:7993`。
  ⚠️ **代理软件没开时，这个配置会让所有 git 远端操作失败**
  （实测报错 `Failed to connect to github.com:443 over proxy 127.0.0.1`）。
  ⇒ 代理没开时用**单次绕过**：`git -c http.proxy= -c https.proxy= push`（不动全局配置）；
  直连是否可用**每次先测**（`git -c http.proxy= -c https.proxy= ls-remote origin`）。
- **仓库路径含中文** ⇒ 脚本里写路径用 `os.path.join` / `Path`，别手拼反斜杠。
- **PowerShell**：5.1 里 `&&` / `||` 不可用；`Remove-Item` 被本地安全策略拒
  （删文件用 `rm -- "路径"` 走回收站，**只允许工作区内的目标**）。
- **写长 commit message**：PowerShell 里带转义引号会解析失败 ⇒ 写到文件再 `git commit -F`。
