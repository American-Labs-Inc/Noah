#!/usr/bin/env python3
"""Noah e-ink renderer - IT8951 (7.8" 1872x1404) over SPI on Jetson Orin Nano.

Proven protocol recipe (2026-08-26 bring-up):
  * 4 MHz SPI max on current wiring; wait HRDY before EVERY preamble
  * bulk pixel writes framed per 2 KB chunk (preamble each chunk)
  * displays via DPY_BUF_AREA 0x0037 only (0x0034 dies after first use)
  * VCOM must be programmed (-1.58 V) every panel power-on
  * DU (mode 1) / A2 (mode 6) complete on current 5 V wiring; full-screen
    GC16 (mode 2) aborts until the power feed is upgraded - use DU for text.

Usage:
    from eink import EInk
    epd = EInk()
    pages = epd.paginate_text(answer, title=question, footer="sources: ...")
    epd.show(pages[0])          # DU refresh, auto ghost management
    epd.close()

CLI self-test:  sudo python3 eink.py ["text to render"]
"""
import re, threading, time
import spidev, gpiod
import numpy as np
from PIL import Image, ImageDraw, ImageFont

RST_LINE, CS_LINE, BUSY_LINE = 112, 136, 122     # gpiochip0 (pins 11 / 24 / 13)
VCOM_MV = 1580                                    # panel sticker: -1.58 V
SPI_HZ = 4000000
W, H = 1872, 1404

MODE_INIT, MODE_DU, MODE_GC16, MODE_A2 = 0, 1, 2, 6

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
MARGIN, TITLE_SIZE, BODY_SIZE, FOOT_SIZE = 118, 48, 40, 28  # 118px = 1cm @ 300dpi
LINE_PITCH = 54
GHOST_FLUSH_EVERY = 8      # white-flush before every Nth refresh


