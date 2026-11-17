"""C4: how does the game itself load/save each layer? (bytecode analysis)"""
import marshal, types, os, dis, io, re

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\uoc2"

def load_pyc(path):
    with open(path, "rb") as f:
        return marshal.loads(f.read()[16:])

def walk(code, out, depth=0, maxdepth=8):
    out.append((code, depth))
    for c in code.co_consts:
        if isinstance(c, types.CodeType) and depth < maxdepth:
            walk(c, out, depth + 1, maxdepth)
    return out

MARK = re.compile(r"(usg|games|last_game|last_conference|document|units\.yml|hqs\.yml|"
                  r"cards\.yml|store\.yml|main\.yml|archive|scenario|conference)", re.I)

for rel in ["state/campaign/campaign.pyc", "state/gamelike/gamelike.pyc",
            "state/game/game.pyc", "main_screen/ctrl.pyc"]:
    p = os.path.join(LIB, rel.replace("/", os.sep))
    if not os.path.isfile(p):
        print(f"!! {rel}")
        continue
    code = load_pyc(p)
    codes = walk(code, [])
    print("=" * 100)
    print(f"### {rel}   ({len(codes)} code objects)")
    print("=" * 100)
    for c, d in codes:
        strs = [x for x in c.co_consts if isinstance(x, str) and MARK.search(x)]
        if not strs:
            continue
        # only show functions whose strings look like file/save plumbing
        if not re.search(r"(usg|units\.yml|hqs\.yml|cards\.yml|store\.yml|main\.yml|"
                         r"archive|last_game|last_conference|\bgames\b)", " ".join(strs), re.I):
            continue
        print(f"\n  fn {c.co_name}  (args: {c.co_varnames[:c.co_argcount]})")
        for s in sorted(set(strs)):
            print(f"      {s!r}")
        # look for zip usage
        zipnames = [n for n in c.co_names if n in
                    ("ZipFile", "writestr", "write", "extractall", "namelist", "infolist",
                     "read", "open", "mkdir", "rmtree", "copyfile", "shutil", "zipfile")]
        if zipnames:
            print(f"      >>> zip ops: {sorted(set(zipnames))}")
    print()
