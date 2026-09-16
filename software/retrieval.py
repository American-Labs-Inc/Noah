#!/usr/bin/env python3
"""Noah hybrid retrieval - vector (nomic) + BM25 with reciprocal-rank fusion,
plus a deterministic crisis-vocabulary -> clinical-term query expansion.

Why: panicked lay queries ("collapsed, not breathing", "knife stuck in my leg")
share no vocabulary with the clinical passages that answer them (CPR/embedded
object). Pure embedding search buried IFRC's chest-compression and impaled-object
chunks below lookalike noise (diagnosed 2026-08-27). Expansion bridges the
vocabulary; BM25 rewards the exact clinical terms; RRF fuses both rankings.
"""
import re
import requests
from rank_bm25 import BM25Okapi

OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
RRF_K = 60

EXPANSIONS = [
    (r"not breathing|stopped breathing|isn'?t breathing|no pulse|collapsed|unresponsive",
     "CPR cardiopulmonary resuscitation chest compressions cardiac arrest"),
    (r"knife in|stuck in|impaled|nail in|embedded",
     "embedded impaled object stabilize pressure around avoid removing"),
    (r"unconscious|passed out|won'?t wake",
     "unconscious unresponsive recovery position airway nothing by mouth"),
    (r"\bburn(?!(s|ing)? when\b[^.]{0,20}\b(urin\w*|pee\w*|piss\w*|wee\w*|on\s+the\s+toilet\b|(?:(?:go|going|goes|went|get|getting|run|running)\s+to|use|using|used|visit|visiting)\s+(?:the\s+)?(?:toilet|bathroom|loo)\b(?![^.]{0,2}\b(?:cleaner|cleaning|heater|bleach|product|spray|tiles|floor|door|sink|mirror|light|i|we|he|she|they|the|a|an|my|his|her|and|when|where|while|because)\b)))|scald|caught fire|boiling water",
     "burn cool running water 20 minutes dressing"),
    (r"sting|stung|wasp|\bbee\b|hornet|allergic",
     "anaphylaxis epinephrine adrenaline auto-injector severe allergic reaction"),
    (r"snake",
     "snakebite venom bite immobilization"),
    (r"poison|overdose|swallowed (bleach|chemical|detergent|kerosene|pills)",
     "poisoning ingestion do not induce vomiting"),
    (r"(fell|fall|hit).{0,40}(neck|back|spine)|spinal|can'?t (feel|move)",
     "spinal injury cervical spine immobilize do not move"),
    (r"bleeding|blood soak",
     "severe bleeding hemorrhage direct pressure dressing"),
    (r"choking|something stuck.{0,15}throat",
     "choking airway obstruction back blows abdominal thrusts"),
    (r"drown", "drowning rescue breathing water"),
    (r"chest pain|heart attack", "heart attack myocardial infarction aspirin"),
    (r"diarrhea|dehydrat", "dehydration oral rehydration solution"),
    (r"seizure|convuls|fit\b", "seizure convulsion protect from injury"),
    (r"scorpion", "scorpion sting cold compress pain venom"),
    (r"tooth.{0,20}(fell|knocked|out)|knocked.?out tooth",
     "knocked out tooth milk saliva dentist socket bleeding"),
    (r"heat ?stroke|not sweating|stopped sweating",
     "heat stroke cooling wet cloths fanning shade emergency"),
    (r"hypotherm|shiver", "hypothermia rewarming dry clothes blankets shelter"),
    (r"electric|current|wire", "electrical shock turn off power source burns"),
    (r"sprain|twisted ankle|swollen ankle|ankle.{0,15}swoll",
     "sprain rest ice compression elevation bandage joint"),
    (r"blister", "blister friction foot clean do not pop dressing"),
    (r"burn(s|ing)? when.{0,12}urinat|painful urination",
     "urinary tract infection urine pain drink plenty water"),
    (r"\btick\b", "tick removal tweezers close to skin head"),
    (r"splinter|thorn", "splinter thorn removal tweezers infected wound soak"),
    (r"head (bump|injury|lump)|hit (his|her|my) head|lump on.{0,10}head|blood.{0,20}head",
     "head injury concussion watch vomiting drowsiness confusion"),
    (r"(bean|seed|object|something).{0,20}(in|up).{0,12}nose|nose.{0,18}(bean|seed|object)",
     "foreign body nose blow nostril close other do not poke"),
    (r"insect.{0,15}ear|ear.{0,20}(insect|bug)",
     "insect in ear oil water float out tilt head"),
    (r"(bleach|chemical|acid).{0,25}eye", "chemical eye burn flush water 20 minutes urgent"),
    (r"asthma|inhaler", "asthma attack sit upright leaning forward calm emergency"),
    (r"(sting|stung).{0,25}(tongue|mouth|lip)|tongue.{0,18}(sting|stung|swell)",
     "sting in mouth tongue ice cold water swelling airway emergency"),
    (r"acid.{0,20}(arm|skin|hand|face)|chemical burn",
     "chemical burn acid rinse water 20 minutes remove contaminated clothing"),
    (r"(hip|pelvis).{0,25}(pain|fell|broken)|elderly.{0,20}fell",
     "hip fracture keep still do not move splint emergency"),
    (r"tooth.{0,22}(pulled|extracted|removed|socket)|bleeding.{0,20}(gum|mouth|socket)",
     "tooth socket bleeding bite gauze pressure 15 minutes"),
    (r"amputat|severed|(cut|chopped|sawed) off",
     "amputation severed part moist cloth plastic bag on ice stump pressure"),
    (r"chest wound|sucking|(hole|stab).{0,15}chest",
     "sucking chest wound seal plastic three sides occlusive"),
    (r"pregnan.{0,30}bleed|vaginal bleed",
     "bleeding pregnancy left side pad urgent transport"),
    (r"testic|scrotum", "testicular torsion sudden pain surgical emergency hours"),
    (r"food poisoning|(vomit|sick).{0,25}after (eating|the meal)",
     "food poisoning vomiting diarrhea fluids rehydration danger signs"),
    (r"(left|forgot|locked).{0,22}car|hot car",
     "child hot car heat stroke remove cool immediately emergency"),
    (r"hang(ed|ing)|noose|strangl", "hanging strangulation support weight CPR neck"),
    (r"fish ?bone", "fish bone throat swallow bread water doctor"),
    (r"rusty nail|puncture", "puncture wound tetanus wash soap booster"),
    (r"\bleech", "leech removal fingernail wash bleeding"),
    (r"mushroom", "wild mushroom poisoning liver hospital sample do not vomit"),
    (r"(bee|wasp)s? (swarm|attack)|many stings|multiple stings",
     "multiple bee stings scrape stingers cold compress reaction"),
    (r"dizzy.{0,28}(stand|getting up)|blood pressure medic",
     "postural dizziness rise slowly sit down medication review"),
    (r"sunburn", "sunburn cool water cover fluids child blisters"),
    (r"sleeping pills|overdose.{0,22}pills",
     "overdose sleeping pills unconscious poison airway recovery position"),
    (r"fish (spine|thorn)|spine in.{0,14}(hand|finger)",
     "splinter thorn fish spine removal tweezers infected"),
    (r"(spoon|open).{0,20}mouth.{0,22}(seizure|convuls|stroke)",
     "seizure nothing in mouth side position do not restrain"),
    (r"woke.{0,22}(crooked|droop)|face droop", "stroke face droop act fast time"),
    (r"febrile|fever.{0,22}(seizure|convuls|shaking)",
     "febrile seizure child nothing in mouth side position"),
    (r"heartburn|burning.{0,16}(chest|stomach).{0,16}(after|eating)",
     "heartburn indigestion antacid after eating"),
    (r"brush.{0,14}(my )?teeth|dental hygiene",
     "brush teeth twice daily toothpaste gums cavities"),
    (r"sparkling|carbonated", "carbonated water drink"),
    (r"honey.{0,14}cough|cough.{0,14}honey", "honey cough soothing warm drink"),
    (r"feel(ing)? (sick|unwell|ill|nauseous|bad)|\bnausea",
     "nausea illness rest fluids fever symptoms when to seek care"),
    (r"feel(ing)? faint|about to faint|dizzy.{0,20}alone",
     "faint lie down raise legs fresh air rest"),
    (r"button batter|swallow.{0,18}batter",
     "swallowed battery emergency hospital x-ray esophagus"),
    (r"cigarette|nicotine", "nicotine poisoning cigarette child do not vomit urgent"),
    (r"(black|smell|rotten).{0,20}wound|gangrene",
     "gangrene severe wound infection hospital do not tighten"),
    (r"panic|anxiety attack", "panic attack slow breathing passes calm sitting"),
    (r"needle.{0,16}(hand|finger|stuck)|sewing needle",
     "needle puncture wash soap tetanus bleeding"),
    (r"(no|without|haven'?t) sle(pt|ep)|sleep depriv",
     "sleep rest fatigue tremor caffeine recovery"),
    (r"road rash|scraped.{0,16}(arm|leg|skin)|graze",
     "abrasion scrape clean water remove debris dressing"),
    (r"(door|slammed).{0,20}finger|finger.{0,20}(door|slam|crush)",
     "crushed finger nail cold compress elevate blood under nail"),
    (r"jellyfish", "jellyfish sting sea water tentacles hot water"),
    (r"sea urchin", "sea urchin spines tweezers hot water soak"),
    (r"high blood sugar|hyperglyc|ketoacid|acetone",
     "diabetic ketoacidosis high sugar water no sugar urgent"),
    (r"(hit|ball|blow).{0,20}eye|eye.{0,18}(trauma|blunt)",
     "eye injury blunt shield do not press urgent vision"),
    (r"broken nose|nose.{0,20}(crooked|broken|punch)",
     "broken nose bleeding lean forward pinch do not straighten"),
    (r"hypotherm|freezing|frozen|shivering", "hypothermia rewarming gradual"),
    (r"heat ?stroke|overheat", "heat stroke cooling"),
    (r"broken (leg|arm|bone|ankle|wrist)|fracture|think.{0,20}broken",
     "closed fracture splint immobilize support do not straighten"),
    (r"(river|dirty|unsafe) water|water safe to drink|purify.{0,15}water",
     "boil water boiling purification disinfect one minute"),
    (r"which plants|plants.{0,30}(safe|eat)|edible plants",
     "universal edibility test steps skin lip tongue wait hours"),
]


