# -*- coding: utf-8 -*-
"""V2: 交付文档自检 v2 —— 表格 / 代码块 / 章节引用 / 坏字符 / 标题层级"""
import io, re

P = r"D:\MiniMax\UOC2存档修改器-开发规范与Prompt.md"
txt = io.open(P, encoding="utf-8").read()
lines = txt.split("\n")
out = io.open(r"D:\MiniMax\_analysis\v2_check.txt", "w", encoding="utf-8")

out.write("行数 = %d, 字符 = %d, 字节 = %d\n" % (len(lines), len(txt), len(txt.encode("utf-8"))))

# 坏字符
bad = [(i, l) for i, l in enumerate(lines, 1) if "\ufffd" in l]
out.write("坏字符(U+FFFD)行数 = %d\n" % len(bad))
for i, l in bad[:5]:
    out.write("   line %d: %s\n" % (i, l[:100]))

# 代码块
fences = [i for i, l in enumerate(lines) if l.strip().startswith("```")]
out.write("``` 数量 = %d -> %s\n" % (len(fences), "成对 OK" if len(fences) % 2 == 0 else "❌ 奇数"))

# 表格
bad_tbl = 0
tables = 0
i = 0
while i < len(lines):
    if lines[i].strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i+1].strip()):
        tables += 1
        n = len(lines[i].strip().strip("|").split("|"))
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            c = len(lines[j].strip().strip("|").split("|"))
            if c != n:
                out.write("  ❌ 表格列数不一致 line %d: 期望 %d 实得 %d\n" % (j + 1, n, c))
                bad_tbl += 1
            j += 1
        i = j
    else:
        i += 1
out.write("表格数 = %d, 列数不一致 = %d\n" % (tables, bad_tbl))

# 标题与引用
heads = {}
for idx, l in enumerate(lines, 1):
    m = re.match(r"^(#{2,4})\s+([\d.]+[a-z]?)\s", l)
    if m:
        heads[m.group(2)] = (idx, l.strip())
refs = set(re.findall(r"§([\d]+(?:\.[\d]+)*[a-z]?)", txt))
missing = sorted(r for r in refs if r not in heads and r.split(".")[0] not in heads)
out.write("章节引用缺失: %s\n" % (missing if missing else "无"))

# 关键锚点
for k in ("3.5", "3.5.1", "3.5.5", "3.5.7", "3.5.8", "3.5.9", "3.5.10", "6.2.1", "11.2c", "11.3", "11.4"):
    out.write("  §%s -> %s\n" % (k, "OK line %d" % heads[k][0] if k in heads else "❌ 缺失"))

# 标题层级连续性
out.write("\n所有一级/二级标题:\n")
for k, (idx, l) in sorted(heads.items(), key=lambda x: x[1][0]):
    if l.startswith("## "):
        out.write("  line %5d  %s\n" % (idx, l))

out.close()
print("ok")
