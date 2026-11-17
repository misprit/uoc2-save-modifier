import marshal, dis, types
p = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\tools\yaml_.pyc"
code = marshal.loads(open(p,"rb").read()[16:])
def find(c, name):
    for k in c.co_consts:
        if hasattr(k, "co_name"):
            if k.co_name == name:
                return k
            r = find(k, name)
            if r is not None: return r
    return None
d = find(code, "_Dumper")
print("=== _Dumper 顶层 ===")
dis.dis(d)
for meth in ("check_short_list", "set_representer", "dict_representer", "str_representer"):
    m = find(d, meth)
    if m:
        print(f"\n=== {meth} ===")
        dis.dis(m)
