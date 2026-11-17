"""每个存档会话的上下文装配。

打开一个存档后，收集其各数据访问对象（units、绑定、翻译、参考列表路径等），
作为 REPL 命令层的上下文。参考列表在首次进入时自动生成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import cards, references
from .config import Config
from .entity_service import BindingStore, apply_bindings
from .savefile import SaveSession, load_yaml
from .translations import TranslationStore
from .units import UnitList


@dataclass
class SessionContext:
    """命令层上下文：封装一个已打开的存档会话。"""

    session: SaveSession
    config: Config
    translations: TranslationStore
    bindings: BindingStore
    units: UnitList = field(init=False)
    # 当前 REPL “选中单位”（select 上下文）
    selected_unit: int | None = None
    scenario_name: str | None = None
    #: 游戏包类型目录（提供 max_st / max_spec 等真实上限）
    catalog: Any = None

    def __post_init__(self) -> None:
        if self.catalog is None:
            from save_modifier_core.catalog import Catalog
            self.catalog = Catalog()
        self.units = UnitList(self.session, catalog=self.catalog)
        self._resolve_scenario()
        self._gen_references_once()
        # 进入会话即应用绑定（应对战役段脚本覆写 type）
        self.reapply_bindings(verbose=False)

    def _resolve_scenario(self) -> None:
        from .savefile import load_yaml
        main_path = self.session.work_dir / "main.yml"
        if not main_path.exists():
            return
        main = load_yaml(main_path)
        # 独立场景存档用 standalone_scenario 标识当前战斗（战役用 in_state）
        standalone = main.get("standalone_scenario")
        if standalone:
            self.scenario_name = standalone
            return
        try:
            self.scenario_name = main["in_state"]["scenario"]
        except (KeyError, TypeError):
            self.scenario_name = None

    def _gen_references_once(self) -> None:
        """进入存档时自动生成参考列表（若隔离目录还没有）。

        列表来源是存档 document/ 剧本层（整个战役的单位/总部定义），不随
        当前战斗推进变化，故只在首次进入时生成一次，不做刷新。

        卡牌参考单独判断文件是否存在：早期的参考目录可能没有卡牌列表，
        进入时补上即可；卡牌定义来自包数据，与具体战役无关。
        """
        ref_dir = self.config.save_dir_for(self.session.name) / "references"
        if not ref_dir.exists():
            doc = self.session.work_dir / "document"
            references.generate_unit_reference(
                doc / "units.yml", ref_dir / "战役部队列表.txt",
                self.translations)
            references.generate_hq_reference(
                doc / "hqs.yml", ref_dir / "战役总部列表.txt",
                self.translations)
        cards.generate_card_reference_if_missing(
            self.config, ref_dir / cards.CARD_REF_DIRNAME, self.translations)

    @property
    def unit_list_path(self) -> Path:
        return self.session.work_dir / "units.yml"

    def reapply_bindings(self, verbose: bool = True) -> int:
        return apply_bindings(self.session, self.units, self.bindings,
                              verbose=verbose)