class EInk:
    def __init__(self, vcom=VCOM_MV, spi_hz=SPI_HZ):
        # Null the handles first so a failure partway can release cleanly. An
        # early-boot init can hit a transient EBUSY (the SPI1 pads are still
        # settling right after the pinmux switch): if that happens AFTER the
        # gpio lines are requested, leaving them held would make every retry
        # fail with EBUSY on our own lines. Release on any init failure.
        self._chip = self._rst = self._cs = self._busy = self._spi = None
        self.lock = threading.RLock()            # serialises panel transactions across threads
        try:
            self._chip = gpiod.Chip("gpiochip0")
            self._rst = self._chip.get_line(RST_LINE)
            self._cs = self._chip.get_line(CS_LINE)
            self._busy = self._chip.get_line(BUSY_LINE)
            self._rst.request(consumer="eink", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])
            self._cs.request(consumer="eink", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])
            self._busy.request(consumer="eink", type=gpiod.LINE_REQ_DIR_IN)
            self._spi = spidev.SpiDev()
            self._spi.open(0, 0)
            self._spi.mode = 0
            self._spi.max_speed_hz = spi_hz
            self.refreshes = 0

            # Reset + boot, then read device info. BOTH the wake (HRDY) and the
            # GET_DEV_INFO read can glitch at cold boot: a desynced SPI read
            # returns shifted words (observed: height read back as 1872 instead
            # of 1404), which used to FATAL the whole UI and force a restart.
            # Retry the entire reset -> SYS_RUN -> GET_DEV_INFO on a bad read.
            info = None
            for attempt in range(4):
                self._rst.set_value(0); time.sleep(0.2)
                self._rst.set_value(1); time.sleep(0.1)
                try:
                    self._ready(4.0)
                except RuntimeError:
                    if attempt == 3:
                        raise RuntimeError("IT8951 not ready after 4 reset attempts")
                    continue
                self._wcmd(0x0001)                   # SYS_RUN
                self._wcmd(0x0302)                   # GET_DEV_INFO
                info = self._rdata(20)
                if (info[0], info[1]) == (W, H) and ((info[3] << 16) | info[2]):
                    break                            # good, synced read
                if attempt == 3:
                    raise RuntimeError("bad device info after 4 tries: %s" % info[:4])
                time.sleep(0.15)                     # desynced read: reset & retry
            self.width, self.height = info[0], info[1]
            self.imgbuf = (info[3] << 16) | info[2]
            self._wreg(0x0004, 0x0001)               # I80CPCR: packed write
            self._wcmd(0x0039); self._wdata(0x0001); self._wdata(vcom)   # set VCOM
            # Load fonts INSIDE the try: a missing font file must also release the
            # GPIO lines + SPI, otherwise the panel locks out with EBUSY on retry.
            self._fonts = {
                "title": ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf", TITLE_SIZE),
                "body":  ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf", BODY_SIZE),
                "foot":  ImageFont.truetype(FONT_DIR + "DejaVuSansMono.ttf", FOOT_SIZE),
            }
        except BaseException:
            self._release_partial()
            raise

    def _release_partial(self):
        """Release whatever __init__ managed to acquire, on a failed init."""
        try:
            if self._spi is not None:
                self._spi.close()
        except Exception:
            pass
        for ln in (self._rst, self._cs, self._busy):
            try:
                if ln is not None:
                    ln.release()
            except Exception:
                pass
        try:
            if self._chip is not None:
                self._chip.close()
        except Exception:
            pass

    # ---------- low-level protocol ----------
    def _ready(self, tmo=6.0):
        t0 = time.time()
        while time.time() - t0 < tmo:
            if self._busy.get_value() == 1:
                return
        raise RuntimeError("IT8951 HRDY timeout")

    def _frame(self, preamble, payload):
        self._ready(); self._cs.set_value(0)
        try:
            self._spi.xfer2(list(preamble)); self._ready()
            self._spi.xfer2(list(payload))
        finally:
            self._cs.set_value(1)                # never leave CS low on a timeout

    def _wcmd(self, v):  self._frame((0x60, 0x00), (v >> 8, v & 0xFF))
    def _wdata(self, v): self._frame((0x00, 0x00), (v >> 8, v & 0xFF))

    def _rdata(self, n):
        self._ready(); self._cs.set_value(0)
        try:
            self._spi.xfer2([0x10, 0x00]); self._ready()
            self._spi.xfer2([0, 0]); self._ready()
            raw = self._spi.xfer2([0] * (2 * n))
        finally:
            self._cs.set_value(1)                # never leave CS low on a timeout
        return [(raw[i] << 8) | raw[i + 1] for i in range(0, 2 * n, 2)]

    def _wreg(self, a, v): self._wcmd(0x0011); self._wdata(a); self._wdata(v)
    def _rreg(self, a):    self._wcmd(0x0010); self._wdata(a); return self._rdata(1)[0]

    # ---------- image path ----------
    def _load(self, *args, **kw):
        with self.lock:                          # one panel transaction at a time
            return self._load_raw(*args, **kw)

    def _load_raw(self, img, x=0, y=0, addr=None):
        """img: np.uint8 (h, w), row-major, 0=black 255=white. 4bpp transfer
        (half the bytes of 8bpp - text is thresholded B/W, no quality loss)."""
        h, w = img.shape
        if w % 2 or x % 4 or x < 0 or y < 0 or x + w > W or y + h > H:
            raise ValueError("bad load area x=%d y=%d w=%d h=%d (need even w, x a "
                             "multiple of 4, inside %dx%d)" % (x, y, w, h, W, H))
        addr = self.imgbuf if addr is None else addr
        self._wreg(0x0208, addr & 0xFFFF)
        self._wreg(0x020A, addr >> 16)
        self._wcmd(0x0021)                       # LD_IMG_AREA
        for v in (0x0020, x, y, w, h):           # little-endian, 4bpp, rot0
            self._wdata(v)
        nib = (img >> 4).astype(np.uint8)        # 0x0 / 0xF
        packed = (nib[:, 0::2] | (nib[:, 1::2] << 4)).tobytes()
        data = np.frombuffer(packed, dtype="<u2").byteswap().tobytes()
        for off in range(0, len(data), 2048):
            self._ready(); self._cs.set_value(0)
            try:
                self._spi.xfer2([0x00, 0x00]); self._ready()
                self._spi.writebytes(data[off:off + 2048])
            finally:
                self._cs.set_value(1)            # never leave CS low on a timeout
        self._wcmd(0x0022)                       # LD_IMG_END

    def _display(self, *args, **kw):
        with self.lock:                          # one panel transaction at a time
            return self._display_raw(*args, **kw)

    def _display_raw(self, mode, x=0, y=0, w=W, h=H, tmo=20.0, addr=None):
        addr = self.imgbuf if addr is None else addr
        self._wcmd(0x0037)                       # DPY_BUF_AREA
        for v in (x, y, w, h, mode, addr & 0xFFFF, addr >> 16):
            self._wdata(v)
        t0 = time.time(); first = last = None
        grace = 2.0                              # a fast DU can finish between polls
        while time.time() - t0 < tmo:
            if self._rreg(0x1224):
                t = time.time() - t0
                if first is None: first = t
                last = t
            elif first is not None and (time.time() - t0 - last) > 0.5:
                break
            elif first is None and time.time() - t0 > grace:
                break                            # never saw busy: already done
        else:
            print("[eink] refresh did not go idle within %.0fs" % tmo, flush=True)
        return 0.0 if first is None else last - first

    def clear(self):
        """Full white via double DU pass (works on current power wiring)."""
        white = np.full((H, W), 0xFF, dtype=np.uint8)
        self._load(white)
        self._display(MODE_DU)
        self._display(MODE_DU)

    def show(self, img, mode=MODE_DU):
        """Load and display a full frame with automatic ghost management."""
        if self.refreshes and self.refreshes % GHOST_FLUSH_EVERY == 0:
            self.clear()
        self._load(img)
        dur = self._display(mode)
        self.refreshes += 1
        return dur

    # --- dual-buffer page slots: preload while reading, flip in ~0.5s ---
    SLOT_STRIDE = 0x290000  # TRUE 8bpp frame footprint 0x281AC0 + pad. RAM fits ONLY slots 0 (imgbuf) and 1 - see 2026-08-29 probe; never add more

    def _slot_addr(self, slot):
        if slot not in (0, 1):                   # RAM holds exactly two frames
            raise ValueError("slot must be 0 or 1, got %r" % (slot,))
        return self.imgbuf + slot * self.SLOT_STRIDE

    def load_page(self, img, slot=0):
        self._load(img, addr=self._slot_addr(slot))

    def show_slot(self, slot=0, mode=MODE_DU):
        return self._display(mode, addr=self._slot_addr(slot))

    def deep_clean(self):
        """Two half-screen GC16 passes - heavier ghost flush (half current draw)."""
        white = np.full((H, W), 0xFF, dtype=np.uint8)
        self._load(white)
        h1 = (H // 2 + 3) // 4 * 4               # keep both passes 4-row aligned (704/700)
        self._display(MODE_GC16, 0, 0, W, h1)
        self._display(MODE_GC16, 0, h1, W, H - h1)

    def close(self):
        # No STANDBY: wake-from-standby proved flaky; idle draw is acceptable
        # and the field device will gate panel power in hardware anyway.
        self._spi.close()
        for ln in (self._rst, self._cs, self._busy):
            ln.release()
        self._chip.close()

    # ---------- text rendering ----------
    def _wrap(self, draw, text, font, maxw):
        lines = []
        for raw in text.split("\n"):
            if not raw.strip():
                lines.append("")
                continue
            m = re.match(r"^(\s*(?:\d+[.)]\s+|[-*•]\s+)?)", raw)
            hang = " " * max(2, len(m.group(1))) if m.group(1).strip() else ""
            words, cur = raw.split(), ""
            firstline = True
            for wd in words:
                cand = (cur + " " + wd).strip() if cur else (wd if firstline else hang + wd)
                probe = cand if firstline else cand
                if draw.textlength(probe, font=font) <= maxw or not cur:
                    cur = cand
                else:
                    lines.append(cur)
                    firstline = False
                    cur = hang + wd
            lines.append(cur)
        return lines

    def paginate_text(self, text, title=None, footer=None):
        """Render text into 1..N full-frame numpy pages (thresholded B/W)."""
        probe = ImageDraw.Draw(Image.new("L", (8, 8)))
        maxw = W - 2 * MARGIN
        body_lines = self._wrap(probe, text, self._fonts["body"], maxw)

        top = MARGIN
        title_lines = []
        if title:
            title_lines = self._wrap(probe, title.strip(), self._fonts["title"], maxw)[:2]
            top += len(title_lines) * (TITLE_SIZE + 10) + 26
        usable = H - top - (FOOT_SIZE + 30 + MARGIN)
        per_page = max(1, usable // LINE_PITCH)
        chunks = [body_lines[i:i + per_page] for i in range(0, len(body_lines), per_page)] or [[]]

        pages = []
        for pi, chunk in enumerate(chunks):
            im = Image.new("L", (W, H), 255)
            d = ImageDraw.Draw(im)
            y = MARGIN
            for tl in title_lines:
                d.text((MARGIN, y), tl, font=self._fonts["title"], fill=0)
                y += TITLE_SIZE + 10
            if title_lines:
                d.line((MARGIN, y + 6, W - MARGIN, y + 6), fill=0, width=4)
                y += 26
            for ln in chunk:
                d.text((MARGIN, y), ln, font=self._fonts["body"], fill=0)
                y += LINE_PITCH
            fy = H - MARGIN - FOOT_SIZE
            avail = maxw
            n = len(chunks)
            foot_txt = footer
            if n > 1:                            # multi-page: counter + nav hint
                pg = "%d/%d" % (pi + 1, n)
                pgw = probe.textlength(pg, font=self._fonts["foot"])
                d.text((W - MARGIN - pgw, fy), pg, font=self._fonts["foot"], fill=0)
                avail = maxw - pgw - 60
                if pi < n - 1:                   # a next page exists
                    foot_txt = "ENTER/SPACE = tjetra / next"
                    if pi > 0:                   # ...and a previous page
                        foot_txt += "   P = mbrapa / prev"
                else:                            # last page
                    foot_txt = "P = mbrapa / prev   ENTER = kthehu / back"
            if foot_txt:
                ftxt = foot_txt
                if probe.textlength(ftxt, font=self._fonts["foot"]) > avail:
                    while ftxt and probe.textlength(ftxt + "…", font=self._fonts["foot"]) > avail:
                        ftxt = ftxt[:-1]
                    ftxt += "…"
                d.text((MARGIN, fy), ftxt, font=self._fonts["foot"], fill=0)
            arr = np.frombuffer(im.tobytes(), dtype=np.uint8).reshape(H, W)
            pages.append(np.where(arr > 160, 255, 0).astype(np.uint8))
        return pages


if __name__ == "__main__":
    import sys
    sample = sys.argv[1] if len(sys.argv) > 1 else (
        "An e-ink display forms its image by moving tiny charged pigment "
        "particles, not by lighting up pixels like an LCD.\n\n"
        "1. Each microcapsule holds white and black particles in a clear fluid.\n"
        "2. A voltage pulls one colour to the surface and pushes the other down.\n"
        "3. The particles then stay put with no power, so the image persists.\n"
        "4. That is why the panel keeps showing a page even after shutdown.\n\n"
        "The trade-off is speed: rewriting the whole panel takes a noticeable "
        "moment, which is why Noah draws typing updates in small strips and only "
        "does a full deep refresh when it needs a clean page.")
    epd = EInk()
    print("panel %dx%d ready, rendering test page..." % (epd.width, epd.height))
    pages = epd.paginate_text(
        sample, title="How does an e-ink display work?",
        footer="Noah offline AI assistant · eink.py self-test")
    t0 = time.time()
    dur = epd.show(pages[0])
    print("page 1/%d shown (load+refresh %.1fs, engine %.1fs)" % (len(pages), time.time() - t0, dur))
    epd.close()
    print("PASS - the panel should show a formatted page")
