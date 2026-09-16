import os, re, requests, chromadb, threading, time
import Jetson.GPIO as GPIO
import sys
sys.path.insert(0, "/home/aldo/.local/lib/python3.10/site-packages")  # sudo cant see user pip
import translator
import safety
import retrieval

DB_PATH = "/home/aldo/emergency-db"
OLLAMA = "http://localhost:11434"
MODEL = "llama3.2:3b"          # local LLM via ollama (multilingual, handles Albanian)
TOP_K = 4
LED_SIGNAL = 7
LED_POWER = 31
_DEGEN = re.compile(r"(\b\w{1,6}\b)(\s+\1\b){7,}")   # token loop ("JE JE JE...")

# Medical-branch prompt. Noah is a general-purpose assistant (see GENERAL_SYSTEM
# below, used for everything by default); this stricter, passages-only prompt is
# used ONLY when a question is classified as a genuine injury/illness/emergency,
# so those answers stay grounded in the bundled first aid references and run
# through the deterministic safety layer.
SYSTEM_PROMPT = """You are Noah, an offline assistant answering a first aid or medical question on a device with no internet access. Your answer must be drawn ONLY from the reference passages provided below. This question has already been identified as a medical or first aid one, so give the grounded emergency answer described here. Do not second-guess whether it is an emergency.

TONE, always: straight to the point and factual. No sympathy lines, no reassurance filler ("stay calm", "I am worried about you"), no apologies, no praise, no exclamation marks, no chit-chat. Every sentence must carry an instruction or a fact.

PERSPECTIVE, always: match who is affected. If the user describes THEIR OWN symptoms ("I feel sick", "my arm is bleeding", "I am dizzy"), speak directly to them as "you", never about "the person", "him", "her", "the victim" or "the patient". If they describe someone else's emergency, give the user the helper's instructions. NEVER deflect with "find someone to help you", "ask someone else" or "talk to somebody", because the user has only this device; always give the actual steps themselves.

EMERGENCY RULES:
1. Answer ONLY using the reference passages. Never invent facts, procedures, medication names, or doses. If the passages give a specific number, use it exactly.
2. If the passages do not cover the situation, say clearly: "My references don't cover this specific situation." Then give the safest general action and state that professional medical help is needed.
3. Start with the single most urgent action in one short sentence. ONLY IF the question asks whether to do something ("should I...", "can I...", "is it safe to...") begin with "Yes" or "No" and the reason. For any other question do NOT begin with the word "Yes" or "No", but begin directly with the action itself. A prohibition like "Do NOT pull it out" counts as the urgent action.
4. Then give numbered steps in the order they must be done. One action per step. Short sentences. Commands, not suggestions.
5. Use plain language a scared non-expert can follow. Translate medical terms. NEVER drop a "do not" warning from the passages.
6. If the passages contain conflicting advice, prefer the IFRC 2025 guidelines over older sources. Older techniques like induced vomiting for poisoning or loosening tourniquets are outdated, so do not recommend them.
7. End by stating when to seek professional medical help and warning signs of worsening.
8. Users may type short, misspelled, panicked fragments. Interpret them charitably. Do not ask clarifying questions unless dangerously ambiguous.
9. If the message suggests the person is unconscious, not breathing, or bleeding heavily, address that first.
10. Do not provide guidance for deliberately harming any person.
11. Never begin with "I'm sorry", "I can't", or "I'm not a medical professional".
12. Two absolute rules: (a) In a severe allergic reaction (face or throat swelling, wheezing after a sting) with an epinephrine auto-injector available, helping the person use it IMMEDIATELY is always correct, never advise waiting for permission. (b) A tourniquet that has been applied must NEVER be loosened or removed outside a medical facility."""

# Small talk answered deterministically - no RAG, no LLM, no MT. A small model
# asked to classify "how are u" can misfire, so greetings, thanks and
# who-are-you get instant, consistent canned replies. Full-string match only,
# so real questions are never hijacked.
_ST_SQ = (r"pershendetje|përshëndetje|tungjatjeta|tung|ckemi|ç'?kemi"
          r"|mir[ëe]mbr[ëe]ma|mir[ëe]m[ëe]ngjes\w*|mir[ëe]dita"
          r"|si je(ni)?|si kalon(i)?|a je mir[ëe]|faleminderit|flm|rrofsh"
          r"|kush je( ti)?|[çc]far[ëe] je ti|[çc]far[ëe] di t[ëe] b[ëe]sh|si punon")
_ST_EN = (r"hello|hi|hey|good (morning|evening|afternoon)|how are (you|u)|how r u"
          r"|what'?s up|thank you|thanks|thx|who are (you|u)|what are (you|u)"
          r"|what can (you|u) do|how do (you|u) work")
