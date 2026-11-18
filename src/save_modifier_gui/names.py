"""显示名 —— 把存档/战役的内部 id 换成玩家看得懂的名字。

⚠️ **别自己拼中文名** —— 中文名全在游戏包的 `localization/chi/strings.yml`，
用 `save_modifier_core.locale` 查（规范 §5.7）。

实测：战役根 `main.yml` 的 `campaign_name` = `id_campaign_name_c_stalingrad_p_dlc4`
⇒ 查到「斯大林格勒」；`blitzkrieg` ⇒ 「闪电战」。
"""

from __future__ import annotations

from save_modifier_core import locale

__all__ = ["pretty_name", "campaign_cn", "scenario_cn"]


def campaign_cn(info) -> str:
    """战役的中文名；查不到就退回 `campaign_id`。"""
    key = getattr(info, "campaign_name", None)
    if key:
        text = locale.text(key)
        if text:
            return text
    return getattr(info, "campaign_id", None) or ""


def scenario_cn(info) -> str:
    """独立场景的名字；查不到就退回 id。"""
    sid = getattr(info, "standalone_scenario", None)
    if not sid:
        return ""
    return locale.text(sid) or sid


def pretty_name(info) -> str:
    """给玩家看的存档名：`<文件名>（战役 · <中文名>）`。"""
    name = getattr(info, "name", "") or ""
    if getattr(info, "standalone_scenario", None):
        return f"{name}（独立场景 · {scenario_cn(info)}）"
    if getattr(info, "campaign_id", None):
        return f"{name}（战役 · {campaign_cn(info)}）"
    return name
