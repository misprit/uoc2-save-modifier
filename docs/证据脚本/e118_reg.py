import marshal, dis
p = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\lib\tools\yaml_.pyc"
code = marshal.loads(open(p,"rb").read()[16:])
ins = list(dis.get_instructions(code))
for i, x in enumerate(ins):
    if x.argval in ("add_representer","add_multi_representer","set_representer","dict_representer","str_representer","int_representer","float_representer","bool_representer","numpy_array","check_short_list"):
        lo = max(0, i-8); hi = min(len(ins), i+6)
        print(f"--- 命中 {x.argval} @ {x.offset} ---")
        for y in ins[lo:hi]:
            print(f"   {y.offset:5d} {y.opname:22s} {y.argval}")
        print()
