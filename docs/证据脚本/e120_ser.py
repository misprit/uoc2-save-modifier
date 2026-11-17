import marshal, dis, re
p = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\tools\serialization.pyc"
code = marshal.loads(open(p,"rb").read()[16:])
names = []
def walk(c):
    for k in c.co_consts:
        if hasattr(k, "co_name"):
            names.append((k.co_name, k.co_varnames[:k.co_argcount], k.co_names))
            walk(k)
walk(code)
for n, args, gnames in names:
    if "dump" in n or "save" in n or "write" in n:
        print(f"def {n}({', '.join(args)})  globals={list(gnames)}")
