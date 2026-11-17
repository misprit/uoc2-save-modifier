import zipfile, io, os, collections, yaml
save = os.path.join(os.environ["LOCALAPPDATA"], ".uoc2", "save")
out = io.open(r"D:\MiniMax\_analysis\e39_census.txt", "w", encoding="utf-8")

def yaml_load(b):
    try: return yaml.safe_load(b)
    except Exception: return None

snap_cnt = collections.Counter(); snap_names = collections.Counter()
units_fmt = collections.Counter()   # 'list[int]' / 'list[dict]' / other
hqs_fmt   = collections.Counter()
cur_units_int = 0; cur_units_total = 0
flow_style = 0; flow_examples = []
root_keys = collections.Counter()
n=0
for dp, _, fs in os.walk(save):
    for f in sorted(fs):
        if not f.lower().endswith(".usg"): continue
        p = os.path.join(dp, f); n+=1
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            # 根级文件集合
            root_keys[tuple(sorted(nm for nm in names if "/" not in nm))] += 1
            # archive 快照
            for g in sorted(set("/".join(nm.split("/")[:2]) for nm in names
                              if nm.startswith("games/") and nm.count("/")>=2)):
                try: inner = zf.read(g + "/archive")
                except Exception: continue
                with zipfile.ZipFile(io.BytesIO(inner)) as iz:
                    d = collections.defaultdict(set)
                    for nm in iz.namelist():
                        if "/" in nm:
                            sd, fn = nm.split("/",1); d[sd].add(fn)
                    for sd, fns in d.items():
                        snap_cnt[len(fns)] += 1; snap_names.update(fns)
            # games/<场景>/units.yml 与 hqs.yml 格式
            for nm in names:
                if not nm.endswith("units.yml") or nm.startswith("document/"): continue
                if nm.startswith("games/") and nm.count("/")==2 or nm.startswith("game/") and nm.count("/")==1:
                    v = yaml_load(zf.read(nm))
                    if isinstance(v, list) and v and isinstance(v[0], int): units_fmt['list[int]'] += 1
                    elif isinstance(v, list) and v and isinstance(v[0], dict): units_fmt['list[dict]'] += 1
                    else: units_fmt[str(type(v).__name__)+"/"+str(v)[:20] if v is not None else "None"] += 1
                    if isinstance(v, list) and v and isinstance(v[0], int): cur_units_total += 1
                if nm.endswith("hqs.yml") and (nm.startswith("games/") and nm.count("/")==2 or nm.startswith("game/") and nm.count("/")==1):
                    raw = zf.read(nm).decode("utf-8", "replace")
                    v = yaml_load(zf.read(nm))
                    if isinstance(v, list) and v and isinstance(v[0], int):
                        hqs_fmt['list[int]'] += 1
                        s = raw.strip()
                        if s.startswith("["):
                            flow_style += 1
                            if len(flow_examples) < 3: flow_examples.append((os.path.relpath(p,save), nm, s[:70]))
                    elif isinstance(v, list) and v and isinstance(v[0], dict): hqs_fmt['list[dict]'] += 1
                    else: hqs_fmt[str(type(v).__name__)] += 1

out.write("存档数 = %d\n\n" % n)
out.write("=== 快照目录文件数分布 ===\n")
for k in sorted(snap_cnt): out.write("  %d 个文件: %d 个快照\n" % (k, snap_cnt[k]))
out.write("\n=== 快照内文件名并集 (%d 种) ===\n" % len(snap_names))
for k, v in snap_names.most_common(): out.write("  %-28s %d\n" % (k, v))
out.write("\n=== games/<场景>/units.yml 格式 ===\n")
for k, v in units_fmt.most_common(): out.write("  %-22s %d\n" % (k, v))
out.write("  其中 list[int]（当前场景 ID 清单）= %d\n" % cur_units_total)
out.write("\n=== games/<场景>/hqs.yml 格式 ===\n")
for k, v in hqs_fmt.most_common(): out.write("  %-22s %d\n" % (k, v))
out.write("  其中流式写法(单行 [..]) = %d\n" % flow_style)
for e in flow_examples: out.write("    %s | %s | %s\n" % e)
out.write("\n=== 根级文件集合 ===\n")
for k, v in root_keys.most_common(): out.write("  x%-3d %s\n" % (v, list(k)))
out.close(); print("ok")
