#!/usr/bin/env python3
"""Noah translation layer. NLLB-200-600M via ctranslate2 int8 on CPU.

MT sandwich: Albanian queries -> English before retrieval; English answers ->
Albanian after generation. The LLM never needs Albanian (gemma3:4b failed it).
Model dir: /data/models/nllb-ct2-int8 (converted from facebook/nllb-200-distilled-600M).
"""
import re
import langdetect
from langdetect import DetectorFactory
DetectorFactory.seed = 0          # langdetect is nondeterministic unless seeded!

HF_MODEL = "facebook/nllb-200-distilled-600M"
CT2_DIR = "/data/models/nllb-ct2-int8"
SQ, EN = "als_Latn", "eng_Latn"
_tok = _ct = None


def _get():
    global _tok, _ct
    if _ct is None:
        import ctranslate2
        from transformers import AutoTokenizer
        _tok = AutoTokenizer.from_pretrained(HF_MODEL)
        _ct = ctranslate2.Translator(CT2_DIR, device="cpu", compute_type="int8",
                                     inter_threads=1, intra_threads=4)
    return _tok, _ct


# Words that essentially never appear in English text, a deterministic sq signal.
SQ_STRONG = {
    "cfare", "çfarë", "eshte", "është", "duhet", "bej", "bëj", "kembe", "këmbë",
    "kafshoi", "kafshuar", "dogj", "djeg", "thike", "thikë", "helm", "helmuar",
    "mbytur", "dhemb", "dhimbje", "plage", "plagë", "femija", "fëmija", "gjak",
    "gjarpri", "gjarperi", "gjarpëri", "ndihme", "ndihmë", "zjarr", "fryme",
    "frymë", "vetëdije", "ndjenja", "shpejt", "menjehere", "menjëherë", "shqip",
    "ujë", "uje", "pyetje", "shoku", "vellai", "vëllai", "motra", "nena", "nëna",
    # 2026-08-31 long-eval: colloquial emergency words langdetect missed
    "pickoi", "pickuar", "akrepi", "akrep", "dridhet", "shkume", "shkumë",
    "korrenti", "korrent", "rrjedh", "ndalon", "hundet", "hundët", "ndjen",
    "vjell", "vjella", "kembet", "këmbët", "doren", "dorën", "naten", "natën",
    "qeni", "barku", "zemra", "zemër", "kocka", "krahun", "diarre", "ethe",
    "vapa", "djersit", "ftohte", "ftohtë", "akull", "teli", "ndricues",
    "ndriçues", "detergjent", "piu", "lindjes", "mjek", "dhembi", "dhëmbi",
    # round 8: "me ra acid ne krah" evaded detection (all words EN-plausible)
    "krah", "krahu", "vithja", "vithet", "hunde", "hundes", "vesh", "veshi",
    "gjuhe", "gjuhë", "sperkati", "spërkati", "zbardhues", "ngrire", "ngrirë",
    "bora", "soba", "sobe", "sobën", "mangall", "gjemb", "monedhe", "monedhë",
    "grep", "astme", "pompa", "fasule", "gunge", "gungë", "shkallet",
    "biciklete", "bicikletë", "urinoj", "flluske", "kyci", "kyçi", "vithja",
    # round 9: inflected forms that evaded detection ("plaga e kembes")
    "plaga", "plagen", "plagës", "kocke", "kockes", "kembes", "gishta",
    "gishtat", "gjoksi", "sharra", "herdhet", "herdheve", "dasme", "hengrem",
    "thoi", "shtypur", "shtatzene", "shtatzënë", "foshnja", "muajshe",
    "fishkellen", "saldimin", "zbehte", "zbehtë", "gjakderdhje",
    # round 10
    "varur", "litar", "bletet", "hale", "peshku", "gozhde", "ndryshkur",
    "shkeli", "unaza", "shushunje", "kerpudha", "tensioni", "perzhit",
    "hekurosur", "theri", "plazh", "oborr", "ngecur", "enjtet",
    # general-mode battery 2026-09-02: everyday words that evaded detection
    "ndihmon", "mjalti", "mjalte", "kollen", "kolla", "dhembet", "dhëmbët",
    "laj", "gjumi", "ushqimin", "fresket",
    # round 12
    "bateri", "gelltitur", "cigare", "paniku", "gjilpera", "mendte",
    "nxire", "qepur", "fjetur", "dridhen",
    # round 13
    "rene", "diellit", "pika", "krampet", "iriq", "kandili", "grire",
    "aksident", "shoferi", "motori", "grusht", "shtremberuar", "aceton",
    "kollitet", "ngeci", "vape",
    # 2026-09-17 review: burn verb forms ("u dogja me soba" had no other signal
    # once "u"/"me" stopped counting as Albanian context)
    "dogja", "dogji", "dogjen", "dogjem", "dogjet", "dogjur", "fyt", "fyti", "fytin",
    # crisis words that carried "po/te/ia" queries once those function words
    # were dropped for colliding with English ("po me digjet soba", "bora te madhe")
    "digjet", "digjem", "madhe", "madh", "sot", "futa", "futi",
}

