import zipfile, io, os, yaml, collections
save = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "save")
out = io.open(r"D:\MiniMax\_analysis\e43_bug.txt","w",encoding="utf-8")
old_hit = new_hit = 0; n = 0
for dp,_,fs in os.walk(save):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        p = os.path.join(dp,f)
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            cur = None
            try:
                m = yaml.safe_load(zf.read("main.yml"))
                if isinstance(m, dict):
                    st = m.get("in_state") or {}
                    cur = st.get("scenario")
            except Exception: pass
            if not cur: continue
            if (cur+"/archive") not in names: continue
            n += 1
            az = zipfile.ZipFile(io.BytesIO(zf.read(cur+"/archive")))
            snaps = sorted({x.split("/")[0] for x in az.namelist()})
            last = snaps[-1] if snaps else None
            old = (last+"/ar_list.yml") in az.namelist() if last else None
            # 新口径：任意快照含 ar_list
            any_snap = any("/ar_list.yml" in x for x in az.namelist())
            lastreal = sorted(snaps, key=lambda s: (s.startswith("deployment"), s))[ -1]
            out.write("%-46s cur=%-22s last_alpha=%-26s 含ar_list=%-5s 任意快照含=%s\n"
                      % (os.path.relpath(p,save), cur, last, old, any_snap))
            if old: old_hit += 1
            if any_snap: new_hit += 1
out.write("\n有当前场景 archive 的存档 = %d ; 旧口径命中 = %d ; 新口径命中 = %d\n" % (n, old_hit, new_hit))
out.close(); print("ok")
