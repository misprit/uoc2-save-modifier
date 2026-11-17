import marshal, dis
p = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\tools\yaml_.pyc"
code = marshal.loads(open(p,"rb").read()[16:])
def find(c, name):
    for k in c.co_consts:
        if hasattr(k, "co_name"):
            if k.co_name == name: return k
            r = find(k, name)
            if r is not None: return r
    return None
for n in ("yaml_dumps", "yaml_dump"):
    m = find(code, n)
    print(f"=== {n} ===")
    dis.dis(m)
print("=== 顶层（找 representer 注册） ===")
for ins in dis.get_instructions(code):
    if ins.opname in ("LOAD_METHOD","LOAD_ATTR","LOAD_NAME","LOAD_GLOBAL") and "represent" in str(ins.argval):
        print(ins.opname, ins.argval)