# SQ_STRONG members that are also ordinary English words. A lone one of these is
# NOT enough to call the text Albanian (it forced e.g. "grep", "vape" to sq and
# round-tripped English through NLLB). They only count alongside a diacritic,
# another Albanian word, or langdetect agreeing.
_SQ_AMBIG = {"grep", "vape", "hale", "bora", "soba", "sot"}
# Albanian function words with no English homograph. One of these next to an
# ambiguous word settles "e kam grep ne dore" as Albanian without langdetect.
# Deliberately absent because they collide with English text: u, e, me, ai, per,
# im/ime (casual "I'm", IME), po (.po/PO), pa/ky/ia (US states), si/sa (SI, SA),
# te, mos, ata (ATA). "ne" (Nebraska) is kept: it carries too much Albanian recall.
_SQ_FUNC = {"ne", "ka", "kam", "eshte", "është", "dhe", "nga", "ti", "cfare", "çfarë",
            "kur", "ku", "tani", "ajo", "je", "kemi", "keni", "nuk", "duhet", "mund",
            "shume", "shumë", "ose", "por", "edhe", "qe", "që", "kjo", "ato", "tij",
            "saj", "ju", "juaj", "jone", "jonë", "mua", "atij", "asaj"}


def is_albanian(text):
    low = text.lower()
    words = set(re.findall(r"[a-zëç]+", low))
    hits = words & SQ_STRONG
    # ë is Albanian-specific (ç is not: "façade"); an unambiguous domain word, or
    # an ambiguous one with Albanian function words around it, is decisive
    if hits - _SQ_AMBIG or "ë" in low or (hits and words & _SQ_FUNC):
        return True
    try:                                         # only an ambiguous word, no Albanian
        return langdetect.detect(text) == "sq"   # context: let the detector decide
    except Exception:                            # ("how do I use grep" -> en)
        return bool(hits)                        # detector unavailable: trust the hit


def _translate(texts, src, tgt):
    tok, ct = _get()
    single = isinstance(texts, str)
    batch = [texts] if single else list(texts)
    tok.src_lang = src
    srcs = [tok.convert_ids_to_tokens(tok.encode(t, truncation=True, max_length=480))
            for t in batch]
    res = ct.translate_batch(srcs, target_prefix=[[tgt]] * len(srcs),
                             max_decoding_length=300, beam_size=2)
    out = []
    for r in res:
        toks = r.hypotheses[0]
        if toks and toks[0] == tgt:
            toks = toks[1:]
        out.append(tok.decode(tok.convert_tokens_to_ids(toks),
                              skip_special_tokens=True).strip())
    return out[0] if single else out