_ST_FULL = re.compile(r"^(\s*(%s|%s)[\s,!.?]*)+$" % (_ST_SQ, _ST_EN), re.IGNORECASE)


def _smalltalk(q):
    t = (q or "").strip().lower()
    if not t or len(t) > 60 or not _ST_FULL.match(t):
        return None
    sq = bool(re.search(_ST_SQ, t, re.IGNORECASE))
    if re.search(r"kush je|[çc]far[ëe] (je|di)|si punon|who are|what (are|can)|how do", t, re.IGNORECASE):
        return ("Jam Noah, asistenti yt personal me AI që punon pa internet, në shqip "
                "dhe anglisht. Pyetmë çfarëdo dhe shtyp ENTER." if sq else
                "I am Noah, your personal offline AI assistant, working in Albanian "
                "and English. Ask me anything and press ENTER.")
    if re.search(r"faleminderit|flm|rrofsh|thank|thx", t, re.IGNORECASE):
        return ("S'ka gjë. Jam këtu për të ndihmuar." if sq else
                "You're welcome. I'm here to help.")
    return ("Përshëndetje. Jam Noah, asistenti yt personal me AI pa internet. "
            "Pyetmë çfarëdo dhe shtyp ENTER." if sq else
            "Hello, I'm Noah, your personal offline AI assistant. Ask me anything "
            "and press ENTER.")


# Is the asker talking about someone else, or about themselves?
_OTHER_PERSON = re.compile(
    r"djal|vajz|burr|grua|nus[ëe]|nen[ëe]|bab[ëae]|gjysh|shok|shoqj?[ëe]"
    r"|f[ëe]mij|foshnj|viktim|personi?\b"
    r"|my (son|daughter|husband|wife|mother|father|child|kid|friend|brother"
    r"|sister|baby|grand\w*)|\bhis \b|\bher \b|\bsomeone\b", re.IGNORECASE)
_FIRST_PERSON = re.compile(
    r"\bndihem|m[ëe] dhemb|me dhemb|\bkam \b|\bjam \b|po m[ëe] |u dogja"
    r"|\bme ka\b|\bm[ëe] ka\b|\bi feel|\bi am\b|\bi'?m\b|\bi have\b|\bmy \b"
    r"|u preva|m[ëe] rrjedh|me rrjedh", re.IGNORECASE)

EPD = None
try:
    from eink import EInk
    EPD = EInk()
    print("[e-ink panel active]")
except Exception as e:
    print(f"[e-ink disabled: {e}]")

MT_OK = os.path.isdir("/data/models/nllb-ct2-int8")
print("[translator %s]" % ("ready, lazy-load (shqip)" if MT_OK else "DISABLED - model missing"))

LEDS_OK = True
try:
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(LED_SIGNAL, GPIO.OUT)
    GPIO.setup(LED_POWER, GPIO.OUT)
    GPIO.output(LED_POWER, GPIO.HIGH)
except Exception as _e:
    LEDS_OK = False
    print(f"[leds disabled: {_e}]")

blinking = False
def blinker():
    while True:
        if not LEDS_OK:
            time.sleep(1.0); continue
        try:
            if blinking:
                GPIO.output(LED_SIGNAL, GPIO.HIGH); time.sleep(0.25)
                GPIO.output(LED_SIGNAL, GPIO.LOW); time.sleep(0.25)
            else:
                GPIO.output(LED_SIGNAL, GPIO.LOW); time.sleep(0.1)
        except Exception:
            time.sleep(1.0)
threading.Thread(target=blinker, daemon=True).start()

# Optional medical reference index, used only by the first aid branch in
# answer(). Noah is a general assistant and runs fine without it: if the index
# is not installed, first aid grounding is simply disabled and medical
# questions fall back to a general answer plus the deterministic warnings.
retriever = None
try:
    client = chromadb.PersistentClient(path=DB_PATH)
    col = client.get_collection("emergency")
    retriever = retrieval.Retriever(col)
    print("[hybrid retrieval ready: %d chunks]" % len(retriever.docs))
except Exception as e:
    print("[medical reference index unavailable, first aid grounding off: %s]" % e)

def embed_query(text):
    r = requests.post(f"{OLLAMA}/api/embed",
                      json={"model": "nomic-embed-text", "input": [text]},
                      timeout=(10, 120))
    return r.json()["embeddings"][0]

GENERAL_SYSTEM = (
    "You are Noah, a helpful personal AI assistant that runs entirely offline on "
    "a small device, with no internet and no cloud. Help the user with whatever "
    "they ask: everyday questions, explanations, learning, coding, writing, "
    "brainstorming, and working through problems. "
    "Talk like a normal person having a conversation. Be warm and clear, not "
    "stiff or robotic, and do not open every reply with filler like 'Of course' "
    "or 'Certainly'. Match the length of your answer to the question, so a quick "
    "question gets a short answer and only a real explanation needs a longer one. "
    "Use plain language and pick whatever format fits, whether that is a short "
    "paragraph, a few steps, a list, or a code block. The screen is small, so get "
    "to the point and do not pad. "
    "You have no internet and no live information such as news, weather, prices, "
    "or today's date, and your knowledge stops at a training cutoff, so say so "
    "plainly when a question needs any of that. If you are not sure or do not "
    "know, just say so instead of making something up, and never pretend you "
    "looked something up. Do not help with anything meant to seriously harm "
    "someone.")


