"""F1 · 全面功能验收 —— 用**真实存档的备份**做一遍全流程。

覆盖（用户要求的三件事 + 撤销/回退）
--------------------------------------
1. **修改是否真的生效** —— 写盘后**重新打开**读回，逐条断言；
2. **是否破坏游戏规则** —— 每一步都用 `gamerules.py`（独立复刻游戏 schema 的规则）查一遍；
3. **未改动的部分是否原样搬运** —— 逐条目 SHA256 比对，只允许目标条目变；
4. **界面动态** —— 见 `f1_ui.md`（浏览器端实测，单独跑）；
5. **撤销 / 回退** —— 每次提交后撤销复原、连续撤销、撤销过期被拒、备份命名递增。

⚠️ **只操作副本**：源是用户真存档的 `_BACKUP.usg`，复制到临时目录再动。
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import sys
import tempfile
import traceback
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from save_modifier_core import Catalog, CorePaths, open_save  # noqa: E402
from save_modifier_core.edits import Edit  # noqa: E402
import gamerules  # noqa: E402

PKGS = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages"
SAVE_DIR = os.path.expandvars(r"%LOCALAPPDATA%\.uoc2\save")

OUT = []
RESULTS = []          # [(分组, 用例, 通过?, 说明)]


def say(s=""):
    OUT.append(s)


def case(group, name, ok, msg=""):
    RESULTS.append((group, name, bool(ok), msg))
    OUT.append("  [%s] %-46s %s" % ("PASS" if ok else "FAIL", name, msg[:120]))
    return bool(ok)


def sha_map(path):
    """存档里每个条目的 SHA256。"""
    out = {}
    with zipfile.ZipFile(path, "r") as zf:
        for n in zf.namelist():
            out[n] = hashlib.sha256(zf.read(n)).hexdigest()
    return out


def diff_entries(a, b):
    """两份存档之间，条目名集合与内容的变化。"""
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    return added, removed, changed


def commit_edits(path, edits, catalog=None):
    """走修改器的真实写入路径：plan → commit。返回 (成功?, 结果)。"""
    with open_save(path) as s:
        plan = s.plan_edit(edits, catalog=catalog)
        if not plan.ok:
            return False, plan
        res = s.commit(plan)
        return bool(res.ok or res.nothing_to_do), res


def undo(path):
    with open_save(path) as s:
        if not s.undo_available():
            return False, "没有可撤销的改动"
        r = s.undo()
        return bool(getattr(r, "ok", False)), r


def read_value(path, reader):
    with open_save(path) as s:
        return reader(s)


# ================================================================ 主流程
def main():
    say("=" * 78)
    say("F1 · 全面功能验收（真实存档的备份 ⇒ 副本）")
    say("=" * 78)

    # ---- 常量与游戏字节码核对 ----
    say()
    say("【0】规则常量与**游戏字节码**核对")
    for name, game_v, ours, ok in gamerules.verify_against_game():
        case("0 常量核对", name, ok, "游戏=%r 我们=%r" % (game_v, ours))

    # ---- 准备副本 ----
    src = None
    for cand in (os.path.join(SAVE_DIR, "campaigns",
                              "Blitzkrieg-ahistorical-Conference4-alter_BACKUP.usg"),
                 os.path.join(SAVE_DIR, "campaigns",
                              "Blitzkrieg-ahistorical-Conference4-alter.usg")):
        if os.path.isfile(cand):
            src = cand
            break
    if src is None:
        say("!! 找不到测试用存档")
        return 1
    tmp = tempfile.mkdtemp(prefix="f1_accept_")
    copy = os.path.join(tmp, "accept.usg")
    shutil.copyfile(src, copy)
    say()
    say("【1】测试对象")
    say("   源（用户真存档的备份）: %s" % src)
    say("   副本: %s" % copy)
    say("   ⚠️ 全程只动副本")

    catalog = Catalog(CorePaths.discover())
    base_sha = sha_map(copy)

    def rules_ok(tag):
        R = gamerules.check_save(copy, PKGS, baseline=copy)
        if not R.ok:
            case("规则", tag, False, R.report()[:400])
            for n, ok, m in R.failed:
                say("        · %s %s" % (n, m[:100]))
            return False
        case("规则", tag, True, "%d 条规则全过" % len(R.items))
        return True

    rules_ok("初始副本（未改）就符合游戏规则")

    # ================================================================ 各类写操作
    def step(group, title, edits, expect, allowed_entries, keep=False):
        """一次完整的「写 → 验 → 撤」循环。"""
        say()
        say("  —— %s" % title)
        ok_commit, res = commit_edits(copy, edits, catalog)
        if not ok_commit:
            errs = getattr(res, "errors", None)
            case(group, title + "（提交）", False, str(errs or res)[:200])
            return False
        case(group, title + "（提交成功）", True, str(getattr(res, "summary", ""))[:120])

        # ① 修改生效了吗 —— 重新打开读回
        got = read_value(copy, expect)
        case(group, title + "（落盘后读回生效）", got is not None and got[0],
             "读到 %r（期望 %r）" % (got, expect[1] if isinstance(expect, tuple) else expect))

        # ② 游戏规则还成立吗
        R = gamerules.check_save(copy, PKGS, baseline=copy)
        if not R.ok:
            case(group, title + "（游戏规则）", False, R.report()[:300])
            for n, ok2, m in R.failed:
                say("        · %s %s" % (n, m[:100]))
        else:
            case(group, title + "（游戏规则）", True, "%d 条规则全过" % len(R.items))

        # ③ 未改动的部分原样搬运了吗
        now = sha_map(copy)
        added, removed, changed = diff_entries(base_sha, now)
        touched = set(allowed_entries)
        unexpected = [e for e in (added + removed + changed) if e not in touched]
        case(group, title + "（只动了目标条目）", not unexpected,
             "变了 %s%s%s%s" % (changed, added, removed,
                                ("；不该动的: %s" % unexpected[:3]) if unexpected else ""))

        # ④ 撤销能复原吗（keep=True 时不撤销 —— 留给下一个 step 做前提）
        if keep:
            base_sha.clear()
            base_sha.update(sha_map(copy))
            case(group, title + "（保留改动给下一步）", True, "基线已更新")
        else:
            ok_undo, r = undo(copy)
            if ok_undo:
                back = sha_map(copy)
                same = all(back.get(k) == v for k, v in base_sha.items()) and \
                    set(back) == set(base_sha)
                case(group, title + "（撤销后完全复原）", same,
                     "撤销后与基线%s" % ("一致" if same else "不一致"))
            else:
                case(group, title + "（撤销）", False, str(r)[:200])
        return True

    # ---- 视图数据（挑几个真实对象）----
    with open_save(copy) as s:
        v = s.view(catalog=catalog)
        units = v.units
        hqs = v.hqs
        store = v.store
        hand = v.hand
        shelf = v.shelf
        theater = []
        try:
            bm = s.battle_main()
            if isinstance(bm, dict):
                theater = bm.get("theater_assets") or []
        except Exception:
            pass
    say()
    say("【2】测试对象的数据：单位 %d · 总部 %d · 手牌 %d · 货架 %d · 商店 %d · 战区资产 %d"
        % (len(units), len(hqs), len(hand), len(shelf), len(store),
           sum(len(g) for g in theater if isinstance(g, list))))

    u0 = units[0]
    h0 = hqs[0]
    unit_id = u0.id
    hq_id = h0.id

    # ---------- A 单位 ----------
    step("A 单位", "改名",
         [Edit("unit_field", {"unit_id": unit_id, "field": "name_brief", "value": "验收改名"})],
         lambda s: (next((x.name_brief for x in s.view(catalog=catalog).units
                          if x.id == unit_id), None) == "验收改名", "验收改名"),
         ["units.yml"])

    step("A 单位", "经验 0→399（上限）",
         [Edit("unit_field", {"unit_id": unit_id, "field": "xp", "value": 399})],
         lambda s: (next((x.xp for x in s.view(catalog=catalog).units
                          if x.id == unit_id), None) == 400, 400),
         ["units.yml"])

    step("A 单位", "现有兵力 +1",
         [Edit("unit_field", {"unit_id": unit_id, "field": "act_st",
                              "value": (u0.act_st or 0) + 1})],
         lambda s: (next((x.act_st for x in s.view(catalog=catalog).units
                          if x.id == unit_id), None) == (u0.act_st or 0) + 1,
                    (u0.act_st or 0) + 1),
         ["units.yml"])

    step("A 单位", "增援兵力 +2",
         [Edit("unit_field", {"unit_id": unit_id, "field": "sup_st",
                              "value": (u0.sup_st or 0) + 2})],
         lambda s: (next((x.sup_st for x in s.view(catalog=catalog).units
                          if x.id == unit_id), None) == (u0.sup_st or 0) + 2,
                    (u0.sup_st or 0) + 2),
         ["units.yml"])

    # 挂特种兵：挑一个该单位类型可挂的
    cand_spec = None
    for name, st in (catalog.spec_types.items() if hasattr(catalog, "spec_types") else []):
        if catalog.spec_can_attach(name, u0.type) and not any(
                sp.get("type") == name for sp in (u0.specs or [])):
            cand_spec = name
            break
    if cand_spec is None:
        st = catalog.spec_type_names()
        for name in st:
            if catalog.spec_can_attach(name, u0.type):
                cand_spec = name
                break
    if cand_spec:
        step("A 单位", "挂一个特种兵",
             [Edit("unit_spec_add", {"unit_id": unit_id, "spec_type": cand_spec})],
             lambda s: (any(sp.get("type") == cand_spec for sp in next(
                 x.specs for x in s.view(catalog=catalog).units if x.id == unit_id)),
                 cand_spec),
             ["units.yml"], keep=True)
        step("A 单位", "卸掉那个特种兵",
             [Edit("unit_spec_remove", {"unit_id": unit_id, "spec_type": cand_spec})],
             lambda s: (not any(sp.get("type") == cand_spec for sp in next(
                 x.specs for x in s.view(catalog=catalog).units if x.id == unit_id)),
                 "已卸掉"),
             ["units.yml"])

    # ---------- B 总部 ----------
    step("B 总部", "改名",
         [Edit("hq_field", {"hq_id": hq_id, "field": "name_brief", "value": "验收总部"})],
         lambda s: (next((x.name_brief for x in s.view(catalog=catalog).hqs
                          if x.id == hq_id), None) == "验收总部", "验收总部"),
         ["hqs.yml"])

    step("B 总部", "CP 改到上限",
         [Edit("hq_field", {"hq_id": hq_id, "field": "cp", "value": 9})],
         lambda s: (next((x.cp for x in s.view(catalog=catalog).hqs
                          if x.id == hq_id), None) == 9, 9),
         ["hqs.yml"])

    step("B 总部", "CP 上限改成 9",
         [Edit("hq_field", {"hq_id": hq_id, "field": "max_cp", "value": 9})],
         lambda s: (next((x.max_cp for x in s.view(catalog=catalog).hqs
                          if x.id == hq_id), None) == 9, 9),
         ["hqs.yml"])

    step("B 总部", "补给改成 0",
         [Edit("hq_field", {"hq_id": hq_id, "field": "supply", "value": 0})],
         lambda s: (next((x.supply for x in s.view(catalog=catalog).hqs
                          if x.id == hq_id), None) == 0, 0),
         ["hqs.yml"])

    step("B 总部", "补给卡车 5 辆",
         [Edit("hq_trucks", {"hq_id": hq_id, "trucks": 5})],
         lambda s: (next((x.trucks for x in s.view(catalog=catalog).hqs
                          if x.id == hq_id), None) == 5, 5),
         ["hqs.yml"])

    # 分支等级
    bl = (h0.branch_levels or {})
    if bl:
        br = sorted(bl)[0]
        cur_lv = (bl[br] or {}).get("level", 0)
        step("B 总部", "分支等级 %d→%d" % (cur_lv, min(3, cur_lv + 1)),
             [Edit("hq_branch_level", {"hq_id": hq_id, "branch": br,
                                      "level": min(3, cur_lv + 1)})],
             lambda s: (next((x.branch_levels.get(br, {}).get("level")
                               for x in s.view(catalog=catalog).hqs if x.id == hq_id),
                              None) == min(3, cur_lv + 1), min(3, cur_lv + 1)),
             ["hqs.yml"])

    # 兵库数量
    pool = h0.force_pool or []
    if pool:
        step("B 总部", "兵库第 1 条数量 +1",
             [Edit("hq_force_pool", {"hq_id": hq_id, "index": 0,
                                     "quantity": (pool[0].get("quantity") or 0) + 1})],
             lambda s: (next((x.force_pool[0].get("quantity")
                               for x in s.view(catalog=catalog).hqs if x.id == hq_id),
                              None) == (pool[0].get("quantity") or 0) + 1,
                        (pool[0].get("quantity") or 0) + 1),
             ["hqs.yml"])

    # 兵库加一条（挑一个同延迟不存在的）
    have = {(e.get("delay", 0), e.get("nationality"), e.get("spec") or e.get("equipment"))
            for e in pool}
    add_spec = None
    for name in catalog.spec_type_names():
        st = catalog.spec_type(name)
        nat = getattr(st, "nationality", None)
        if (0, nat, name) not in have:
            add_spec = (name, nat)
            break
    if add_spec:
        name, nat = add_spec
        step("B 总部", "兵库加一条（%s）" % name,
             [Edit("hq_force_pool_add", {"hq_id": hq_id,
                                         "entry": {"spec": name, "nationality": nat,
                                                   "quantity": 1, "delay": 0}})],
             lambda s: (any(e.get("spec") == name for e in next(
                 x.force_pool for x in s.view(catalog=catalog).hqs if x.id == hq_id)),
                 name),
             ["hqs.yml"], keep=True)
        step("B 总部", "兵库移除那一条",
             [Edit("hq_force_pool_remove", {"hq_id": hq_id,
                                            "index": len(pool)})],
             lambda s: (not any(e.get("spec") == name for e in next(
                 x.force_pool for x in s.view(catalog=catalog).hqs if x.id == hq_id)),
                 "已移除"),
             ["hqs.yml"])

    # ---------- C 卡牌 ----------
    if hand:
        pos = hand[0].position
        step("C 卡牌", "手牌槽位 %d 的 is_free 翻转" % pos,
             [Edit("card_set", {"position": pos, "field": "is_free",
                                "value": not hand[0].is_free})],
             lambda s: (next((c.is_free for c in s.view(catalog=catalog).hand
                              if c.position == pos), None) == (not hand[0].is_free),
                        not hand[0].is_free),
             ["cards.yml"])
        step("C 卡牌", "移除手牌槽位 %d" % pos,
             [Edit("card_remove", {"position": pos})],
             lambda s: (not any(c.position == pos for c in s.view(catalog=catalog).hand),
                        "已移除"),
             ["cards.yml"])

    # 加一张到手牌（挑一个白名单里的）
    wl = catalog.card_whitelist(read_value(copy, lambda s: s))
    add_card = wl.allowed_types()[0] if wl.allowed_types() else None
    if add_card:
        used = {c.position for c in hand}
        level = str(read_value(copy, lambda s: (s.root_main() or {}).get("level") or ""))
        deck_limit = gamerules.CARD_DECK_LIMIT.get(level, 5)
        pos = next((p for p in range(1, deck_limit + 1) if p not in used), None)
        if pos:
            step("C 卡牌", "加一张到手牌（%s，槽位 %d）" % (add_card, pos),
                 [Edit("card_add", {"card_type": add_card, "position": pos})],
                 lambda s: (any(c.card_type == add_card for c in s.view(catalog=catalog).hand),
                            add_card),
                 ["cards.yml"])

    if shelf:
        spos = shelf[0].position
        step("C 卡牌", "货架槽位 %d 换成 %s" % (spos, add_card or shelf[0].card_type),
             [Edit("card_store_set", {"position": spos,
                                      "card_type": add_card or shelf[0].card_type})],
             lambda s: (next((c.card_type for c in s.view(catalog=catalog).shelf
                              if c.position == spos), None) == (add_card or shelf[0].card_type),
                        add_card or shelf[0].card_type),
             ["main.yml"])
        step("C 卡牌", "下架货架槽位 %d" % spos,
             [Edit("card_store_remove", {"position": spos})],
             lambda s: (not any(c.position == spos for c in s.view(catalog=catalog).shelf),
                        "已下架"),
             ["main.yml"])

    # ---------- D 商店 ----------
    if store:
        e0 = store[0]
        new_price = (e0.price or 0) + 3
        step("D 商店", "价格改 %d" % new_price,
             [Edit("store_set", {"front": e0.front, "sub": e0.sub, "index": 0,
                                 "field": "price", "value": new_price})],
             lambda s: (next((x.price for x in s.view(catalog=catalog).store
                              if x.front == e0.front and x.sub == e0.sub), None) == new_price,
                        new_price),
             ["store.yml"])
        new_qty = (e0.quantity or 1) + 2
        step("D 商店", "库存改 %d" % new_qty,
             [Edit("store_set", {"front": e0.front, "sub": e0.sub, "index": 0,
                                 "field": "quantity", "value": new_qty})],
             lambda s: (next((x.quantity for x in s.view(catalog=catalog).store
                              if x.front == e0.front and x.sub == e0.sub), None) == new_qty,
                        new_qty),
             ["store.yml"])
        step("D 商店", "下架第 1 条",
             [Edit("store_remove", {"front": e0.front, "sub": e0.sub, "index": 0})],
             lambda s: (len(s.view(catalog=catalog).store) == len(store) - 1,
                        "少了一条"),
             ["store.yml"])

    # ---------- E 概览 ----------
    step("E 概览", "声望 +10",
         [Edit("progress", {"field": "prestige", "value": 400})],
         lambda s: (s.view(catalog=catalog).prestige == 400, 400),
         ["main.yml"])
    step("E 概览", "分数 +100",
         [Edit("progress", {"field": "score", "value": 5599})],
         lambda s: (s.view(catalog=catalog).score == 5599, 5599),
         ["main.yml"])

    # ---------- F 战区资产（L3）----------
    # 这个存档是 Blitzkrieg，可能没有进行中的战斗 ⇒ 换一个有战斗的存档
    ta_src = None
    for info in []:
        pass
    from save_modifier_core import list_saves
    for info in list_saves():
        if not info.is_primary:
            continue
        try:
            with open_save(info.save_id) as s:
                bm = s.battle_main()
                if isinstance(bm, dict) and bm.get("theater_assets"):
                    ta_src = info.save_id
                    break
        except Exception:
            continue
    if ta_src:
        ta_copy = os.path.join(tmp, "theater.usg")
        shutil.copyfile(str([i for i in list_saves() if i.save_id == ta_src][0].path), ta_copy)
        ta_base = sha_map(ta_copy)
        with open_save(ta_copy) as s:
            bm = s.battle_main()
            grp = None
            phase = bm.get("phase")
            tas = bm.get("theater_assets") or []
            grp = tas[phase] if isinstance(phase, int) and 0 <= phase < len(tas) else (tas[0] if tas else [])
            a0 = (grp or [{}])[0]
        asset = a0.get("asset")
        tot = a0.get("uses_total")
        urn = a0.get("uses_turn")
        new_tu = (a0.get("to_use") or 0) + 1
        if isinstance(tot, int) and new_tu > tot:
            new_tu = tot
        ok_commit, res = commit_edits(
            ta_copy, [Edit("theater_asset", {"asset": asset, "to_use": new_tu,
                                            "uses_total": tot, "uses_turn": urn})], catalog)
        case("F 战区资产", "改「当前可用」→%d" % new_tu, ok_commit,
             str(getattr(res, "errors", ""))[:160])
        if ok_commit:
            with open_save(ta_copy) as s:
                bm2 = s.battle_main()
                g2 = bm2.get("theater_assets")[bm2.get("phase") or 0]
                got = next((a for a in g2 if a.get("asset") == asset), {})
            case("F 战区资产", "落盘后读回生效", got.get("to_use") == new_tu,
                 "读到 %r（期望 %r）" % (got.get("to_use"), new_tu))
            R = gamerules.check_save(ta_copy, PKGS, baseline=ta_copy)
            case("F 战区资产", "游戏规则仍成立", R.ok, R.report()[:300])
            now = sha_map(ta_copy)
            added, removed, changed = diff_entries(ta_base, now)
            case("F 战区资产", "只动了战斗 main.yml",
                 all(("games/" in e) or e in ("main.yml",) for e in (added + removed + changed)),
                 "变了 %s" % changed[:3])
            ok_undo, r = undo(ta_copy)
            back = sha_map(ta_copy) if ok_undo else {}
            same = ok_undo and back == ta_base
            case("F 战区资产", "撤销后完全复原", same,
                 "" if same else "撤销=%r" % (r,))
        # 越界：to_use > uses_total
        ok2, res2 = commit_edits(
            ta_copy, [Edit("theater_asset", {"asset": asset,
                                             "to_use": (tot or 0) + 5,
                                             "uses_total": tot, "uses_turn": urn})], catalog)
        case("F 战区资产", "越界（当前可用 > 本场景剩余）被拦", not ok2,
             str(getattr(res2, "errors", ""))[:160])
        # 越界：uses_turn = 0
        ok3, res3 = commit_edits(
            ta_copy, [Edit("theater_asset", {"asset": asset, "to_use": 0,
                                             "uses_total": tot, "uses_turn": 0})], catalog)
        case("F 战区资产", "越界（每回合恢复 = 0）被拦", not ok3,
             str(getattr(res3, "errors", ""))[:160])
    else:
        say("  （本机没有正在战斗的存档 ⇒ 战区资产这部分跳过）")

    # ================================================================ 越界总表
    say()
    say("【3】越界 / 非法操作必须被拦（而且磁盘不能变）")
    before = sha_map(copy)
    illegal = [
        ("单位经验 9999", Edit("unit_field", {"unit_id": unit_id, "field": "xp", "value": 9999})),
        ("单位经验 -1", Edit("unit_field", {"unit_id": unit_id, "field": "xp", "value": -1})),
        ("总部 CP 99", Edit("hq_field", {"hq_id": hq_id, "field": "cp", "value": 99})),
        ("总部 CP 上限 99", Edit("hq_field", {"hq_id": hq_id, "field": "max_cp", "value": 99})),
        ("总部 CP 上限 0", Edit("hq_field", {"hq_id": hq_id, "field": "max_cp", "value": 0})),
        ("总部补给 9", Edit("hq_field", {"hq_id": hq_id, "field": "supply", "value": 9})),
        ("补给卡车 0", Edit("hq_trucks", {"hq_id": hq_id, "trucks": 0})),
        ("补给卡车 99", Edit("hq_trucks", {"hq_id": hq_id, "trucks": 99})),
        ("手牌槽位 99", Edit("card_add", {"card_type": "air_attack_axis", "position": 99})),
        ("不存在的卡牌类型", Edit("card_add", {"card_type": "no_such_card", "position": 1})),
        ("商店库存 0", Edit("store_set", {"front": e0.front, "sub": e0.sub, "index": 0,
                                         "field": "quantity", "value": 0})) if store else None,
        ("商店价格 -1", Edit("store_set", {"front": e0.front, "sub": e0.sub, "index": 0,
                                          "field": "price", "value": -1})) if store else None,
        ("商店上架游戏没有的装备", Edit("store_add", {"front": e0.front, "sub": e0.sub,
                                                     "entry": {"equipment": "spaceship",
                                                               "nationality": "german",
                                                               "price": 5, "quantity": 1}})) if store else None,
    ]
    for item in illegal:
        if item is None:
            continue
        name, edit = item
        okc, res = commit_edits(copy, [edit], catalog)
        errs = getattr(res, "errors", None)
        blocked = (not okc) and bool(errs)
        after = sha_map(copy)
        case("越界拦截", name, blocked,
             "被拦：%s" % (str(errs)[:120] if errs else "!! 没被拦"))
        case("越界拦截", name + "（磁盘未变）", after == before,
             "" if after == before else "!! 磁盘变了")

    # ================================================================ 撤销 / 回退
    say()
    say("【4】撤销 / 回退")
    # 4.1 连续三次提交 ⇒ 连续撤销 ⇒ 全复原
    base4 = sha_map(copy)
    ok1, _ = commit_edits(copy, [Edit("progress", {"field": "prestige", "value": 500})], catalog)
    ok2, _ = commit_edits(copy, [Edit("unit_field", {"unit_id": unit_id, "field": "xp",
                                                 "value": 111})], catalog)
    ok3, _ = commit_edits(copy, [Edit("hq_field", {"hq_id": hq_id, "field": "cp",
                                                  "value": 4})], catalog)
    case("撤销", "连续三次提交都成功", ok1 and ok2 and ok3)
    u1, _ = undo(copy)
    u2, _ = undo(copy)
    u3, _ = undo(copy)
    after4 = sha_map(copy)
    case("撤销", "连续撤销三次后完全复原", u1 and u2 and u3 and after4 == base4,
         "" if after4 == base4 else "还差 %s" % diff_entries(base4, after4)[2][:3])

    # 4.2 撤销栈深度
    with open_save(copy) as s:
        n_before = s.undo_count()
    commit_edits(copy, [Edit("progress", {"field": "score", "value": 1234})], catalog)
    with open_save(copy) as s:
        n_after = s.undo_count()
    case("撤销", "撤销栈深度 +1", n_after == n_before + 1, "%d → %d" % (n_before, n_after))
    undo(copy)

    # 4.3 撤销过期（外部改了文件）⇒ 必须拒绝
    commit_edits(copy, [Edit("progress", {"field": "prestige", "value": 321})], catalog)
    # 外部动手脚：把文件里的 main.yml 换掉
    import zipfile as _z
    tmpzip = copy + ".tmp"
    with zipfile.ZipFile(copy, "r") as zin, zipfile.ZipFile(tmpzip, "w") as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == "main.yml":
                data = data.replace(b"prestige: 321", b"prestige: 999")
            zout.writestr(it, data)
    os.replace(tmpzip, copy)
    oku, resu = undo(copy)
    blocked = (not oku) and bool(getattr(resu, "errors", None))
    case("撤销", "撤销基准过期（外部改过文件）⇒ 拒绝执行", blocked,
         str(getattr(resu, "errors", ""))[:180])
    # 把文件恢复回备份，重新来
    shutil.copyfile(src, copy)
    case("撤销", "恢复测试副本（从备份重拷）", os.path.isfile(copy))

    # 4.4 备份文件命名递增
    say()
    say("【5】备份")
    bdir = os.path.dirname(copy)
    for i in range(3):
        commit_edits(copy, [Edit("progress", {"field": "prestige", "value": 200 + i})], catalog)
    bk = sorted(f for f in os.listdir(bdir) if "BACKUP" in f)
    case("备份", "每次提交都生成备份", len(bk) >= 3, repr(bk))
    case("备份", "备份名带递增序号", any("_BACKUP_2" in f or "_BACKUP_3" in f for f in bk), repr(bk))
    # 备份能不能还原
    if bk:
        bak = os.path.join(bdir, bk[0])
        shutil.copyfile(bak, copy)
        with open_save(copy) as s:
            pv = s.view(catalog=catalog)
        case("备份", "用备份覆盖后存档可正常打开", pv is not None,
             "声望=%s 单位=%d" % (pv.prestige, len(pv.units)))

    # ================================================================ 汇总
    shutil.rmtree(tmp, ignore_errors=True)
    say()
    say("=" * 78)
    groups = {}
    for g, n, ok, m in RESULTS:
        groups.setdefault(g, [0, 0])
        groups[g][0] += 1
        if not ok:
            groups[g][1] += 1
    say("汇总：")
    for g, (tot, bad) in groups.items():
        say("   %-14s %2d 项，失败 %d" % (g, tot, bad))
    nfail = sum(1 for _, _, ok, _ in RESULTS if not ok)
    say("总计 %d 项，失败 %d 项 ⇒ %s" % (len(RESULTS), nfail, "全部通过" if nfail == 0 else "有失败"))
    say("=" * 78)
    return 0 if nfail == 0 else 2


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:
        OUT.append(traceback.format_exc())
        rc = 3
    io.open(r"D:\MiniMax\_analysis\f1_accept.txt", "w", encoding="utf-8", newline="\n").write(
        "\n".join(OUT))
    print("written  rc=%s" % rc)
