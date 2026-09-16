# Noah software

Everything runs on the Jetson under systemd. The paths assume a user called `aldo` with the code in `/home/aldo`. Either create that user, or search and replace the paths in the `.py` files and the service units.

## Components

| File | What it does |
|---|---|
| `noah_ui.py` | The device interface: the e-ink screens, keyboard input, the power button watcher (sleep and power off), the typing refresh, and answer pagination. |
| `noah_splash.py` | The early boot splash. It paints a loading screen as soon as the panel is up, well before the full UI is ready, so booting feels smoother. |
| `assistant.py` | Ties the pipeline together. General questions, which are the default, go straight to the local model: detect the language, translate, ask the model, translate back. Only clearly medical questions also go through retrieval and the safety layer. Small talk gets a fixed reply. |
| `safety.py` | The safety layer for medical questions: 50 bilingual first aid rules, 9 full answer replacements, a scrubber that drops dangerous sentences, a rule veto map, and a medication caution. It also tests itself, since `python3 safety.py` runs a 260 case matrix. |
| `translator.py` | Albanian and English through NLLB-200 (CTranslate2 int8), with language detection, idiom rewrites, and roughly 150 fixes applied after translation. |
| `retrieval.py` | Hybrid retrieval over the optional first aid index: BM25 plus Chroma vectors, fused by reciprocal rank, with query expansions and a filter for outdated advice. |
| `eink.py` | The IT8951 e-ink driver over SPI and GPIO: 4bpp transfers, partial refresh, the controller RAM map, and the GC16 and DU waveforms. |
| `ingest.py` | Builds the optional first aid index from the reference PDFs, with a blocklist for outdated medical advice. |
| `recovery_strips.py` | A glass recovery tool that sweeps the screen strip by strip in black and white. Run it with the service stopped. |
| `system/` | The systemd units and the logind config. |
| `eval/` | The eval harness and every bilingual question set from the 13 audit rounds. |
| `tools/` | Controller diagnostics (the RAM readback probes). |

## Setup

### 1. Base system

JetPack 6.x (Ubuntu 22.04) on a Jetson Orin Nano 8 GB. Then:

```bash
sudo apt update && sudo apt install -y python3-pip busybox librsvg2-bin
pip3 install chromadb requests pillow numpy rank_bm25 langdetect \
             ctranslate2 transformers sentencepiece Jetson.GPIO spidev
```

### 2. LLM runtime

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

### 3. Translation model (Albanian)

Convert NLLB-200-distilled-600M to CTranslate2 int8 and place it at
`/data/models/nllb-ct2-int8`:

```bash
pip3 install "ctranslate2" "transformers[torch]"
ct2-transformers-converter --model facebook/nllb-200-distilled-600M \
  --output_dir /data/models/nllb-ct2-int8 --quantization int8
```

### 4. Optional first aid library (not included, for copyright reasons)

Noah works as a general assistant without this step. You only need it for the optional first aid feature, which answers medical questions from trusted references instead of the model alone. To turn it on, create `~/emergency-library/` and add:

- **IFRC International First Aid, Resuscitation and Education Guidelines 2025**, from ifrc.org
- **WHO Psychological First Aid: Guide for Field Workers**, from who.int
- **Where There Is No Doctor** by David Werner, free from hesperian.org
- **FEMA "Are You Ready?"**, from fema.gov (public domain)
- **FM 21-76 US Army Survival Manual**, public domain. Trim it to the medical and survival chapters so retrieval stays focused.

Then build the index. Stop any ollama models you do not need first, because ingest uses a lot of memory:

```bash
python3 ingest.py     # → ~/emergency-db (about 4,800 chunks)
```

If you skip this, `assistant.py` still starts normally and the first aid feature is simply off. Medical questions then fall back to a general answer with the safety warnings still added.

### 5. Panel driver notes (read before the first boot)

- Set `VCOM_MV` in `eink.py` to the value on your own panel's sticker.
- The pinmux service is mandatory (see `hardware/wiring.md`).
- SPI stays at 4 MHz. The controller stores every frame as 8 bits per pixel, so its 8 MB of RAM fits exactly two frames. Do not add parked buffers, and do not display partial areas from parked slots. These limits were mapped the hard way, and `tools/` has the probes that proved them.

### 6. Services

```bash
sudo cp system/noah-ui.service system/fix-gpio-pinmux.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/logind.conf.d
sudo cp system/noah-power-logind.conf /etc/systemd/logind.conf.d/
sudo systemctl daemon-reload
sudo systemctl enable --now fix-gpio-pinmux noah-ui
sudo systemctl restart systemd-logind
```

Optional: install the early boot splash so the loading screen appears sooner. It also uses the pinmux drop-in that brings the panel up earlier in boot:

```bash
sudo cp system/noah-splash.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/fix-gpio-pinmux.service.d
sudo cp system/fix-gpio-pinmux.service.d/10-early.conf \
        /etc/systemd/system/fix-gpio-pinmux.service.d/
sudo systemctl daemon-reload
sudo systemctl enable noah-splash
```

Pair the BB Q10 keyboard once with `bluetoothctl` (`pair` then `trust`).

## Running the eval

```bash
cd eval
python3 sq_eval_runner.py sq_long_questions.txt /tmp/out.txt
```

`safety.py` doubles as a regression test. Running `python3 safety.py` must print `ALL PASS` after any change to the rules. When you find a new way for the model to fail, the routine is to add the rule and pattern, add a matrix case, and rerun the question. That loop, repeated over 13 audit rounds, is where the safety layer came from.