# Crisis-Albanian normalization: panicked typing drops diacritics, which wrecks
# NLLB. Restore the statistically-dominant forms for this domain + fix idioms.
SQ_IDIOMS = [
    ("ka humbur ndjenjat", "ka humbur vetëdijen"),
    ("pa ndjenja", "pa vetëdije"),
    ("i ra te fiket", "ka humbur vetëdijen"),
    ("i bie te fiket", "po humb vetëdijen"),
    # ambiguous nouns NLLB mistranslates, so embed the English term to steer it
    # (round 7: "flluskë"→bubble→trouser flotation; "kyçi"→cord care)
    ("flluske", "blister (fshikëz)"),
    ("flluska", "blister (fshikëz)"),
    ("flluskë", "blister (fshikëz)"),
    ("kyci i kembes", "nyja e këmbës (ankle)"),
    ("kyçi i këmbës", "nyja e këmbës (ankle)"),
    ("rriqra", "rriqra (tick)"),
    ("rriqer", "rriqër (tick)"),
    ("kokerr fasule", "send i vogël (a bean, foreign object)"),
    ("kokërr fasule", "send i vogël (a bean, foreign object)"),
    ("shushunje", "shushunjë (leech)"),
    ("hale peshku", "halë peshku (fish bone)"),
    ("kerpudha te egra", "kërpudha të egra (wild mushrooms)"),
    ("me luge", "me lugë (spoon)"),
    ("gjemb peshku", "gjemb peshku (fish spine splinter)"),
    ("hedh miell", "hedh miell (flour)"),
    ("hape gjumi", "hape gjumi (sleeping pills)"),
    ("uji me gaz", "ujë i gazuar (sparkling water)"),
    ("uje me gaz", "ujë i gazuar (sparkling water)"),
    ("laj dhembet", "laj dhëmbët (brush my teeth)"),
    ("mjalti per kollen", "mjalti për kollën (honey for cough)"),
    ("po me merren mendte", "po më vjen rrotull, gati të më bjerë të fikët (I feel faint and dizzy)"),
    ("me merren mendte", "më vjen rrotull (I feel faint)"),
    ("me shkoi gjilpera", "më hyri gjilpëra (a sewing needle pierced)"),
    ("bateri ore", "bateri ore (button battery)"),
    ("i eshte grire", "është gërvishtur rëndë (badly scraped skin, road rash)"),
    ("grire krahu", "gërvishtur krahu (scraped arm, road rash)"),
    ("kandili i detit", "kandili i detit (jellyfish)"),
    ("iriq deti", "iriq deti (sea urchin)"),
    # "me" + crisis verb = the clitic "më" (bit ME), not "with"
    ("me kafshoi", "më kafshoi"),
    ("me ka kafshuar", "më ka kafshuar"),
    ("me dhemb", "më dhemb"),
    ("me dogji", "më dogji"),
    ("me theri", "më theri"),
    ("me ra", "më ra"),
    ("a ta heq", "a duhet ta heq"),
    # disambiguation: "mbytet" = both choking and drowning; food context = choking
    ("po mbytet me ushqim", "i ka ngecur ushqimi në fyt dhe nuk merr dot frymë"),
    ("po mbytet nga ushqimi", "i ka ngecur ushqimi në fyt dhe nuk merr dot frymë"),
    ("mbytet me ushqim", "i ka ngecur ushqimi në fyt"),
    # stroke idioms: literal MT of "i ra pika" destroys retrieval
    ("i ra pika", "ka pësuar goditje në tru"),
    ("i ka rene pika", "ka pësuar goditje në tru"),
    ("i ka r[ëe]n[ëe] pika", "ka pësuar goditje në tru"),
    ("i varet goja", "i është shtrembëruar goja në një anë"),
    # dialect: "flama" = flu/cold, otherwise MT loses the topic entirely
    ("me ka rene flama", "kam marrë grip"),
    ("me ka r[ëe]n[ëe] flama", "kam marrë grip"),
    ("flama", "gripi"),
]
SQ_WORDS = {
    "te": "të", "ne": "në", "eshte": "është", "jane": "janë", "cfare": "çfarë",
    "bej": "bëj", "ben": "bën", "kembe": "këmbë", "dore": "dorë", "koke": "kokë",
    "qafe": "qafë", "shpine": "shpinë", "zemer": "zemër", "mushkeri": "mushkëri",
    "syte": "sytë", "uje": "ujë", "fryme": "frymë", "femija": "fëmija",
    "femije": "fëmijë", "nena": "nëna", "per": "për", "qe": "që", "shume": "shumë",
    "thike": "thikë", "plage": "plagë", "semure": "sëmurë", "semundje": "sëmundje",
    "temperature": "temperaturë", "ndihme": "ndihmë", "menjehere": "menjëherë",
    "veshtire": "vështirë", "gjarperi": "gjarpëri", "perdor": "përdor",
    "vjellje": "vjellje", "gelltiti": "gëlltiti", "gelltitur": "gëlltitur",
}