def expand(q):
    extra = [terms for pat, terms in EXPANSIONS if re.search(pat, q, re.IGNORECASE)]
    return q + " " + " ".join(extra) if extra else q


def _tok(t):
    return re.findall(r"[a-z0-9]+", t.lower())


_OBSOLETE = re.compile(
    r"loosen the (tie|tourniquet)|release the (tie|tourniquet)|let the blood circulate"
    r"|loosen it every|heel of your lower hand on (his|her|the) belly"
    r"|(make|force|help|get) (him|her|them|the (person|child|baby|patient|kid|victim)"
    r"|a (person|child|baby)) (to )?(vomit|throw up)|induce (vomiting|emesis)", re.I)
# A negation only exempts the phrase when it GOVERNS it. The scope rules live in
# safety.NEG_ATTACHED so all three filters agree ("do not remove or loosen the
# tourniquet" is exempt, an incidental "never" elsewhere in the sentence is not).
from safety import NEG_ATTACHED as _OBSOLETE_NEG


def _is_obsolete(text):
    """True if a chunk asserts obsolete doctrine (tourniquet-loosening, emesis)
    as an instruction. Negated forms ('do NOT loosen the tourniquet') are the
    correct advice and must survive, but only an attached negation counts."""
    for sent in re.split(r"(?<=[.!?\n])", text):
        for m in _OBSOLETE.finditer(sent):
            if not _OBSOLETE_NEG.search(sent[:m.start()]):
                return True
    return False


