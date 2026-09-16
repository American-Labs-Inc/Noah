#!/usr/bin/env python3
"""Discriminate RAM storage format: does the controller expand 4bpp loads
to 8bpp (1 byte/pixel, row pitch 1872)? Also verify a non-overlapping
second frame base works cleanly end-to-end."""
import sys
sys.path.insert(0, "/home/aldo")
import numpy as np
import eink

def stamp(m): print(m, flush=True)

EPD = eink.EInk()
stamp("imgbuf=0x%08X  I80CPCR=0x%04X" % (EPD.imgbuf, EPD._rreg(0x0004)))

H, W = eink.H, eink.W
img = np.zeros((H, W), np.uint8)
for r in (0, 100, 1000):
    img[r, 0:64] = 255
EPD._load(img)

def burst_read(addr, nwords):
    EPD._wcmd(0x0012)
    for v in (addr & 0xFFFF, addr >> 16, nwords & 0xFFFF, nwords >> 16):
        EPD._wdata(v)
    EPD._wcmd(0x0013)
    words = EPD._rdata(nwords)
    EPD._wcmd(0x0015)
    b = bytearray()
    for w_ in words:
        b += bytes((w_ >> 8, w_ & 0xFF))
    return bytes(b)

# 8bpp hypothesis: row r at imgbuf + r*1872, white pixel stored as 0xF0
r0 = burst_read(EPD.imgbuf, 48)                      # 96 bytes
stamp("row0   head: %s.." % r0[:24].hex())
stamp("row0 @64..95: %s   (8bpp says zeros start at 64)" % r0[64:96].hex())
for r in (100, 1000):
    got = burst_read(EPD.imgbuf + r * 1872, 16)
    stamp("row%d @8bpp pitch: %s  (%s)" % (r, got[:16].hex(),
          "MARKER" if got[:8] == b"\xf0" * 8 else "no marker"))

# candidate second frame base (8bpp footprint 0x281AC0, padded stride 0x290000)
BASE2 = EPD.imgbuf + 0x290000
img2 = np.zeros((H, W), np.uint8)
img2[0, 0:64] = 255
img2[1403, 0:64] = 255
EPD._load(img2, addr=BASE2)
h2 = burst_read(BASE2, 16)
t2 = burst_read(BASE2 + 1403 * 1872, 16)
stamp("slot1' head: %s (%s)" % (h2[:8].hex(), "MARKER" if h2[:8] == b"\xf0" * 8 else "BAD"))
stamp("slot1' tail: %s (%s)" % (t2[:8].hex(), "MARKER" if t2[:8] == b"\xf0" * 8 else "BAD"))
# original imgbuf frame must be UNTOUCHED by the slot1' load (no overlap)
r1000 = burst_read(EPD.imgbuf + 1000 * 1872, 16)
stamp("imgbuf row1000 after slot1' load: %s (%s)" % (r1000[:8].hex(),
      "STILL MARKER - no overlap" if r1000[:8] == b"\xf0" * 8 else "CLOBBERED"))
d = EPD._display(eink.MODE_DU, addr=BASE2)
stamp("display from slot1' ok %.2fs - ALL CHECKS DONE" % d)
