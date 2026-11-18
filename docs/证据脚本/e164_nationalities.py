# -*- coding: utf-8 -*-
"""e164 —— 国籍表 / 国籍中文名 / 特种兵国籍分布（U11 全量视图分组用）。

跑法（仓库根目录）：
    .\\python\\python.exe docs\\证据脚本\\e164_nationalities.py

结论（2026-11-18 实测）：
  1. 国籍表在 **nationalities.yml**（base 包 40 个）+ **nationalities_2.yml**（空模板 {}）；
     两个都是**文件**，不走 entity_types/<目录>/ 那套目录索引。
  2. 375 个特种兵类型分布在 **31 个国籍**上；同名国籍（苏联/意大利/波兰/罗马尼亚/瑞士/
     南斯拉夫）各有**两个 id**（本国阵营 + 参战国版本）⇒ 全量视图靠「阵营分隔带」区分。
  3. **游戏自己的 locale 键有错**：croatian 的 name_brief 写的是 `id_croatian_brief`，
     那个键在中文表里译成了「匈牙利」；正确的键是 `id_croatian_name_brief` → 克罗地亚。
     （375 个特种兵里没有克罗地亚的，所以不影响分组，但这个坑要知道。）
  4. 20 个国籍带 `parent_nationality`（游戏判定「可挂」时用）。
"""
from __future__ import annotations

import io
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))

from save_modifier_core import locale  # noqa: E402
from save_modifier_core.catalog import Catalog  # noqa: E402
from save_modifier_core.paths import CorePaths  # noqa: E402


def main() -> int:
    paths = CorePaths.discover()
    cat = Catalog(paths)
    store = locale.TranslationStore(paths, locale="chi")

    nats = cat._nationalities()
    print("== 国籍表：%d 个 ==" % len(nats))

    # ---- 1) 同名国籍（中文名撞车）----
    cn = {}
    for k, v in nats.items():
        key = v.get("name_brief")
        text = store.get(key) if key else ""
        cn[k] = text or k
    dup = {}
    for k, text in cn.items():
        dup.setdefault(text, []).append(k)
    collisions = {t: ks for t, ks in dup.items() if len(ks) > 1}
    print("\n== 中文名撞车的国籍（%d 组）==" % len(collisions))
    for text, ks in sorted(collisions.items()):
        detail = " / ".join("%s(%s)" % (k, nats[k].get("faction")) for k in ks)
        print("  %s ← %s" % (text, detail))

    # ---- 2) 特种兵国籍分布 ----
    rows = []
    for name in cat.spec_type_names():
        t = cat.spec_type(name)
        rows.append((name, t.nationality or "", t.faction or ""))
    cnt = Counter(n for _, n, _ in rows)
    print("\n== 375 个特种兵的国籍分布（%d 个国籍有货）==" % len(cnt))
    for n, c in cnt.most_common():
        print("  %-16s %-6s %3d" % (n, cn.get(n, n), c))

    # ---- 3) 父国籍 ----
    parents = {k: v.get("parent_nationality") for k, v in nats.items()
               if v.get("parent_nationality")}
    print("\n== 带父国籍的：%d 个 ==" % len(parents))
    for k, p in sorted(parents.items()):
        print("  %-16s → %-12s（%s）" % (k, p, cn.get(p, p)))

    # ---- 4) 游戏自己的 locale 错键 ----
    print("\n== locale 错键 ==")
    for k, v in nats.items():
        key = v.get("name_brief")
        if not key:
            continue
        text = store.get(key)
        alt = store.get(key.replace("_brief", "_name_brief"))
        if alt and alt != text:
            print("  %s: name_brief=%s → 「%s」，但 %s → 「%s」"
                  % (k, key, text, key.replace("_brief", "_name_brief"), alt))

    print("\n== 抽查 ==")
    for t in ("us_recon_42", "ger_towed_arty_42", "sov_spec_dlc9"):
        s = cat.spec_type(t)
        print("  %-18s %-10s %-8s %s" % (t, s.name_brief and store.get(s.name_brief),
                                         s.nationality, s.flags))
    return 0


if __name__ == "__main__":
    sys.exit(main())
