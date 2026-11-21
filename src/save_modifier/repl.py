"""自测入口 —— 对核心库 `save_modifier_core` 的命令行外壳。

**它不是产品界面。** 玩家用的是 GUI（另一个项目里的静态查看器），
这里只是给开发者/排查问题时用的终端入口：直接调用核心库的 8 个函数，
把中间结果（视图、diff、校验、撤销栈）打印出来。

旧版 REPL 里的这些能力**已经砍掉**（规范 §7.5、§0.3）：

| 砍掉的东西 | 为什么 |
|---|---|
| `create-type` / `create-spec`（新建单位/特种类型） | 要写游戏包，跨存档共享，**游戏内回退不掉** |
| `bind` / `bindInfo` / `reu`（类型绑定） | 同上 —— 绑定写的是 temp mod，不是存档 |
| `rename`（重命名 temp mod 实体） | 改名**直接写明文**（`name_brief` / `name_full`） |
| `troopName` / `brief` / `full`（本地化写入） | 同上 —— 不写 temp mod，不写本地化包 |
| `qs` / `ql`（快速存读档） | 产品决策：**不做**频繁存读档（§0.3、§7.5） |
| `type <id> <类型>`（改编制） | 硬约束：**不改单位编制**（§0.4） |

保留的只有"读"和"改存档本身"的部分 —— 而这些现在全部由核心库实现，
本模块只做**参数解析与打印**。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 允许直接 `python src/save_modifier/repl.py` 运行
if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from save_modifier_core import (Catalog, CorePaths, Edit, list_saves,  # noqa: E402
                                open_save, validate)

__all__ = ["run_repl", "Repl"]

HELP_TEXT = """自测入口（核心库的命令行外壳）：

--- 存档 ---
saves                        列出本机存档
open <序号|save_id>          打开存档
view                         当前存档概览（阶段 / 能力位 / 各表条目数）
caps                         只看能力位
units [关键字]               列出单位（可按 id / 名称 / type 过滤）
hqs                          列出总部
cards                        列出卡牌（根表 + 手里）
store                        列出商店
types [unit|spec|card|hq]    列出类型目录（候选值）

--- 编辑（先 plan，确认后再 commit）---
xp <单位id> <值>             经验值 0..400
st <单位id> <活跃> [压制]    战力 act_st / sup_st
name <单位id> <明文>         改显示名（**直接写明文**）
spec <单位id> <特种类型>      加特种
unspec <单位id> <类型> [idx]  卸特种
supspec <单位id> <类型> <0|1> [idx]  特种兵的压制（0=被压制 1=活跃）
pool <总部id> <条目序号> <数量>  总部兵库存量
ptg <值>                     声望
score <值>                   分数
card add <卡牌类型> [槽位]     加卡
card del <槽位>               删卡
store set <战线> <序号> <price|quantity> <值>   改商店条目
store del <战线> <序号>        下架商店条目（删条目）
hand                         恢复上次会议的牌局
asset <资产名> <可用次数> [总次数] [每回合]     战区资产（仅战斗中）

--- 写回 ---
plan                         显示上一次编辑的 diff 与校验结果
commit                       提交（备份 → 校验 → 原子替换，并压撤销栈）
undo                         撤销上一次提交（撤销前校验基准）
stack                        看撤销栈

