#!/usr/bin/env python3
"""Noah device UI. Standalone e-ink + USB-keyboard interface.

Runs on the console TTY at boot (noah-ui.service) or manually via
`sudo python3 noah_ui.py`. Keys: type + ENTER = ask; while an answer is
shown: ENTER/space/n = next page, p = previous, ESC = home, any letter =
start a new question. Ctrl+C exits.
"""
import sys, os, re, time, select, termios, tty, signal, struct, threading, subprocess

sys.path.insert(0, "/home/aldo/.local/lib/python3.10/site-packages")
sys.path.insert(0, "/home/aldo")
os.chdir("/home/aldo")

import numpy as np
from PIL import Image, ImageDraw, ImageFont

print("[noah-ui] loading pipeline (chroma + BM25 + panel)...", flush=True)
import assistant                     # REPL is __main__-guarded; import wires everything
from eink import W, H, MODE_DU, MODE_A2, MODE_GC16

EPD = assistant.EPD
if EPD is None:
    print("[noah-ui] FATAL: e-ink panel unavailable, check wiring/pinmux", flush=True)
    sys.exit(1)

FD = "/usr/share/fonts/truetype/dejavu/"
F_TITLE = ImageFont.truetype(FD + "DejaVuSans-Bold.ttf", 120)
F_SUB = ImageFont.truetype(FD + "DejaVuSans.ttf", 40)
F_IN = ImageFont.truetype(FD + "DejaVuSansMono.ttf", 44)
F_HINT = ImageFont.truetype(FD + "DejaVuSans.ttf", 30)

INPUT_Y, INPUT_H = 840, 160
HOME_SLOT = 1                      # static home screen parked in controller RAM.
                                   # RAM MAP (2026-08-29, probed): the IT8951 stores
                                   # every frame 8bpp = 0x281AC0 bytes, so its 8MB
                                   # SDRAM fits exactly TWO frames above imgbuf:
                                   # slot 0 = imgbuf (working frame), slot 1 = home.
                                   # There are NO other slots. Ever.
_partials = 0
_prev_strip = None                 # last input strip, for diff-region updates
_home_loaded = False


def _np(im):
    a = np.frombuffer(im.tobytes(), dtype=np.uint8).reshape(im.size[1], im.size[0])
    return np.where(a > 160, 255, 0).astype(np.uint8)


