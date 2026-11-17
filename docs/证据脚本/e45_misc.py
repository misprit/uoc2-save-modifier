import os, io, zipfile, yaml, collections
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
out = io.open(r"D:\MiniMax\_analysis\e45_misc.txt","w",encoding="utf-8")
p = os.path.join(G, "Old Saves", "Victory in the West", "经典难度", "west-Husky.usg")
with zipfile.ZipFile(p) as zf:
    for nm in ("games/husky/hqs.yml","games/husky/units.yml"):
        raw = zf.read(nm)
        out.write("%s  (%d bytes)\n  前 90 字节 = %r\n\n" % (nm, len(raw), raw[:90]))
    az = zipfile.ZipFile(io.BytesIO(zf.read("games/husky/archive")))
    # forts.yml 样例
    for nm in az.namelist():
        if nm.endswith("/forts.yml"):
            out.write("forts.yml 样例 (%s):\n%s\n" % (nm, az.read(nm).decode("utf-8","replace")[:400]))
            break
# 流式写法普查：所有 games/*/hqs.yml 原始字节是否以 [ 开头
flow = collections.Counter(); ex = []
for dp,_,fs in os.walk(G):
    for f in fs:
        if not f.lower().endswith(".usg"): continue
        q = os.path.join(dp,f)
        with zipfile.ZipFile(q) as zf:
            for nm in zf.namelist():
                if nm.startswith("games/") and nm.count("/")==2 and nm.endswith(("hqs.yml","units.yml")):
                    raw = zf.read(nm).decode("utf-8","replace").strip()
                    flow["流式" if raw.startswith("[") else "块式(- 开头)"] += 1
                    if raw.startswith("[") and len(ex)<4: ex.append((os.path.relpath(q,G), nm, raw[:60]))
out.write("\n=== games/<场景>/{hqs,units}.yml 文本形态 ===\n")
for k,v in flow.items(): out.write("  %-14s %d\n" % (k,v))
for e in ex: out.write("    %s | %s | %s\n" % e)
out.close(); print("ok")