def _embed(text):
    r = requests.post(f"{OLLAMA}/api/embed",
                      json={"model": EMBED_MODEL, "input": [text]},
                      timeout=(10, 120))
    r.raise_for_status()                         # a clear error instead of a KeyError
    return r.json()["embeddings"][0]


class Retriever:
    def __init__(self, collection):
        self.col = collection
        got = collection.get()
        self.ids = got["ids"]
        self.docs = got["documents"]
        self.metas = got["metadatas"]
        self._idx = {cid: i for i, cid in enumerate(self.ids)}
        if not self.docs:                        # BM25Okapi divides by corpus size
            raise ValueError("emergency index is empty: run ingest.py first")
        self.bm25 = BM25Okapi([_tok(d) for d in self.docs])

    def search(self, q_en, k=4, pool=10):
        qx = expand(q_en)
        # vector ranking (on the expanded query)
        res = self.col.query(query_embeddings=[_embed(qx)], n_results=pool)
        vec_ids = res["ids"][0]
        # bm25 ranking
        scores = self.bm25.get_scores(_tok(qx))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:pool]
        bm_ids = [self.ids[i] for i in order if scores[i] > 0]   # no score-0 padding
        # reciprocal-rank fusion
        fused = {}
        for lst in (vec_ids, bm_ids):
            for r, cid in enumerate(lst):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + r)
        ranked = sorted(fused, key=fused.get, reverse=True)
        # drop obsolete-doctrine chunks (non-IFRC) that survived the corpus purge
        top = []
        for cid in ranked:
            d = self.docs[self._idx[cid]]
            s = self.metas[self._idx[cid]]["source"]
            if "IFRC" not in s and _is_obsolete(d):
                continue
            top.append(cid)
            if len(top) == k:
                break
        chunks = [self.docs[self._idx[c]] for c in top]
        sources = [self.metas[self._idx[c]]["source"] for c in top]
        return chunks, sources


if __name__ == "__main__":
    import chromadb
    col = chromadb.PersistentClient(path="/home/aldo/emergency-db").get_collection("emergency")
    ret = Retriever(col)
    tests = [
        "my father collapsed and he is not breathing what do i do",
        "there is a knife stuck in my leg should i pull it out",
        "the snake bit me on the foot what to do",
        "my friend is bleeding a lot from his leg",
        "My friend is unconscious. Should I give him water?",
        "The baby was burned with water. What should I do?",
    ]
    for q in tests:
        print("== HYBRID top-4:", q)
        chunks, sources = ret.search(q)
        for s, c in zip(sources, chunks):
            print("   [%-12s] %s" % (s[:12], c[:95].replace("\n", " ")))
        print()