def normalize_sq(text):
    import re
    t = text
    for a, b in SQ_IDIOMS:
        t = re.sub(re.escape(a), b, t, flags=re.IGNORECASE)
    for a, b in SQ_WORDS.items():
        t = re.sub(r"\b%s\b" % a, b, t, flags=re.IGNORECASE)
    return t


def sq_to_en(text):
    return _translate(normalize_sq(text), SQ, EN)


# NLLB lacks the Albanian medical register: curated post-MT corrections,
# built from an audited phrase battery (2026-08-29). Evidence-based only.
SQ_FIXES = [
    (r"ngjitu\w* p[ëe]rpara", "përkuluni përpara"),
    (r"ngjit\w* kok[ëe]n (mbrapa|prapa)", "anoni kokën prapa"),
    (r"frym[ëe]zo(jeni|ni|je)", "merrni frymë"),
    (r"frym[ëe]zon\b", "merr frymë"),
    (r"frym[ëe]zo\w*", "merrni frymë"),
    (r"hidhni (ndonj[ëe] |çdo )?gjak\w*", "pështyjeni gjakun"),
    (r"(t[ëe] )?flis\w* gjak\w*", "pështyni gjakun"),
    (r"shp[ëe]rth\w+ (çdo|ndonj[ëe]) gjak\w*( q[ëe] d\w+)?", "pështyjeni çdo gjak që del"),
    (r"\bqyshje\b", "vjellje"),
    (r"uj[ëe] t[ëe] ftoht[ëe] \(jo t[ëe] ftoht[ëe]\)", "ujë të vakët (jo të akullt)"),
    (r"sponjo(ni|jeni)", "fshijeni me leckë të njomë"),
    (r"mjaftoni dor[ëe]n", "zhysni dorën"),
    (r"t[ëe] tokik", "lokal"),
    (r"ngjyra m[ëe] e madhe", "skuqje më e madhe"),
    (r"shkarko\w*", "largoni"),
    (r"\bsyja\b", "syri"),
    (r"\bnga sy\b", "nga syri"),
    (r"mb[ëe]shtjellni syrin me uj[ëe]", "shpëlajeni syrin me ujë"),
    (r"mjesh t[ëe] hyj[ëe] uji", "mos lejoni të hyjë uji"),
    (r"zhurmo\w* p[ëe]rmes goj[ëe]s", "merrni frymë me gojë"),
    (r"respiro\w* p[ëe]rmes goj[ëe]s", "merrni frymë me gojë"),
    (r"dressing(it|ut)\b", "fashës"),
    (r"dressing\w*", "fashë"),
    (r"gjaku\s+(i\s+)?mbyt\w*\s+(p[ëe]rmes|n[ëe]p[ëe]r|nga)", "gjaku depërton nëpër"),
    (r"mashtroj[ëe]?\b", "përtypë"),
    (r"mashtroni\b", "përtypni"),
    (r"mashtron\b", "përtyp"),
    (r"shp[ëe]rth\w+ (k[ëe]mb[ëe]n|krahun|dor[ëe]n)", r"lidheni me shinë \1"),
    (r"pozit[ëe]n e rim[ëe]k[ëe]mbjes", "pozicionin e shpëtimit"),
    (r"pozicionin e rim[ëe]k[ëe]mbjes", "pozicionin e shpëtimit"),
    (r"hidhni gjak\b", "pështyjeni gjakun"),
    (r"mb[ëe]shtjellni zjarrin", "mbulojeni djegien"),
    (r"push\w* pjes[ëe]n e but[ëe]", "shtrëngoni pjesën e butë"),
    (r"push pjes[ëe]n", "shtrëngoni pjesën"),
    (r"pusho\w* p[ëe]rmes goj[ëe]s", "merrni frymë me gojë"),
    (r"hapni frym[ëe]", "merrni frymë"),
    (r"thithni çdo gjak", "pështyjeni çdo gjak"),
    (r"u ul dhe u shtr[ëe]ngua p[ëe]rpara", "uluni dhe përkuluni përpara"),
    (r"\bdjegi\b", "djegien"),
    (r"\s*bullshit\s*", " "),
    (r"t[ëe] hos[ëe]", "të kollitet"),
    (r"lugina e majt[ëe]", "ija e majtë"),
    (r"lugin[ëe]s s[ëe] djatht[ëe]", "ijës së djathtë"),
    (r"pundim i kthimit", "dhimbje kur hiqet dora"),
    (r"me nj[ëe] veshje t[ëe] past[ëe]r", "me një fashë të pastër"),
    (r"me nj[ëe] l[ëe]kur[ëe] t[ëe] past[ëe]r", "me një fashë të pastër"),
    (r"shp[ëe]rth\w+ ngadal[ëe]", "derdhni ngadalë"),
    (r"shp[ëe]rth\w+ .{0,12}(uj[ëe]|filxhan)", "derdhni ngadalë ujë"),
    (r"t[ëe] vrullur", "marramendje"),
    (r"\bpomp\b", "pomadë"),
    (r"ngjyra e rritur", "skuqje e shtuar"),
    # 2026-08-31 long-eval audit additions:
    (r"[çc]akull[ëe]?n?\w*", "nofullën"),
    (r"ngjit\w* kok[ëe]n (e tij |e saj )?larg", "anojani kokën pas"),
    (r"shtr[ëe]ngo\w* kok[ëe]n (e tij |e saj )?larg", "anojani kokën pas"),
    (r"Shkencat po p[ëe]rkeq[ëe]sohen", "Shenjat e përkeqësimit"),
    (r"\bShpirtimi\b", "Frymëmarrja"),
    (r"Pjella e f[ëe]mij[ëe]s", "Lëkura e fëmijës"),
    (r"\brabin[ëe]\b", "tërbim"),
    (r"\brabin[ëe]n\b", "tërbimin"),
    (r"MJ[ËE]M[ËE]N syt[ëe]", "MOS i fërkoni sytë"),
    (r"\bMJ[ËE]M?[ËE]?N[ËE]?\b", "MOS"),
    (r"duart e gota", "duart e palara"),
    (r"shkopin e dor[ëe]s", "fundin e shuplakës"),
    (r"madh[ëe]sin[ëe] e nx[ëe]n[ëe]sve( tuaj)?", "madhësinë e bebëzave"),
    (r"\bnx[ëe]n[ëe]sve tuaj\b", "bebëzave tuaja"),
    (r"ngjitni brakun", "ngrijani mjekrën"),
    (r"R[ËE]SHIM:", "KUJDES:"),
    (r"\bqajit\b", "të qarit"),
    (r"(\bJE\b[ ,]*){4,}", " "),
    (r"[Tt]hithni uj[ëe] t[ëe] [çc]muar", "Derdhni ujë të freskët"),
    (r"uj[ëe] t[ëe] [çc]muar", "ujë të freskët"),
    (r"vaj antibiotik", "pomadë antibiotike"),
    (r"xhel[ëe] e naft[ëe]s", "vazelinë"),
    (r"pla[çc]k[ëe] gaze", "garza"),
    # round 7: prompt-template echoes + fresh MT garbles
    (r"Filloni me veprimin m[ëe] (t[ëe] )?urgjent[:.]?\s*", ""),
    (r"Pastaj jepni hapa t[ëe] num[ëe]ruar n[ëe] rendin q[ëe] duhet t[ëe] kryhen[:.]?\s*", ""),
    (r"ngush[ëe]llim i r[ëe]nd[ëe] i barkut", "ngurtësim i barkut"),
    (r"gjak t[ëe] pjekur", "vjellje me gjak"),
    (r"\bFev[ëe]ria\b", "Ethe"),
    (r"Motimi i ushqimit", "Refuzimi i ushqimit"),
    (r"\bQytni\b", "Pritni"),
    (r"mbi gjunj[ëe] (e|t[ëe]) majt[ëe]", "mbi ijën e majtë"),
    (r"mbi gjunj[ëe] (e|t[ëe]) djatht[ëe]", "mbi ijën e djathtë"),
    (r"pajisje t[ëe] prodhuar p[ëe]r t[ëe] hequr l[ëe]kur[ëe]n", "vegël për heqjen e rriqrës"),
    (r"kap(ur|ni)? l[ëe]kur[ëe]n sa m[ëe] afr[ëe] l[ëe]kur[ëe]s", "kapni rriqrën sa më afër lëkurës"),
    (r"\bpiker[ëe]\b", "pincetë"),
    (r"l[ëe]kur[ëe] t[ëe] sh[ëe]mtuar", "leukoplast i butë (moleskin)"),
    (r"\bkaset[ëe]\b", "leukoplast"),
    (r"helmin e bi[çc]iklet[ëe]s", "kaskën e biçikletës"),
    (r"[Tt]hithni uj[ëe]", "Derdhni ujë"),
    (r"uj\w* (t[ëe]|e) [çc]muar", "ujë të freskët"),
    (r"pikat e stomakut", "ulçerat e stomakut"),
    # strip classification-label echoes that survive into the Albanian text
    (r"(?m)^\s*(E )?P[ËE]RGJITHSHME\s*:\s*", ""),
    (r"(?m)^\s*(URGJENC[ËE]|EMERGJENC[ËE]|GENERAL|EMERGENCY)\s*:\s*", ""),
    (r"(?m)^\s*Kjo [ëe]sht[ëe] nj[ëe] (pyetje|situat[ëe]) (e p[ëe]rgjithshme|urgjente)[.:]?\s*", ""),
    (r"F[ëe]mija [ëe]sht[ëe] ve[çc]an[ëe]risht i pasur me hekur", "Mëlçia është veçanërisht e pasur me hekur"),
    (r"[Uu]ji i xhuxhur", "Uji i gazuar"),
    (r"[Pp]esh\w*(?=\s+dh[ëe]mb)", "lani"),
    (r"l[ëe]ngje, shuma", "lëngje, supa"),
    (r"\bfjetra e djalit\b", "ethja e djalit"),
    (r"\bShp[ëe]tohu n[ëe] nj[ëe] vend", "Shko në një vend"),
    (r"t[ëe] magjepsur( dhe t[ëe] v[ëe]shtira)?", "me marramendje"),
    (r"madh[ëe]si\w* (e|s[ëe]) nx[ëe]n[ëe]sve", "madhësinë e bebëzave"),
    (r"(e )?vajit t[ëe] vajit( t[ëe] vajit)*", "vazelinë"),
    (r"institucion\w* t[ëe] lindjes", "spital"),
    (r"\bvjeksim\b", "të vjella"),
    (r"\bvremje\b", "vjellje"),
    (r"je mj[ëe]m[ëe]n", "mbajeni të palëvizur"),
    (r"MJ[ËE]N.?I jepni", "MOS i jepni"),
    (r"\bmjesh\b", "mos"),
    (r"xhelis[ëe] s[ëe] naft[ëe]s", "vazelinë"),
]


