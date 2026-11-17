# -*- coding: utf-8 -*-
"""E32: 检查点(last_*) 里究竟有哪些文件；document/ 是否在检查点里"""
import os, io, zipfile, yaml, collections

G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
OUT = io.open(r"D:\MiniMax\_analysis\e32_out.txt", "w", encoding="utf-8")
def P(*a):
    OUT.write(" ".join(str(x) for x in a) + "\n")

saves = []
for dirpath, _, files in os.walk(G):
    for f in files:
        if f.lower().endswith(".usg"):
            saves.append(os.path.join(dirpath, f))
saves.sort()

counter = collections.Counter()
has_doc_in_cp = 0
total_cp = 0
for p in saves:
    try:
        zf = zipfile.ZipFile(p)
    except Exception:
        continue
    names = zf.namelist()
    for cp in ("last_conference", "last_game"):
        files = sorted(n[len(cp)+1:] for n in names if n.startswith(cp + "/"))
        if files:
            total_cp += 1
            counter[tuple(files)] += 1
            if any(f.startswith("document") for f in files):
                has_doc_in_cp += 1
    zf.close()

P(f"存档数 = {len(saves)}, 含检查点的存档 = {total_cp}")
P(f"检查点里含 document/ 的: {has_doc_in_cp}")
P("")
P("检查点文件清单组合（按出现次数）:")
for files, n in counter.most_common():
    P(f"  x{n}: {list(files)}")

# 顶层目录普查
P("")
P("=" * 100); P("[B] 各存档顶层条目（前缀）分布"); P("=" * 100)
top = collections.Counter()
for p in saves:
    try:
        zf = zipfile.ZipFile(p)
    except Exception:
        continue
    names = zf.namelist()
    pre = set()
    for n in names:
        if n.startswith("document/"):
            pre.add("document/")
        elif "/" in n:
            pre.add(n.split("/")[0] + "/")
        else:
            pre.add("<root file>")
    for x in pre:
        top[x] += 1
    zf.close()
for k, v in sorted(top.items(), key=lambda x: -x[1]):
    P(f"  {k:28s} {v}")

OUT.close()
print("done")
