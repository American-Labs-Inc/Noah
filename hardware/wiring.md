# Wiring guide

All references are to the Jetson Orin Nano Developer Kit. Header pins are
counted from the printed "1" on the carrier board (odd/even rows). **Never
connect or disconnect anything with power applied.**

## 1. E-ink panel (Waveshare IT8951 HAT (B))

The HAT is *not* stacked on the 40-pin header. It is wired with individual
jumpers so the enclosure can position it freely. The HAT header follows the
Raspberry Pi layout, so the pin numbers match on both ends.

| Signal | Jetson 40-pin | HAT pin | Notes |
|---|---|---|---|
| 5V | pin 2 (and 4) | 5V (2/4) | ⚠️ One jumper sags under load (see §4). |
| GND | pin 6 (add 9/14) | GND (6/9/14) | More grounds = better. |
| SCK | pin 23 (SPI1_SCK) | CLK | 4 MHz max on jumper wiring. 12 MHz corrupts commands. |
| MOSI | pin 19 (SPI1_MOSI) | DIN | |
| MISO | pin 21 (SPI1_MISO) | DOUT | |
| CS | pin 24 | CS | Driven as GPIO (gpiochip0 line 136), not hardware CS. |
| RST | pin 11 | RST | gpiochip0 line 112. |
| BUSY (HRDY) | pin 13 | BUSY | gpiochip0 line 122. |

Panel specifics baked into the driver ([`software/eink.py`](../software/eink.py)):
VCOM **−1.58 V** (read your own panel's sticker and change `VCOM_MV`!),
SPI 4 MHz, 4-bits-per-pixel transfers.

**Pinmux is mandatory.** JetPack boots these pads in the wrong function; the
included [`fix-gpio-pinmux.service`](../software/system/fix-gpio-pinmux.service)
writes the pad registers with `busybox devmem` at every boot (SPI1 pads to
SFIO, CS and RST to GPIO, LED pads). Without it the panel reads all zeros.
Do not rely on `jetson-io` overlays, because on this system they silently fail
to apply at boot.

## 2. Power button

A momentary switch across the **PWR BTN ↔ GND pins of the 12-pin button
header (J14)**. Behavior is implemented in software (`noah_ui.py` watches the
key events; systemd-logind is told to ignore the key):

- Short press: silent suspend / wake (model stays warm, ~3 s to usable).
- Hold ≈ 3 s: draws a persistent "FIKUR · POWERED OFF" screen, then clean
  shutdown. The image stays on the e-ink while the device is off.
- Short press while off: powers back on.

## 3. LEDs

| LED | Jetson pin (BOARD) | Notes |
|---|---|---|
| Power | 31 | Series resistor ≈ 330 Ω to GND. |
| Signal ("thinking") | 7 | Blinks while an answer is being generated. |

Both shine through the printed `NOAH_LED_Lens.stl`.

## 4. Power, read this twice

- Supply: USB-C PD, **15 V profile** (65 W class). The Jetson barrel/USB-C
  input takes it directly.
- ⚠️ **The 20 V cable trap.** Some USB-C cable + supply combinations negotiate
  **20 V**, which is above the dev kit's rating. During development one cable
  was found doing exactly that. Before running from any battery or new
  supply: verify the negotiated voltage with a USB-C power meter or
  multimeter, and physically mark known-good cables. Never power Noah from
  an unverified cable.
- ⚠️ **5 V panel feed.** The e-ink drive current over a single 5 V jumper
  causes voltage sag: full-screen deep refreshes abort, and at the worst
  point half-screen refreshes failed silently. The software works around it
  (half-screen deep refreshes only), but the real fix is copper: run 5 V
  from **both** pin 2 and pin 4 and grounds from pins 6 + 9 + 14 (parallel
  jumpers), or better, a soldered harness. After reinforcement, the software
  can be switched to single-pass full-screen refreshes.

## 5. Assembly order

See [assembly.md](assembly.md).
