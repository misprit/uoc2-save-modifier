"""e169 —— 「给手牌加空降/登陆卡 ⇒ 游戏读档崩溃」的取证。

**背景**：U187。2026-11-25 用户报：「用修改器直接给手牌赋予空降卡牌会崩溃，
我给霸王行动的手牌加了 82 空降师，但这关本来 82 空降师已经登场了」。
动手改之前，先把「哪些卡会召唤单位」「游戏自己怎么算『这个单位还能不能用』」
「存档里到底长什么样」这些**事实**钉死。

**结论（全部来自实测，不是推断）**

| 问题 | 答案 | 出处 |
|---|---|---|
| 游戏包里一共多少张卡？ | **39 张** | ① |
| 哪些卡「会召唤单位」？ | **恰好 10 张**，全是空降 / 登陆：`tactical_para_{german,polish,soviet,uk,us}`、`divisional_para_allies_{1,82,101}`、`tactical_naval_assault_{uk,us}`；其余 **29 张**是战区资产 / 补给 / 卡车 / HQ（`has_unit: false`）⇒ **`has_unit` 就是「会召唤单位」的权威标志** | ① |
| 游戏怎么算「已被召唤过的单位」？ | `Campaign.get_used_card_unit_ids()`（`campaign.pyc:1902`）= `used_card_types_with_unit` 里所有 id 的并集 | ② |
| 游戏怎么算「这个单位 id 被占了」？ | `Game.is_unit_id_referenced(unit_id)`（`game.pyc:845-848`）= 父类判定 **或** 「手牌（`campaign.card_deck`）里有没有卡引用这个 id」⇒ **同一个 id 既被「已召唤过」记录、又被手牌引用 ⇒ 冲突** | ② |
| 手牌加卡那条路上原本有几道护栏？ | **只有一道**：「本战役有没有为它登记可召唤的单位」（`document/main.yml.card_type_units`）—— **没查「那个单位是不是已经被召唤过」** | ③ |
| 货架（`card_store`）那侧为什么没事？ | 走 `card_whitelist`，它**本来就把**「已召唤过 / 手牌里已有同类型 / 本战役没登记 / 预留单位阵亡」全排除了 | ③ |
| 玩家存档里能直接看到冲突吗？ | 能：`campaigns/tester-cards.usg` 的手牌里 3 张召唤卡，它们的 `unit_id` **全部**已在 `used_card_types_with_unit` 里，且对应单位**已在 `units.yml` 里**（已登场） | ④ |
| ⚠️ **游戏自己也会在 `cards.yml` 里留召唤卡** | 会 —— 玩家全部存档里**所有**召唤卡共 **40 行**，其中 **26 行 `used=false`**、**10 行 `is_free=false`**（`west-Conference4-3.usg`、`west-f.usg`、`west-first-try.usg` …），它们的 `unit_id` **同样**在 `used_card_types_with_unit` 里、单位**同样**已登场 ⇒ **这个形态本身不是异常** ⇒ 离线**定位不到**崩溃点 | ④ |
| 那这条规则是什么？ | **保守兜底**（用户 2026-11-25 拍板「最保险」）：把「往手牌里塞召唤卡」**整类掐掉**。**不是**「已定位到根因的修复」 | — |
| 但缺护栏这件事是实打实的 | `_card_add` 当时**只**查「本战役有没有登记可召唤的单位」，**没查**「这个单位是不是已经被召唤过 / 是不是已在手牌 / 是不是已上架过」—— 而货架那侧的 `card_whitelist` 这三条**全都查了** ⇒ 两边护栏不对称 | ③ |

**跑法（仓库根目录）**：
    .\\python\\python.exe docs\\证据脚本\\e169_card_summon.py

只读：不写任何存档。
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

from save_modifier_core import Catalog, CorePaths, list_saves, open_save   # noqa: E402

GAME_LIB = Path(r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib")

OUT: list[str] = []


def p(*a) -> None:
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


# ---------------------------------------------------------------- ① 卡牌类型
def probe_card_types() -> None:
    p("=" * 78)
    p("① 游戏包里的全部卡牌类型")
    p("=" * 78)
    try:
        cat = Catalog(CorePaths.discover())
    except Exception as e:                                  # pragma: no cover
        p("   [拿不到游戏包] %s: %s" % (type(e).__name__, e))
        return
    names = cat.card_type_names()
    p("   卡牌类型总数 = %d" % len(names))
    summon = []
    for n in sorted(names):
        d = cat.card_type(n) or {}
        if d.get("has_unit"):
            summon.append(n)
            p("   [召唤] %-32s faction=%-7s meta_type=%-22s cost=%s"
              % (n, d.get("faction"), d.get("meta_type"), d.get("cost")))
    p("   has_unit=true 的卡 = %d 张；其余 %d 张不召唤单位"
      % (len(summon), len(names) - len(summon)))


# ------------------------------------------------------------ ② 游戏的判定
def _load(rel: str):
    with open(GAME_LIB / rel, "rb") as f:
        return marshal.loads(f.read()[16:])


def _walk(code, path=""):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            yield path + "/" + k.co_name, k
            yield from _walk(k, path + "/" + k.co_name)


def probe_game_code() -> None:
    p("")
    p("=" * 78)
    p("② 游戏自己的判定（字节码）")
    p("=" * 78)
    try:
        game = _load(os.path.join("uoc2", "state", "game", "game.pyc"))
        camp = _load(os.path.join("uoc2", "state", "campaign", "campaign.pyc"))
    except Exception as e:                                  # pragma: no cover
        p("   [读不到游戏字节码] %s: %s" % (type(e).__name__, e))
        return
    for src, want in ((camp, ("get_used_card_unit_ids",)),
                      (game, ("is_unit_id_referenced",))):
        for path, fn in _walk(src):
            if fn.co_name in want:
                buf = io.StringIO()
                dis.dis(fn, file=buf, depth=0)
                names = [ln.split("(")[-1].split(")")[0].strip()
                         for ln in buf.getvalue().split("\n")
                         if "LOAD_ATTR" in ln]
                p("   %s" % path)
                p("      读到的属性：%s" % sorted(set(n for n in names if n)))


# -------------------------------------------------- ③ 两条路的护栏差在哪
def probe_guards() -> None:
    p("")
    p("=" * 78)
    p("③ 两条路的护栏差在哪")
    p("=" * 78)
    handlers = (REPO / "src" / "save_modifier_core" / "handlers.py").read_text(
        encoding="utf-8")
    body = handlers[handlers.index("def _card_add("):
                    handlers.index("def _card_set(")]
    p("   `_card_add`（加到手牌）里的 `has_unit` 相关行：")
    for ln in body.split("\n"):
        if "has_unit" in ln or "空降" in ln or "used_card_types_with_unit" in ln:
            p("      %s" % ln.strip())
    p("   ⇒ 手牌这条路**不查** `used_card_types_with_unit` / 单位是否已登场。")
    p("")
    p("   `_card_store_add`（上架到货架）里的白名单判定：")
    cat = (REPO / "src" / "save_modifier_core" / "catalog.py").read_text(
        encoding="utf-8")
    wl = cat[cat.index("def card_whitelist("):cat.index("def theater_asset_types(")]
    for ln in wl.split("\n"):
        s = ln.strip()
        if s.startswith("reasons.append") or "used_card_types_with_unit" in s:
            p("      %s" % s)


# ------------------------------------------------------------ ④ 存档普查
def probe_saves() -> None:
    p("")
    p("=" * 78)
    p("④ 玩家存档里「手牌里的召唤卡 vs 已被召唤过的单位」")
    p("=" * 78)
    try:
        cat = Catalog(CorePaths.discover())
    except Exception as e:                                  # pragma: no cover
        p("   [拿不到游戏包] %s: %s" % (type(e).__name__, e))
        return
    summon = set()
    for n in cat.card_type_names():
        if (cat.card_type(n) or {}).get("has_unit"):
            summon.add(n)

    for info in list_saves():
        try:
            with open_save(info.save_id) as save:
                hand = save.root_cards()
                main = save.root_main()
                used = main.get("used_card_types_with_unit") or {}
                units = {u.get("id") for u in save.root_units()
                         if isinstance(u, dict)}
                hits = []
                for c in hand:
                    if not isinstance(c, dict):
                        continue
                    ct = c.get("card_type")
                    if ct not in summon:
                        continue
                    uid = c.get("unit_id")
                    # ⚠️ `used_card_types_with_unit` 的**键是卡类型**，
                    # **值才是被召唤掉的单位 id 列表** ⇒ 要两层查。
                    hits.append((c.get("position"), ct, uid,
                                 uid in ((used or {}).get(ct) or []),
                                 uid in units, c.get("used")))
                if not hits:
                    continue
                p("")
                p("   ### %s" % info.save_id)
                p("       手牌里有 %d 张召唤卡：" % len(hits))
                for pos, ct, uid, in_used, in_units, used_flag in hits:
                    p("       槽位=%-3s %-32s unit_id=%-7s used=%-5s 已召唤过=%-5s 单位已登场=%s"
                      % (pos, ct, uid, used_flag, in_used, in_units))
        except Exception as e:                              # pragma: no cover
            p("   [%s 读失败] %s: %s" % (info.save_id, type(e).__name__, e))


def main() -> None:
    probe_card_types()
    probe_game_code()
    probe_guards()
    probe_saves()
    p("")
    p("（本脚本只读；不写任何存档）")


if __name__ == "__main__":
    main()
