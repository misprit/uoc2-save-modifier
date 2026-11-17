"""REPL 命令层：解析命令、维护会话上下文（存档、选中单位、类型绑定），
并把命令分发给对应的 cmd_* 实现。

命令总览（help 输出）：
  存档管理:  open/reload(qs/ql) save exit help
  声望/资产: ptg <数量>  |  st <资产名> <to_use,total,turn>
  卡牌:      cardList | cardAdd/cardBuy <卡牌类型> [位置]
             cardDel/cardUnused <位置|卡牌类型>（仅战役存档）
  单位:      find <关键字> | select <id> | xp <id> <值> | str <id> <活跃> [压制]
             type <id> <类型> | spec <id> <特种> | unspec <id> <特种> [idx]
             set <id> <字段> <值>
  绑定/实体: bind <id> <类型> | bindInfo | create-type <原型> [新名]
             create-spec <原型> [新名]
  本地化:    troopName <id> <文本> | brief <id> <文本> | full <实体> <文本>
  杂项:      refs [refs|uoc2|temp|orig](打开参考/数据/临时mod/原版包目录) | which
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from . import cards, entity_service, game_state, localize
from .entity_service import BindingStore
from .savefile import SaveSession, load_yaml, quick_load, quick_save
from .session import SessionContext

HELP_TEXT = """指令（<参数>为必填，[参数]可选）：

--- 存档 ---
open [存档名]            重新选择/打开存档（不带参则列出可选）
save | s                 把修改保存回 .usg
qs [后缀]                备份当前存档为 <存档名><后缀>.usg（默认 _quick）
ql [后缀]                从备份恢复
re                       重新从 .usg 加载（丢弃未保存修改）
exit                     退出

--- 声望 / 战区资产 ---
ptg <数量>               设定声望；ptg +N / ptg -N 在当前值上增减
st <代码> <a,total,turn> 战区资产：air/airArt/airRec/pb/supply/ss/nb
                         例：st air 2,0,2（每回合2次，不限总次数）

--- 卡牌（仅战役存档）---
cardList                 列出当前卡槽（1–5 为宽松范围，实际槽位数随难度）
cardAdd <卡牌类型> [位置] 添加卡；省略位置取第一个空槽；同位置会覆盖旧卡
cardBuy <卡牌类型> [位置] 购买卡：添加同时扣除卡牌费用，不允许覆盖
cardDel <位置|卡牌类型>   删除一张卡
cardUnused <位置|卡牌类型> 把卡设为未使用过（used: false，保留 unit_id）
                         添加时 unit_id 恒为 null；
                         添加的卡阵营与战役阵营不符时需二次确认

--- 单位 ---
find <关键字>            按名称/本地化id/type 查单位，列出候选 id
select <id>              选中单位作为后续命令的默认对象（可省略 id）
xp [id] <值>             经验值（0-400）
str [id] <活跃> [压制]    战力：活跃战力 act_st，压制 sup_st（合计>7 时提示）
type [id] <类型>         单位类型
spec [id] <特种名>       给单位挂特种（同名可重复挂）
unspec [id] <特种名> [idx] 移除特种；同名多条时只卸一条（默认第一条）
set <id> <字段> <值>     改任意字段（如 set 27 losses 0）

--- 实体/绑定 ---
create-type <原型> [新名] [--model-from <包|路径>]
                          以原版单位为原型克隆新单位类型到 temp mod
                          --model-from 指定模型 meta 来源：base/dlc1/... 或路径
                          （包目录或直接的 *_meta.yml；路径可用引号包裹空格）
create-spec <原型> [新名]   以原版特种为原型克隆新特种
bind <id> <类型>            绑定：单位 → 类型（写入绑定文件并应用）
bindInfo                    列出当前绑定
rename <旧名> <新名>        重命名 temp mod 实体（同步文件与绑定）
reu                         重新应用全部绑定（应对战役段脚本覆写）

--- 本地化 ---
troopName <id> <文本>       给单个单位改显示名（加 _custom 后缀）
brief <实体名|单位id> <文本> 改实体的简称（数字 id 需先 bind；实体名可直接改）
full <实体名> <文本>        改特种实体全称（如 full xxx_custom 新全称）