def _is_firstaid_question(q_en):
    """True only when the message is clearly about an injury, illness or
    emergency, so it should be routed to the grounded medical branch. Noah is
    a general assistant, so anything else, and anything unclear, is GENERAL
    and answered from the model's own knowledge. Runs with NO reference
    passages in the prompt, so the first aid corpus can never drag a general
    question (e.g. 'world war 2' -> combat-wound advice) into a medical
    answer."""
    try:
        r = requests.post(f"{OLLAMA}/api/generate", json={
            "model": MODEL,
            "system": ("Label the user's message with exactly one word. "
                       "FIRSTAID = it describes an injury, illness, symptom, pain, "
                       "wound, poisoning, accident, or asks for medical, first aid "
                       "or safety help. GENERAL = anything else: greetings, history, "
                       "geography, science, math, coding, cooking, sports, trivia, "
                       "definitions, opinions, writing, or everyday questions. "
                       "Reply with only the word FIRSTAID or GENERAL."),
            "prompt": q_en,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 4},
        }, timeout=(10, 60))
        out = r.json().get("response", "").strip().upper()
    except Exception:
        return None                              # classifier unavailable: err toward the safety path
    if "FIRST" in out:
        return True
    return False                                 # GENERAL or unclear -> general


def _general_answer(q_en):
    """Answer a general question (not first aid) from the model's own knowledge, no passages."""
    try:
        r = requests.post(f"{OLLAMA}/api/generate", json={
            "model": MODEL,
            "system": GENERAL_SYSTEM,
            "prompt": "QUESTION: %s\n\nANSWER:" % q_en,
            "stream": False,
            "options": {"temperature": 0.4, "num_ctx": 2048, "num_predict": 500},
        }, timeout=(10, 300))
        resp = r.json().get("response", "").strip()
    except Exception:
        resp = ""
    if _DEGEN.search(resp):                              # degeneration loop
        resp = ""
    resp = safety.danger_scrub(resp)             # belt: drop any stray unsafe line
    if not resp.strip():                         # after the scrub, so a fully
        resp = "Sorry, I could not answer that." # scrubbed answer is never empty
    return resp


def _to_sq(text):
    """Translate an answer to Albanian, keeping the English if MT fails."""
    try:
        return translator.en_to_sq(text)
    except Exception as e:
        print("[translator failed, leaving English: %s]" % e)
        return text


