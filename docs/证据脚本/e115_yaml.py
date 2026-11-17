import marshal, dis, sys
p = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\tools\yaml_.pyc"
code = marshal.loads(open(p,"rb").read()[16:])
print("=== 常量 ===")
def walk(c, depth=0):
    for k in c.co_consts:
        if hasattr(k, "co_name"):
            print("  "*depth + f"def {k.co_name}({', '.join(k.co_varnames[:k.co_argcount])})")
            walk(k, depth+1)
        elif isinstance(k, str) and len(k) < 120:
            print("  "*depth + f"const: {k!r}")
walk(code)
print("\n=== 顶层 dis ===")
dis.dis(code, depth=0)
