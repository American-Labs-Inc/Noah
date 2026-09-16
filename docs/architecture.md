# Architecture

```
 keyboard (BT HID) ──► noah_ui.py ──► assistant.answer(question)
                          │                       │
                          │   1. smalltalk?  → canned bilingual reply
                          │   2. is_albanian? → sq→en (NLLB ct2 int8)
                          │   3. classify intent (LLM, no passages)
                          │                       │
                          │        ┌──────────────┴───────────────┐
                          │     GENERAL (default)          FIRST AID (medical only)
                          │        │                              │
                          │  llama3.2:3b answers          4. hybrid retrieval
                          │  from its own knowledge          (BM25 + Chroma, RRF)
                          │  (+ light danger scrub)       5. llama3.2:3b, passages only
                          │        │                         + first-person patient stamp
                          │        │                      6. degeneration/short retries
                          │        │                      7. SAFETY LAYER (safety.py):
                          │        │                         fired_rules → CONTRA →
                          │        │                         danger_scrub → med caution
                          │        │                      8. prepend KUJDES warnings
                          │        └──────────────┬───────────────┘
                          │                       │
                          │            en→sq translation + ~150 SQ fixes
                          ▼                       ▼
                    e-ink display  ◄──────  paginated answer
                    (IT8951 driver, eink.py)
```

Noah is a general assistant. By default every question is answered from what the local model already knows. A short classifier call, run without any reference passages so the first aid material can never leak into an everyday answer, decides whether a question is really about an injury, an illness, or an emergency. Only those go to the grounded first aid branch, which searches the optional reference index and runs the safety layer. If that index is not installed, the medical branch falls back to a general answer with the safety warnings still added.

## Key design decisions

- **General by default, grounded where it matters.** The main path is a plain general assistant. The first aid grounding and the safety layer are a specialization that only kicks in for real medical questions. They keep those answers safe and sourced, without turning everyday questions into first aid.
- **The rules sit above the model, for medical answers.** A 3B model cannot be trusted with life and death edge cases. So in the medical branch, every dangerous case found during testing became a fixed warning, triggered by a pattern match, that prints before the model's own text no matter what the model says. The model adds the depth and the rules set the floor. See [safety-system.md](safety-system.md).
- **The translation sandwich.** The model never sees Albanian. The question goes in, gets translated to English, the model answers in English, and the answer is translated back. Idiom rewrites and a large correction table are applied afterward, because a general translation model does not know the Albanian medical vocabulary.
- **E-ink discipline.** The IT8951 stores each frame at 8 bits per pixel, so its 8 MB of RAM holds exactly two frames, the working one and the parked home screen. A full screen deep refresh in one pass draws more than the prototype's 5 V wiring can supply, so deep refreshes run as two half screen GC16 passes. Typing uses 16px aligned A2 strips, with a clean up pass every time it returns home.
- **Power states.** A short press of the button sleeps the device, keeping RAM and the warm model, and it wakes in about three seconds. A long press shows a "Powered off" screen, which e-ink holds at zero power, and then shuts down cleanly. A small splash service paints a loading screen as soon as the panel is ready, before the rest of the interface is up.

## Timings (measured on the prototype)

| Event | Time |
|---|---|
| Cold boot to ready | about 50 to 60 s |
| Wake from sleep | about 3 s |
| General English answer | about 10 to 20 s |
| Albanian answer | slower, because of translation |
| Deep home repaint | about 5.5 s |
