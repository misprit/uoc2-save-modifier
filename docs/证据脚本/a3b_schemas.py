"""Stage 3b: units.yml / hqs.yml are lists -> dump entries properly."""
import os, yaml, json

OUT = r"D:\MiniMax\_analysis\extracted"

def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def flat(obj, prefix="", depth=0, out=None, maxdepth=2):
    if out is None:
        out = []
    if depth > maxdepth:
        out.append((prefix, f"<{type(obj).__name__}>"))
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat(v, f"{prefix}.{k}" if prefix else str(k), depth + 1, out, maxdepth)
    elif isinstance(obj, list):
        if obj and all(not isinstance(x, (dict, list)) for x in obj):
            out.append((prefix, repr(obj)[:160]))
        else:
            for i, v in enumerate(obj[:3]):
                flat(v, f"{prefix}[{i}]", depth + 1, out, maxdepth)
            if len(obj) > 3:
                out.append((f"{prefix}[...]", f"{len(obj)} items"))
    else:
        out.append((prefix, repr(obj)[:160]))
    return out

for tag in ["conf3", "ahist2"]:
    base = os.path.join(OUT, tag)
    print("#" * 78)
    print("# SAVE:", tag)
    print("#" * 78)
    for fn in ["units.yml", "hqs.yml"]:
        data = load(os.path.join(base, fn))
        print(f"\n===== {fn}: list of {len(data)} =====")
        for entry in data[:2]:
            for k, v in flat(entry):
                print(f"   {k} = {v}")
            print("   " + "-" * 40)
    print()
