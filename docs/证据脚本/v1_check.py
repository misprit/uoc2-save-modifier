# -*- coding: utf-8 -*-
"""V1: 交付文档自检 —— 表格列数、代码块闭合、章节引用"""
import io, re, os

P = r"D:\MiniMax\UOC2存档修改器-开发规范与Prompt.md"
txt = io.open(P, encoding="utf-8").read()
lines = txt.split("\n")
out = io.open(r"D:\MiniMax\_analysis\v1_check.txt", "w", encoding="utf-8")

out.write("行数 = %d, 字节 = %d\n" % (len(lines), len(txt.encode("utf-8"))))

# 1) 代码块闭合
fences = [i for i, l in enumerate(lines) if l.strip().startswith("```")]
out.write("``` 数量 = %d  -> %s\n" % (len(fences), "成对 OK" if len(fences) % 2 == 0 else "❌ 奇数，未闭合"))

# 2) 表格列数
bad = 0
i = 0
tables = 0
while i < len(lines):
    if lines[i].strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i+1].strip()):
        tables += 1
        hdr = lines[i].strip().strip("|").split("|")
        n = len(hdr)
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            c = len(lines[j].strip().strip("|").split("|"))
            if c != n:
                out.write("  ❌ 表格列数不一致 line %d: 期望 %d 实得 %d\n" % (j + 1, n, c))
                bad += 1
            j += 1
        i = j
    else:
        i += 1
out.write("表格数 = %d, 列数不一致的行 = %d\n" % (tables, bad))

# 3) 章节引用有效性
heads = set()
for l in lines:
    m = re.match(r"^#{2,4}\s+([\d.]+)\s", l)
    if m:
        heads.add(m.group(1).rstrip("."))
refs = set(re.findall(r"§([\d]+(?:\.[\d]+)*[a-z]?)", txt))
missing = sorted(r for r in refs if r not in heads and r.split(".")[0] not in heads)
out.write("章节引用中找不到对应标题的: %s\n" % (missing if missing else "无"))

# 4) 关键锚点存在性
for key in ["3.4.4", "3.4.4.1", "3.4.4.5", "3.4.4.7", "3.4.4.8", "11.2b"]:
    out.write("  §%s -> %s\n" % (key, "存在" if key in heads else "❌ 缺失"))

# 5) 尾行是否以换行结束
out.write("文件以换行结尾: %s\n" % txt.endswith("\n"))
out.close()
print("ok")
