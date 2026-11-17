"""验证随包 CPython 的 tkinter 能力：能否建窗、PhotoImage 能否读 PNG、能否任意缩放。

这是 GUI 技术方案的地基，必须先实测。
"""

from __future__ import annotations

import io
import struct
import sys
import zlib

print("python:", sys.version)
print("tkinter import:", end=" ")
try:
    import tkinter as tk

    print("OK", tk.TkVersion)
except Exception as exc:  # pragma: no cover
    print("FAIL", exc)
    raise SystemExit(1)

root = tk.Tk()
root.withdraw()
print("Tk root:", root.tk.call("info", "patchlevel"))
print("tk windowingsystem:", root.tk.call("tk", "windowingsystem"))

PNG = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\assets\surfaces\unit\us_inf_dlc7\sheet_L.png"
SPEC = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\assets\surfaces\specialist\spec_panzer_grenadier\sheet_large.png"
STEP = r"D:\SteamLibrary\steamapps\common\Unity of Command 2\_packages\base\assets\surfaces\steps\step.png"


def probe(path: str) -> None:
    try:
        img = tk.PhotoImage(file=path)
    except Exception as exc:
        print(f"  PhotoImage FAIL {path}: {exc}")
        return
    print(f"  PhotoImage OK {path.rsplit(chr(92), 1)[-1]} -> {img.width()}x{img.height()}")
    for n in (2, 4):
        try:
            small = img.subsample(n, n)
            print(f"    subsample({n}) -> {small.width()}x{small.height()}")
        except Exception as exc:
            print(f"    subsample({n}) FAIL {exc}")
    # PPM 往返：能不能把自造像素塞进去
    try:
        w, h = 4, 4
        ppm = b"P6\n4 4\n255\n" + bytes([255, 0, 0] * 16)
        img2 = tk.PhotoImage(data=ppm, format="ppm")
        print(f"    PPM 注入 OK -> {img2.width()}x{img2.height()}")
    except Exception as exc:
        print(f"    PPM 注入 FAIL: {exc}")


for p in (PNG, SPEC, STEP):
    probe(p)

print("\n--- 纯标准库 PNG 解码器自测 ---")


def decode_png(path: str) -> tuple[int, int, bytes]:
    raw = open(path, "rb").read()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "not a png"
    pos = 8
    idat = bytearray()
    width = height = bitdepth = colortype = 0
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos : pos + 4])
        ctype = raw[pos + 4 : pos + 8]
        body = raw[pos + 8 : pos + 8 + length]
        if ctype == b"IHDR":
            width, height, bitdepth, colortype = struct.unpack(">IIBB", body[:10])
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
        pos += 12 + length
    data = zlib.decompress(bytes(idat))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colortype]
    bpp = channels * bitdepth // 8
    stride = width * bpp
    out = bytearray()
    prev = bytearray(stride)
    p = 0
    for _ in range(height):
        ft = data[p]
        p += 1
        line = bytearray(data[p : p + stride])
        p += stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out += line
        prev = line
    return width, height, bytes(out)


for p in (PNG, STEP):
    try:
        w, h, px = decode_png(p)
        print(f"  decode {p.rsplit(chr(92), 1)[-1]} -> {w}x{h} bytes={len(px)}")
    except Exception as exc:
        print(f"  decode FAIL {p}: {exc}")

root.destroy()
