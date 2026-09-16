#!/usr/bin/env python3
"""Noah boot splash. Paint the loading screen on the e-ink panel as EARLY in
boot as possible, then release the panel so noah_ui.py can take over.

Runs from noah-splash.service: a tiny, early, oneshot unit ordered BEFORE
noah-ui.service. It imports ONLY the panel driver (spidev/gpiod/numpy/PIL,
~0.2s), never `assistant` (chroma + BM25 + LLM warm-up, the ~20s that used to
pass before anything appeared). The e-ink holds the painted image with no
refresh, so 'Starting Noah / One moment' stays on screen through the heavy
noah_ui startup until flash_home() reveals the typing screen.

KEEP THE RENDER IN SYNC with noah_ui.py: boot_image() / _boot_band_im().
"""
import sys, time
sys.path.insert(0, "/home/aldo/.local/lib/python3.10/site-packages")
sys.path.insert(0, "/home/aldo")

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from eink import EInk, W, H, MODE_DU

FD = "/usr/share/fonts/truetype/dejavu/"
F_TITLE = ImageFont.truetype(FD + "DejaVuSans-Bold.ttf", 120)
F_SUB = ImageFont.truetype(FD + "DejaVuSans.ttf", 40)
F_HINT = ImageFont.truetype(FD + "DejaVuSans.ttf", 30)
BOOT_BAND_Y, BOOT_BAND_H = 780, 120

LOGO = None
try:
    LOGO = (Image.open("/home/aldo/noah_logo.png").convert("L")
            .resize((680, 125), Image.LANCZOS))
except Exception:
    pass


def _np(im):
    a = np.frombuffer(im.tobytes(), dtype=np.uint8).reshape(im.size[1], im.size[0])
    return np.where(a > 160, 255, 0).astype(np.uint8)


def _center(d, text, font, y):
    d.text(((W - d.textlength(text, font=font)) // 2, y), text, font=font, fill=0)


def _brand(d, im):
    if LOGO is not None:
        im.paste(LOGO, ((W - LOGO.width) // 2, 160))
    else:
        _center(d, "Noah", F_TITLE, 170)
    _center(d, "by American Labs", F_SUB, 315)
    t = "american.al"
    d.text((W - d.textlength(t, font=F_HINT) - 118, H - 150), t, font=F_HINT, fill=0)


def _boot_band_im(k):
    im = Image.new("L", (W, BOOT_BAND_H), 255)
    d = ImageDraw.Draw(im)
    r, gap = 16, 90
    cx0 = (W - gap * 2) // 2
    cy = BOOT_BAND_H // 2
    for i in range(3):
        x = cx0 + i * gap
        box = (x - r, cy - r, x + r, cy + r)
        if i < k:
            d.ellipse(box, fill=0)
        else:
            d.ellipse(box, outline=0, width=3)
    return im


def boot_image(k=0):
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    _brand(d, im)
    d.line((150, 440, W - 150, 440), fill=0, width=4)
    _center(d, "Po nis Noah…  ·  Starting Noah…", F_SUB, 500)
    _center(d, "Një çast…  ·  One moment…", F_SUB, 600)
    im.paste(_boot_band_im(k), (0, BOOT_BAND_Y))
    return _np(im)


def main():
    # We start VERY early in boot (before the snapd/docker CPU storm), so the
    # /dev nodes or the panel controller may not be ready for a beat. Retry the
    # init briefly instead of giving up, so the screen still appears fast.
    t0 = time.time()
    epd = None
    last = None
    while time.time() - t0 < 12.0:               # soft bound: an in-flight init may overrun it
        try:
            epd = EInk()
            break
        except Exception as e:
            if last is None:                     # log the first transient once
                print("[noah-splash] waiting for panel (%r)" % e, flush=True)
            last = e
            time.sleep(0.4)
    if epd is None:
        print("[noah-splash] panel not ready: %s" % last, flush=True)
        return
    try:
        epd.show(boot_image(0), MODE_DU)
        print("[noah-splash] loading screen painted (%.1fs)" % (time.time() - t0), flush=True)
    except Exception as e:
        print("[noah-splash] paint failed: %s" % e, flush=True)
    finally:
        try:
            epd.close()                # release SPI + GPIO for noah_ui; image persists
        except Exception:
            pass


if __name__ == "__main__":
    main()
