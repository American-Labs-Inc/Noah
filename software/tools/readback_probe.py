#!/usr/bin/env python3
"""Data-integrity probe: does what we WRITE actually land where we point?
1) LISAR register write/readback stress (30x) - catches SPI corruption on
   register writes (the mechanism that would displace whole frames).
2) Full-frame load, then MEM_BST_RD readback at 3 row offsets - compares
   wire-expected bytes vs controller RAM, and scans for displaced markers.
Run with noah-ui STOPPED."""
import sys, time
sys.path.insert(0, "/home/aldo")
import numpy as np
import eink

def stamp(m): print(m, flush=True)

EPD = eink.EInk()
stamp("panel up, imgbuf=0x%08X" % EPD.imgbuf)

# ---- 1) register write/readback stress ----
bad = 0
tests = [0x0000, 0xFFFF, 0x4850, 0xA5A5, 0x5A5A] * 6
for i, v in enumerate(tests):
    EPD._wreg(0x0208, v)
    r = EPD._rreg(0x0208)
    if r != v:
        bad += 1
        stamp("  LISAR MISMATCH #%d: wrote 0x%04X read 0x%04X" % (i, v, r))
EPD._wreg(0x0208, EPD.imgbuf & 0xFFFF)   # restore
stamp("reg stress: %d/30 corrupted" % bad)

# ---- 2) frame readback ----
H, W = eink.H, eink.W
img = np.zeros((H, W), np.uint8)          # black frame
for r in (0, 100, 1000):                  # distinctive white marker runs
    img[r, 0:64] = 255
# expected wire bytes (same pipeline as _load)
nib = (img >> 4).astype(np.uint8)
packed = (nib[:, 0::2] | (nib[:, 1::2] << 4)).tobytes()
expect = np.frombuffer(packed, dtype="<u2").byteswap().tobytes()
ROW = W // 2                              # packed bytes per row

stamp("loading test frame (no display)...")
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

ok = True
for r in (0, 100, 1000):
    off = r * ROW
    got = burst_read(EPD.imgbuf + off, 32)          # 64 bytes
    exp = expect[off:off + 64]
    match = got == exp
    ok = ok and match
    stamp("row %4d: %s" % (r, "OK" if match else "MISMATCH got=%s exp=%s" %
                           (got[:16].hex(), exp[:16].hex())))
    if not match:
        # scan +-2 rows around expectation for the displaced marker
        win = burst_read(EPD.imgbuf + max(0, off - 2 * ROW), (4 * ROW) // 2)
        k = win.find(exp[:16])
        stamp("  marker found at delta %s bytes" %
              (str(k - min(off, 2 * ROW)) if k >= 0 else "NOT FOUND in +-2 rows"))
stamp("frame readback: %s" % ("CLEAN" if ok else "CORRUPTED"))
