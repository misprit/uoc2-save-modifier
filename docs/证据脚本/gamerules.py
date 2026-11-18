"""游戏硬约束的**独立复刻**（验收器用；不依赖修改器自己的代码）。

为什么要独立
------------
修改器自己拦范围（`handlers.py` 的 `HQ_CP_MIN` 之类）只能证明「修改器拦住了」；
要证明「**游戏**能读这个存档」，规则必须**独立于修改器**地从**游戏自己的 schema / 常量**取证。

本模块的做法
------------
* 常量与范围**直接从游戏的 .pyc 里读出来**：
  - `uoc2.state.constants` → `hq_max_cp` / `hq_min_max_cp` / `ap_max_value` /
    `unit_max_entr_level` / `max_supply` / `max_supply_hubs` / `max_branch_level` /
    `card_deck_limit` / `card_store_limit`
  - `uoc2.state.entities.data_validation.unit._scenario_base_unit_schema` →
    `xp: Range(min=0, max=400)`、`uv: Any(..., None)`、`act_st/sup_st: Range(min=0)`
  - `uoc2.state.entities.data_validation.hq._branch_levels` →
    `level/suppressed: Range(min=0, max=None)`（**schema 不封顶** ⇒ 上限 3 是游戏逻辑而非 schema）
* 然后对写回后的存档逐条检查。

⚠️ **只把「超了游戏读档就失败」的算 FAIL**（voluptuous 校验失败）；
游戏逻辑层面的约束（分支等级 ≤3、兵库/商店重复）只记**警告** ——
游戏自己写出来的存档里就有重复（实测：eur 商店有两条 german armor），
把它们算 FAIL 会误报。
"""

from __future__ import annotations

import os
import sys
import zipfile

# ---------------------------------------------------------------- 游戏常量（出处见注释）
#: `uoc2.state.constants` → hq_min_max_cp
HQ_MIN_MAX_CP = 3
#: `uoc2.state.constants` → hq_max_cp
HQ_MAX_CP = 9
#: `uoc2.state.constants` → card_deck_limit
CARD_DECK_LIMIT = {"easy": 5, "normal": 5, "classic": 4, "hard": 3}
#: `uoc2.state.constants` → card_store_limit
CARD_STORE_LIMIT = {"easy": 5, "normal": 5, "classic": 5, "hard": 5}
#: `uoc2.state.constants` → ap_max_value（单位的行动点上限）
UNIT_AP_MAX = 3
#: `uoc2.state.constants` → unit_max_entr_level（被压制的等级数上限）
UNIT_ENTR_MAX = 2
#: `uoc2.state.constants` → max_supply（补给上限，单位与总部同值）
SUPPLY_MAX = 3
#: `uoc2.state.constants` → max_supply_hubs（补给卡车数上限）
TRUCK_MIN, TRUCK_MAX = 1, 5
#: `uoc2.state.constants` → max_branch_level（**逻辑**上限，不是 schema 上限）
BRANCH_MAX = 3
#: `uoc2.state.entities.data_validation.unit._scenario_base_unit_schema` → xp
UNIT_XP_MAX = 400
#: 特种兵槽位（idx 0..2）
SPEC_SLOTS_MAX = 3
#: 战区资产「每回合恢复」≥ 1（游戏的 positive_int_schema）
THEATER_USES_TURN_MIN = 1


# ---------------------------------------------------------------- 与游戏字节码核对
def _game_lib():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import gamelib  # noqa: F401
    return gamelib


def verify_against_game() -> list:
    """当场核对：上面写的常量**确实**来自游戏字节码。

    返回 `[(项目, 游戏里的值, 我们写的值, 一致?)]`。
    """
    _game_lib()
    import importlib
    out = []
    try:
        const = importlib.import_module("uoc2.state.constants")
        for name, ours in (("hq_min_max_cp", HQ_MIN_MAX_CP), ("hq_max_cp", HQ_MAX_CP),
                           ("ap_max_value", UNIT_AP_MAX),
                           ("unit_max_entr_level", UNIT_ENTR_MAX),
                           ("max_supply", SUPPLY_MAX), ("max_supply_hubs", TRUCK_MAX),
                           ("max_branch_level", BRANCH_MAX),
                           ("card_deck_limit", CARD_DECK_LIMIT),
                           ("card_store_limit", CARD_STORE_LIMIT)):
            got = getattr(const, name, None)
            out.append((name, got, ours, got == ours))
    except Exception as exc:
        out.append(("constants 模块加载失败", str(exc), None, False))
    # xp 的 400 直接从游戏的 schema 对象里读
    try:
        um = importlib.import_module("uoc2.state.entities.data_validation.unit")
        sch = getattr(um, "_scenario_base_unit_schema", {})
        xp = sch.get("xp") if isinstance(sch, dict) else None
        ok = "max=400" in repr(xp)
        out.append(("unit.xp Range(max=400)", repr(xp)[:90], UNIT_XP_MAX, ok))
    except Exception as exc:
        out.append(("unit schema 读取失败", str(exc), None, False))
    return out


