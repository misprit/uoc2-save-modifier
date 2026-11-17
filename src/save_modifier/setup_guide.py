"""首次运行配置引导。

工具随分发提供一份带注释的初始配置 `config/config.default.yml`；首次运行
（或配置里 `setup_done: false`）时把它复制为 `config/config.yml`，再走一遍
问答确认游戏数据目录、原版包目录与本地化语言，并把答案就地写回该文件。
就地更新只替换已知键所在的那一行，模板里的注释因此得以保留——用户不必等
引导跑过才有带注释的配置文件可看。

所有问答都有默认值，直接回车即采用默认；从管道读入（stdin 已结束）时按默认
值继续，不会卡住。

每一步都先说明“这一项是做什么的、去哪里找、留空会怎样”，
因为这三项直接影响后续能不能按中文名检索单位与购买卡牌。

问答函数 `ask` 可注入，便于测试时用脚本化的答案替代真实 stdin。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from . import config as config_mod

Ask = Callable[[str], str]
Out = Callable[[str], None]

_LOCALE_HINTS = {"chi": "简体中文", "eng": "英文"}

# 初始模板缺失时的兜底文本（正常分发一定带 config/config.default.yml）
_FALLBACK_TEMPLATE = """# UOC2 存档修改器配置
uoc2_appdata: "%LOCALAPPDATA%/.uoc2"
state_dir: ""
uoc2_orig_packages_path: ""
mod_search_paths: []
locale: "chi"
setup_done: false
"""

_TOP_KEY = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)\s*:")


class SetupAborted(Exception):
    """用户在引导中按 Ctrl-C 取消。"""


def first_run(config_path: Path | None = None) -> bool:
    """是否属于初次使用：配置文件不存在，或配置里尚未完成引导。"""
    return not setup_completed(config_path)


def setup_completed(config_path: Path | None = None) -> bool:
    """配置里的 setup_done 是否为真。

    文件不存在 → 未完成；键缺失 → 视为已完成（兼容未写该键的旧配置，
    避免每次启动都重新引导）；显式 `setup_done: false`（初始模板）→ 未完成。
    """
    path = Path(config_path) if config_path else config_mod.find_config_file()
    if not path.is_file():
        return False
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return True  # 读取/解析错误交由正常加载流程报告
    if not isinstance(data, dict):
        return True
    return data.get("setup_done", True) is not False


def _expand(path: str) -> str:
    return os.path.expandvars(path)


class _Reader:
    """带默认值与 EOF 记忆的问答器。"""

    def __init__(self, ask: Ask, out: Out):
        self.ask = ask
        self.out = out
        self.eof = False

    def text(self, prompt: str, default: str) -> str:
        try:
            raw = self.ask(prompt)
        except EOFError:
            self.eof = True
            self.out(f"（未检测到输入，采用默认值：{default or '留空'}）")
            return default
        except KeyboardInterrupt:
            raise SetupAborted() from None
        return raw.strip() or default

    def yes(self, prompt: str, default: bool = False) -> bool:
        try:
            raw = self.ask(prompt).strip().lower()
        except EOFError:
            self.eof = True
            return default
        except KeyboardInterrupt:
            raise SetupAborted() from None
        if not raw:
            return default
        return raw in ("y", "yes", "是", "1", "true")


def _q(value: str) -> str:
    """把字符串写成 YAML 双引号标量（JSON 字符串是合法的 YAML）。"""
    return json.dumps(value, ensure_ascii=False)


def _dump_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_q(str(v)) for v in value) + "]"
    return _q(str(value))


def template_text() -> str:
    """读取随分发提供的初始配置模板；找不到时用内置兜底文本。"""
    path = config_mod.default_config_template()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK_TEMPLATE


def update_config_text(text: str, values: dict[str, Any]) -> str:
    """把 values 就地写回配置文本：替换同名顶层键所在行，保留其余内容与注释。

    值统一写成单行标量/流式列表；替换某个键时顺带丢弃它后面紧跟的块列表
    续行（`  - 值`），这样块列表写法也能被流式写法干净替换。
    """
    out_lines: list[str] = []
    handled: set[str] = set()
    skipping_block = False
    for line in text.splitlines():
        m = _TOP_KEY.match(line)
        if m and m.group("key") in values:
            key = m.group("key")
            out_lines.append(f"{key}: {_dump_value(values[key])}")
            handled.add(key)
            skipping_block = True
            continue
        if skipping_block:
            if line.strip() and line[:1] in (" ", "\t"):
                continue  # 旧块列表的续行
            skipping_block = False
        out_lines.append(line)
    missing = [k for k in values if k not in handled]
    if missing:
        out_lines.append("")
        out_lines.extend(f"{k}: {_dump_value(values[k])}" for k in missing)
    return "\n".join(out_lines).rstrip("\n") + "\n"


def render_config(values: dict[str, object]) -> str:
    """按值渲染配置文件文本（初始模板 + 就地更新）。"""
    search_paths = values.get("mod_search_paths") or []
    if isinstance(search_paths, (str, Path)):
        search_paths = [str(search_paths)]
    merged = dict(values)
    merged["mod_search_paths"] = list(search_paths)
    return update_config_text(template_text(), merged)


def _available_locales(packages: Path) -> list[str]:
    """列出所有包内 localization 下的语言目录名（去重排序）。"""
    locales: set[str] = set()
    if not packages.is_dir():
        return []
    try:
        pkg_dirs = [p for p in packages.iterdir() if p.is_dir()]
    except OSError:
        return []
    for pkg in pkg_dirs:
        loc = pkg / "localization"
        if loc.is_dir():
            locales.update(p.name for p in loc.iterdir() if p.is_dir())
    return sorted(locales)


def _ask_appdata(r: _Reader) -> str:
    default = str(Path(_expand(config_mod.DEFAULT_APP_DATA)))
    r.out("\n[1/3] 游戏数据目录")
    r.out("  作用：游戏的存档（save\\）与临时 mod（_packages\\）都在这里。")
    r.out("  位置：一般是 %LOCALAPPDATA%\\.uoc2，即")
    r.out(f"        {default}")
    r.out("  说明：游戏至少运行过一次才会出现该目录。")
    while True:
        value = _expand(r.text(f"  数据目录 [{default}]: ", default))
        if Path(value).is_dir():
            has_save = (Path(value) / "save").is_dir()
            r.out(f"  已确认：{value}"
                  + ("" if has_save else "（注意：其中还没有 save 目录）"))
            return value
        r.out(f"  警告：{value} 当前不存在。")
        r.out("        常见原因是路径写错，或游戏从未运行过（先启动一次游戏）。")
        r.out("        若你改过游戏的存档位置，请填实际位置。")
        if r.yes("  仍然使用该路径？(y/N): ") or r.eof:
            return value
        r.out("  请重新输入。")


def _ask_orig_packages(r: _Reader) -> str:
    default = config_mod.DEFAULT_ORIG_PACKAGES
    r.out("\n[2/3] 原版包目录（游戏安装目录下的 _packages）")
    r.out("  作用：读取单位/总部/卡牌的中文名与卡牌费用，并以原版为原型创建新类型。")
    r.out("  位置：游戏安装目录下的 _packages 文件夹。Steam 版可在库中右键游戏 →")
    r.out("        管理 → 浏览本地文件，看到 _packages 即可。默认位置：")
    r.out(f"        {default}")
    r.out("  留空：仍可修改声望/战力/经验等数值，但单位与总部只显示本地化 id，")
    r.out("        find 不能按中文名搜索，cardBuy 与创建新类型不可用。")
    value = r.text(f"  原版包目录 [{default}]: ", default)
    if not value:
        r.out("  已跳过（原版包路径留空）：中文名解析、cardBuy 与创建新类型将不可用。")
        return ""
    value = _expand(value)
    if not (Path(value) / "base").is_dir():
        r.out(f"  警告：{value} 下没有 base 目录，可能不是有效的 _packages 路径。")
        r.out("        _packages 里应当有 base、dlc1 之类的子目录。")
        if not (r.yes("  仍然使用该路径？(y/N): ") or r.eof):
            return ""
    return value


def _ask_locale(r: _Reader, orig_packages: str) -> str:
    r.out("\n[3/3] 本地化语言（决定读取哪一套名称文本）")
    r.out("  可选：chi = 简体中文（默认），eng = 英文。")
    if orig_packages:
        avail = _available_locales(Path(orig_packages))
        if avail:
            shown = "、".join(f"{x}（{_LOCALE_HINTS.get(x, x)}）" for x in avail)
            r.out(f"  该包内可用的语言目录：{shown}")
    value = r.text("  语言 [chi]: ", "chi")
    if value not in ("chi", "eng"):
        r.out(f"  提示：{value} 不是 chi/eng 之一，仍按原样写入。")
    if orig_packages:
        avail = _available_locales(Path(orig_packages))
        if avail and value not in avail:
            r.out(f"  警告：包内没有 {value} 语言目录，名称将退回本地化 id。")
            r.out(f"        建议改用：{'、'.join(avail)}")
    return value


def run_setup(
    config_path: Path | None = None,
    *,
    ask: Ask = input,
    out: Out = print,
) -> Path:
    """执行一次配置引导并写出配置文件，返回写入的路径。

    用户按 Ctrl-C 时抛 SetupAborted；写入失败时抛 OSError。
    """
    path = Path(config_path) if config_path else config_mod.find_config_file()
    out("=" * 62)
    out("UOC2 存档修改器 · 配置引导")
    out("=" * 62)
    out("首次使用时确认三项设置即可，然后才进入修改界面。")
    out("之后随时可以：")
    out(f"  · 直接编辑配置文件：{path}；")
    out("  · 或加 --setup 参数重新走一遍本引导。")
    out("每项直接回车即采用方括号中的默认值。")
    if path.exists():
        out(f"\n注意：{path} 已存在，本次引导会就地更新其中这几项（注释保留）。")
    out(f"配置文件：{path}")
    out("状态目录（解包工作区与参考列表）默认在启动脚本旁的 data/，"
        "可用配置项 state_dir 改到游戏数据目录或自定义路径。")

    r = _Reader(ask, out)
    appdata = _ask_appdata(r)
    orig = _ask_orig_packages(r)
    locale = _ask_locale(r, orig)
    # 已配置的 state_dir 原样保留；没写则按默认（启动脚本旁 data/）解析
    state_dir = config_mod.resolve_state_dir(
        config_mod._load_raw(path).get("state_dir"), Path(_expand(appdata)))
    values = {
        "uoc2_appdata": appdata,
        "uoc2_orig_packages_path": orig,
        "locale": locale,
        "setup_done": True,
    }

    out("\n" + "-" * 62)
    out("配置摘要")
    out(f"  数据目录：{appdata}")
    out(f"  状态目录：{state_dir}（解包工作区与参考列表）")
    out(f"  原版包  ：{orig or '（未配置）'}")
    out(f"  语言    ：{locale}（{_LOCALE_HINTS.get(locale, '未知')}）")
    out("-" * 62)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(values), encoding="utf-8")
    out(f"配置已写入：{path}")
    out("以后要改配置，编辑该文件即可，或运行 --setup 重新引导。")
    return path
