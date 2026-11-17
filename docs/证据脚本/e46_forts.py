import os, io, zipfile
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
out = io.open(r"D:\MiniMax\_analysis\e46_forts.txt","w",encoding="utf-8")
for dp,_,fs in os.walk(G):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        q=os.path.join(dp,f)
        with zipfile.ZipFile(q) as zf:
            for g in sorted(set("/".join(n.split("/")[:2]) for n in zf.namelist() if n.startswith("games/") and n.count("/")>=2)):
                try: inner=zf.read(g+"/archive")
                except Exception: continue
                az=zipfile.ZipFile(io.BytesIO(inner))
                for nm in az.namelist():
                    if nm.endswith("/forts.yml"):
                        out.write("%s | %s\n%s\n\n" % (os.path.relpath(q,G), nm, az.read(nm).decode("utf-8","replace")[:500]))
                        break
                else: continue
                break
        break
    else: continue
    break
out.close(); print("ok")
