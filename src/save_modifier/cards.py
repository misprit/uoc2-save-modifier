"""卡牌（campaign cards.yml）编辑与卡牌参考列表生成。

战役存档根目录的 cards.yml 记录当前持有的卡牌，形如：

    - card_type: truck_axis
      is_free: false
      position: 1
      unit_id: null
      used: false

要点（来自真实存档样本）：
- position 从 1 开始计数，次序可以跳跃（1、3 有卡而 2 空着）；
- 空槽位对应字段不存在，不会写出占位条目，故不能用 cards 数量推槽位数；
- 槽位上限随难度不同（3–5），脚本只做宽松校验：最多 5 个卡槽。

卡牌类型（card_type）是 <包>/data/entity_types/cards/<名>.yml 的文件名主干，
卡牌元类型（meta_type）取值见同目录的 card_meta_types.yml。本模块负责：
1. 扫描原版包与扩展搜索路径，汇总可用的卡牌类型（含费用、阵营、标题 id）；
2. 读写存档 cards.yml（增删、购买、重置 used）；
3. 生成按阵营分类的中文卡牌参考列表。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .savefile import dump_yaml, load_yaml

CARDS_FILENAME = "cards.yml"
CARD_SLOTS_MAX = 5  # 宽松上限：真实槽位数 3–5 视难度而定，不做精确校验

FACTION_LABELS = {
    "allies": "西方盟军",
    "axis": "轴心国",
    "soviet": "苏联",
    "unknown": "未知阵营",
}
FACTION_ORDER = ["axis", "allies", "soviet"]
UNKNOWN_FACTION = "unknown"

CARD_TYPE_REL = Path("data/entity_types/cards")

# 卡牌参考列表的组织：references/<此目录名>/<阵营>.txt，每阵营一个文件
CARD_REF_DIRNAME = "卡牌列表"

# 新卡字段的写入顺序，与游戏存档一致；dump_yaml 保留插入顺序，元组次序
# 即新卡的 YAML 键序。
CARD_FIELD_ORDER = ("card_type", "is_free", "position", "unit_id", "used")


class CardError(Exception):
    """卡牌相关操作的可预期错误。"""


def _natural_key(name: str) -> tuple:
    """包名自然序键：dlc2 排在 dlc10 之前。"""
    return tuple(int(part) if part.isdigit() else part
                 for part in re.split(r"(\d+)", name))


# ---- 卡牌目录（原版包扫描） ----

def _search_roots(config) -> list[Path]:
    """卡牌定义的搜索根：原版包目录在前，扩展搜索路径在后（后者覆盖前者）。"""
    roots: list[Path] = []
    if getattr(config, "orig_packages", None):
        roots.append(Path(config.orig_packages))
    for p in getattr(config, "mod_search_paths", []) or []:
        roots.append(Path(p))
    return [r for r in roots if r.is_dir()]


def load_card_catalog(config) -> dict[str, dict]:
    """汇总可用的卡牌类型：{card_type: {"data": ..., "package": 包名}}。

    后加载的包（按自然序）覆盖先加载的同名卡牌，与本地化合并规则一致。
    """
    catalog: dict[str, dict] = {}
    for root in _search_roots(config):
        pkg_dirs = sorted((p for p in root.iterdir() if p.is_dir()),
                          key=lambda p: _natural_key(p.name))
        for pkg in pkg_dirs:
            card_dir = pkg / CARD_TYPE_REL
            if not card_dir.is_dir():
                continue
            for f in sorted(card_dir.glob("*.yml")):
                try:
                    data = load_yaml(f)
                except Exception:  # noqa: BLE001 单个坏文件不应拖垮整份清单
                    continue
                if isinstance(data, dict):
                    catalog[f.stem] = {"data": data, "package": pkg.name}
    return catalog


def card_faction(card_data: dict) -> str:
    return str(card_data.get("faction") or UNKNOWN_FACTION)


def faction_label(faction: str) -> str:
    return FACTION_LABELS.get(faction, faction)


# ---- 存档内卡牌列表 ----

def _new_card(card_type: str, position: int) -> dict:
    return {"card_type": card_type, "is_free": False, "position": position,
            "unit_id": None, "used": False}


class CardList:
    """某个战役存档 cards.yml 的读写视图。"""

    def __init__(self, session):
        if getattr(session.save, "kind", "campaign") != "campaign":
            raise CardError("卡牌命令仅适用于战役存档（独立场景存档没有 cards.yml）。")
        self.path: Path = session.work_dir / CARDS_FILENAME
        raw = load_yaml(self.path) if self.path.exists() else []
        self.cards: list[dict] = [c for c in (raw or []) if isinstance(c, dict)]
        self._sort()

    # ---- 查询 ----
    def _sort(self) -> None:
        self.cards.sort(key=lambda c: int(c.get("position") or 0))

    def positions(self) -> list[int]:
        return sorted(int(c.get("position") or 0) for c in self.cards)

    def find_position(self, pos: int) -> Optional[dict]:
        for c in self.cards:
            if int(c.get("position") or 0) == pos:
                return c
        return None

    def find_by_type(self, card_type: str) -> Optional[dict]:
        for c in self.cards:
            if c.get("card_type") == card_type:
                return c
        return None

    def empty_position(self) -> Optional[int]:
        used = set(self.positions())
        for pos in range(1, CARD_SLOTS_MAX + 1):
            if pos not in used:
                return pos
        return None

    # ---- 修改 ----
    def remove(self, pos: int) -> Optional[dict]:
        card = self.find_position(pos)
        if card is None:
            return None
        self.cards.remove(card)
        self.persist()
        return card

    def put(self, card: dict) -> None:
        """写入一张卡：同 position 的旧卡被替换（覆盖语义由调用方保证）。"""
        pos = int(card["position"])
        self.cards = [c for c in self.cards
                      if int(c.get("position") or 0) != pos]
        self.cards.append(card)
        self._sort()
        self.persist()

    def persist(self) -> None:
        dump_yaml(self.path, self.cards)


def parse_position(raw: str) -> int:
    """解析并宽松校验卡槽位置（1–5）。"""
    try:
        pos = int(raw)
    except (TypeError, ValueError):
        raise CardError(f"卡槽位置需为整数: {raw!r}") from None
    if not 1 <= pos <= CARD_SLOTS_MAX:
        raise CardError(f"卡槽位置需在 1–{CARD_SLOTS_MAX} 之间（收到 {pos}）。")
    return pos


def build_card(card_type: str, position: int) -> dict:
    return _new_card(card_type, position)


def campaign_faction(work_dir: Path) -> Optional[str]:
    """读取战役扮演阵营（document/main.yml 的 player_faction）。"""
    path = Path(work_dir) / "document" / "main.yml"
    if not path.exists():
        return None
    try:
        data = load_yaml(path)
    except Exception:  # noqa: BLE001 阵营只用于软校验，读不到就跳过
        return None
    value = data.get("player_faction") if isinstance(data, dict) else None
    return str(value) if value else None


# ---- 参考列表 ----

def _fmt_card(card_type: str, entry: dict, trans) -> str:
    data = entry.get("data") or {}

    def tr(key: str) -> str:
        raw = data.get(key)
        if not isinstance(raw, str) or not raw:
            return "—"
        text = trans.get(raw) if trans is not None else ""
        return f"{text}（{raw}）" if text else raw

    cost = data.get("cost")
    recoup = data.get("recoup")
    cost_text = "—" if cost is None else str(cost)
    if recoup is not None:
        cost_text += f"（回收 {recoup}）"
    persistent = "是" if data.get("persistent") else "否"
    has_unit = "是" if data.get("has_unit") else "否"
    lines = [
        f"卡牌类型：{card_type}",
        f"标题：{tr('title')}",
        f"副标题：{tr('subtitle')}",
        f"说明：{tr('description')}",
        f"元类型：{data.get('meta_type') or '—'}    费用：{cost_text}    "
        f"持久：{persistent}    含单位：{has_unit}",
        "",
    ]
    return "\n".join(lines) + "\n"


def group_cards_by_faction(catalog: dict[str, dict]) -> dict[str, list[str]]:
    """按阵营分组：{阵营: [卡牌类型, ...]}，阵营顺序固定，未知阵营排在最后。"""
    groups: dict[str, list[str]] = {}
    for card_type in sorted(catalog):
        faction = card_faction(catalog[card_type].get("data") or {})
        groups.setdefault(faction, []).append(card_type)
    order = FACTION_ORDER + sorted(f for f in groups if f not in FACTION_ORDER)
    return {f: groups[f] for f in order if f in groups}


def format_faction_reference(faction: str, card_types: list[str],
                             catalog: dict[str, dict], trans) -> str:
    """生成单个阵营的卡牌列表文本（每阵营一个文件）。"""
    parts = [f"===== {faction_label(faction)}（{faction}）"
             f" 共 {len(card_types)} 张 =====\n\n"]
    if faction == UNKNOWN_FACTION:
        parts.append("（卡牌定义缺少 faction 字段或取值无法识别，归入本文件）\n\n")
    for card_type in card_types:
        parts.append(_fmt_card(card_type, catalog[card_type], trans))
    return "".join(parts)


def reference_filename(faction: str) -> str:
    """阵营对应的参考文件名：<阵营中文名>.txt（未知取值直接用作文件名）。"""
    return f"{faction_label(faction)}.txt"


def generate_card_reference(config, output_dir: Path, trans,
                            verbose: bool = True) -> int:
    """把卡牌参考按阵营分文件写入 output_dir，返回写入条目数。

    卡牌定义来自包数据而非存档剧本层，与具体战役无关；包未配置或没有
    卡牌定义时跳过（不创建空目录）。
    """
    catalog = load_card_catalog(config)
    if not catalog:
        if verbose:
            print("警告：未在包目录中找到卡牌定义，跳过卡牌参考列表生成。")
        return 0
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # 同级的单文件汇总（战役卡牌列表.txt）是废弃格式，生成目录时清除
    legacy = output_dir.parent / "战役卡牌列表.txt"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
    groups = group_cards_by_faction(catalog)
    for faction, card_types in groups.items():
        (output_dir / reference_filename(faction)).write_text(
            format_faction_reference(faction, card_types, catalog, trans),
            encoding="utf-8")
    if verbose:
        print(f"卡牌参考列表已生成: {output_dir} "
              f"({len(groups)} 个阵营文件，{len(catalog)} 条目)")
    return len(catalog)


def generate_card_reference_if_missing(config, output_dir: Path, trans) -> int:
    """参考目录不存在或为空时才生成；已有文件则保持不动。"""
    output_dir = Path(output_dir)
    if output_dir.is_dir() and any(output_dir.glob("*.txt")):
        return 0
    return generate_card_reference(config, output_dir, trans, verbose=False)