def _center(d, text, font, y, im_w=W):
    d.text(((im_w - d.textlength(text, font=font)) // 2, y), text, font=font, fill=0)


LOGO = None
try:
    LOGO = (Image.open("/home/aldo/noah_logo.png").convert("L")
            .resize((680, 125), Image.LANCZOS))
except Exception as _e:
    print("[noah-ui] logo unavailable, text fallback: %s" % _e, flush=True)


def _brand(d, im):
    """Noah wordmark + byline + site. Drawn identically on the home and
    sleep screens so wake transitions never repaint the heavy logo pixels."""
    if LOGO is not None:
        im.paste(LOGO, ((W - LOGO.width) // 2, 160))
    else:
        _center(d, "Noah", F_TITLE, 170)
    _center(d, "by American Labs", F_SUB, 315)
    t = "american.al"
    d.text((W - d.textlength(t, font=F_HINT) - 118, H - 150), t, font=F_HINT, fill=0)


def home_image(buf="", status="gati · ready"):
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    _brand(d, im)
    d.line((150, 440, W - 150, 440), fill=0, width=4)
    _center(d, "Asistent AI pa internet · Offline AI assistant", F_SUB, 480)
    _center(d, "Pyetmë çfarëdo dhe shtyp ENTER", F_SUB, 620)
    _center(d, "Ask me anything and press ENTER", F_SUB, 680)
    strip = input_image(buf)
    im.paste(Image.fromarray(strip), (0, INPUT_Y))
    d.text((118, H - 150), status, font=F_HINT, fill=0)
    return _np(im)


def input_image(buf, status=""):
    im = Image.new("L", (W, INPUT_H), 255)
    d = ImageDraw.Draw(im)
    d.rectangle((118, 4, W - 118, 116), outline=0, width=3)   # 1cm from each edge
    shown = "> " + buf + "_"
    trimmed = buf
    while d.textlength(shown, font=F_IN) > W - 284 and len(trimmed) > 4:
        trimmed = trimmed[1:]
        shown = "> …" + trimmed + "_"
    d.text((142, 28), shown, font=F_IN, fill=0)               # 118 box + 24 inner pad
    if status:
        d.text((142, 122), status, font=F_HINT, fill=0)
    return _np(im)


def show_home(buf="", status="gati · ready"):
    global _partials, _prev_strip
    EPD.show(home_image(buf, status), MODE_DU)
    _partials = 0
    _prev_strip = None


# ---- boot / loading screen (2026-09-11) ----------------------------------
# The pipeline (chroma + BM25 import ~2.5s) and the LLM warm-up (~6s cold)
# finish before the main loop starts, so if we painted the normal typing
# screen at boot the input box would sit there unresponsive for several
# seconds. Instead we show a calm loading screen with NO input box until the
# assistant is actually live, then flash_home() reveals the typing screen.
# A small ring indicator animates so the device never looks frozen.
BOOT_BAND_Y, BOOT_BAND_H = 780, 120       # full-width strip for the animated dots


def _boot_band_im(k):
    """3 rings, k of them filled (k = 0..3): a calm 'working' indicator."""
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


def show_boot():
    EPD.show(boot_image(0), MODE_DU)


def _boot_ticker(done):
    """Animate the ring band via cheap full-width partial DU until done is set."""
    k = 0
    while not done.wait(0.7):
        k = k % 3 + 1
        try:
            strip = _np(_boot_band_im(k))
            with EPD.lock:                       # hold across load+display so the
                EPD._load(strip, 0, BOOT_BAND_Y) # main thread cannot interleave
                EPD._display(MODE_DU, 0, BOOT_BAND_Y, W, BOOT_BAND_H)
        except Exception:
            return


_home_np = None
_sleep_req = False
SLEPT = object()          # paging_loop result: the sleep screen is up, do not repaint home
SLEEP_FLAG = "/run/noah-sleep-drawn"


def _on_sleep_signal(signum, frame):
    global _sleep_req
    _sleep_req = True


signal.signal(signal.SIGUSR1, _on_sleep_signal)


# ---- power-off screen (2026-09-02, fresh design) -------------------------
# Noah watches the power-button input events itself (logind is set to ignore
# the key): short press = suspend exactly as before; holding ~3s draws the
# FIKUR screen and does a clean poweroff. E-ink keeps the image unpowered,
# so the off screen stays visible the whole time the device is off. A TERM
# handler covers other clean shutdowns (sudo poweroff); restarts/reboots
# deliberately draw nothing.
_off_req = [None]                      # None | "button" | "term"


def draw_off_screen():
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    _brand(d, im)
    d.line((150, 440, W - 150, 440), fill=0, width=4)
    _center(d, "FIKUR  ·  POWERED OFF", F_SUB, 480)
    _center(d, "Shtyp butonin për ta ndezur", F_SUB, 620)
    _center(d, "Press the button to power on", F_SUB, 680)
    EPD._load(_np(im))
    h1 = (H // 2 + 3) // 4 * 4                   # 4-row aligned halves (704/700)
    EPD._display(MODE_GC16, 0, 0, W, h1)         # crisp: image persists for
    EPD._display(MODE_GC16, 0, h1, W, H - h1)    # days on the dead panel
    print("[noah-ui] off screen drawn", flush=True)


def _handle_off_request(source):
    try:
        draw_off_screen()
    except Exception as e:                       # the off screen is nice to have,
        print("[noah-ui] off screen failed: %s" % e, flush=True)   # the power-off is not
    if source == "button":
        subprocess.Popen(["systemctl", "poweroff"])
    time.sleep(1)
    os._exit(0)


def _on_term(signum, frame):
    try:
        jobs = subprocess.run(["systemctl", "list-jobs", "--no-legend"],
                              capture_output=True, text=True, timeout=2).stdout
        if re.search(r"(poweroff|halt)\.target\s+\S*\s*start", jobs):
            _off_req[0] = "term"       # main loop draws, then exits
            return
    except Exception:
        pass
    os._exit(0)


signal.signal(signal.SIGTERM, _on_term)


def _find_power_devices():
    devs, name = [], ""
    try:
        for ln in open("/proc/bus/input/devices"):
            if ln.startswith("N: "):
                name = ln
            elif ln.startswith("H: ") and ("Power" in name or "gpio-keys" in name):
                m = re.search(r"event(\d+)", ln)
                if m:
                    devs.append("/dev/input/event" + m.group(1))
    except Exception:
        pass
    return devs


def _power_button_thread():
    devs = _find_power_devices()
    if not devs:
        print("[noah-ui] power watcher: NO BUTTON DEVICE FOUND", flush=True)
        return
    fds = [os.open(d, os.O_RDONLY) for d in devs]
    print("[noah-ui] power watcher on %s" % ",".join(devs), flush=True)
    pressed_at = None
    guard_until = 0.0                  # ignore the wake press after resume
    last_tick = time.time()
    while True:
        try:
            r, _, _ = select.select(fds, [], [], 0.25)
            now = time.time()
            if now - last_tick > 5.0:      # we slept through a suspend: the next
                guard_until = now + 5.0    # events are the wake press - ignore
                pressed_at = None
            last_tick = now
            for fd in r:
                try:
                    data = os.read(fd, 24 * 16)
                except OSError:
                    continue
                for off in range(0, len(data) - 23, 24):
                    _, _, etype, code, value = struct.unpack_from("llHHi", data, off)
                    if etype != 1 or code != 116:        # EV_KEY, KEY_POWER
                        continue
                    if value == 1:
                        pressed_at = now
                    elif value == 0 and pressed_at is not None:
                        held = now - pressed_at
                        pressed_at = None
                        if now < guard_until:
                            continue
                        if held < 3.0:           # any release before the 3.0s
                            print("[noah-ui] button: suspend", flush=True)   # power-off = short press
                            subprocess.Popen(["systemctl", "suspend"])
            if pressed_at is not None and time.time() - pressed_at >= 3.0:
                pressed_at = None
                if time.time() >= guard_until:
                    print("[noah-ui] button held: powering off", flush=True)
                    _off_req[0] = "button"
        except Exception as e:             # an unhandled error must not kill the
            print("[noah-ui] power watcher error (continuing): %s" % e, flush=True)
            time.sleep(2.0)                # watcher: that silently disables sleep/off


def draw_sleep_screen():
    """Painted just before suspend so a sleeping device is unmistakable."""
    global _partials, _prev_strip
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    # Brand block at the SAME position as the home screen: the heavy logo
    # pixels then never flip on wake, so the wake redraw has no saturated
    # ink to erase (kills the eroded-subtitle/ghost class).
    _brand(d, im)
    d.line((150, 440, W - 150, 440), fill=0, width=4)
    _center(d, "DUKE FJETUR  ·  SLEEPING", F_SUB, 480)
    _center(d, "Shtyp butonin për ta zgjuar", F_SUB, 620)
    _center(d, "Press the button to wake", F_SUB, 680)
    EPD.show(_np(im), MODE_DU)
    _partials = 0
    _prev_strip = None
    try:
        open(SLEEP_FLAG, "w").write("1")
    except Exception:
        pass
    print("[noah-ui] sleep screen drawn", flush=True)


def ensure_home_slot():
    """Park the home screen in controller RAM once; reuse forever."""
    global _home_loaded, _home_np
    if not _home_loaded:
        _home_np = home_image("", "gati · ready")
        EPD.load_page(_home_np, HOME_SLOT)
        _home_loaded = True


def flash_home():
    """-> home: FULL-SCREEN deep repaint - fresh home image loaded into the
    main buffer, then GC16 over each half (full screen in one GC16 pass
    power-aborts on the thin 5V feed; halves complete). GC16 drives every
    pixel regardless of the controller's frame belief, so each return home
    self-heals whatever the fast A2 typing mode or a glitched command left
    behind (user-chosen 2026-08-29: dumb full repaints beat smart diffs on
    this hardware). The old stitched-frame bug blamed on these halves was
    actually the slot-overlap RAM bug, since fixed; halves run from the
    MAIN buffer only - area ops from imgbuf are the weeks-proven class."""
    global _partials, _prev_strip, _home_np
    if _home_np is None:
        _home_np = home_image("", "gati · ready")
    t = time.time()
    EPD._load(_home_np)                          # fresh home into main buffer
    h1 = (H // 2 + 3) // 4 * 4                   # 4-row aligned halves (704/700)
    d1 = EPD._display(MODE_GC16, 0, 0, W, h1)
    d2 = EPD._display(MODE_GC16, 0, h1, W, H - h1)
    EPD.refreshes = 0
    print("[noah-ui] flash_home GC16 halves %.2f/%.2f (total %.1fs)"
          % (d1, d2, time.time() - t), flush=True)
    _partials = 0
    _prev_strip = None


def _align16(a, b, limit):
    a = max(0, (a // 16) * 16)
    b = min(limit, ((b + 15) // 16) * 16)
    return a, b


def update_input(buf, status="", mode=MODE_DU):
    global _partials, _prev_strip
    if _partials >= 12:                       # ghost management: periodic full redraw
        show_home(buf, "gati · ready")
        if not status:
            return
    strip = input_image(buf, status)
    prev, _prev_strip = _prev_strip, strip
    if prev is not None and prev.shape == strip.shape:
        diff = np.any(prev != strip, axis=0)
        cols = np.nonzero(diff)[0]
        if cols.size == 0:
            return
        x0, x1 = _align16(int(cols[0]), int(cols[-1]) + 1, W)
        rows = np.nonzero(np.any(prev[:, x0:x1] != strip[:, x0:x1], axis=1))[0]
        y0, y1 = _align16(int(rows[0]), int(rows[-1]) + 1, INPUT_H)
        if (x1 - x0) * (y1 - y0) < 0.6 * W * INPUT_H:   # small change: send sliver
            EPD._load(strip[y0:y1, x0:x1], x0, INPUT_Y + y0)
            EPD._display(mode, x0, INPUT_Y + y0, x1 - x0, y1 - y0)
            _partials += 1
            return
    EPD._load(strip, 0, INPUT_Y)
    EPD._display(mode, 0, INPUT_Y, W, INPUT_H)
    _partials += 1


def read_bytes(timeout):
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    if not r:
        return b""
    try:
        return os.read(sys.stdin.fileno(), 64)
    except OSError:
        return b""


def drain():
    while read_bytes(0):
        pass


def warm_model():
    print("[noah-ui] warming LLM...", flush=True)
    try:
        assistant.requests.post(f"{assistant.OLLAMA}/api/generate", json={
            "model": assistant.MODEL, "prompt": "ok", "stream": False,
            "options": {"num_predict": 1}}, timeout=180)
        return True
    except Exception as e:
        print("[noah-ui] warmup failed: %s" % e, flush=True)
        return False


def ask(question):
    import threading
    update_input(question, "Duke menduar… · Thinking…")
    print("[noah-ui] Q: %r" % question, flush=True)
    t0 = time.time()
    done = threading.Event()

    def ticker():                                # live elapsed-seconds status
        while not done.wait(6.0):
            try:
                update_input(question, "Duke menduar… · Thinking…  %ds" % (time.time() - t0))
            except Exception:
                return

    th = threading.Thread(target=ticker, daemon=True)
    th.start()
    try:
        text, sources = assistant.answer(question)
    except Exception as e:
        print("[noah-ui] answer error: %s" % e, flush=True)
        return None
    finally:
        done.set()
        th.join(timeout=25)
    pages = EPD.paginate_text(
        text, title=question,
        footer="ENTER = kthehu / back")
    print("[noah-ui] answered in %.1fs, %d page(s), %d chars: %r" % (
        time.time() - t0, len(pages), len(text), text[:120]), flush=True)
    return pages


def paging_loop(pages):
    """Show pages; return None to go home, or a first char of a new question.
    SINGLE-BUFFER paging: controller RAM holds exactly two frames (8bpp
    footprints - see HOME_SLOT note) and the second one parks the home
    screen, so pages go through the main buffer. A page turn costs ~4s
    (load + display); the old dual-slot preload SILENTLY CORRUPTED
    overlapping frames and must never come back at this RAM size."""
    i = 0
    EPD.show(pages[0], MODE_DU)
    drain()
    guard = time.time() + 1.2

    def goto(idx):
        nonlocal i, guard
        i = idx
        EPD.show(pages[idx], MODE_DU)
        drain()
        guard = time.time() + 1.2

    while True:
        data = read_bytes(0.5)
        global _sleep_req
        if _off_req[0]:
            _handle_off_request(_off_req[0])
        if _sleep_req:
            _sleep_req = False
            draw_sleep_screen()
            return SLEPT                         # sleep screen stays up; wake repaints home
        if data and time.time() < guard:
            continue                             # discard too-early keypresses
        for b in data:
            c = bytes([b])
            if c in (b"\r", b"\n"):
                if i < len(pages) - 1:
                    goto(i + 1)
                else:
                    return None                  # deliberate ENTER on last page -> home
            elif c in (b" ", b"n") and i < len(pages) - 1:
                goto(i + 1)
            elif c == b"p" and i > 0:
                goto(i - 1)
            elif c == b"\x1b":
                return None
            elif 32 < b < 127 and chr(b) not in "np ":
                return chr(b)                    # start typing a new question


def main():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    buf = ""
    try:
        threading.Thread(target=_power_button_thread, daemon=True).start()
        show_boot()                            # calm loading screen (no input box)
        boot_done = threading.Event()
        bt = threading.Thread(target=_boot_ticker, args=(boot_done,), daemon=True)
        bt.start()
        ok = warm_model()                      # ~6s cold: input box must NOT be up yet
        boot_done.set()
        bt.join(timeout=25)                    # a refresh can poll for up to 20s
        if ok:
            flash_home()                       # reveal the typing screen, crisp over the loader
        else:
            show_home("", "Modeli s'u ngarkua · The model didn't load")
        print("[noah-ui] READY", flush=True)
        last_draw, dirty = 0.0, False
        panel_errs = []                        # recent loop exceptions, for escalation
        fast_until = 0.0                       # typing burst: A2 + tighter cadence
        last_iter = time.time()
        global _sleep_req
        while True:
          try:
            data = read_bytes(0.3)
            now = time.time()
            if _off_req[0]:
                _handle_off_request(_off_req[0])
            if _sleep_req:
                _sleep_req = False
                draw_sleep_screen()
                buf, dirty = "", False
                continue
            if now - last_iter > 8.0:          # time jump = we just woke up
                print("[noah-ui] wake detected, redrawing home", flush=True)
                drain()
                flash_home()                   # deep GC16 rewrite: no sleep-screen ghosts
                buf, dirty = "", False
            last_iter = now
            if data:
                fast_until = now + 60.0
            for ch in data.decode("utf-8", "ignore"):   # decode so multibyte
                o = ord(ch)                              # Albanian ç, ë survive
                if o in (13, 10):                       # ENTER
                    q = buf.strip()
                    if q and (len(q) < 3 or len(set(q.lower().replace(" ", ""))) < 3):
                        # mashed/held keys: don't burn an LLM call on garbage
                        print("[noah-ui] rejected garbage input: %r" % q[:40], flush=True)
                        buf = ""
                        update_input("", "Nuk e kuptova, provo përsëri · I didn't catch that, try again")
                        dirty = False
                        last_draw = time.time()
                    elif q:
                        drain()
                        pages = ask(q)
                        buf = ""
                        if pages is None:
                            update_input("", "Diçka shkoi keq, provo përsëri · Something went wrong, try again")
                        else:
                            nxt = paging_loop(pages)
                            if nxt is SLEPT:            # sleep screen is up: leave it
                                nxt = None              # (the wake path repaints home)
                            else:
                                flash_home()            # one GC16 transition, deghosts too
                            if nxt:
                                buf = nxt
                        dirty = bool(buf)
                        last_draw = time.time()
                        last_iter = time.time()         # answer flow isn't a wake:
                                                        # without this, the time spent
                                                        # answering/reading trips the
                                                        # >8s wake detector and home
                                                        # repaints twice
                elif o in (127, 8):                     # backspace: WORD-wise,
                    # remove the trailing word plus any punctuation stuck to it
                    # (or a bare trailing punctuation run), then redraw
                    buf = re.sub(r"(\w+\W*|\W+)$", "", buf)
                    dirty = True
                elif o == 27:                           # ESC: clear line
                    buf = ""
                    dirty = True
                elif ch.isprintable() and len(buf) < 200:   # printable incl. ç, ë
                    buf += ch
                    if not ch.isalnum():                # word-at-a-time refresh:
                        dirty = True                    # letters buffer silently;
                                                        # space, comma, dot, ?, !
                                                        # or any punctuation draws
            fast = now < fast_until
            if dirty:                                   # draw immediately on trigger
                update_input(buf, mode=(MODE_A2 if fast else MODE_DU))
                last_draw = now
                dirty = False
          except KeyboardInterrupt:
            raise
          except Exception as e:                        # a one-off panel glitch (HRDY
            if _off_req[0]:                             # timeout, SPI desync) must not
                _handle_off_request(_off_req[0])        # crash the UI; while shutting
            now = time.time()                           # down, finish the power-off instead
            panel_errs = [t for t in panel_errs if now - t < 120.0] + [now]
            if len(panel_errs) >= 3:                    # wedged panel: exit so systemd
                print("[noah-ui] repeated panel errors, exiting for a hard reset: %s" % e, flush=True)
                raise                                   # restarts us and EInk() re-inits with RST
            print("[noah-ui] loop error, recovering (%d/3): %s" % (len(panel_errs), e), flush=True)
            try:
                drain(); flash_home()                   # repaint home, keep going
                last_iter = time.time()                 # repaint worked: not a wake
            except Exception:
                pass                                    # leave last_iter stale so the
            buf, dirty = "", False                      # wake path retries the repaint
            time.sleep(0.5)                             # (and counts toward escalation)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print("[noah-ui] exit", flush=True)


if __name__ == "__main__":
    main()