def _polish_sq(text):
    for pat, rep in SQ_FIXES:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    lines = []
    for ln in text.split("\n"):
        m = re.match(r"^(\s*(?:\d+\.\s*)?)(\w)(.*)$", ln, re.UNICODE)
        lines.append(m.group(1) + m.group(2).upper() + m.group(3) if m else ln)
    return "\n".join(lines)


def en_to_sq(text):
    """Line-by-line to preserve numbered-step structure."""
    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.strip()]
    if not idx:
        return text
    translated = _translate([lines[i] for i in idx], EN, SQ)
    for i, t in zip(idx, translated):
        lines[i] = t
    return _polish_sq("\n".join(lines))


if __name__ == "__main__":
    import time
    t0 = time.time(); _get()
    print("load: %.1fs" % (time.time() - t0))
    for q in ["gjarpri me kafshoi ne kembe cfare te bej",
              "femija u dogj me uje te valuar cfare te bej",
              "shoku im eshte pa ndjenja a duhet ti jap uje"]:
        t0 = time.time()
        print("SQ :", q)
        print("EN :", sq_to_en(q), "(%.1fs, det=%s)" % (time.time() - t0, langdetect.detect(q)))
        print()
    sample = ("Do not give him anything to eat or drink.\n"
              "1. Lay him on his side with his head tilted back.\n"
              "2. Check that he is breathing normally.\n"
              "3. Seek medical help immediately.")
    t0 = time.time()
    print("EN answer -> SQ:")
    print(en_to_sq(sample))
    print("(%.1fs)" % (time.time() - t0))
