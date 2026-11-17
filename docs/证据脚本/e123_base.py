import marshal, dis
p = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\tools\yaml_.pyc"
code = marshal.loads(open(p,"rb").read()[16:])
ins = list(dis.get_instructions(code))
for i,x in enumerate(ins):
    if x.opname == "BUILD_CLASS":
        print("--- class 构建上下文 ---")
        for y in ins[max(0,i-10):i+2]:
            print(f"   {y.offset:5d} {y.opname:20s} {y.argval}")