--- 其他 ---
refs [目标]                 打开参考目录：refs(默认)/uoc2/temp(临时 mod)/orig(原版包)
which                       显示当前存档与工作目录
help | h                    本帮助
"""

_ARG_RE = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')


def split_command(line: str) -> list[str]:
    """按空白分词，并支持用引号包裹含空格的参数（如 Windows 绝对路径）。

    不处理反斜杠转义，避免破坏 Windows 路径。
    """
    tokens = []
    for m in _ARG_RE.findall(line):
        if len(m) >= 2 and m[0] == m[-1] and m[0] in "\"'":
            tokens.append(m[1:-1])
        else:
            tokens.append(m)
    return tokens


# help 中列出的短别名：dispatch 以 "cmd_<名>" 查方法，类属性别名不会被命中，
# 故在此统一映射（同时覆盖旧命令名）。
COMMAND_ALIASES = {
    "s": "save",
    "h": "help",
    "quickSave": "qs",
    "quickLoad": "ql",
    "editUnit": "create-type",
    "editSpec": "create-spec",
    "bindType": "bind",
    "setUnit": "set",
}


class CommandError(Exception):
    pass


class Repl:
    """命令分发器。持有当前存档会话（可切换）。"""

    def __init__(self, config, select_first: bool = True):
        self.config = config
        self._ctx: Optional[SessionContext] = None
        self._translations = None

    @property
    def ctx(self) -> SessionContext:
        """当前存档会话；未打开时抛 CommandError。

        以 property 访问取代各处 None 判空：handler 只要用到 ctx，
        未打开存档就会得到明确报错并被 dispatch 捕获。
        """
        if self._ctx is None:
            raise CommandError("当前未打开存档，先使用 open 选择存档。")
        return self._ctx

    @ctx.setter
    def ctx(self, value: SessionContext) -> None:
        self._ctx = value

    # ---- 翻译（懒加载） ----
    @property
    def translations(self):
        if self._translations is None:
            from .translations import TranslationStore
            self._translations = TranslationStore(
                self.config.orig_packages, self.config.locale)
        return self._translations

    # ---- 存档选择 ----
    def list_primary_saves(self) -> list:
        from .savefile import primary_saves, scan_all_saves
        return primary_saves(scan_all_saves(
            self.config.campaigns_dir, self.config.games_dir))

    def _find_by_name(self, name: str):
        """在战役/场景目录中按名称找主存档；找到返回 SaveFile，否则 None。"""
        from .savefile import SaveFile, detect_save_kind
        for d in (self.config.campaigns_dir, self.config.games_dir):
            p = d / f"{name}.usg"
            if p.exists():
                return SaveFile(p, kind=detect_save_kind(p))
        return None

    def open_save(self, name: Optional[str] = None) -> bool:
        """打开存档。name 为 None 时列出可选让用户输入。

        同时支持战役（save/campaigns）与独立场景（save/games）两类存档：
        列表合并展示并标注类型；按名称打开时先精确匹配，再退回
        “列出可选”的交互流程。
        """
        from .savefile import SaveFile
        saves = self.list_primary_saves()
        # 无任何存档时不进入交互（避免把“选错目录”伪装成可选）
        if not saves:
            print(f"在 {self.config.campaigns_dir} 与 {self.config.games_dir} "
                  "未找到主存档 (.usg)。")
            print("请确认游戏数据目录配置正确。")
            return False

        def _describe(index: int, s: SaveFile) -> str:
            tag = "场景" if s.kind == "standalone" else "战役"
            return f"  {index}. {s.name}  ({tag}存档)"

        chosen = None
        if name:
            chosen = next((s for s in saves if s.name == name), None)
            if chosen is None:
                # 允许带编号/后缀的手动档（备份）作为目标
                chosen = self._find_by_name(name)
            if chosen is None:
                print(f"未找到存档 {name}")
                return False
        else:
            print("可用的存档：")
            for i, s in enumerate(saves, 1):
                print(_describe(i, s))
            print("  (或输入完整文件名) ")
            inp = input("选择序号或名称 > ").strip()
            if inp.isdigit() and 1 <= int(inp) <= len(saves):
                chosen = saves[int(inp) - 1]
            elif inp:
                chosen = next((s for s in saves if s.name == inp), None)
                if chosen is None:
                    chosen = self._find_by_name(inp)
            if chosen is None:
                print("未选择有效存档。")
                return False

        # 装配会话
        session = SaveSession(self.config, chosen)
        self.ctx = SessionContext(
            session=session,
            config=self.config,
            translations=self.translations,
            bindings=BindingStore(self.config.save_dir_for(session.name)),
        )
        # 记住上次（写到 modifier_root/last_save.txt）
        try:
            last = self.config.modifier_root / "last_save.txt"
            last.parent.mkdir(parents=True, exist_ok=True)
            last.write_text(session.name, encoding="utf-8")
        except OSError:
            pass
        print(f"当前存档: {session.name}")
        return True

    def auto_open_last(self) -> bool:
        """若存在 last_save.txt 且对应存档在，自动打开。"""
        last = self.config.modifier_root / "last_save.txt"
        if last.exists():
            name = last.read_text(encoding="utf-8").strip()
            if name:
                return self.open_save(name)
        return False

    # ---- 命令分发 ----
    def dispatch(self, line: str) -> bool:
        """处理一行输入。返回 False 表示应退出。"""
        parts = split_command(line)
        if not parts:
            return True
        cmd, args = parts[0], parts[1:]
        cmd = COMMAND_ALIASES.get(cmd, cmd)
        try:
            # 未打开存档时只放行无需会话的命令
            if self._ctx is None and cmd not in (
                "open", "help", "h", "exit", "quit", "save"
            ):
                raise CommandError("当前未打开存档，先使用 open 选择存档。")
            # 命令名中的连字符映射为下划线以匹配方法名
            method_name = "cmd_" + cmd.replace("-", "_")
            handler = getattr(self, method_name, None)
            if handler is None:
                print(f"未知指令: {cmd}（输入 help 查看指令）")
                return True
            return bool(handler(args))
        except (CommandError, cards.CardError) as e:
            print(f"错误: {e}")
            return True
        except Exception as e:  # noqa: BLE001 命令层兜底，避免一次报错退出
            import traceback
            traceback.print_exc()
            print(f"执行出错: {e}")
            return True

    # ---- 各命令实现 ----
    def cmd_help(self, args) -> bool:
        print(HELP_TEXT)
        return True

    h = cmd_help

    def cmd_open(self, args) -> bool:
        name = args[0] if args else None
        self.open_save(name)
        return True

    def cmd_save(self, args) -> bool:
        self.ctx.session.commit()
        return True

    s = cmd_save

    def cmd_exit(self, args) -> bool:
        return False

    def cmd_quit(self, args) -> bool:
        return False

    def cmd_re(self, args) -> bool:
        self.ctx.session.reload()
        # 重建 units 与重应用绑定
        self.ctx.units.load()
        self.ctx.reapply_bindings(verbose=False)
        print("已重新加载。")
        return True

    def cmd_reu(self, args) -> bool:
        n = self.ctx.reapply_bindings(verbose=True)
        print(f"已应用 {n} 处绑定。")
        return True

    def cmd_qs(self, args) -> bool:
        suffix = args[0] if args else "_quick"
        if not suffix.startswith("_"):
            suffix = "_" + suffix
        target = quick_save(self.ctx.session, suffix)
        print(f"已备份: {target.name}" if target else "备份失败。")
        return True

    quickSave = cmd_qs

    def cmd_ql(self, args) -> bool:
        suffix = args[0] if args else "_quick"
        if not suffix.startswith("_"):
            suffix = "_" + suffix
        quick_load(self.ctx.session, suffix)
        self.ctx.units.load()
        self.ctx.reapply_bindings(verbose=False)
        return True

    quickLoad = cmd_ql

    # --- 声望/资产 ---
    def cmd_ptg(self, args) -> bool:
        """ptg <数量> 绝对赋值；ptg +N / ptg -N 在当前值上增减。"""
        raw = args[0] if args else ""
        if raw.startswith(("+", "-")) and raw[1:].isdigit():
            current = game_state.get_prestige(self.ctx.session) or 0
            game_state.set_prestige(self.ctx.session, current + int(raw))
            return True
        if raw.isdigit():
            game_state.set_prestige(self.ctx.session, int(raw))
            return True
        print("用法: ptg <数量>（前缀 + / - 表示增减）")
        return True

    prestige = cmd_ptg

    def cmd_st(self, args) -> bool:
        if len(args) < 2:
            print("用法: st <代码> <to_use,total,turn>  例: st air 2,0,2")
            return True
        alias = args[0]
        try:
            vals = [int(x) for x in args[1].split(",")]
        except ValueError:
            print("参数需为逗号分隔的三个整数。")
            return True
        if len(vals) != 3:
            print("需要 3 个数值: to_use,total,turn")
            return True
        game_state.set_theater_asset(self.ctx.session, alias, *vals)
        return True

    setTheaterAssets = cmd_st

    # --- 卡牌（仅战役存档） ---

    def _card_list(self) -> "cards.CardList":
        return cards.CardList(self.ctx.session)

    def _card_catalog(self) -> dict:
        return cards.load_card_catalog(self.config)

    def _card_title(self, card_type: str, catalog: dict) -> str:
        """卡牌的中文标题 + 类型名；无翻译时退回类型名。"""
        entry = catalog.get(card_type) or {}
        title = (entry.get("data") or {}).get("title")
        name = self.translations.get(title) if title else ""
        return f"{name}（{card_type}）" if name else str(card_type)

    def _confirm(self, prompt: str) -> bool:
        """REPL 内的二次确认；非交互输入（EOF）视为取消。"""
        try:
            ans = input(f"{prompt} [y/N] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return ans in ("y", "yes", "是")

    def _faction_ok(self, card_type: str, catalog: dict) -> bool:
        """软校验：卡牌阵营与战役扮演阵营不符时要求二次确认。

        战役阵营来自 document/main.yml 的 player_faction；读不到、或包中
        没有该卡牌定义时只提示，不拦截。
        """
        entry = catalog.get(card_type)
        if entry is None:
            print(f"提示：包中未找到卡牌定义 {card_type}，跳过阵营校验。")
            return True
        data = entry.get("data") or {}
        raw_faction = data.get("faction")
        if not raw_faction:
            print(f"提示：卡牌 {card_type} 缺少 faction 字段（异常数据），"
                  "跳过阵营校验。")
            return True
        card_faction = cards.card_faction(data)
        campaign = cards.campaign_faction(self.ctx.session.work_dir)
        if campaign is None:
            print("提示：未读到战役阵营（document/main.yml 的 player_faction），"
                  "跳过阵营校验。")
            return True
        if card_faction == campaign:
            return True
        return self._confirm(
            f"警告：卡牌 {card_type} 属于{cards.faction_label(card_faction)}"
            f"（{card_faction}），本战役扮演的是{cards.faction_label(campaign)}"
            f"（{campaign}）。确定仍要添加？")

    def _resolve_card(self, raw: str, card_list: "cards.CardList"):
        """按位置（纯数字）或卡牌类型定位一张现有卡；找不到时打印并返回 None。"""
        if raw.isdigit():
            card = card_list.find_position(int(raw))
            if card is None:
                print(f"槽位 {raw} 没有卡牌。")
            return card
        card = card_list.find_by_type(raw)
        if card is None:
            print(f"当前没有卡牌 {raw}。")
        return card

    def cmd_cardList(self, args) -> bool:
        card_list = self._card_list()
        catalog = self._card_catalog()
        if not card_list.cards:
            print("当前没有卡牌。")
        else:
            print(f"当前卡牌（{len(card_list.cards)} 张）：")
            for c in card_list.cards:
                traits = []
                if c.get("used"):
                    traits.append("已使用")
                if c.get("is_free"):
                    traits.append("免费")
                if c.get("unit_id") is not None:
                    traits.append(f"unit_id={c.get('unit_id')}")
                suffix = f"（{'，'.join(traits)}）" if traits else ""
                print(f"  槽位 {c.get('position')}: "
                      f"{self._card_title(c.get('card_type'), catalog)}{suffix}")
        free = [p for p in range(1, cards.CARD_SLOTS_MAX + 1)
                if card_list.find_position(p) is None]
        print(f"空槽位（宽松范围 1–{cards.CARD_SLOTS_MAX}，实际槽位数随难度）："
              f"{'、'.join(map(str, free)) if free else '无'}")
        return True

    def _add_card(self, args, buy: bool) -> bool:
        """cardAdd / cardBuy 的共同实现：buy=True 时扣费且禁止覆盖。"""
        usage = ("cardBuy <卡牌类型> [位置]" if buy
                 else "cardAdd <卡牌类型> [位置]")
        if not args:
            print(f"用法: {usage}")
            return True
        card_type = args[0]
        card_list = self._card_list()
        catalog = self._card_catalog()
        if len(args) > 1:
            pos = cards.parse_position(args[1])
        else:
            pos = card_list.empty_position()
            if pos is None:
                print(f"没有空卡槽（宽松范围 1–{cards.CARD_SLOTS_MAX}）；"
                      "请指定要覆盖的位置，或先删除一张卡。")
                return True

        existing = card_list.find_position(pos)
        if buy:
            if existing is not None:
                print(f"槽位 {pos} 已有卡牌 {existing.get('card_type')}，"
                      "购买不允许覆盖；先删除或改用 cardAdd。")
                return True
            entry = catalog.get(card_type)
            if entry is None:
                raise cards.CardError(
                    f"无法确定 {card_type} 的购买费用：包中未找到该卡牌定义。")
            cost = (entry.get("data") or {}).get("cost")
            if not isinstance(cost, int):
                raise cards.CardError(f"卡牌 {card_type} 没有可用的费用字段。")

        if not self._faction_ok(card_type, catalog):
            print("已取消，未写入存档。")
            return True

        if buy:
            current = game_state.get_prestige(self.ctx.session) or 0
            if current < cost:
                print(f"声望不足：卡牌费用 {cost}，当前声望 {current}。")
                return True

        if existing is not None:
            print(f"覆盖槽位 {pos} 上的卡牌 {existing.get('card_type')}。")
        card_list.put(cards.build_card(card_type, pos))
        print(f"{'已购买' if buy else '已添加'}卡牌 "
              f"{self._card_title(card_type, catalog)} 到槽位 {pos}。")
        if buy:
            game_state.set_prestige(self.ctx.session, current - cost)
            print(f"已扣除 {cost} 声望，当前声望 {current - cost}。")
        return True

    def cmd_cardAdd(self, args) -> bool:
        return self._add_card(args, buy=False)

    def cmd_cardBuy(self, args) -> bool:
        return self._add_card(args, buy=True)

    def cmd_cardDel(self, args) -> bool:
        if not args:
            print("用法: cardDel <位置|卡牌类型>")
            return True
        card_list = self._card_list()
        card = self._resolve_card(args[0], card_list)
        if card is None:
            return True
        pos = int(card.get("position") or 0)
        removed = card_list.remove(pos)
        if removed is None:
            print(f"槽位 {pos} 未找到可删除的卡牌，未修改存档。")
            return True
        print(f"已删除槽位 {pos} 的卡牌 "
              f"{self._card_title(removed.get('card_type'), self._card_catalog())}。")
        return True

    def cmd_cardUnused(self, args) -> bool:
        if not args:
            print("用法: cardUnused <位置|卡牌类型>")
            return True
        card_list = self._card_list()
        card = self._resolve_card(args[0], card_list)
        if card is None:
            return True
        if card.get("used") is False:
            print(f"槽位 {card.get('position')} 的卡牌本来就是未使用状态。")
            return True
        card["used"] = False
        card_list.persist()
        print(f"槽位 {card.get('position')} 的卡牌已设为未使用过（used: false）。")
        return True

    # --- 单位 ---
    def cmd_find(self, args) -> bool:
        if not args:
            print("用法: find <关键字>（中文名/本地化id/type）")
            return True
        results = self.ctx.units.find_by_name(args[0], self.translations)
        if not results:
            print(f"未找到匹配 '{args[0]}' 的单位。")
            return True
        print(f"匹配 {len(results)} 个单位：")
        for u in results[:40]:
            brief = u.get("name_brief", "")
            name = self.translations.get(brief) or brief
            print(f"  id={u.get('id'):<5} type={u.get('type'):<18} {name}")
        if len(results) > 40:
            print(f"... 共 {len(results)} 条，仅显示前 40。")
        return True

    def cmd_select(self, args) -> bool:
        if not args or not args[0].isdigit():
            print("当前无选中单位。用法: select <id>")
            return True
        uid = int(args[0])
        u = self.ctx.units.get(uid)
        if u is None:
            print(f"单位 {uid} 不在 units.yml。")
            return True
        self.ctx.selected_unit = uid
        brief = u.get("name_brief", "")
        name = self.translations.get(brief) or brief
        print(f"已选中单位 {uid}: {name} (type={u.get('type')}, "
              f"act_st={u.get('act_st')}, xp={u.get('xp')})")
        return True

    def cmd_xp(self, args) -> bool:
        uid, rest = self._resolve_field_id(args, nvalue=1)
        if uid is None or not rest or not rest[0].isdigit():
            print("用法: xp <id> <值>  或 (选中后) xp <值>")
            return True
        self.ctx.units.set_xp(uid, int(rest[0]))
        return True

    def cmd_str(self, args) -> bool:
        uid, rest = self._resolve_field_id(args, nvalue=2)
        if uid is None or not rest:
            print("用法: str <id> <活跃> [压制]  或 (选中后) str <活跃> [压制]")
            return True
        try:
            act = int(rest[0])
            sup = int(rest[1]) if len(rest) > 1 else None
        except ValueError:
            print("战力需为整数。")
            return True
        self.ctx.units.set_strength(uid, act, sup)
        return True

    strength = cmd_str

    def cmd_type(self, args) -> bool:
        uid, rest = self._resolve_field_id(args, nvalue=1)
        if uid is None or not rest:
            print("用法: type <id> <类型>  或 (选中后) type <类型>")
            return True
        self.ctx.units.set_type(uid, rest[0])
        return True

    def cmd_spec(self, args) -> bool:
        uid, rest = self._resolve_field_id(args, nvalue=1)
        if uid is None or not rest:
            print("用法: spec <id> <特种名>  或 (选中后) spec <特种名>")
            return True
        self.ctx.units.add_spec(uid, rest[0])
        return True

    specToUnit = cmd_spec

    def cmd_unspec(self, args) -> bool:
        """unspec 支持可选的 idx，用于同名特种只卸一条。

        三种写法：unspec <id> <特种名> [idx] / (选中后) unspec <特种名> [idx]。
        不写 idx 时移除该类型的第一条。
        """
        uid, rest = self._resolve_field_id(args, nvalue=1)
        if uid is None and self.ctx.selected_unit is not None \
                and len(args) == 2 and args[1].isdigit():
            # 选中单位 + “特种名 idx” 形式，_resolve_field_id 会误判，这里补上
            uid, rest = self.ctx.selected_unit, args
        if uid is None or not rest:
            print("用法: unspec <id> <特种名> [idx]  或 (选中后) unspec <特种名> [idx]")
            return True
        idx = None
        if len(rest) >= 2 and rest[1].isdigit():
            idx = int(rest[1])
        self.ctx.units.remove_spec(uid, rest[0], idx)
        return True

    def _resolve_field_id(self, args: list[str], nvalue: int):
        """高频字段命令的 id 解析。

        两种形式：
          1) 无选中单位：必须写 <id> <值...>，args[0] 是 id；
          2) 有选中单位且参数个数恰好是值的个数（或更少，如 str 可省略压制）：
             第一个参数解释为值，作用于选中单位。
        返回 (uid, 剩余参数=值部分)。uid 为 None 表示参数不足以解析。
        """
        sel = self.ctx.selected_unit
        # 有选中单位且首参不是“明显多值”（即 args 长度 <= nvalue）=> 值是首参
        if sel is not None and args and len(args) <= nvalue:
            # 若首参是数字且后面还有值（如 str 6 0：nvalue=2, args=[6,0]）也走这里
            return sel, args
        # 否则首参应为 id
        if args and args[0].isdigit():
            return int(args[0]), args[1:]
        return None, []

    def cmd_set(self, args) -> bool:
        if len(args) < 3:
            print("用法: set <id> <字段> <值>  例: set 27 losses 0")
            return True
        try:
            uid = int(args[0])
        except ValueError:
            print("id 需为数字。")
            return True
        raw = args[2]
        value: object
        try:
            value = int(raw)
        except ValueError:
            value = raw
        self.ctx.units.set_field(uid, args[1], value)
        return True

    setUnit = cmd_set

    # --- 实体/绑定 ---
    def cmd_create_type(self, args) -> bool:
        positional: list[str] = []
        model_from: Optional[str] = None
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("--model-from", "-m"):
                if i + 1 >= len(args):
                    print("--model-from 需要一个值（包名或路径）。")
                    return True
                model_from = args[i + 1]
                i += 2
            elif a.startswith("--model-from="):
                model_from = a.split("=", 1)[1]
                i += 1
            else:
                positional.append(a)
                i += 1
        if not positional:
            print("用法: create-type <原型类型> [新类型名] "
                  "[--model-from <base|dlc1|...|路径>]")
            return True
        prototype = positional[0]
        new_name = positional[1] if len(positional) > 1 else None
        campaign = self._campaign_id()
        entity_service.create_type_from_prototype(
            self.config, self.ctx.session, campaign, prototype,
            new_name=new_name, kind="unit", model_from=model_from, verbose=True)
        return True

    editUnit = cmd_create_type

    def cmd_create_spec(self, args) -> bool:
        if any(a in ("--model-from", "-m") or a.startswith("--model-from=")
               for a in args):
            print("提示：create-spec 不支持 --model-from（特种实体没有模型 meta），"
                  "该参数将被忽略。")
            cleaned: list[str] = []
            skip_next = False
            for a in args:
                if skip_next:
                    skip_next = False
                    continue
                if a in ("--model-from", "-m"):
                    skip_next = True
                    continue
                if a.startswith("--model-from="):
                    continue
                cleaned.append(a)
            args = cleaned
        if not args:
            print("用法: create-spec <原型特种> [新名]")
            return True
        campaign = self._campaign_id()
        entity_service.create_type_from_prototype(
            self.config, self.ctx.session, campaign, args[0],
            new_name=args[1] if len(args) > 1 else None,
            kind="specialist", verbose=True)
        return True

    editSpec = cmd_create_spec

    def cmd_bind(self, args) -> bool:
        if len(args) < 2 or not args[0].isdigit():
            print("用法: bind <单位id> <类型>  例: bind 27 inf_02_custom")
            return True
        entity_service.bind_unit_to_type(
            self.ctx.session, self.ctx.units, self.ctx.bindings,
            int(args[0]), args[1])
        return True

    bindType = cmd_bind

    def cmd_bindInfo(self, args) -> bool:
        items = list(self.ctx.bindings.items())
        if not items:
            print("当前无绑定。")
            return True
        print("单位类型绑定：")
        for uid, tname in items:
            u = self.ctx.units.get(uid)
            if u:
                brief = u.get("name_brief", "")
                name = self.translations.get(brief) or brief
                print(f"  id={uid:<5} {name} -> {tname}")
            else:
                print(f"  id={uid:<5} (不在当前 units.yml) -> {tname}")
        return True

    # --- 本地化 ---
    def cmd_troopName(self, args) -> bool:
        if len(args) < 2 or not args[0].isdigit():
            print("用法: troopName <id> <文本>")
            return True
        uid = int(args[0])
        u = self.ctx.units.get(uid)
        if u is None:
            print(f"单位 {uid} 不在 units.yml。")
            return True
        text = " ".join(args[1:])
        localize.localize_unit_name_brief(self.ctx.session, u, uid, text)
        self.ctx.units.persist()
        return True

    def cmd_brief(self, args) -> bool:
        # brief <实体名|单位id> <文本>：改实体的简称
        if len(args) < 2:
            print("用法: brief <实体名|单位id> <文本>")
            return True
        if args[0].isdigit():
            # 数字 id：改绑定单位对应的实体简称
            uid = int(args[0])
            tname = self.ctx.bindings.get(uid)
            if tname is None:
                print(f"单位 {uid} 没有绑定类型，先使用 bind。")
                return True
            ent = self._load_bound_entity(tname)
            if ent is None:
                return True
        else:
            # 实体名：直接改该实体（spec/unit 通用）
            ent = self._load_entity(args[0])
            if ent is None:
                return True
        localize.localize_entity_text(self.ctx.session, ent, " ".join(args[1:]),
                                      field="brief")
        return True

    def cmd_full(self, args) -> bool:
        # full <实体名> <文本>（特种）或 full <id> <文本>
        if len(args) < 2:
            print("用法: full <实体名|单位id> <文本>")
            return True
        if args[0].isdigit():
            uid = int(args[0])
            tname = self.ctx.bindings.get(uid)
            if tname is None:
                print(f"单位 {uid} 没有绑定类型。")
                return True
            ent = self._load_bound_entity(tname)
            if ent is None:
                return True
        else:
            ent = self._load_entity(args[0])
            if ent is None:
                return True
        localize.localize_entity_text(self.ctx.session, ent, " ".join(args[1:]),
                                      field="full")
        return True

    def cmd_rename(self, args) -> bool:
        """rename <旧名> <新名>：重命名 temp mod 中的实体。

        同步改名 type/meta/surfaces 文件、更新 name id，并把绑定文件中
        引用旧名的记录改为新名。
        """
        if len(args) < 2:
            print("用法: rename <旧实体名> <新实体名>")
            return True
        old, new = args[0], args[1]
        ent = self._load_entity(old)
        if ent is None:
            return True
        ok = ent.rename_entity(new, verbose=True)
        if not ok:
            return True
        # 同步绑定文件
        updated = False
        for uid, tname in list(self.ctx.bindings.items()):
            if tname == old:
                self.ctx.bindings.set(uid, new)
                print(f"绑定已更新: 单位 {uid} -> {new}")
                updated = True
        if not updated:
            print("无绑定引用旧名。")
        return True

    def _campaign_id(self) -> str:
        main = load_yaml(self.ctx.session.work_dir / "main.yml")
        return main.get("campaign_id", "base")

    def _load_bound_entity(self, tname: str):
        """从 temp mod 加载绑定类型对应的实体（unit 优先，退回 specialist）。"""
        from .entities import load_entity
        mod = self.config.temp_mod_dir_for(self.ctx.session.name)
        for kind in ("unit", "specialist"):
            try:
                return load_entity(mod, tname, kind, verbose=False)
            except FileNotFoundError:
                continue
        print(f"在 temp mod 中未找到实体 {tname}（先使用 create-type/create-spec）。")
        return None

    def _load_entity(self, name: str):
        from .entities import load_entity
        mod = self.config.temp_mod_dir_for(self.ctx.session.name)
        for kind in ("unit", "specialist"):
            try:
                return load_entity(mod, name, kind, verbose=False)
            except FileNotFoundError:
                continue
        print(f"在 temp mod 中未找到实体 {name}。")
        return None

    # --- 杂项 ---
    # refs 子目标：(显示名, 路径来源)
    REFS_TARGETS = {
        "refs": ("参考列表目录", "refs"),
        "uoc2": (".uoc2 目录", "uoc2"),
        "temp": ("临时 mod 目录", "temp"),
        "orig": ("原版包目录", "orig"),
    }
    REFS_ALIASES = {
        "ref": "refs",
        "reference": "refs",
        "appdata": "uoc2",
        ".uoc2": "uoc2",
        "mod": "temp",
        "packages": "orig",
        "original": "orig",
    }

    def cmd_refs(self, args) -> bool:
        """打开参考目录：refs [refs|uoc2|temp|orig]。"""
        key = args[0].lower() if args else "refs"
        key = self.REFS_ALIASES.get(key, key)
        if key not in self.REFS_TARGETS:
            print("用法: refs [refs|uoc2|temp|orig]")
            print("  refs         参考列表目录（单位/总部/卡牌 txt）")
            print("  refs uoc2    .uoc2 数据目录")
            print("  refs temp    本存档的临时 mod 目录（_packages/<存档>_temp）")
            print("  refs orig    脚本使用的原版包搜索路径")
            return True

        label, kind = self.REFS_TARGETS[key]
        name = self.ctx.session.name
        if kind == "refs":
            path = self.config.save_dir_for(name) / "references"
        elif kind == "uoc2":
            path = self.config.uoc2_appdata
        elif kind == "temp":
            path = self.config.temp_mod_dir_for(name)
        else:
            path = self.config.orig_packages

        if path is None:
            print(f"{label}未配置（config.yml 的 uoc2_orig_packages_path 为空且未探测到）。")
            return True
        path = Path(path)
        if kind == "refs" and path.is_dir():
            # 早期生成的参考目录可能缺少卡牌列表，打开前补齐
            cards.generate_card_reference_if_missing(
                self.config, path / cards.CARD_REF_DIRNAME,
                self.translations)
        if not path.exists():
            if kind == "refs":
                print("参考列表尚未生成。")
            else:
                print(f"{label}不存在: {path}")
            return True
        os.startfile(path)  # 仅 Windows 提供该函数
        print(f"已打开{label}: {path}")
        return True

    def cmd_which(self, args) -> bool:
        ctx = self.ctx
        print(f"存档: {ctx.session.name}")
        print(f"状态目录: {self.config.state_dir}")
        print(f"工作目录: {ctx.session.work_dir}")
        print(f"临时 mod: {self.config.temp_mod_dir_for(ctx.session.name)}")
        print(f"绑定文件: {ctx.bindings.path}")
        return True


def run_repl(config, repl: Optional[Repl] = None, skip_open: bool = False) -> None:
    """启动 REPL 主循环。

    repl: 可复用的 Repl 实例；为 None 时新建。
    skip_open: 若已预先 open 过存档，设为 True 跳过自动打开。
    """
    if repl is None:
        repl = Repl(config)
        skip_open = False
    if not skip_open:
        # 尝试自动打开上次存档；失败则列出
        if not repl.auto_open_last():
            print("未找到上次使用的存档，请选择：")
            repl.open_save(None)
    print("输入 help 查看指令。")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break
        if not line:
            continue
        if not repl.dispatch(line):
            print("再见。")
            break
