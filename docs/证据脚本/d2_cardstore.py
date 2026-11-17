"""D2: where is card_store / conference_start_state written & cleared?
     Plus disassembly of the conference/session transition functions."""
import marshal, types, os, dis, io, re

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\uoc2"

def load_pyc(path):
    with open(path, "rb") as f:
        return marshal.loads(f.read()[16:])

def walk(code, out, depth=0):
    out.append(code)
    for c in code.co_consts:
        if isinstance(c, types.CodeType) and depth < 8:
            walk(c, out, depth + 1)
    return out

print("=" * 100)
print("A) every .pyc that mentions 'card_store' or 'conference_start_state'")
print("=" * 100)
hits = {}
for dp, dn, fn in os.walk(LIB):
    for f in sorted(fn):
        if not f.endswith(".pyc"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, LIB).replace("\\", "/")
        try:
            code = load_pyc(p)
        except Exception:
            continue
        for c in walk(code, []):
            strs = [x for x in c.co_consts if isinstance(x, str)]
            if any(s in ("card_store", "conference_start_state") for s in strs):
                hits.setdefault(rel, []).append((c.co_name, sorted(
                    set(s for s in strs if s in ("card_store", "conference_start_state")))))
for rel, lst in sorted(hits.items()):
    print(f"\n  {rel}")
    for fn_name, strs in lst:
        print(f"      fn {fn_name:44s} {strs}")

print()
print("=" * 100)
print("B) disassembly of the transition functions")
print("=" * 100)
code = load_pyc(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
codes = {c.co_name: c for c in walk(code, [])}
for name in ["set_conference", "end_segment", "play_game", "continue_game",
             "_save_campaign_main_file", "_load_campaign_objects"]:
    c = codes.get(name)
    if c is None:
        print(f"  !! {name}")
        continue
    print(f"\n--- fn {name}({', '.join(c.co_varnames[:c.co_argcount])}) ---")
    buf = io.StringIO()
    dis.dis(c, file=buf)
    keep = []
    for line in buf.getvalue().splitlines():
        s = line.strip()
        if any(k in s for k in ("LOAD_CONST", "LOAD_ATTR", "LOAD_METHOD", "STORE_ATTR",
                                "STORE_FAST", "CALL", "COMPARE_OP", "CONTAINS")):
            keep.append(s)
    for s in keep[:70]:
        print("   ", s)
    if len(keep) > 70:
        print(f"    ... (+{len(keep)-70} more ops)")