# ---------------------------------------------------------------- 规则检查
class Rules:
    """一组检查结果：FAIL = 游戏会读档失败；WARN = 游戏逻辑层面（不算坏）。"""

    def __init__(self):
        self.items = []      # (名称, 通过?, 说明)
        self.warns = []      # (名称, 说明)

    def add(self, name, ok, msg=""):
        self.items.append((name, bool(ok), msg))
        return ok

    def warn(self, name, msg=""):
        self.warns.append((name, msg))

    @property
    def failed(self):
        return [x for x in self.items if not x[1]]

    @property
    def ok(self):
        return not self.failed

    def report(self):
        out = ["  %-46s %s %s" % (n, "PASS" if ok else "FAIL", m[:110])
               for n, ok, m in self.items]
        out += ["  [警告] %-40s %s" % (n, m[:110]) for n, m in self.warns]
        return "\n".join(out)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _nonneg(v):
    return _is_int(v) and v >= 0


def check_save(save_path: str, packages_dir: str | None = None,
               baseline: str | None = None) -> Rules:
    """对存档做「游戏硬约束」检查。

    `packages_dir` = 游戏包目录（查 unit/specialist/card 类型是否存在）；没给就跳过。
    `baseline`    = 基线存档（用来把「原存档本来就有的重复」从 FAIL 里排除）。
    """
    import yaml
    R = Rules()
    unit_types, spec_types, card_types = {}, {}, {}
    if packages_dir:
        unit_types = _load_dir(packages_dir, "unit_types")
        spec_types = _load_dir(packages_dir, "specialists")
        card_types = _load_dir(packages_dir, "cards")
    base_dup = _baseline_dupes(baseline) if baseline else set()

    with zipfile.ZipFile(save_path, "r") as zf:
        names = zf.namelist()

        def load(entry):
            try:
                return yaml.safe_load(zf.read(entry))
            except Exception:
                return None

        # ---- 根 main.yml ----
        main = load("main.yml") or {}
        level = str(main.get("level") or "")
        R.add("main.level 是已知难度", level in CARD_DECK_LIMIT, "level=%r" % level)
        R.add("main.prestige ≥ 0", _nonneg(main.get("prestige", 0)))
        R.add("main.score ≥ 0", _nonneg(main.get("score", 0)))
        cs = main.get("card_store")
        if isinstance(cs, list):
            limit = CARD_STORE_LIMIT.get(level, 5)
            R.add("main.card_store 条数 ≤ %d" % limit, len(cs) <= limit, "%d 条" % len(cs))
            pos = [c.get("position") for c in cs if isinstance(c, dict)]
            R.add("main.card_store 槽位不重复", len(pos) == len(set(pos)), repr(pos))
            R.add("main.card_store 槽位都在 1..%d" % limit,
                  all(_is_int(p) and 1 <= p <= limit for p in pos), repr(pos))
            bad = [c.get("card_type") for c in cs if isinstance(c, dict)
                   and card_types and c.get("card_type") not in card_types]
            R.add("main.card_store 的卡牌类型游戏都认识", not bad, repr(bad[:3]))

        # ---- 根 units.yml ----
        units = load("units.yml") or []
        if isinstance(units, list):
            bad = []
            for u in units:
                if not isinstance(u, dict):
                    continue
                uid = u.get("id")
                xp = u.get("xp", 0)
                if not _nonneg(xp) or xp > UNIT_XP_MAX:
                    bad.append(("xp", uid, xp))
                if not _nonneg(u.get("act_st", 0)):
                    bad.append(("act_st", uid, u.get("act_st")))
                if not _nonneg(u.get("sup_st", 0)):
                    bad.append(("sup_st", uid, u.get("sup_st")))
                e = u.get("entr", 0)
                if not _is_int(e) or e < 0 or e > UNIT_ENTR_MAX:
                    bad.append(("entr", uid, e))
                sp = u.get("supply", 0)
                if not _is_int(sp) or sp < 0 or sp > SUPPLY_MAX:
                    bad.append(("supply", uid, sp))
                ap = u.get("ap", 0)
                if not _is_int(ap) or ap < 0 or ap > UNIT_AP_MAX:
                    bad.append(("ap", uid, ap))
                uv = u.get("uv")
                # 游戏的 uv 是 Any(..., None) ⇒ **允许 None**
                if uv is not None and not (isinstance(uv, list) and len(uv) == 2
                                           and all(_nonneg(x) for x in uv)):
                    bad.append(("uv", uid, uv))
                specs = u.get("specs")
                if isinstance(specs, list):
                    if len(specs) > SPEC_SLOTS_MAX:
                        bad.append(("specs 超过 %d" % SPEC_SLOTS_MAX, uid, len(specs)))
                    for s in specs:
                        if not isinstance(s, dict):
                            continue
                        if not isinstance(s.get("type"), str):
                            bad.append(("spec.type", uid, s.get("type")))
                        elif spec_types and s["type"] not in spec_types:
                            bad.append(("spec 类型不存在", uid, s.get("type")))
                        idx = s.get("idx")
                        if idx is not None and (not _is_int(idx) or idx < 0):
                            bad.append(("spec.idx", uid, idx))
                if unit_types and u.get("type") not in unit_types:
                    bad.append(("单位类型不存在", uid, u.get("type")))
            R.add("units 每个字段都在游戏 schema 范围内", not bad, repr(bad[:4]))

        # ---- 根 hqs.yml ----
        hqs = load("hqs.yml") or []
        if isinstance(hqs, list):
            bad = []
            for h in hqs:
                if not isinstance(h, dict):
                    continue
                hid = h.get("id")
                cp, mcp = h.get("cp"), h.get("max_cp")
                if not _is_int(cp) or cp < 0 or cp > HQ_MAX_CP:
                    bad.append(("cp", hid, cp))
                if not _is_int(mcp) or mcp < HQ_MIN_MAX_CP or mcp > HQ_MAX_CP:
                    bad.append(("max_cp", hid, mcp))
                sup = h.get("supply", 0)
                if not _is_int(sup) or sup < 0 or sup > SUPPLY_MAX:
                    bad.append(("supply", hid, sup))
                tr = h.get("trucks")
                if tr is not None and (not _is_int(tr) or tr < TRUCK_MIN or tr > TRUCK_MAX):
                    bad.append(("trucks", hid, tr))
                if not _nonneg(h.get("xp", 0)):
                    bad.append(("xp", hid, h.get("xp")))
                if not _nonneg(h.get("xp_target", 0)):
                    bad.append(("xp_target", hid, h.get("xp_target")))
                bl = h.get("branch_levels")
                if isinstance(bl, dict):
                    for br, node in bl.items():
                        if not isinstance(node, dict):
                            continue
                        lv, su = node.get("level", 0), node.get("suppressed", 0)
                        # schema 只要求 ≥ 0（Range(min=0, max=None)）⇒ 硬约束只有下限
                        if not _is_int(lv) or lv < 0:
                            bad.append(("分支等级", (hid, br), lv))
                        if not _is_int(su) or su < 0:
                            bad.append(("压制等级", (hid, br), su))
                        if _is_int(lv) and _is_int(su) and lv + su > BRANCH_MAX:
                            R.warn("分支等级+压制 > %d（游戏逻辑上限，schema 不拦）" % BRANCH_MAX,
                                   "%s %s: %s+%s" % (hid, br, lv, su))
                fp = h.get("force_pool")
                if isinstance(fp, list):
                    seen = set()
                    for i, e in enumerate(fp):
                        if not isinstance(e, dict):
                            continue
                        q = e.get("quantity")
                        if not _is_int(q) or q < 0:
                            bad.append(("兵库数量", (hid, i), q))
                        if bool(e.get("spec")) and bool(e.get("equipment")):
                            bad.append(("兵库同时有 spec 与 equipment", (hid, i), None))
                        if not e.get("spec") and not e.get("equipment"):
                            bad.append(("兵库既没 spec 也没 equipment", (hid, i), None))
                        key = "fp:%s:%s:%s:%s" % (hid, e.get("delay", 0), e.get("nationality"),
                                                 e.get("spec") or ("eq:" + str(e.get("equipment"))))
                        if key in seen:
                            if key not in base_dup:
                                R.warn("兵库同身份同延迟重复（游戏允许，修改器口径是「新增时拦」）",
                                       "%s 第 %d 条" % (hid, i))
                        seen.add(key)
                        if spec_types and e.get("spec") and e["spec"] not in spec_types:
                            bad.append(("兵库特种兵类型不存在", (hid, i), e.get("spec")))
            R.add("hqs 每个字段都在游戏 schema 范围内", not bad, repr(bad[:4]))

        # ---- 根 cards.yml ----
        cards = load("cards.yml") or []
        if isinstance(cards, list):
            limit = CARD_DECK_LIMIT.get(level, 5)
            bad = []
            pos = [c.get("position") for c in cards if isinstance(c, dict)]
            R.add("cards 条数 ≤ %d（难度 %s 的手牌上限）" % (limit, level),
                  len(cards) <= limit, "%d 张" % len(cards))
            R.add("cards 槽位不重复", len(pos) == len(set(pos)), repr(pos))
            R.add("cards 槽位都在 1..%d" % limit,
                  all(_is_int(p) and 1 <= p <= limit for p in pos), repr(pos))
            for c in cards:
                if isinstance(c, dict) and card_types \
                        and c.get("card_type") not in card_types:
                    bad.append(c.get("card_type"))
            R.add("cards 的卡牌类型游戏都认识", not bad, repr(bad[:3]))

        # ---- 根 store.yml ----
        store = load("store.yml") or {}
        if isinstance(store, dict):
            bad = []
            for front, blob in store.items():
                if not isinstance(blob, dict):
                    continue
                for sub in ("store", "elite_store"):
                    items = blob.get(sub)
                    if not isinstance(items, list):
                        continue
                    seen = set()
                    for i, e in enumerate(items):
                        if not isinstance(e, dict):
                            continue
                        p, q = e.get("price"), e.get("quantity")
                        if not _is_int(p) or p < 0:
                            bad.append(("price", (front, sub, i), p))
                        if not _is_int(q) or q < 1:
                            bad.append(("quantity", (front, sub, i), q))
                        if bool(e.get("spec")) and bool(e.get("equipment")):
                            bad.append(("同时有 spec 与 equipment", (front, sub, i), None))
                        key = "st:%s:%s:%s:%s" % (front, sub,
                                                e.get("nationality"),
                                                e.get("spec") or e.get("equipment"))
                        if key in seen:
                            if key not in base_dup:
                                R.warn("同商店重复条目（游戏允许，修改器口径是「新增时拦」）",
                                       "%s/%s 第 %d 条" % (front, sub, i))
                        seen.add(key)
                        if spec_types and e.get("spec") and e["spec"] not in spec_types:
                            bad.append(("特种兵不存在", (front, sub, i), e.get("spec")))
            R.add("store 每条都在游戏 schema 范围内", not bad, repr(bad[:4]))

        # ---- 战斗目录里的战区资产（L3）----
        bad = []
        checked = 0
        for entry in names:
            if not (entry.startswith("games/") and entry.endswith("/main.yml")):
                continue
            d = load(entry)
            if not isinstance(d, dict):
                continue
            ta = d.get("theater_assets")
            if not isinstance(ta, list) or not ta:
                continue
            checked += 1
            for grp in ta:
                if not isinstance(grp, list):
                    continue
                for a in grp:
                    if not isinstance(a, dict):
                        continue
                    tu, ut, urn = a.get("to_use"), a.get("uses_total"), a.get("uses_turn")
                    if not _nonneg(tu):
                        bad.append((entry, a.get("asset"), "to_use", tu))
                    if ut is not None and not _nonneg(ut):
                        bad.append((entry, a.get("asset"), "uses_total", ut))
                    if not _is_int(urn) or urn < THEATER_USES_TURN_MIN:
                        bad.append((entry, a.get("asset"), "uses_turn", urn))
                    if _is_int(tu) and _is_int(ut) and tu > ut:
                        bad.append((entry, a.get("asset"), "to_use>uses_total", (tu, ut)))
        if checked:
            R.add("战区资产三个字段都在游戏 schema 范围内", not bad, repr(bad[:4]))
    return R


