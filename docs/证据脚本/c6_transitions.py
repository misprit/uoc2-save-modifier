"""C6: disassemble campaign.pyc state-transition functions."""
import marshal, types, os, dis, io

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

code = load_pyc(os.path.join(LIB, "state", "campaign", "campaign.pyc"))
codes = {c.co_name: c for c in walk(code, [])}

WANT = ["save", "load", "_save_campaign_main_file", "_save_campaign_objects",
        "_save_campaign_units", "_load_campaign_units", "_save_campaign_game_files",
        "set_conference", "play_game", "continue_game", "end_segment",
        "revert_last_game", "revert_last_game_to_deployment",
        "revert_last_conference", "can_revert_to_last_conference",
        "can_end_segment", "get_last_game_scenario_name",
        "_load_revert_campaign_data", "get_currenct_game_serialization"]

for name in WANT:
    c = codes.get(name)
    if c is None:
        print(f"!! {name} not found")
        continue
    print("=" * 96)
    print(f"fn {name}({', '.join(c.co_varnames[:c.co_argcount])})")
    print("=" * 96)
    buf = io.StringIO()
    dis.dis(c, file=buf)
    txt = buf.getvalue()
    # keep only the interesting ops: names / consts
    for line in txt.splitlines():
        if any(k in line for k in ("LOAD_CONST", "LOAD_METHOD", "LOAD_ATTR", "CALL", "STORE_FAST")):
            print("   ", line.strip())
    print()
