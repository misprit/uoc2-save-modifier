import os, collections, time, yaml
GAME = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
PK = os.path.join(GAME, "_packages")
c = collections.Counter()
b = collections.Counter()
for dlc in sorted(os.listdir(PK)):
    d = os.path.join(PK, dlc, "data")
    if not os.path.isdir(d):
        continue
    for sub in sorted(os.listdir(d)):
        sd = os.path.join(d, sub)
        if not os.path.isdir(sd):
            continue
        n = nb = 0
        for rt, dn, fn in os.walk(sd):
            for f in fn:
                if f.endswith((".yml", ".yaml")):
                    n += 1
                    nb += os.path.getsize(os.path.join(rt, f))
        c[sub] += n
        b[sub] += nb
print("%-16s %8s %12s" % ("data 子目录", "yml 数", "字节"))
for k, v in c.most_common():
    print("%-16s %8d %12d" % (k, v, b[k]))
print("合计 yml = %d, 字节 = %.1f MB" % (sum(c.values()), sum(b.values()) / 1024 / 1024))
# maps 里是什么
md = os.path.join(PK, "base", "data", "maps")
if os.path.isdir(md):
    print("base/data/maps 前 10 项:", sorted(os.listdir(md))[:10])
    sub = sorted(os.listdir(md))[:1]
    for s in sub:
        p = os.path.join(md, s)
        if os.path.isdir(p):
            print("  %s/ -> %d 个文件" % (s, len(os.listdir(p))))
