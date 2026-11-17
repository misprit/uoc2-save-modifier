"""Extract string constants + names from the game's .pyc modules (Py3.14 bytecode)."""
import marshal, types, os, sys, io, re, collections

LIB = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\uoc2"

def load_pyc(path):
    with open(path, "rb") as f:
        data = f.read()
    # pyc header: magic(4) flags(4) mtime(4) size(4)  == 16 bytes
    return marshal.loads(data[16:])

def walk(code, consts, names, depth=0, maxdepth=6):
    for c in code.co_consts:
        if isinstance(c, str):
            consts.append(c)
        elif isinstance(c, types.CodeType) and depth < maxdepth:
            walk(c, consts, names, depth + 1, maxdepth)
    names.extend(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType) and depth < maxdepth:
            names.extend(c.co_names)

def module_strings(path):
    try:
        code = load_pyc(path)
    except Exception as e:
        return None, None, str(e)
    consts, names = [], []
    walk(code, consts, names)
    return consts, names, None

if __name__ == "__main__":
    targets = sys.argv[1:]
    for t in targets:
        p = os.path.join(LIB, t)
        consts, names, err = module_strings(p)
        if err:
            print(f"!! {t}: {err}")
            continue
        print("=" * 78)
        print(f"### {t}   ({len(consts)} strings, {len(set(names))} names)")
        print("=" * 78)
        seen = set()
        for c in consts:
            if c in seen:
                continue
            seen.add(c)
            if 0 < len(c) <= 120 and not c.startswith("\n"):
                print(f"   {c!r}")
