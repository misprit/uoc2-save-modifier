import io, os, re, sys
from pathlib import Path
p = str(Path(__file__).resolve().parent.parent / "开发规范与Prompt.md")
b = open(p, "rb").read()
print("字节 =", len(b))
print("BOM =", b[:3] == b"\xef\xbb\xbf")
print("CRLF 次数 =", b.count(b"\r\n"), "| 裸 CR =", b.count(b"\r") - b.count(b"\r\n"))
print("U+FFFD =", b.count(b"\xef\xbf\xbd".decode("utf-8").encode("utf-8")))
t = b.decode("utf-8")
print("行数 =", t.count("\n") + 1)
print("字符 =", len(t))
need = ["### 3.2b 认出", "#### 4.6.1 商店的", "### 9.1 场景预设", "#### 9.1.6 外部静态整理数据",
        "40. **⚠️ 独立场景的场景预设不在存档里**", "41. **⚠️ 外部静态整理数据是缓存不是权威源**",
        "e71_which.py", "e55_ident.py"]
for n in need:
    print(("OK  " if n in t else "MISS ") + n.encode("ascii", "replace").decode("ascii"))
# 标题层级（跳过围栏代码块：块内的 # 注释不是标题）
t_nocode = re.sub(r"```.*?```", "", t, flags=re.S)
hs = re.findall(r"^(#{1,6}) (.+)$", t_nocode, re.M)
prev = 0
bad = []
for h, s in hs:
    lv = len(h)
    if prev and lv > prev + 1:
        bad.append((h, s))
    prev = lv
print("标题层级跳跃 =", [ (len(a), b.encode("ascii", "replace").decode("ascii")) for a, b in bad ] if bad else "无")
# 表格列数
lines = t.split("\n")
i = 0
tbl = 0
bad_t = 0
while i < len(lines):
    if lines[i].strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:\-|]+\|\s*$", lines[i + 1]):
        tbl += 1
        n = lines[i].count("|")
        j = i
        while j < len(lines) and lines[j].strip().startswith("|"):
            if lines[j].count("|") != n:
                bad_t += 1
                print("  列数不一致 line", j + 1, ":", lines[j][:80])
            j += 1
        i = j
    else:
        i += 1
print("表格 =", tbl, "列数不一致 =", bad_t)