def answer(question):
    global blinking
    blinking = True
    try:
        st = _smalltalk(question)
        if st:
            return st, []
        is_sq = MT_OK and translator.is_albanian(question)
        q_en = question
        if is_sq:
            try:
                q_en = translator.sq_to_en(question)
            except Exception as e:                   # MT load/translate failure:
                print("[translator failed, answering in English: %s]" % e)
                is_sq = False                        # degrade to English-only
        # Noah is a general-purpose assistant: by default every question is
        # answered from the local model's own knowledge. Only a question the
        # intent classifier judges to be about an injury, illness or emergency
        # is routed to the grounded medical branch below (retrieval over the
        # bundled first aid references + the deterministic safety layer). This
        # keeps first aid framing OFF everyday questions while preserving a
        # grounded, safety-checked path for genuine medical ones.
        if _is_firstaid_question(q_en) is False:   # only an explicit GENERAL skips the
            resp = _general_answer(q_en)           # safety path; a classifier failure
            if is_sq:                              # (None) falls through to it instead
                resp = _to_sq(resp)
            return resp, []
        # medical / first aid branch: grounded answer + safety layer
        names = safety.fired_rules(question, q_en, is_sq)
        if retriever is None:                    # no reference library installed:
            resp = _general_answer(q_en)         # answer generally (already scrubbed),
            resp, replaced = safety.body_guard(names, resp, is_sq)  # but still run the
            med = (not replaced) and safety.med_caution(resp)       # FULL safety layer:
            if is_sq and not replaced:           # CONTRA replacement + med caution +
                resp = _to_sq(resp) # the prepended warnings
            warns = safety.check(question, q_en, is_sq)
            if warns:
                resp = "\n\n".join(warns) + "\n\n" + resp
            if med:
                resp += "\n\n" + (safety.MED_CAUTION_SQ if is_sq else safety.MED_CAUTION_EN)
            return resp, []
        try:
            chunks, sources = retriever.search(q_en, k=TOP_K)
        except Exception:
            chunks, sources = [], []
        context = "\n\n---\n\n".join(
            f"[Source: {s}]\n{c}" for s, c in zip(sources, chunks))
        # perspective stamp: MT often drops the first person from Albanian
        # ("ndihem semure" -> "feels sick"), so the model answers about "the
        # person". Detect I-the-patient questions deterministically.
        both = (question + " " + q_en).lower()
        note = ""
        if not _OTHER_PERSON.search(both) and _FIRST_PERSON.search(both):
            note = ("\nNOTE: The asker IS the patient. Address them directly "
                    "as 'you', never 'the person', 'him' or 'her'.")
        prompt = (f"REFERENCE PASSAGES:\n\n{context}\n\n"
                  f"USER QUESTION: {q_en}{note}\n\nANSWER:")
        try:
            r = requests.post(f"{OLLAMA}/api/generate", json={
                "model": MODEL,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.25, "num_ctx": 3072, "num_predict": 400}
            }, timeout=(10, 300))
            resp = r.json().get("response", "")
        except Exception:
            resp = ""
        # degeneration guard: a token loop ("JE JE JE...") is long but garbage -
        # blank it so the short-answer retry below regenerates
        if _DEGEN.search(resp):
            resp = ""
        # short-answer guard: one-liners retry once with an expand demand
        # (smalltalk never reaches here - it is answered deterministically)
        if len(resp.strip()) < 180:
            try:
                r2 = requests.post(f"{OLLAMA}/api/generate", json={
                    "model": MODEL,
                    "system": SYSTEM_PROMPT,
                    "prompt": prompt + " Answer the question completely and informatively, because a single sentence is not enough. If it is an emergency, give the full numbered first aid steps.",
                    "stream": False,
                    "options": {"temperature": 0.2, "num_ctx": 3072, "num_predict": 400}
                }, timeout=(10, 300))
                resp2 = r2.json().get("response", "")
            except Exception:
                resp2 = ""
            if _DEGEN.search(resp2):                 # a looping retry is garbage too
                resp2 = ""
            if len(resp2.strip()) > len(resp.strip()):
                resp = resp2
        # deterministic guard: strip a leading Yes/No unless the question asked whether
        _modal = re.search(r"\b(should|shall|can|could|may|must) (i|we|you|he|she|they)\b"
                           r"|\bis it (safe|ok|okay|alright)\b", q_en, re.IGNORECASE)
        _wh = re.search(r"\b(what|how|when|where|why|who)\b[^.?!]{0,25}"
                        r"\b(should|shall|can|could|may|must)\b", q_en, re.IGNORECASE)
        if not _modal or _wh:
            m = re.match(r"^(yes|no)[,.:]?\s+", resp.strip(), re.IGNORECASE)
            if m:
                resp = resp.strip()[m.end():]
                if resp:
                    resp = resp[0].upper() + resp[1:]
        resp, replaced = safety.body_guard(names, resp, is_sq)
        if not replaced:
            resp = safety.danger_scrub(resp)   # drop inverted-advice sentences
        med = (not replaced) and safety.med_caution(resp)
        if is_sq and not replaced:
            resp = _to_sq(resp)
        if not resp.strip():                     # model/retrieval failed: never return
            resp = ("Më vjen keq, nuk munda të përgjigjem."   # an empty body
                    if is_sq else "Sorry, I could not answer that.")
        warns = safety.check(question, q_en, is_sq)
        if warns:
            resp = "\n\n".join(warns) + "\n\n" + resp
        if med:
            resp += "\n\n" + (safety.MED_CAUTION_SQ if is_sq else safety.MED_CAUTION_EN)
        return resp, sorted(set(sources))
    finally:
        blinking = False

def main():
    print("Noah offline assistant ready. Type a question (or 'quit').\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() == "quit":
            break
        t0 = time.time()
        text, sources = answer(q)
        dt = time.time() - t0
        print(f"\n{text}\n")
        print(f"[sources: {', '.join(sources)} | {dt:.1f}s]\n")
        if EPD:
            try:
                short = [s.rsplit(".", 1)[0][:40] for s in sources]
                pages = EPD.paginate_text(text, title=q,
                                          footer="sources: " + ", ".join(short))
                EPD.show(pages[0])
                for i in range(1, len(pages)):
                    try:
                        input(f"[panel: page {i}/{len(pages)} shown - Enter for next]")
                    except (EOFError, KeyboardInterrupt):
                        break
                    EPD.show(pages[i])
            except Exception as e:
                print(f"[e-ink error: {e}]")

    if EPD:
        try: EPD.close()
        except Exception: pass
    if LEDS_OK:                                  # GPIO was never set up otherwise
        try:
            GPIO.output(LED_POWER, GPIO.LOW)
            GPIO.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
