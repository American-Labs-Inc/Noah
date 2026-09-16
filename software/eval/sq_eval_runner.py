#!/usr/bin/env python3
"""Albanian eval runner: one question at a time through the full pipeline,
per-question watchdog (survives a mid-call freeze), and RESUME across
restarts. If the device powers off, relaunch with the same output path and
it continues from the next unanswered question instead of starting over."""
import sys, time, threading, traceback
sys.path.insert(0, "/home/aldo")
import assistant

QF = sys.argv[1] if len(sys.argv) > 1 else "/home/aldo/eval/sq_long_questions.txt"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/home/aldo/eval/sq_long_out.txt"

qs = [l.strip() for l in open(QF, encoding="utf-8")
      if l.strip() and not l.startswith("#")]

# resume: count fully-completed answers already in OUT (each ends in a
# "--- burimet:" line), skip them, and append the rest.
done = 0
try:
    with open(OUT, encoding="utf-8") as fh:
        done = sum(1 for l in fh if l.startswith("--- burimet:"))
except FileNotFoundError:
    pass


def answer_with_watchdog(q, timeout=420):
    res = {}

    def _call():
        try:
            res["v"] = assistant.answer(q)
        except Exception:
            res["e"] = traceback.format_exc(limit=3)

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout)
    if "v" in res:
        return res["v"], ""
    return ("", []), res.get("e", "WATCHDOG TIMEOUT %ds" % timeout)


mode = "a" if done else "w"
out = open(OUT, mode, encoding="utf-8")
if not done:
    out.write("Noah soak eval: %s, %d questions, model %s\n"
              % (time.strftime("%Y-%m-%d %H:%M"), len(qs), assistant.MODEL))
else:
    out.write("\n=== RESUMED %s at Q%d ===\n" % (time.strftime("%H:%M"), done + 1))
    print("resuming from Q%d/%d" % (done + 1, len(qs)), flush=True)
out.flush()

for i, q in enumerate(qs, 1):
    if i <= done:
        continue
    for attempt in (1, 2):
        t0 = time.time()
        (resp, sources), err = answer_with_watchdog(q)
        dt = time.time() - t0
        if resp and resp.strip():
            break
        print("Q%d attempt %d empty/failed (%.0fs), retry" % (i, attempt, dt), flush=True)
        time.sleep(5)
    out.write("\n=== Q%d (%.1fs%s) ===\n%s\n--- pergjigja ---\n%s\n--- burimet: %s\n"
              % (i, dt, "" if attempt == 1 else ", retry", q,
                 resp.strip() if resp else "[EMPTY]\n" + err,
                 ", ".join(sources)))
    out.flush()
    print("Q%d/%d done %.1fs" % (i, len(qs), dt), flush=True)

out.write("\n=== EVAL COMPLETE %s ===\n" % time.strftime("%H:%M:%S"))
out.close()
print("EVAL COMPLETE", flush=True)
