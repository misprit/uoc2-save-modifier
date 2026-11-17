import marshal, dis
p = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\tools\yaml_.pyc"
code = marshal.loads(open(p,"rb").read()[16:])
ins = list(dis.get_instructions(code))
for i,x in enumerate(ins):
    if x.opname in ("LOAD_BUILD_CLASS","MAKE_FUNCTION") and 300 < x.offset < 360:
        print(f"--- {x.offset} {x.opname} ---")
        for y in ins[max(0,i-12):i+3]:
            print(f"   {y.offset:5d} {y.opname:20s} {y.argval}")
