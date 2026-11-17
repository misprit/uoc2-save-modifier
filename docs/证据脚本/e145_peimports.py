"""解析 PE 导入表：看 .pyd/.dll 到底缺哪个依赖（纯标准版）。"""

from __future__ import annotations

import struct
import sys
from pathlib import Path


def read_imports(path: Path) -> list[str]:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("not PE")
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off : pe_off + 4] != b"PE\0\0":
        raise ValueError("bad PE sig")
    coff = pe_off + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    pe32plus = magic == 0x20B
    dd_off = opt + (112 if pe32plus else 96)
    imp_rva, imp_size = struct.unpack_from("<II", data, dd_off + 8)

    sections = []
    sec_off = opt + opt_size
    for i in range(num_sections):
        s = sec_off + i * 40
        name = data[s : s + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, s + 8)
        sections.append((vaddr, vsize, raddr, rsize))

    def rva2off(rva: int) -> int:
        for vaddr, vsize, raddr, rsize in sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return raddr + (rva - vaddr)
        raise ValueError(f"bad rva {rva:#x}")

    out: list[str] = []
    off = rva2off(imp_rva)
    while True:
        entry = data[off : off + 20]
        if len(entry) < 20 or entry == b"\0" * 20:
            break
        name_rva = struct.unpack_from("<I", entry, 12)[0]
        if name_rva == 0:
            break
        noff = rva2off(name_rva)
        end = data.index(b"\0", noff)
        out.append(data[noff:end].decode("ascii", "replace"))
        off += 20
    return out


for arg in sys.argv[1:]:
    p = Path(arg)
    try:
        imps = read_imports(p)
    except Exception as exc:
        print(f"{p.name}: 解析失败 {exc}")
        continue
    print(f"=== {p.name} ===")
    for imp in imps:
        print(f"    {imp}")
