# -*- coding: utf-8 -*-
"""V6: 交付文档终检 —— 修正 v2 的标题正则（emoji 前缀 / 尾随句点），
并新增：残留旧策略措辞扫描、关键锚点存在性、层名一致性、编号连续性。"""
import io, re, sys
from pathlib import Path

P = str(Path(__file__).resolve().parent.parent / "开发规范与Prompt.md")
txt = io.open(P, encoding="utf-8").read()
lines = txt.split("\n")
out = io.open(str(Path(__file__).resolve().parent / "v6_check.txt"), "w", encoding="utf-8")

ok = True
def fail(msg):
    global ok
    ok = False
    out.write("  ❌ " + msg + "\n")

out.write("行数 = %d, 字符 = %d, 字节 = %d\n"
          % (len(lines), len(txt), len(txt.encode("utf-8"))))

# 1) 坏字符
bad = [(i, l) for i, l in enumerate(lines, 1) if "\ufffd" in l]
out.write("坏字符(U+FFFD)行数 = %d\n" % len(bad))
if bad:
    fail("存在坏字符")

# 2) 代码块闭合
fences = [i for i, l in enumerate(lines) if l.strip().startswith("```")]
out.write("``` 数量 = %d -> %s\n" % (len(fences), "成对 OK" if len(fences) % 2 == 0 else "❌ 奇数"))
if len(fences) % 2:
    fail("代码块未闭合")

# 3) 表格列数
def _cols(s):
    # 转义竖线 \| 是单元格内容的一部分，不算列分隔符
    return len(s.replace("\\|", "\x00").strip("|").split("|"))

bad_tbl, tables, i = 0, 0, 0
while i < len(lines):
    if lines[i].strip().startswith("|") and i + 1 < len(lines) \
       and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
        tables += 1
        n = _cols(lines[i].strip())
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            c = _cols(lines[j].strip())
            if c != n:
                fail("表格列数不一致 line %d: 期望 %d 实得 %d" % (j + 1, n, c))
                bad_tbl += 1
            j += 1
        i = j
    else:
        i += 1
out.write("表格数 = %d, 列数不一致 = %d\n" % (tables, bad_tbl))

# 4) 标题解析：允许 emoji / 符号前缀与尾随句点
heads = {}
for idx, l in enumerate(lines, 1):
    m = re.match(r"^(#{2,6})\s+(.*)$", l)
    if not m:
        continue
    body = m.group(2)
    body = re.sub(r"^[^0-9A-Za-z\u4e00-\u9fff]+", "", body)   # 去 emoji/⚠️/⭐ 前缀
    m2 = re.match(r"^([\d]+(?:\.[\d]+)*[a-z]?)\.?(?:\s|$)", body)
    if m2:
        heads[m2.group(1)] = (idx, l.strip())

out.write("识别到编号标题 %d 个\n" % len(heads))

# 5) 所有 §引用都要有落点
refs = sorted(set(re.findall(r"§([\d]+(?:\.[\d]+)*[a-z]?)", txt)))
missing = []
for r in refs:
    if r in heads:
        continue
    # 允许引用父章节（§3.4.4 命中 §3.4）
    parts = r.split(".")
    hit = False
    for k in range(len(parts) - 1, 0, -1):
        if ".".join(parts[:k]) in heads:
            hit = True
            break
    if not hit:
        missing.append(r)
out.write("§引用 %d 个, 缺失 = %s\n" % (len(refs), missing if missing else "无"))
if missing:
    fail("章节引用无落点: %s" % missing)

# 6) 关键锚点
KEY = ["0.1", "0.2", "3.4", "3.4.4", "3.4.4.5", "3.4.4.6", "3.4.4.7", "3.4.5", "3.4.5.1",
       "3.4.5.3", "3.5", "3.5.1", "3.5.3", "3.5.6", "3.5.7", "3.5.8", "3.5.9",
       "3.5.10", "4.1", "5.4", "6.1", "6.1b", "6.2", "6.2.1", "6.2b", "6.4", "7", "7.1", "7.2", "7.3",
       "7.4", "7.5", "7.6", "7.7", "10", "11.1", "11.2", "11.2b", "11.2c", "11.3",
       "11.4", "11.6", "11.7", "12", "13"]
out.write("\n关键锚点:\n")
for k in KEY:
    if k in heads:
        out.write("  §%-8s -> OK line %d\n" % (k, heads[k][0]))
    else:
        out.write("  §%-8s -> ❌ 缺失\n" % k)
        fail("关键锚点缺失 §%s" % k)

