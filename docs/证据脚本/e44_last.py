import os, io, zipfile, yaml
G = r"C:\Users\misprit\AppData\Local\.uoc2\save"
out = io.open(r"D:\MiniMax\_analysis\e44_last.txt","w",encoding="utf-8")
saves=[]
for dp,_,fs in os.walk(G):
    for f in fs:
        if f.lower().endswith(".usg"): saves.append(os.path.join(dp,f))
saves.sort()
for p in saves:
    rel=os.path.relpath(p,G)
    zf=zipfile.ZipFile(p); names=zf.namelist()
    try: m=yaml.safe_load(zf.read("main.yml")) or {}
    except Exception: m={}
    ins=m.get("in_state") or {}; scen=ins.get("scenario"); sa=m.get("standalone_scenario")
    cur = ("games/%s"%scen) if scen else ("game" if sa else None)
    if not cur or (cur+"/archive") not in names: continue
    az=zipfile.ZipFile(io.BytesIO(zf.read(cur+"/archive")))
    snaps=sorted({n.split("/")[0] for n in az.namelist()})
    last=snaps[-1]
    nl=az.namelist()
    out.write("%s\n  cur=%s  快照数=%d\n  字典序最后=%s  含ar_list=%s\n" %
              (rel, cur, len(snaps), last, (last+"/ar_list.yml") in nl))
    out.write("  该快照实际文件: %s\n\n" % sorted({n.split("/",1)[1] for n in nl if n.startswith(last+"/")}))
out.close(); print("ok")
