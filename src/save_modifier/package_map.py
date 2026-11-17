"""战役 → 包 映射。

创建新单位类型时，模型 meta 文件优先在“战役所在包”找（如 dlc1/blitzkrieg），
再退回 base；而 unit_type 配置与 surfaces 贴图基本都在 base。
"""

from __future__ import annotations

CAMPAIGN_TO_PACKAGE: dict[str, str] = {
    "france": "base", "tutorial": "base", "west": "base",
    "blitzkrieg": "dlc1",
    "barbarossa": "dlc2",
    "moscow": "dlc3",
    "stalingrad": "dlc4",
    "don": "dlc5",
    "desert": "dlc6",
    "fox": "dlc7",
    "kursk": "dlc8", "zitadelle": "dlc8",
    "balaton": "dlc9", "berlin": "dlc9",
    "ardennes": "dlc10",
}


def package_for_campaign(campaign_name: str) -> str:
    return CAMPAIGN_TO_PACKAGE.get(campaign_name, "base")