--- 其他 ---
selftest                     核心库自检（能力位 / 类型表 / 往返无损）
refs                         生成名册参考表（单位/总部 → 临时目录，并打印路径）
paths                        显示探测到的路径
exit                         退出
"""

#: 战区资产的简写 → 存档里的真实资产名
ASSET_ALIASES = {
    "air": "air_attack",
    "airArt": "flying_artillery",
    "airRec": "long_range_recon",
    "pb": "precision_bombing",
    "supply": "air_supply",
    "ss": "saturation_strike",
    "nb": "naval_bombardment",
}


class ReplError(Exception):
    """命令用法错误。"""


class Repl:
    """极简命令行外壳。"""

    def __init__(self):
        self.paths = CorePaths.discover()
        self.catalog = Catalog(self.paths)
        self._save = None
        self._last_plan = None
        self._last_edits: list[Edit] = []
        self._translations = None

    # ---------------------------------------------------------------- 工具

    @property
    def translations(self):
        """游戏原版的本地化表（只读）—— 用来把 id 翻成中文名。"""
        if self._translations is None:
            from .translations import TranslationStore
            self._translations = TranslationStore(
                self.paths.game_packages_dir, "chi")
        return self._translations

    def _cn(self, text: str | None) -> str:
        """把本地化 id 翻成中文；翻不到就原样返回。"""
        if not text:
            return ""
        return self.translations.get(text) or text

    @property
    def save(self):
        if self._save is None:
            raise ReplError("当前未打开存档，先用 saves / open 选一个。")
        return self._save

    def close(self) -> None:
        if self._save is not None:
            self._save.close()
            self._save = None

    # ---------------------------------------------------------------- 命令

    def cmd_help(self, args) -> bool:
        print(HELP_TEXT)
        return True

    def cmd_exit(self, args) -> bool:
        self.close()
        return False

    def cmd_saves(self, args) -> bool:
        saves = [s for s in list_saves(self.paths) if s.is_primary]
        if not saves:
            print(f"在 {self.paths.save_root} 下没有找到 .usg")
            return True
        print(f"存档根目录: {self.paths.save_root}\n")
        for i, s in enumerate(saves, 1):
            tag = "场景" if s.is_standalone else "战役"
            print(f"  {i:2d}. {s.display_name}  [{tag}]  {s.save_id}")
        return True

    def cmd_open(self, args) -> bool:
        if not args:
            raise ReplError("用法: open <序号|save_id>")
        saves = [s for s in list_saves(self.paths) if s.is_primary]
        if not saves:
            raise ReplError("本机没有存档")
        target = None
        if args[0].isdigit():
            i = int(args[0])
            if not (1 <= i <= len(saves)):
                raise ReplError(f"序号超出范围（1..{len(saves)}）")
            target = saves[i - 1]
        else:
            target = next((s for s in saves if s.save_id == args[0]
                           or s.path.name == args[0]
                           or s.path.stem == args[0]), None)
            if target is None:
                raise ReplError(f"未找到存档 {args[0]}")
        self.close()
        self._save = open_save(target.save_id, self.paths)
        print(f"已打开: {target.display_name}  ({target.path})")
        return True

    def cmd_view(self, args) -> bool:
        v = self.save.view(self.catalog)
        print(f"阶段: {v.stage}")
        print(f"声望: {v.prestige}   分数: {v.score}")
        if v.battle_turn:
            print(f"当前战斗回合: {v.battle_turn}")
        print(f"能力位: {_caps_text(v.capabilities)}")
        print(f"单位 {len(v.units)}  总部 {len(v.hqs)}  "
              f"卡牌 {len(v.cards)}  手里 {len(v.hand)}  商店 {len(v.store)}")
        for w in v.warnings:
            print(f"⚠️ {w}")
        return True

    def cmd_caps(self, args) -> bool:
        print(_caps_text(self.save.capabilities()))
        return True

    def cmd_units(self, args) -> bool:
        v = self.save.view(self.catalog)
        key = args[0].lower() if args else ""
        for u in v.units:
            cn = self._cn(u.name_brief)
            label = f"{cn} {u.display_name}" if cn else u.display_name
            hay = f"{u.id} {u.type or ''} {label}".lower()
            if key and key not in hay:
                continue
            st = f"act={u.act_st} sup={u.sup_st}"
            if u.max_st is not None:
                st += f"/{u.max_st}"
            spec = ",".join(s.get("type", "?") for s in u.specs)
            print(f"  {u.id:4d}  {label[:28]:28s}  {u.type or '-':16s}  "
                  f"xp={u.xp}  {st}  spec=[{spec}]")
        return True

    def cmd_hqs(self, args) -> bool:
        v = self.save.view(self.catalog)
        for h in v.hqs:
            cn = self._cn(h.name_brief)
            label = f"{cn} {h.display_name}" if cn else h.display_name
            pool = ", ".join(
                f"{p.get('equipment') or p.get('spec')}×{p.get('quantity')}"
                for p in h.force_pool)
            print(f"  {h.id:4d}  {label[:28]:28s}  cp={h.cp}/{h.max_cp}  "
                  f"兵库[{pool}]")
        return True

    def cmd_cards(self, args) -> bool:
        v = self.save.view(self.catalog)
        for c in v.cards:
            print(f"  根表  槽{c.position}  {c.card_type}  "
                  f"{'免费' if c.is_free else '付费'}"
                  f"{'  已用' if c.used else ''}")
        for c in v.hand:
            print(f"  手里  槽{c.position}  {c.card_type}  "
                  f"{'免费' if c.is_free else '付费'}"
                  f"{'  已用' if c.used else ''}")
        if not v.cards and not v.hand:
            print("（没有卡牌）")
        return True

    def cmd_store(self, args) -> bool:
        v = self.save.view(self.catalog)
        if not v.store:
            print("（没有商店）")
            return True
        for i, e in enumerate(v.store):
            print(f"  {e.front:10s} {e.what:22s} 价 {e.price:4d}  库存 {e.quantity:4d}"
                  f"  {e.nationality or ''}")
        return True

    def cmd_types(self, args) -> bool:
        what = (args[0].lower() if args else "unit")
        table = {
            "unit": self.catalog.unit_type_names,
            "spec": self.catalog.spec_type_names,
            "card": self.catalog.card_type_names,
            "hq": self.catalog.hq_type_names,
        }.get(what)
        if table is None:
            raise ReplError("用法: types [unit|spec|card|hq]")
        names = table()
        print(f"{len(names)} 个：")
        for n in names:
            print(f"  {n}")
        return True

    # ---- 编辑 ----

    def cmd_xp(self, args) -> bool:
        uid, value = _int_args(args, 2, "xp <单位id> <值>")
        return self._plan([Edit.unit_field(uid, "xp", value)])

    def cmd_st(self, args) -> bool:
        if len(args) < 2:
            raise ReplError("用法: st <单位id> <活跃> [压制]")
        uid = _as_int(args[0], "单位 id")
        act = _as_int(args[1], "活跃战力")
        edits = [Edit.unit_field(uid, "act_st", act)]
        if len(args) > 2:
            edits.append(Edit.unit_field(uid, "sup_st", _as_int(args[2], "压制战力")))
        return self._plan(edits)

    def cmd_name(self, args) -> bool:
        if len(args) < 2:
            raise ReplError("用法: name <单位id> <明文>")
        uid = _as_int(args[0], "单位 id")
        text = " ".join(args[1:])
        return self._plan([Edit.unit_field(uid, "name_brief", text)])

    def cmd_spec(self, args) -> bool:
        if len(args) < 2:
            raise ReplError("用法: spec <单位id> <特种类型>")
        uid = _as_int(args[0], "单位 id")
        return self._plan([Edit.unit_spec_add(uid, args[1])])

    def cmd_unspec(self, args) -> bool:
        if len(args) < 2:
            raise ReplError("用法: unspec <单位id> <类型> [idx]")
        uid = _as_int(args[0], "单位 id")
        idx = _as_int(args[2], "idx") if len(args) > 2 else None
        return self._plan([Edit.unit_spec_remove(uid, args[1], idx)])

    def cmd_supspec(self, args) -> bool:
        """特种兵的「被压制」状态（0 = 被压制，1 = 活跃）。"""
        if len(args) < 3:
            raise ReplError(
                "用法: supspec <单位id> <类型> <0|1> [idx]（0=被压制 1=活跃）")
        uid = _as_int(args[0], "单位 id")
        flag = args[2]
        if flag not in ("0", "1"):
            raise ReplError("第三个参数只能是 0（被压制）或 1（活跃）")
        idx = _as_int(args[3], "idx") if len(args) > 3 else None
        return self._plan([Edit.unit_spec_active(uid, args[1], idx, flag == "1")])

    def cmd_pool(self, args) -> bool:
        if len(args) < 3:
            raise ReplError("用法: pool <总部id> <条目序号> <数量>")
        hq = _as_int(args[0], "总部 id")
        idx = _as_int(args[1], "条目序号")
        qty = _as_int(args[2], "数量")
        return self._plan([Edit.hq_force_pool(hq, idx, qty)])

    def cmd_ptg(self, args) -> bool:
        value, = _int_args(args, 1, "ptg <值>")
        return self._plan([Edit.progress("prestige", value)])

    def cmd_score(self, args) -> bool:
        value, = _int_args(args, 1, "score <值>")
        return self._plan([Edit.progress("score", value)])

    def cmd_card(self, args) -> bool:
        if not args:
            raise ReplError("用法: card add <卡牌类型> [槽位] | card del <槽位>")
        act = args[0].lower()
        if act == "add":
            if len(args) < 2:
                raise ReplError("用法: card add <卡牌类型> [槽位]")
            pos = _as_int(args[2], "槽位") if len(args) > 2 else None
            return self._plan([Edit.card_add(args[1], position=pos)])
        if act == "del":
            if len(args) < 2:
                raise ReplError("用法: card del <槽位>")
            return self._plan([Edit.card_remove(_as_int(args[1], "槽位"))])
        raise ReplError(f"未知 card 子命令 {args[0]}（add / del）")

    def cmd_store_set(self, args) -> bool:
        # ⚠️ U116：商店是**两层**结构（`store.yml` = 战线 → {store, elite_store}）
        # ⇒ 核心库签名是 (front, sub, index, field, value) —— 以前这里**少传 sub**
        # ⇒ 一敲就 TypeError。sub 可省（默认普通商店 `store`）。
        if len(args) < 4:
            raise ReplError(
                "用法: store set <战线> <序号> <price|quantity> <值> [store|elite_store]")
        front = args[0]
        idx = _as_int(args[1], "条目序号")
        field = args[2]
        if field not in ("price", "quantity"):
            raise ReplError("字段只能是 price 或 quantity")
        value = _as_int(args[3], "值")
        sub = args[4] if len(args) > 4 else "store"
        if sub not in ("store", "elite_store"):
            raise ReplError("子商店只能是 store 或 elite_store")
        return self._plan([Edit.store_set(front, sub, idx, field, value)])

    def cmd_store_del(self, args) -> bool:
        if len(args) < 2:
            raise ReplError(
                "用法: store del <战线> <条目序号> [store|elite_store]")
        front = args[0]
        idx = _as_int(args[1], "条目序号")
        sub = args[2] if len(args) > 2 else "store"
        if sub not in ("store", "elite_store"):
            raise ReplError("子商店只能是 store 或 elite_store")
        return self._plan([Edit.store_remove(front, sub, idx)])

    def cmd_hand(self, args) -> bool:
        return self._plan([Edit.hand_restore()])

    def cmd_asset(self, args) -> bool:
        if len(args) < 2:
            raise ReplError(
                "用法: asset <资产名> <可用次数> [总次数] [每回合]")
        name = ASSET_ALIASES.get(args[0], args[0])
        to_use = _as_int(args[1], "可用次数")
        total = _as_int(args[2], "总次数") if len(args) > 2 else None
        # ⚠️ U116：每回合恢复必须 ≥ 1（游戏硬范围）⇒ 省略时取 1，
        # 以前传 0 ⇒ 必然被核心库拒（「uses_turn=0 必须是不小于 1 的整数」）。
        turn = _as_int(args[3], "每回合次数") if len(args) > 3 else 1
        return self._plan([Edit.theater_asset(
            name, to_use=to_use, uses_total=total, uses_turn=turn)])

    # ---- 写回 ----

    def cmd_plan(self, args) -> bool:
        if self._last_plan is None:
            print("（还没有待提交的编辑）")
            return True
        plan = self._last_plan
        print(plan.summary())
        for note in plan.notes:
            print(f"  · {note}")
        for change in plan.changes:
            print(f"\n--- {change.entry}（{change.layer}）---")
            print(change.diff)
        v = validate(plan)
        print(f"\n校验: {v.summary()}")
        for e in v.errors:
            print(f"  ❌ {e}")
        for w in v.warnings:
            print(f"  ⚠️ {w}")
        return True

    def cmd_commit(self, args) -> bool:
        if self._last_plan is None:
            raise ReplError("没有待提交的编辑。")
        if not self._last_plan.ok:
            raise ReplError("计划里有错误，先修掉再提交（看 plan）。")
        res = self.save.commit(self._last_plan)
        print(res.summary())
        for e in res.errors:
            print(f"  ❌ {e}")
        for w in res.warnings:
            print(f"  ⚠️ {w}")
        if res.ok:
            self._last_plan = None
            self._last_edits = []
            print(f"备份: {res.backup.name if res.backup else '—'}")
            print("撤销: undo")
        return True

    def cmd_undo(self, args) -> bool:
        res = self.save.undo()
        print(res.summary())
        for e in res.errors:
            print(f"  ❌ {e}")
        for w in res.warnings:
            print(f"  ⚠️ {w}")
        return True

    def cmd_stack(self, args) -> bool:
        from save_modifier_core.undo import load_stack, stack_path_for
        path = stack_path_for(self.save.path)
        records, errs = load_stack(self.save.path)
        for e in errs:
            print(f"⚠️ {e}")
        if not records:
            print("撤销栈是空的")
            return True
        print(f"撤销栈: {path}（{len(records)} 条）")
        for i, r in enumerate(records, 1):
            mark = "← 栈顶" if i == len(records) else ""
            print(f"  {i}. {r.time}  {r.summary}  [{', '.join(r.entry_names)}] {mark}")
        return True

    # ---- 其他 ----

    def cmd_refs(self, args) -> bool:
        """生成名册参考表（单位 / 总部）—— 写到临时目录并打印路径。"""
        import tempfile

        from save_modifier_core import yamlio

        from . import references

        doc_units = self.save.read_yaml("document/units.yml", [])
        doc_hqs = self.save.read_yaml("document/hqs.yml", [])
        if not isinstance(doc_units, list):
            doc_units = []
        if not isinstance(doc_hqs, list):
            doc_hqs = []

        tmp = Path(tempfile.mkdtemp(prefix="uoc2_refs_"))
        units_src = tmp / "units.yml"
        hqs_src = tmp / "hqs.yml"
        units_src.write_bytes(yamlio.dump(doc_units))
        hqs_src.write_bytes(yamlio.dump(doc_hqs))

        trans = self.translations
        references.generate_unit_reference(units_src, tmp / "units.txt", trans)
        references.generate_hq_reference(hqs_src, tmp / "hqs.txt", trans)
        print(f"参考表目录: {tmp}")
        return True

    def cmd_selftest(self, args) -> bool:
        from save_modifier_core import catalog as cat_mod
        print("核心库自检")
        print(f"  游戏目录: {self.paths.game_dir or '（未探测到）'}")
        print(f"  存档根目录: {self.paths.save_root}")
        units = self.catalog.unit_type_names()
        specs = self.catalog.spec_type_names()
        cards = self.catalog.card_type_names()
        hqs = self.catalog.hq_type_names()
        print(f"  类型表: 单位 {len(units)}  特种 {len(specs)}  "
              f"卡牌 {len(cards)}  总部 {len(hqs)}")
        if not units:
            print("  ⚠️ 没读到单位类型表 —— 战力上限校验会退化为软警告")
        saves = [s for s in list_saves(self.paths) if s.is_primary]
        print(f"  存档数: {len(saves)}")
        for s in saves[:3]:
            try:
                with open_save(s.save_id, self.paths) as sv:
                    caps = sv.capabilities()
                    print(f"    {s.display_name}: {_caps_text(caps)}")
            except Exception as exc:                      # noqa: BLE001
                print(f"    {s.display_name}: 打不开（{exc}）")
        _ = cat_mod
        return True

    def cmd_paths(self, args) -> bool:
        print(f"游戏目录: {self.paths.game_dir or '（未探测到）'}")
        print(f"存档根目录: {self.paths.save_root}")
        print(f"  战役: {self.paths.campaigns_dir}")
        print(f"  场景: {self.paths.games_dir}")
        print("  归档区（玩家自建，游戏不认）: "
              f"{[d.name for d in self.paths.archive_dirs()]}")
        print(f"用户包目录: {self.paths.user_packages_dir}")
        for p in self.paths.packages():
            print(f"  包: {p}")
        return True

    # ---------------------------------------------------------------- 内部

    def _plan(self, edits: list[Edit]) -> bool:
        """规划一批编辑并立刻显示 diff（**不碰磁盘**）。"""
        plan = self.save.plan_edit(edits, catalog=self.catalog)
        self._last_plan = plan
        self._last_edits = list(edits)
        if not plan.ok:
            print("❌ 计划有错误：")
            for e in plan.errors:
                print(f"  {e}")
            return True
        print(plan.summary())
        for note in plan.notes:
            print(f"  · {note}")
        for w in plan.warnings:
            print(f"  ⚠️ {w}")
        v = validate(plan)
        print(f"校验: {v.summary()}")
        print("（看 diff 用 plan；写入用 commit）")
        return True


def _caps_text(caps) -> str:
    """能力位的一行摘要。"""
    on = [name for name, value in vars(caps).items() if value]
    return " ".join(on) if on else "（全无）"


def _as_int(text: str, what: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        raise ReplError(f"{what} 必须是整数（收到 {text!r}）") from None


def _int_args(args, n: int, usage: str) -> tuple:
    if len(args) < n:
        raise ReplError(f"用法: {usage}")
    return tuple(_as_int(a, "参数") for a in args[:n])


def run_repl(argv: list[str] | None = None) -> int:
    """进入自测入口。"""
    repl = Repl()
    print("UOC2 存档修改器 —— 自测入口（核心库命令行外壳）")
    print("输入 help 看命令；exit 退出。\n")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split()
        cmd, args = parts[0], parts[1:]
        method = getattr(repl, "cmd_" + cmd.replace("-", "_"), None)
        if method is None:
            print(f"未知指令: {cmd}（help 看列表）")
            continue
        try:
            if not method(args):
                break
        except ReplError as exc:
            print(f"错误: {exc}")
        except Exception as exc:                          # noqa: BLE001
            import traceback
            traceback.print_exc()
            print(f"执行出错: {exc}")
    repl.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_repl(argv)


if __name__ == "__main__":  # pragma: no cover
    os.chdir(Path(__file__).resolve().parent.parent.parent)
    raise SystemExit(run_repl())
