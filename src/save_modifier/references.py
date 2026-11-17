"""参考列表生成。

从存档的 document/ 目录（战役“剧本”）读取本战役出现的单位与总部，
结合翻译，生成纯文本参考列表（供 Ctrl+F 查 id）。

生成到每存档隔离目录 <存档隔离>/references/，与工具目录无关；进入存档
会话时自动生成（见 session 初始化）。
"""

from __future__ import annotations

from pathlib import Path


def _fmt_unit(unit: dict, trans) -> str:
    name_brief = unit.get("name_brief", "")
    name = trans.get(name_brief) or name_brief
    type_ = unit.get("type", "")
    return f"id：{unit.get('id')}\n名称：{name} {name_brief}\n初始类型：{type_}\n\n"


def _fmt_hq(hq: dict, trans) -> str:
    name_brief = hq.get("name_brief", "")
    name = trans.get(name_brief) or name_brief
    nation = hq.get("nationality", "")
    lines = [f"id：{hq.get('id')}", f"名称：{name} {name_brief}"]
    if hq.get("name_full"):
        full = trans.get(hq["name_full"]) or hq["name_full"]
        lines.append(f"全称: {full} {hq['name_full']}")
    lines.append(f"国家：{nation}")
    lines.append("")
    return "\n".join(lines) + "\n"


def generate_unit_reference(doc_units_path: Path, output_path: Path, trans) -> int:
    """从 document/units.yml 生成单位参考列表，返回写入条目数。"""
    import yaml

    if not doc_units_path.exists():
        print(f"警告：未找到 {doc_units_path}，跳过单位参考列表生成。")
        return 0
    with open(doc_units_path, "r", encoding="utf-8") as f:
        units = yaml.safe_load(f) or []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for u in units:
            f.write(_fmt_unit(u, trans))
    print(f"单位参考列表已生成: {output_path} ({len(units)} 条目)")
    return len(units)


def generate_hq_reference(doc_hqs_path: Path, output_path: Path, trans) -> int:
    """从 document/hqs.yml 生成总部参考列表，返回写入条目数。"""
    import yaml

    if not doc_hqs_path.exists():
        print(f"警告：未找到 {doc_hqs_path}，跳过总部参考列表生成。")
        return 0
    with open(doc_hqs_path, "r", encoding="utf-8") as f:
        hqs = yaml.safe_load(f) or []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for h in hqs:
            f.write(_fmt_hq(h, trans))
    print(f"总部参考列表已生成: {output_path} ({len(hqs)} 条目)")
    return len(hqs)