# 7) 旧策略残留：不该再出现的措辞
#    例外：§3.4.5.3 的“旧建议（已作废，留档对比）”整块是刻意保留的对照原文，跳过
BANNED = [
    (r"同步\s*`?last_", "残留“同步 last_*”"),
    (r"两个检查点都同步", "残留“两个检查点都同步”"),
    (r"验证\s*`?last_conference`?\s*同步", "残留“验证 last_conference 同步”"),
    (r"验证\s*`?last_game`?\s*同步", "残留“验证 last_game 同步”"),
    (r"必须一起同步", "残留“必须一起同步”"),
    (r"多写一处不会坏", "残留“多写一处不会坏”"),
    (r"回滚点同步", "残留“回滚点同步”"),
    (r"必须同时改\s*`?document", "残留“必须同时改 document/…”"),
    (r"新增单位[时，：:].*必须", "残留“新增单位…必须…”"),
    (r"修改器新增单位时", "残留“修改器新增单位时…”"),
    (r"可选开关.*同时写入回滚检查点", "残留“可选开关：同时写入回滚检查点”"),
    (r"场景预设编辑器.*高级功能", "残留“场景预设编辑器（高级功能）”"),
]
# 标记留档区间（明确标注为作废的原文块）
archive_from = archive_to = -1
for i, l in enumerate(lines):
    if "旧建议（已作废，留档对比）" in l:
        archive_from = i
    if archive_from >= 0 and archive_to < 0 and "作废理由见" in l:
        archive_to = i
out.write("\n旧策略残留扫描:\n")
if archive_from >= 0:
    out.write("  （跳过留档对照块 line %d..%d）\n" % (archive_from + 1, archive_to + 1))
hits = 0
for pat, why in BANNED:
    for i, l in enumerate(lines, 1):
        if archive_from >= 0 and archive_from < i - 1 <= archive_to:
            continue
        if re.search(pat, l):
            out.write("  ❌ line %d: %s\n      %s\n" % (i, why, l.strip()[:120]))
            hits += 1
if hits == 0:
    out.write("  ✅ 无残留\n")

# 8) 允许存在的措辞：必须明确标注“已推翻/作废”
out.write("\n“已推翻/作废”标注检查:\n")
for pat in (r"已被 §7 推翻", r"已作废", r"作废理由"):
    n = sum(1 for l in lines if re.search(pat, l))
    out.write("  %-16s 命中 %d 处\n" % (pat, n))
    if n == 0:
        fail("缺少推翻说明: %s" % pat)

# 9) 五层名一致性
out.write("\n分层名一致性:\n")
for tag in ("L1 根状态", "L2 检查点", "L3 战斗实时层", "L4 回合边界历史", "L5 战役文档"):
    n = sum(1 for l in lines if tag in l)
    out.write("  %-14s 出现 %d 次\n" % (tag, n))

# 10) 顶层章节编号连续
top = sorted((k for k in heads if "." not in k and k.isdigit()), key=int)
out.write("\n顶层章节: %s\n" % top)
for idx in range(len(top) - 1):
    if int(top[idx + 1]) != int(top[idx]) + 1:
        fail("顶层章节不连续: %s -> %s" % (top[idx], top[idx + 1]))
if [int(x) for x in top] != list(range(0, len(top))):
    fail("顶层章节编号不是 0..N 连续: %s" % top)

# 11) §10 坑清单编号连续性
out.write("\n§10 坑清单编号:\n")
try:
    s = lines.index("## 10. 已知坑清单")
    e = lines.index("## 11. 验收清单")
    seq = []
    for l in lines[s:e]:
        m = re.match(r"^(\d+)\.\s", l)
        if m:
            seq.append(int(m.group(1)))
    out.write("  编号序列 = %s\n" % (seq,))
    if seq != list(range(1, len(seq) + 1)):
        fail("§10 编号不连续: %s" % (seq,))
    dup = [x for x in set(seq) if seq.count(x) > 1]
    if dup:
        fail("§10 编号重复: %s" % dup)
    out.write("  ✅ 1..%d 连续\n" % len(seq))
except ValueError as ex:
    fail("§10/§11 边界未找到: %s" % ex)

out.write("\n=========== 结论: %s ===========\n" % ("✅ 全部通过" if ok else "❌ 存在问题"))
out.close()
print("ok, ok=%s" % ok)
