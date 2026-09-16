#!/usr/bin/env python3
"""One-time glass recovery using ONLY the typing-strip op class:
full-width strip loads + strip displays from the MAIN buffer (the exact
mechanics the typing path has proven for weeks; <=128px tall, ~8% of pixels
per op, power-safe and protocol-safe). Black sweep, white sweep, every
pixel actively driven twice, wiping today's garbage and resyncing the
controller's frame state. Leaves the glass white; the service restart
paints home. Run with the noah-ui service STOPPED."""
import sys, time
sys.path.insert(0, "/home/aldo")
import numpy as np
import eink

t0 = time.time()
def stamp(m): print("%6.1f  %s" % (time.time() - t0, m), flush=True)

stamp("init panel (RST clears any poisoned engine state)")
EPD = eink.EInk()
W, H = eink.W, eink.H
STRIP = 108                       # 1404 = 13 * 108 exactly; <=128px proven
black = np.zeros((STRIP, W), np.uint8)
white = np.full((STRIP, W), 255, np.uint8)

for name, strip in (("black", black), ("white", white)):
    stamp("%s sweep (13 strips)" % name)
    for y in range(0, H, STRIP):
        EPD._load(strip, y=y)
        EPD._display(eink.MODE_DU, 0, y, W, STRIP)
    stamp("%s sweep done" % name)

stamp("recovery complete, glass should be uniform white")
