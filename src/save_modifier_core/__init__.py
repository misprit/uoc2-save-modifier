"""UOC2 存档修改器 —— 核心库。

面向《统一指挥 2》(Unity of Command II) 的存档修改核心能力，**无界面**：
GUI 直接 `import` 本包使用。

对外接口（规范 §0.2）
----------------------
```python
from save_modifier_core import list_saves, open_save

for info in list_saves():
    print(info.display_name)

with open_save("campaigns/west.usg") as save:
    view = save.view()
    print(view.stage, view.prestige, len(view.units))
```

**备份与撤销**（规范 §6.4）：`save.commit(plan)` 写回前自动生成 `<存档名>_BACKUP.usg`，
并把本次改动压进**落盘**的撤销栈；`save.undo()` 撤销上一次提交
（撤销前会校验基准，基准过期就拒绝，不硬改）。

**分层**（规范 §7）—— 本包只写 L1（根目录的 5 个 YAML），
L2 检查点 / L3 战斗实时层 / L4 回合历史 / L5 战役文档 一律只读；
唯一的 L3 例外是"当前进行中战斗"的战区资产 `theater_assets`。

**依赖**：只用标准库 + PyYAML。不 import tkinter，不启子进程，不依赖游戏进程。
"""

from __future__ import annotations

from . import catalog
from . import campaigns
from . import locale
from .capabilities import Capabilities
from .campaigns import (CampaignData, CampaignIndex, CampaignPosition,
                        Conference, Scenario, ScenarioRoster, StoreListing)
from .catalog import CardWhitelist, Catalog, UnitType
from .commit import CommitResult, commit, make_backup
from .container import (CardView, HqView, RuinedCity, Save,
                        SaveUnreadable, StoreEntryView,
                        UnitView, View)
from .discovery import (SaveInfo, is_archived_path, list_saves,
                        resolve_save_id)
from .edits import UNSET, Edit
from .locale import TranslationStore
from .paths import CorePaths
from .plan import FileChange, Plan, ValidationResult, plan_edit, validate
from .undo import UndoRecord, UndoResult, stack_path_for

__all__ = [
    "Capabilities",
    "CampaignData",
    "CampaignIndex",
    "CampaignPosition",
    "CardView",
    "CardWhitelist",
    "Catalog",
    "CommitResult",
    "Conference",
    "CorePaths",
    "Edit",
    "FileChange",
    "HqView",
    "Plan",
    "RuinedCity",
    "Save",
    "SaveInfo",
    "SaveUnreadable",
    "Scenario",
    "ScenarioRoster",
    "StoreEntryView",
    "StoreListing",
    "TranslationStore",
    "UNSET",
    "UndoRecord",
    "UndoResult",
    "UnitType",
    "UnitView",
    "ValidationResult",
    "View",
    "campaigns",
    "catalog",
    "commit",
    "list_saves",
    "locale",
    "make_backup",
    "open_save",
    "plan_edit",
    "resolve_save_id",
    "stack_path_for",
    "validate",
]

__version__ = "0.1.0"


def open_save(save_id: str, paths: CorePaths | None = None) -> Save:
    """打开一个存档。

    参数
    ----
    save_id : `list_saves()` 返回的 `save_id`（相对存档根目录的 posix 路径），
              也可以直接给绝对路径。
    paths   : 路径集合；不给就自动探测。

    返回 `Save` 对象（用完记得 `close()`，或用 `with`）。
    """
    paths = paths or CorePaths.discover()
    from .discovery import read_root_main
    path = resolve_save_id(save_id, paths)
    if not path.is_file():
        raise FileNotFoundError(f"存档不存在：{path}")

    main = read_root_main(path)
    standalone = main.get("standalone_scenario") or None
    in_state = main.get("in_state") or {}
    try:
        st = path.stat()
        mtime, size = st.st_mtime, st.st_size
    except OSError:
        mtime, size = 0.0, 0

    info = SaveInfo(
        save_id=save_id if "/" in save_id or "\\" in save_id
        else path.relative_to(paths.save_root).as_posix(),
        path=path,
        kind="standalone" if standalone else "campaign",
        # ⚠️ 游戏只认 campaigns / games ⇒ 其它位置 = 玩家自建的归档区
        archived=is_archived_path(path, paths),
        is_primary=True,
        campaign_id=main.get("campaign_id") or None,
        campaign_name=main.get("campaign_name") or None,
        scenario=in_state.get("scenario") or None,
        standalone_scenario=standalone,
        mtime=mtime,
        size=size,
    )
    return Save(info, paths)