def _baseline_dupes(baseline: str) -> set:
    """基线存档里**本来就有的**重复（兵库 / 商店）—— 这些不算新增违规。"""
    import yaml
    out = set()
    try:
        with zipfile.ZipFile(baseline, "r") as zf:
            names = zf.namelist()
            hqs = yaml.safe_load(zf.read("hqs.yml")) if "hqs.yml" in names else []
            for h in (hqs or []):
                if not isinstance(h, dict):
                    continue
                for e in (h.get("force_pool") or []):
                    if isinstance(e, dict):
                        out.add("fp:%s:%s:%s:%s" % (
                            h.get("id"), e.get("delay", 0), e.get("nationality"),
                            e.get("spec") or ("eq:" + str(e.get("equipment")))))
            store = yaml.safe_load(zf.read("store.yml")) if "store.yml" in names else {}
            for front, blob in (store or {}).items():
                if not isinstance(blob, dict):
                    continue
                for sub in ("store", "elite_store"):
                    for e in (blob.get(sub) or []):
                        if isinstance(e, dict):
                            out.add("st:%s:%s:%s:%s" % (front, sub, e.get("nationality"),
                                                       e.get("spec") or e.get("equipment")))
    except Exception:
        pass
    return out


def _load_dir(packages_dir: str, sub: str) -> dict:
    out = {}
    if not os.path.isdir(packages_dir):
        return out
    import yaml
    for pkg in sorted(os.listdir(packages_dir)):
        d = os.path.join(packages_dir, pkg, "data", "entity_types", sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".yml"):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    raw = yaml.safe_load(fh.read())
            except Exception:
                continue
            if isinstance(raw, dict):
                out[f[:-4]] = raw
    return out
