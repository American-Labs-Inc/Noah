#!/usr/bin/env python3
"""Noah deterministic safety overrides.

Keyword-triggered, pre-written warnings prepended before the LLM answer.
No LLM involved: regex in, fixed text out. Bilingual by construction -
English patterns run against the MT-translated query, Albanian patterns
against the raw input as a second net. Warnings are phrased conditionally
so a false positive is harmless and a miss is the only failure that costs.
"""
import re

# (name, en_pattern, sq_pattern, en_warning, sq_warning)
RULES = [
    ("unconscious",
     r"unconscious|not responding|unresponsive|won'?t wake|passed out|knocked out|no feelings",
     r"pa ndjenja|pa vet[ëe]dije|s'?ka ndjenja|humbur (ndjenjat|vet[ëe]dijen)|nuk zgjohet|pa nd[ëe]rgjegje|ra t[ëe] fik[ëe]t",
     "WARNING: An unconscious person must NEVER be given anything by mouth, no water, food, or medicine (choking danger).",
     "KUJDES: Një personi pa vetëdije MOS i jepni kurrë asgjë nga goja, as ujë, as ushqim, as ilaçe (rrezik mbytjeje)."),

    ("not-breathing",
     r"not breathing|stopped breathing|isn'?t breathing|no pulse|no breath|collapsed",
     r"nuk merr frym[ëe]|s'?merr frym|nuk frymon|pa puls|s'?ka puls|u rr[ëe]zua pa",
     "WARNING: If the person is not breathing, start chest compressions NOW: push hard and fast in the center of the chest, 100-120 per minute, about 5 cm deep. Do not stop until help arrives or they start breathing.",
     "KUJDES: Nëse personi nuk merr frymë, fillo MENJËHERË shtypjet e gjoksit: shtyp fort dhe shpejt në mes të gjoksit, 100-120 herë në minutë, rreth 5 cm thellë. Mos u ndal derisa të vijë ndihma ose të marrë frymë."),

    ("burn",
     r"\bburn(?!(s|ing)? when\b[^.]{0,20}\b(urin\w*|pee\w*|piss\w*|wee\w*|on\s+the\s+toilet\b|(?:(?:go|going|goes|went|get|getting|run|running)\s+to|use|using|used|visit|visiting)\s+(?:the\s+)?(?:toilet|bathroom|loo)\b(?![^.]{0,2}\b(?:cleaner|cleaning|heater|bleach|product|spray|tiles|floor|door|sink|mirror|light|i|we|he|she|they|the|a|an|my|his|her|and|when|where|while|because)\b)))(?!\w*.{0,18}after eat)|scald|caught fire|boiling water|hot oil|hot water|acid (fell|spilled|splashed|got|on)|(spilled|splashed|got).{0,12}acid",
     r"\bdogj\w*(?!.{0,30}kandil)|djegie|djeg[ëe]?(?!.{0,25}(urino|gjoksi pas|pas ngr[ëe]nies))(?!.{0,30}kandil)|p[ëe]rv[ëe]lua|p[ëe]rzhit\w*|skuq\w*.{0,22}diell|uj[ëe] t[ëe] valuar|uj[ëe] i nxeht[ëe]|m[ëe] ra acid|acid\w*.{0,22}(krah|dor[ëe]|k[ëe]mb[ëe]|fytyr|l[ëe]kur)",
     "WARNING: Cool the burn with cool running water for at least 20 minutes. NEVER remove clothing stuck to the burn. Never apply ice, butter, or toothpaste.",
     "KUJDES: Ftohe djegien me ujë të rrjedhshëm të freskët për të paktën 20 minuta. MOS i hiq kurrë rrobat e ngjitura pas djegies. Mos vendos akull, gjalpë ose pastë dhëmbësh."),

    ("anaphylaxis",
     r"\bsting|\bstung|wasp|\bbee\b|hornet|allergic|anaphyla",
     r"picko\w*|pickuar|pickim|thumbo\w*|thumbim|grenz[ëae]\w*|blet[ëae]\w*|alergji|akrep\w*|ther\w*.{0,22}(blet[ëae]|grenz[ëae])",
     "WARNING: Face swelling or trouble breathing after a sting is a severe allergic emergency. Use an epinephrine auto-injector (EpiPen) NOW if available. Scrape a bee stinger off the skin quickly, do not squeeze it.",
     "KUJDES: Fryrja e fytyrës ose vështirësia në frymëmarrje pas pickimit është urgjencë e rëndë alergjike. Përdor MENJËHERË autoinjektorin e epinefrinës (EpiPen) nëse e ke. Hiqe thumbin duke e kruar shpejt nga lëkura, mos e shtrydh."),

    ("impaled",
     r"knife in|stuck in (his|her|my|the) (?!throat|windpipe|mouth)|impaled|nail in|embedded in|object in (his|her|my|the) (?!throat|windpipe|mouth)",
     r"(kam|ka|[ëe]sht[ëe]) thik\w* (n[ëe]|te)\b|(i|e) ngulur|ngulur n[ëe]",
     "WARNING: Do NOT pull out an object stuck in the body. Stabilize it in place with bulky dressings and bandage around it.",
     "KUJDES: MOS e hiq objektin e ngulur në trup. Fiksoje në vend me garza të trasha dhe lidhe rreth e rrotull tij."),

    ("spinal",
     r"(fell|fall|hit).{0,40}(neck|back|spine)|neck.{0,20}(hurt|pain|injur)|spinal|spine|can'?t (feel|move).{0,15}(legs|arms)|no feeling in.{0,10}legs",
     r"qaf[ëae].{0,25}(dhemb|dhimbje|lëndu|lendu)|(ra|u rr[ëe]zua).{0,40}(qaf[ëae]|kurriz|shpin[ëe])|kurriz|shtyll[ëe]s? kurrizore|nuk (i |e )?(ndjen|l[ëe]viz)\w*.{0,20}(k[ëe]mb[ëe]t|duart|gjymtyr)|(ra|u rr[ëe]zua) (nga|n[ëe]) ([çc]atia|pema|lart[ëe]sia|kali|traktori|shkall\w*)|aksident\w* (me )?(makin[ëe]|motor\w*)|ra nga motori",
     "WARNING: Possible spinal injury, do NOT move the person or their head/neck unless they are in immediate danger. Do not let them sit up or walk.",
     "KUJDES: Dëmtim i mundshëm i shtyllës kurrizore, MOS e lëviz personin as kokën/qafën, veç nëse është në rrezik të menjëhershëm. Mos e lër të ngrihet a të ecë."),

    ("poison",
     r"poison|overdose|(swallowed|ate|took|drank) (?:(?:some |a |the |his |her )?(?:bleach|chemicals?|detergent|kerosene|gasoline|petrol|lamp oil|lighter fluid|paraffin|antifreeze|weed ?killer|rat poison|cleaning (?:product|fluid|liquid))|(?:pills|medicine|medicines|tablets)\b|(?:too many|lots of|a lot of|a bottle of|all the|all of the|a handful of|\d+) (?:pills|tablets|medicines?))",
     r"helm|helmuar|g[ëe]lltiti?|piu .{0,25}(detergjent|benzin[ëe]|vajgur\w*|kimikat|zbardhues|gaz|naft[ëe]|hollues|aceton|alkool)|mbidoz[ëe]|ka ngr[ëe]n[ëe] ila[çc]|h[ëe]ngri ila[çc]|p[ëe]rpiu ila[çc]|h[ëe]ngri k[ëe]rpudha|k[ëe]rpudha t[ëe] egra|piu .{0,28}(hape|hapa|ila[çc]e)|hape gjumi|h[ëe]ngri cigar\w*|cigar\w*.{0,22}(h[ëe]ngri|p[ëe]rtyp)|piu dy her[ëe]|dy her[ëe] ila[çc]",
     "WARNING: Do NOT make the person vomit. Give nothing by mouth unless a medical professional tells you to.",
     "KUJDES: MOS e bëj personin të vjellë. Mos i jep asgjë nga goja pa udhëzimin e një mjeku."),

    ("tourniquet",
     r"tourniquet",
     r"turniket|rrip\w* shtr[ëe]ngues|liro\w*\W+(rripin|rripi|turniket)",
     "WARNING: Once a tourniquet is applied, do NOT loosen or remove it. Write down the time it was applied.",
     "KUJDES: Pasi të vendoset rripi shtrëngues (turniketa), MOS e liro dhe mos e hiq. Shëno orën kur u vendos."),

    ("drowning",
     r"(pulled|rescued|got).{0,30}(from|out of).{0,15}water|drown|nearly drowned",
     r"(nxorr[ëe]m|nxora).{0,25}nga uji|mbytur n[ëe] uj[ëe]|po mbytej",
     "WARNING: After a drowning incident: lay the person on their side (recovery position), keep them still and warm, and do NOT press on their belly to force water out. If they stop breathing normally, start CPR. Every drowning patient needs medical evaluation.",
     "KUJDES: Pas mbytjes në ujë: shtrije personin në krah (pozicioni i shpëtimit), mbaje të qetë e ngrohtë, dhe MOS ia shtyp barkun për të nxjerrë ujin. Nëse i ndalon frymëmarrja normale, fillo CPR. Çdo i mbytur ka nevojë për kontroll mjekësor."),

    ("snakebite",
     r"snake.{0,25}bit|snakebite|bitten by.{0,15}snake|viper|\bsnake\b",
     r"gjarp[ëe]?ri?.{0,25}kafsho|kafsho\w*.{0,30}gjarp[ëe]?r|kafshim.{0,10}gjarpri|gjarp[ëe]?r\w*|nep[ëe]rk[ëe]",
     "WARNING: For snakebite do NOT cut the wound, suck out venom, or apply a tourniquet. Keep the person still and the bitten limb immobile.",
     "KUJDES: Për kafshim gjarpri MOS e prit plagën, mos thith helmin dhe mos vendos rrip shtrëngues. Mbaje personin të qetë dhe gjymtyrën të palëvizur."),

    ("childbirth",
     r"labor|contractions|giving birth|baby is coming|pregnan\w*.{0,35}(pain|labou?r|contract)",
     r"dhimbjet? e lindjes|po lind\b|shtatz[ëe]n[ëae].{0,40}dhimbje|i erdhi koha e lindjes",
     "WARNING: If the baby is coming and you cannot reach medical care: use clean hands and clean cloths. Let the birth happen naturally, do NOT pull the baby and do NOT press on the belly. Dry the baby, place it skin-to-skin on the mother's chest and cover both. Do not cut the cord without clean tools. Get medical help.",
     "KUJDES: Nëse foshnja po vjen dhe s'arrini dot te mjeku: duar dhe rroba të pastra. Lëreni lindjen të ndodhë natyrshëm, MOS e tërhiqni foshnjën dhe MOS e shtypni barkun. Thajeni foshnjën, vendoseni lëkurë-më-lëkurë në gjoksin e nënës dhe mbulojini të dy. Mos e prisni kërthizën pa vegla të pastra. Kërkoni ndihmë mjekësore."),

    ("fever",
     r"high fever|fever.{0,30}(days|for \d)|temperature.{0,20}(high|days)",
     r"ethe t[ëe] larta|ethe.{0,25}dit[ëe]|temperatur[ëe].{0,15}e lart[ëe]|flam[ëae]|i (hipen|hipi|u ngjit) temperatura",
     "WARNING: High fever lasting more than 2 days needs a health worker, it can be malaria, typhoid or another infection that needs diagnosis. Meanwhile: plenty of fluids, light clothing, cool sponging. Do NOT start antibiotics on your own.",
     "KUJDES: Ethe të larta mbi 2 ditë duan mjek, mund të jetë malarie, tifo a një infeksion tjetër që duhet diagnostikuar. Ndërkohë: shumë lëngje, rroba të lehta, fshirje me leckë të vakët. MOS fillo antibiotikë me kokën tënde."),

    ("dental",
     r"(broken|knocked.?out|lost|chipped|pulled|extracted|removed).{0,15}tooth|tooth.{0,25}(broke|knocked|fell|pulled|extracted|removed|out)",
     r"(thye|ra|r[ëe]n[ëe]|doli|hoq\w*|u thye).{0,18}dh[ëe]mb\w*|dh[ëe]mb\w*.{0,22}(thye|\bra\b|r[ëe]n[ëe]|doli)",
     "WARNING: Mouth bleeding: bite firmly on a clean folded cloth for 15 minutes. If a permanent tooth came out whole, do NOT scrub it, keep it in milk or in the person's own saliva and see a dentist within a few hours; it can sometimes be saved.",
     "KUJDES: Gjakderdhje nga goja: kafshoni fort një leckë të pastër të palosur për 15 minuta. Nëse një dhëmb i përhershëm ka dalë i tëri, MOS e fërkoni, mbajeni në qumësht ose në pështymën e vetë personit dhe shkoni te dentisti brenda pak orësh; ndonjëherë shpëtohet."),

    ("rehydration",
     r"diarrh|rehydration|\bors\b|dehydrat|vomit(ing)? (all day|for hours|constantly)|food poisoning|(vomit|sick|throwing up).{0,30}after (eating|food|the meal)",
     r"diarre|barkqitje|dehidrim|jasht[ëe]qitje|vjell (gjith[ëe] dit[ëe]n|pa pushim|vazhdimisht)|t[ëe] vjella.{0,32}(h[ëe]ngr\w*|ushqim|mish)|pasi h[ëe]ngr\w*.{0,30}t[ëe] vjella",
     "REHYDRATION DRINK (exact recipe): 1 liter of clean water + half a level teaspoon of salt + 8 level teaspoons of sugar. Taste it: no saltier than tears. Give small sips every few minutes, even if there is vomiting.",
     "PIJA REHIDRUESE (receta e saktë): 1 litër ujë i pastër + gjysmë lugë çaji kripë (rrafsh) + 8 lugë çaji sheqer (rrafsh). Provoje: të mos jetë më e kripur se lotët. Jepi gllënjka të vogla çdo pak minuta, edhe nëse vjell."),

    ("heatstroke",
     r"heat ?stroke|collapsed.{0,30}(sun|heat)|(sun|heat).{0,35}collapsed|skin.{0,20}hot and dry|hot and dry skin|not sweating|stopped sweating|(sun|heat|hot).{0,45}(dizzy|not sweat)|(left|forgot|locked|stuck).{0,28}(car|vehicle)|hot car",
     r"goditje nga (nxeht[ëe]sia|dielli)|i ra t[ëe] fik[ëe]t nga (dielli|vapa)|l[ëe]kur[ëae].{0,20}(nxeht[ëe]|e that[ëe])|nuk djersit|(u )?nxeh\w*.{0,30}diell|diell\w*.{0,35}(rrotull|marramendje|t[ëe] fik[ëe]t)|vap[ëae]?\w*.{0,30}(rrotull|marramendje|t[ëe] fik[ëe]t)|(harru\w*|mbyll\w*|ngec\w*).{0,28}(makin[ëe]|vetur[ëe])|makin[ëe]\w*.{0,18}(diell|vap[ëe])|pika e diellit",
     "WARNING: Hot dry skin after collapsing in heat = heat stroke. Cool them FAST: shade, remove extra clothing, wet cloths and fanning. Give sips of water ONLY if they are fully awake and can swallow, never if drowsy or confused.",
     "KUJDES: Lëkurë e nxehtë e thatë pas rrëzimit në vapë = goditje nga nxehtësia. Ftohe SHPEJT: hije, hiqi rrobat e tepërta, lecka të lagura dhe fresk. Jepi gllënjka ujë VETËM nëse është plotësisht zgjuar dhe gëlltit dot, kurrë nëse është i përgjumur a i hutuar."),

    ("seizure",
     r"seizure|convuls|(is )?shaking all over|(?:\b(?:a|an|another|the|this|that|each|every|his|her|their|my|your|its|last|first|second|new)\s+(?:\w+\s+){0,2}?(?<!shoes )(?<!gloves )(?<!boots )(?<!clothes )(?<!pants )(?<!they )(?<!these )(?<!those )(?<!both )fit\b(?!\s+(?:me|you|him|her|them|us|well|badly|properly|nicely|perfectly|snugly|fine|tightly|loosely|securely|correctly|into|inside|through|over|under|on)\b)|\b(?:febrile|epileptic|convulsive|violent|sudden|tonic|grand mal|absence)\s+fits?\b|(?<!it )(?<!shoe )(?<!mask )(?<!dress )(?<!shirt )(?<!size )\bfits\b(?!\s+(?:all|me|you|him|her|them|us|well|badly|properly|nicely|perfectly|snugly|fine|into|in the|on|over|inside|through|for|like)\b)|\b(?:might|may|could|will|would|started to|start to|began to|begin to|going to|about to)\s+fit\b|\bfit again\b|\bto fit\b(?!\s+(?:in|into|the|a|an|him|her|them|you|me|us|it|well|properly|through|over|under|on|inside)\b)|\bfitting\b(?!\s+(?:room|in|into|the|a|an|him|her|them|it|well)\b)|\bfitted\b(?!\s+(?:with|the|a|an|into|in|him|her|them|it|out)\b))|epilep|krize.{0,15}dridh|foam(ing)? (at|in) (the |his |her )?mouth|trembling all over",
     r"krize.{0,25}dridh|po dridhet i (gjith[ëe]|t[ëe]ri)|dridhej i (gjith[ëe]|t[ëe]ri)|filloi t[ëe] dridhej|dridhet.{0,35}shkum[ëe]?|shkum[ëe]?.{0,25}(goj[ëe]|dridh)|konvulsion|epilepsi|kriz[ëe] epileptike|hap\w* goj[ëe]n me lug[ëe]|lug[ëe] n[ëe] goj[ëe]",
     "WARNING: During a seizure: do NOT hold the person down and put NOTHING in their mouth. Move hard objects away, cushion the head, and time the seizure. Afterwards lay them on their side. Get medical help if it lasts over 5 minutes, repeats, or it is their first seizure.",
     "KUJDES: Gjatë krizës: MOS e mbaj personin me forcë dhe MOS i fut ASGJË në gojë. Largo sendet e forta, mbroji kokën me diçka të butë dhe mat sa zgjat. Pas krizës shtrije në krah. Kërko ndihmë mjekësore nëse zgjat mbi 5 minuta, përsëritet, ose është kriza e parë."),

    ("electrical",
     r"electric(al)? (shock|burn|current|wire)|electrocut|power line|got shocked|(caught|grabbed|holding|stuck).{0,30}(live )?wire|current (caught|got|grabbed)",
     r"rrym[ëae] elektrike|goditje elektrike|elektrizua|kabllo elektrike|korr?ent\w*|e kapi rryma|i kapur pas telit|tel\w* elektrik",
     "WARNING: Electricity, before touching anyone still in contact with the source, CUT THE POWER or push the wire away with dry wood or plastic, never with bare hands. Electrical burns can be deep inside even when the skin looks minor: medical check is needed. If they are unresponsive and not breathing, start CPR.",
     "KUJDES: Rryma elektrike, para se të prekësh dikë që është ende në kontakt me burimin, NDËRPRIT RRYMËN ose largoje kabllon me dru a plastikë të thatë, kurrë me duar të zhveshura. Djegiet elektrike mund të jenë të thella brenda edhe kur lëkura duket mirë: duhet kontroll mjekësor. Nëse s'përgjigjet dhe nuk merr frymë, fillo CPR."),

    ("diabetic",
     r"diabet\w*.{0,90}(dizzy|faint|confus|shak|sweat|weak|unconscious)|low blood sugar|hypoglyc",
     r"diabet\w*.{0,50}(marramendje|t[ëe] fik[ëe]t|hutuar|djers|dridh|dob[ëe]t)|sheqeri i ul[ëe]t",
     "WARNING: A diabetic who is dizzy, shaky, sweaty or confused may have LOW blood sugar. If they are awake and can swallow, give sugar NOW, sugar, honey, juice or candy, and repeat in 10 minutes if not better. NEVER give anything by mouth if unconscious; get emergency help.",
     "KUJDES: Një diabetik me marramendje, dridhje, djersë a hutim mund të ketë sheqer TË ULËT. Nëse është zgjuar dhe gëlltit dot, jepi sheqer TANI, sheqer, mjaltë, lëng frutash a karamele, dhe përsërite pas 10 minutash nëse s'përmirësohet. KURRË asgjë nga goja nëse është pa vetëdije; kërko ndihmë urgjente."),

    ("animal-bite",
     r"(dog|cat|animal|bat|fox).{0,25}bit|bitten by.{0,20}(a |the )?(dog|cat|animal|bat|fox)",
     r"kafshuar\w*.{0,25}(qen|mace|kafsh[ëe])|(qen\w*|mace\w*|kafsh[ëe]\w*).{0,30}kafshu",
     "WARNING: Animal bite, wash the wound RIGHT NOW with soap and running water for 15 minutes. Do not close it tightly. There is rabies and tetanus risk: see a health worker as soon as possible, even if the wound looks small.",
     "KUJDES: Kafshim kafshe, laje plagën TANI me sapun dhe ujë të rrjedhshëm për 15 minuta. Mos e mbyll fort. Ka rrezik tërbimi dhe tetanozi: shko te mjeku sa më shpejt, edhe nëse plaga duket e vogël."),

    ("choking",
     r"choking|(food|meat|bone|piece|something|object|toy|marble)\b[^.]{0,12}(stuck|lodged)[^.]{0,15}(throat|windpipe|airway)|(piece|meat|bone|food|something|object)\b[^.]{0,12}(stuck|lodged)[^.]{0,25}(can'?t|cannot) breathe|can'?t breathe.{0,25}food|swallowed\s+(?:(?:a|an|some|the|his|her|my|their|one of|part of|a part of)\s+)?(?:\w+\s+){0,2}?(?:piece|bit|chunk|bite|bone|meat|food|bread|candy|sweet|grape|grapes|nut|peanut|coin|toy|toys|marble|lego|button|battery|magnet|bead|pin|stone|pebble|cap|lid|ring|bag|dog|sausage|screw|nail|object|something|it)\b[^.]{0,30}(can'?t|cannot) breathe|something stuck.{0,15}throat",
     r"(po )?mbytet (me|nga) ushqim|ka ngecur ushqimi|i z[ëe] fryma nga ushqimi",
     "WARNING: If they are coughing hard or can speak: do NOT interfere, encourage them to keep coughing until it clears. Only if they CANNOT breathe, speak or cough: give up to 5 firm blows between the shoulder blades with the heel of your hand, then up to 5 abdominal thrusts (fist above the navel, pull sharply in and up). Alternate 5 and 5 until it clears. If they become unresponsive, start CPR.",
     "KUJDES: Nëse kollitet fort ose flet dot: MOS ndërhy, nxite të kollitet vetë derisa të dalë. VETËM nëse nuk merr dot frymë, nuk flet dot dhe nuk kollitet dot: jepi deri në 5 goditje të forta mes shpatullave me fund të shuplakës, pastaj deri në 5 shtytje barku (grushti mbi kërthizë, tërhiq fort brenda e lart). Alterno 5 e 5 derisa të dalë. Nëse humb vetëdijen, fillo CPR."),

    # Generic airway-distress fallback for "can't breathe / turning blue" phrasings
    # that name no specific cause. It yields to rules whose advice would conflict
    # with it (see _FALLBACK_YIELDS_TO below) and stacks on the rest.
    # NOTE (added 2026-09-17, review fix): the bilingual text here is new and
    # should be checked through the eval harness before relying on it.
    ("breathing-distress",
     r"can'?t breathe|cannot breathe|trouble breathing|difficulty breathing|hard to breathe|struggling to breathe|can'?t catch (my |his |her |their )?breath|turning blue|going blue|lips (are )?blue|gasping",
     r"nuk (marr|merr) dot frym[ëe]|s'?(marr|merr) dot frym|vështir[ëe]si.{0,12}frym|z[ëe]n[ëe] fryma|gulço|kaltëro|kalter",
     "WARNING: Trouble breathing, gasping, or turning blue is an emergency. Get emergency help now. Keep them calm and loosen tight clothing. If they have their own inhaler or allergy auto-injector, help them use it. If they choke on food and cannot cough, speak, or breathe, give up to 5 back blows between the shoulder blades then up to 5 abdominal thrusts. If they stop breathing or become unresponsive, start CPR.",
     "KUJDES: Vështirësia në frymëmarrje, gulçimi ose kaltërimi janë urgjencë. Kërko ndihmë urgjente tani. Mbaje të qetë dhe liroji rrobat e ngushta. Nëse ka inhalatorin ose autoinjektorin e vet të alergjisë, ndihmoje ta përdorë. Nëse mbytet me ushqim dhe nuk kollitet, flet a merr dot frymë, jepi deri në 5 goditje mes shpatullave pastaj deri në 5 shtytje barku. Nëse i ndalon fryma ose humb vetëdijen, fillo CPR."),

    ("stroke",
     r"stroke|face.{0,25}(droop|crooked|twisted)|(droop|crooked|twisted).{0,25}(face|mouth)|can'?t (move|lift).{0,20}arm.{0,50}(mouth|face|speech)|slurred speech",
     r"i (ra|bie) pika|goditje n[ëe] tru|i varet goja|shtremb[ëe]ruar goja|nuk flet dot.{0,30}krah|nuk l[ëe]viz dot krahun",
     "WARNING: Face drooping, arm weakness, or trouble speaking = possible STROKE. Every minute matters: get emergency medical help NOW and note the time the symptoms started. Do NOT give food, drink, or any medicine. If drowsy, lay them on their side.",
     "KUJDES: Goja e shtrembëruar, dobësia e krahut ose vështirësia në të folur = GODITJE NË TRU e mundshme. Çdo minutë ka rëndësi: kërko ndihmë mjekësore urgjente TANI dhe shëno orën kur nisën shenjat. MOS i jep ushqim, pije a ilaçe. Nëse është i përgjumur, shtrije në krah."),

    ("fracture",
     r"broken (arm|leg|bone|wrist|ankle|hand|foot)|fracture|\bbroke (his|her|my|their) (arm|leg|wrist|ankle|hand|foot)|bone.{0,22}(came|sticking|coming|is) out|bone.{0,20}(protrud|expos|visible)|open fracture|crush\w*|caught in.{0,20}(press|machine|door)",
     r"thyer (krahun|k[ëe]mb[ëe]n|dor[ëe]n|kock[ëe]n|kyçin)|ka thyer|thyerje|vith\w*.{0,25}(dhemb|dhimbje|thye)|(dhemb|dhimbje).{0,20}vith\w*|(u rr[ëe]zua|ra).{0,35}nuk ngrihet dot|kock[ëe]?\w*.{0,25}(dal[ëe]|del|doli|jasht[ëe])|(doli|ka dal[ëe]).{0,22}kock|(z[ëe]n[ëe]|zuri).{0,25}(dor[ëe]n?|k[ëe]mb[ëe]n?|gisht)|pres[ëae]\w*.{0,20}shtyp|krejt t[ëe] shtypur",
     "WARNING: Keep the broken limb completely still. Splint it against something rigid and padded, wrapped firmly but not tight. Do NOT try to straighten the bone. A proper cast from medical care is needed, a bandage alone is not a treatment.",
     "KUJDES: Mbaje gjymtyrën e thyer krejt të palëvizur. Vendosi shinë me diçka të fortë e të mbushur, lidhur fort por jo shtrënguar. MOS u përpiq ta drejtosh kockën. Duhet allçi nga mjeku, vetëm fasha nuk e shëron."),

    ("heart-attack",
     r"chest pain|crushing.{0,25}chest|pain.{0,30}left arm|heart attack",
     r"dhimbje.{0,20}gjoks|gjoks\w*.{0,25}dhemb|krahu? i majt[ëe]|atak.{0,12}zem[ëe]r",
     "WARNING: Crushing chest pain may be a heart attack. Call for emergency help immediately and keep the person seated, calm and still. If they are fully alert and not allergic to it, they may slowly chew one aspirin. Do NOT give anyone else's medication.",
     "KUJDES: Dhimbja shtypëse në gjoks mund të jetë atak në zemër. Thirr menjëherë ndihmën mjekësore dhe mbaje personin ulur, të qetë e të palëvizur. Nëse është plotësisht i vetëdijshëm dhe jo alergjik, mund të përtypë ngadalë një aspirinë. MOS i jep ilaçet e të tjerëve."),

    ("bleeding",
     r"(bleeding|blood).{0,45}(won'?t|will not|does ?n'?t|not) stop(?!.{0,20}nose)|bleeding (heavily|badly|a lot|profusely)|losing (a lot of|so much) blood|blood (is )?(pouring|gushing|spurting)",
     r"(rrjedh|del|humb|po (m[ëe] )?ik[ëe]n).{0,20}(shum[ëe] )?gjak(?!\w*.{0,6}nga hund)|gjakderdhje e (r[ëe]nd[ëe]|madhe)|gjaku (nuk|s'?) ?(po )?ndalon|(nuk|s'?) ?(po )?ndalon gjaku",
     "WARNING: For heavy bleeding from a wound: press hard DIRECTLY on the wound with a clean cloth NOW and do not let go. If blood soaks through, add more cloth on top, do NOT remove the soaked one. Raise the limb if possible. Keep pressing without pause until help arrives.",
     "KUJDES: Për gjakderdhje të madhe nga një plagë: shtyp fort DREJTPËRDREJT mbi plagë me një leckë të pastër TANI dhe mos e lësho. Nëse gjaku depërton, shto leckë tjetër sipër, MOS e hiq të lagurën. Ngrije gjymtyrën lart nëse mundesh. Vazhdo shtypjen pa pushim derisa të vijë ndihma."),

    ("hypothermia",
     r"hypotherm|shiver\w*.{0,30}(cold|freez)|(freezing|ice.?cold).{0,30}(shiver|trembl|confus)|found.{0,25}(freezing|ice.?cold)|frostbit|frozen (toes|fingers|feet|hands)|(toes|fingers).{0,25}(white|frozen|numb)",
     r"hipotermi|dridhet.{0,30}(ftoht[ëe]|akull)|(ftoht[ëe]|akull).{0,30}dridhet|ftoht[ëe] akull|ngrir[ëe] (nga|s[ëe]) (t[ëe] )?ftohti|ngrir[ëe].{0,18}(bor[ëae]|d[ëe]bor[ëae]|acar)|gishta\w*.{0,30}(t[ëe] )?(bardh[ëe]|ngrir[ëe]|mavi)|m[ëe]rdhi\w*",
     "WARNING: Severe cold exposure: get them to shelter, replace wet clothes with dry ones, and wrap the whole body including head and neck. Warm sweet drinks ONLY if fully awake and able to swallow. Do NOT rub the skin, do NOT apply direct hot water, and give no alcohol. Handle gently and get medical help.",
     "KUJDES: Ftohje e rëndë: çoje në strehë, ndërroji rrobat e lagura me të thata dhe mbështille gjithë trupin bashkë me kokën e qafën. Pije të ngrohta me sheqer VETËM nëse është plotësisht zgjuar dhe gëlltit dot. MOS ia fërko lëkurën, MOS përdor ujë të nxehtë direkt dhe asnjë alkool. Trajtoje butë dhe kërko ndihmë mjekësore."),

    ("head-injury",
     r"(hit|bump|blow|blood|bleeding|wound|fell|crash).{0,30}head|head.{0,25}(bleed|blood|bump|lump|wound|injur)",
     r"(gjak|goditje|gung[ëe]|l[ëe]ndim|plag[ëe]).{0,25}kok[ëe]|kok[ëe]n?.{0,25}(gjak|goditj|gung[ëe]|plag[ëe])|(ra|u rr[ëe]zua).{0,35}(gjak nga koka|n[ëe] kok[ëe])|(ra|u rr[ëe]zua).{0,45}(po vjell|p[ëe]rgjum\w*|nuk mban syt[ëe])|ra (nga|n[ëe]) shkall\w*",
     "WARNING: Head wound: press gently on the bleeding with a clean cloth, do NOT press hard if the skull may be damaged. Keep them resting with head and shoulders slightly raised. Nothing to eat or drink. If the fall was violent, keep the neck still. Get urgent help if there is vomiting, confusion, unequal pupils, worsening drowsiness, or clear fluid from the nose or ears.",
     "KUJDES: Plagë në kokë: shtyp butë mbi gjakderdhjen me leckë të pastër, MOS shtyp fort nëse kafka mund të jetë dëmtuar. Mbaje shtrirë me kokën e supet pak të ngritura. Asgjë për të ngrënë a pirë. Nëse rrëzimi ishte i fortë, mbaje qafën të palëvizur. Kërko ndihmë urgjente nëse ka të vjella, hutim, bebëza të pabarabarta, përgjumje në rritje, ose lëng i kthjellët nga hunda a veshët."),

    ("chemical-eye",
     r"(bleach|chemical|acid|detergent|cleaner|lime|cement).{0,30}(in|into|splashed|got).{0,12}eye|eye.{0,25}(bleach|chemical|acid)|splashed.{0,20}eye",
     r"sp[ëe]rkat\w*.{0,25}sy|(zbardhues|kimikat|acid\w*|detergjent|g[ëe]lqere).{0,28}sy|sy\w*.{0,22}(zbardhues|kimikat|acid)",
     "WARNING: Chemical in the eye, flush NOW with clean water, continuously, for at least 20 minutes: hold the eyelid open and pour from the nose side outward so it does not run into the other eye. Remove contact lenses. Do NOT rub. Then urgent medical care.",
     "KUJDES: Kimikat në sy, shpëlaje TANI me ujë të pastër, pa ndërprerje, të paktën 20 minuta: mbaje kapakun hapur dhe derdh nga ana e hundës nga jashtë, që të mos i shkojë syrit tjetër. Hiq lentet e kontaktit. MOS e fërko. Pastaj kujdes mjekësor urgjent."),

    ("asthma",
     r"asthma.{0,45}(attack|can'?t breathe|inhaler)|inhaler.{0,25}(empty|ran out|finished|lost|no more)|no inhaler",
     r"astm[ëe]?\w*.{0,45}(pomp[ëae]|frym|nuk merr)|pomp[ëae].{0,25}(mbaruar|bosh|humbur)",
     "WARNING: Asthma attack with no working inhaler: sit them upright, leaning slightly forward, do not lay them down. Keep them calm with slow, steady breaths. Get emergency help NOW if lips or face turn bluish, they cannot speak full sentences, or it is not easing.",
     "KUJDES: Krizë astme pa pompë: mbaje ulur drejt, pak të përkulur përpara, mos e shtri. Qetësoje, me frymëmarrje të ngadalta e të njëtrajtshme. Kërko ndihmë urgjente TANI nëse buzët a fytyra i mavijosen, nuk flet dot fjali të plota, ose nuk po i lehtësohet."),

    ("carbon-monoxide",
     r"(headache|dizzy|drowsy|nauseous).{0,50}(stove|heater|brazier|generator|chimney|charcoal)|(stove|heater|brazier|generator|charcoal).{0,50}(headache|dizzy|drowsy)|carbon monoxide",
     r"(dhemb koka|dhimbje koke|marramendje|p[ëe]rgjum\w*).{0,50}(sob[ëae]n?|stuf[ëae]|mangall|oxhak|gjenerator)|(sob[ëae]n?|stuf[ëae]|mangall|oxhak|gjenerator).{0,50}(dhemb|dhimbje koke|marramendje|p[ëe]rgjum)|monoksid",
     "WARNING: Headache or dizziness in everyone in a room with a stove or heater = possible CARBON MONOXIDE poisoning. Get everyone OUTSIDE into fresh air NOW, open doors and windows, turn the stove/heater off, and do not go back inside. Anyone drowsy or confused needs urgent medical care.",
     "KUJDES: Dhimbje koke a marramendje te të gjithë në një dhomë me sobë a ngrohëse = helmim i mundshëm me MONOKSID KARBONI. Nxirrini të gjithë JASHTË në ajër të pastër TANI, hapni dyer e dritare, fikni sobën, dhe mos u ktheni brenda. Kush është i përgjumur a i hutuar ka nevojë urgjente për mjek."),

    ("nose-object",
     r"(object|bean|seed|pea|bead|something small|small object).{0,28}(in|up|into).{0,12}(nose|nostril)|(nose|nostril).{0,22}(object|bean|seed|bead)",
     r"(fut|hyr)\w*.{0,32}hund[ëe]|hund[ëe]\w*.{0,25}(send|objekt|kok[ëe]rr|fasule|far[ëe]|rruaz[ëe])|send.{0,28}hund[ëe]",
     "WARNING: Object in the nose: have them breathe through the MOUTH and stay calm. Do NOT poke anything into the nostril, it pushes the object deeper. Press the empty nostril closed and have them blow out sharply through the blocked side a few times. If it does not come out, see a health worker. This is NOT choking, no back blows or belly thrusts unless they truly cannot breathe.",
     "KUJDES: Send në hundë: le të marrë frymë me GOJË dhe qetësoje. MOS fut asgjë në vrimën e hundës, e shtyn më thellë. Mbylli me gisht vrimën e lirë dhe le të nxjerrë frymën fort disa herë nga ana e bllokuar. Nëse nuk del, shko te mjeku. Kjo NUK është mbytje me ushqim, pa goditje shpine e pa shtytje barku, veç nëse vërtet nuk merr dot frymë."),

    ("amputation",
     r"(cut|sawed|chopped|sliced) off.{0,22}(finger|toe|hand|foot|arm|leg)|amputat|severed|(finger|toe|hand)s?.{0,15}(cut|chopped|sawed) off",
     r"(preu|prer[ëe]|k[ëe]puti?).{0,25}(gisht|dor[ëe]|k[ëe]mb[ëe]|krah)|sharra.{0,25}gisht|gisht\w*.{0,25}(prer[ëe]|k[ëe]put)|amputim",
     "WARNING: Amputation: first stop the bleeding at the injury, press hard with a clean cloth; a tourniquet only if pressure is not enough. Wrap the severed part in clean, slightly moist cloth, seal it in a plastic bag, and put the BAG on cold water or ice, the part must never touch ice directly. Bring it with the person to the hospital NOW: hours matter.",
     "KUJDES: Pjesë e prerë e trupit: në fillim ndal gjakderdhjen te plaga, shtyp fort me leckë të pastër; rrip shtrëngues vetëm nëse shtypja s'mjafton. Mbështille pjesën e prerë me leckë të pastër pak të njomë, mbylle në qese plastike dhe vëre QESEN mbi ujë të ftohtë a akull, pjesa të mos e prekë kurrë akullin direkt. Merre me vete në spital TANI: orët kanë rëndësi."),

    ("chest-wound",
     r"chest wound|wound.{0,25}chest|(sucking|whistling|hissing).{0,28}(chest|wound|breath)|(hole|stabbed).{0,20}chest",
     r"plag[ëae]\w*.{0,20}gjoks|gjoks\w*.{0,25}plag[ëae]|fishkell\w*.{0,30}(frym|plag)|(vrim[ëe]|thik[ëe]).{0,20}gjoks",
     "WARNING: A chest wound that hisses or bubbles with breathing is critical. Seal it NOW with a piece of plastic (or a gloved hand), taped on three sides only so air can escape but not enter. Let them sit half-upright, leaning toward the injured side. Emergency help immediately. If they suddenly worsen after sealing, lift one edge of the seal.",
     "KUJDES: Plaga në gjoks që fërshëllen a bën flluska me frymëmarrjen është kritike. Mbylle TANI me një copë plastike (ose me dorë me dorezë), e ngjitur me leukoplast vetëm në tre anë, që ajri të dalë por të mos hyjë. Mbaje gjysmë-ulur, të anuar nga ana e plagosur. Ndihmë urgjente menjëherë. Nëse përkeqësohet befas pas mbylljes, ngri njërën anë të plastikës."),

    ("pregnancy-bleeding",
     r"pregnan\w*.{0,35}bleed|bleed\w*.{0,30}pregnan|vaginal bleeding",
     r"shtatz[ëe]n[ëae]?\w*.{0,35}(gjakderdhje|gjak)|gjakderdhje.{0,30}shtatz[ëe]n",
     "WARNING: Bleeding in pregnancy is an emergency for mother and baby. Do NOT press on the belly and put nothing inside, an external pad only. Lay her on her LEFT side, keep her warm, nothing to eat or drink. Get her to medical care urgently and bring the soaked pads so staff can judge the blood loss.",
     "KUJDES: Gjakderdhja në shtatzëni është urgjencë për nënën dhe foshnjën. MOS e shtyp barkun dhe mos fut asgjë brenda, vetëm pecetë të jashtme. Shtrije në krahun e MAJTË, mbaje ngrohtë, asgjë për të ngrënë a pirë. Çoje urgjentisht te mjeku dhe merrni pecetat e njomura, që mjekët të vlerësojnë humbjen e gjakut."),

    ("infant-sick",
     r"(baby|infant|newborn).{0,35}(diarrh|vomit|fever)|\d ?-?(week|month)s?.?.?old.{0,30}(diarrh|vomit|fever)",
     r"foshnj\w*.{0,35}(diarre|vjell|ethe|temperatur)|(muajsh\w*|javsh\w*).{0,28}(diarre|vjell|ethe)",
     "WARNING: A baby under 6 months with diarrhea, vomiting or fever can become dangerously dehydrated within HOURS, see a health worker TODAY. Keep breastfeeding often and give the rehydration drink in small sips between feeds. Danger signs needing help NOW: sunken eyes or sunken soft spot, dry mouth, no wet diapers, unusual sleepiness.",
     "KUJDES: Foshnja nën 6 muajsh me diarre, të vjella a ethe mund të dehidratohet rrezikshëm brenda ORËSH, çojeni te mjeku SOT. Vazhdoni gjidhënien shpesh dhe jepini pijen rehidruese me gllënjka të vogla mes gjireve. Shenja rreziku që duan ndihmë TANI: sy të futur a vend i butë i futur, gojë e thatë, pa pelena të lagura, përgjumje e pazakontë."),

    ("testicle-pain",
     r"testic\w*.{0,30}pain|pain\w*.{0,30}testic|scrotum.{0,25}(pain|swoll)",
     r"dhimbje.{0,30}herdh\w*|dhemb\w*.{0,25}herdh\w*|herdh\w*.{0,30}(dhimbje|dhemb|enjtur)",
     "WARNING: Sudden severe testicle pain can be torsion, the blood supply is cut off. This is a surgical emergency: get to a hospital NOW; the testicle can usually be saved only within about 6 hours. Go even if the pain eases. Nothing to eat or drink on the way.",
     "KUJDES: Dhimbja e fortë e papritur e herdheve mund të jetë përdredhje, i pritet gjaku. Është urgjencë kirurgjikale: shko në spital TANI; herdha shpëtohet zakonisht vetëm brenda rreth 6 orësh. Shko edhe nëse dhimbja qetësohet. Asgjë për të ngrënë a pirë rrugës."),

    ("hanging",
     r"hang(ed|ing)?.{0,28}(rope|neck|noose|himself|herself|themselves)|found.{0,22}hanging|strangl",
     r"t[ëe] varur.{0,28}(litar|tavan)|varur n[ëe] litar|var\w* veten|litar\w*.{0,22}qaf[ëe]",
     "WARNING: Hanging: lift and support the body IMMEDIATELY to take the weight off the neck, call others to help. Cut well above the knot; do not waste time untying it. Once down: loosen everything around the neck; if they are not breathing start CPR; keep the neck as still as possible. Get emergency help and do not leave the person alone.",
     "KUJDES: Varje: ngrije dhe mbaje trupin MENJËHERË që pesha të mos rëndojë në qafë, thirr të tjerë në ndihmë. Prite litarin mbi nyjë; mos humb kohë duke e zgjidhur. Sapo të ulet: liro gjithçka rreth qafës; nëse nuk merr frymë fillo CPR; mbaje qafën sa më të palëvizur. Kërko ndihmë urgjente dhe mos e lër vetëm."),

    ("fishbone",
     r"fish ?bone.{0,22}(throat|stuck)|bone.{0,15}stuck.{0,15}throat|pill.{0,20}stuck|stuck pill|tablet.{0,15}stuck",
     r"hal[ëe]\w?.{0,20}(peshku|fyt|ngecur)|ngecur.{0,20}hal[ëe]|ila[çc]\w{0,3}.{0,20}ngec|ngeci ila[çc]\w*",
     "WARNING: A fish bone, pill or other object stuck in the throat of someone who can breathe and talk is NOT choking, no belly thrusts. Try a few sips of water or a bite of soft bread. Do NOT poke fingers or objects down the throat. If it does not pass, or pain, drooling or trouble swallowing grows, see a health worker. Emergency only if breathing stops.",
     "KUJDES: Halë peshku, ilaç a send tjetër i ngecur në fyt te dikush që merr frymë e flet NUK është mbytje, pa shtytje barku. Provo pak gllënjka ujë ose një kafshatë bukë të butë. MOS fut gishta a sende në fyt. Nëse nuk kalon, ose shtohet dhimbja, jargët a vështirësia në gëlltitje, shko te mjeku. Urgjencë vetëm nëse i ndalet fryma."),

    ("rusty-nail",
     r"(stepped|trod|stood).{0,18}(rusty )?nail|rusty nail|puncture wound|needle.{0,18}(stuck|in my|pierced|went into)",
     r"gozhd[ëe]\w*.{0,25}ndryshkur|shkeli n[ëe] gozhd[ëe]|gozhd[ëe] t[ëe] ndryshkur|gjilp[ëe]r[ëae]?\w*.{0,25}(dor[ëe]|gisht|k[ëe]mb[ëe]|hyri|shkoi)",
     "WARNING: A puncture from a rusty nail: wash it thoroughly for 15 minutes with soap and running water, let it bleed a little first. Cover it loosely. Deep dirty punctures carry TETANUS risk: see a health worker within 48 hours about a tetanus shot. Watch for spreading redness, warmth, pus or fever.",
     "KUJDES: Shpim nga gozhdë e ndryshkur: laje mirë 15 minuta me sapun e ujë të rrjedhshëm, lëre në fillim të kullojë pak gjak. Mbuloje lirshëm. Shpimet e thella të pista kanë rrezik TETANOZI: shko te mjeku brenda 48 orësh për vaksinën. Vëzhgo skuqje që zgjerohet, nxehtësi, qelb a ethe."),

    ("stuck-ring",
     r"ring.{0,22}(stuck|swell|won'?t come)|(stuck|tight) ring",
     r"unaz[ëae].{0,25}(ngecur|gisht|shtr[ëe]nguar)|gisht\w*.{0,22}unaz[ëae]",
     "WARNING: Ring stuck on a swelling finger: cool the hand in cold water and keep it raised to shrink the swelling, then use soap or oil and twist the ring off gently. Do NOT force it. If the finger turns cold, blue or numb, or the ring will not come off, get to a health worker urgently, a tight ring can cut off the blood supply.",
     "KUJDES: Unazë e ngecur në gisht që po enjtet: ftohe dorën në ujë të ftohtë dhe mbaje lart që të ulet ënjtja, pastaj sapun a vaj dhe rrotulloje unazën butë. MOS e forco. Nëse gishti ftohet, mavijoset a mpihet, ose unaza s'del, shko urgjent te mjeku, unaza e shtrënguar e pret gjakun."),

    ("leech",
     r"\bleech",
     r"shushunj\w*",
     "WARNING: Leech: slide a fingernail (or a flat card) under its mouth and push it off sideways, do NOT burn it, salt it, or rip it off; that makes it spit into the wound. Wash with soap and water. It may bleed for a while, that is normal. Cover it and watch for infection.",
     "KUJDES: Shushunja: fut thoin (a një kartë të hollë) nën gojën e saj dhe shtyje anash, MOS e djeg, mos i hidh kripë dhe mos e shkul me forcë, se villet në plagë. Laje me sapun e ujë. Mund të rrjedhë gjak për ca kohë, është normale. Mbuloje dhe vëzhgo për infeksion."),

    ("mushroom",
     r"(ate|eaten|had).{0,22}(wild )?mushroom|mushroom.{0,15}poison",
     r"k[ëe]rpudha\w*.{0,25}(egra|helm)|h[ëe]ngri k[ëe]rpudha",
     "WARNING: Wild mushroom poisoning can be DEADLY even if symptoms fade, with the most dangerous mushrooms people feel better for hours while the liver is failing. Get to hospital NOW; do not wait to see if it passes. Do NOT make them vomit. Bring a sample or a photo of the mushroom.",
     "KUJDES: Helmimi nga kërpudhat e egra mund të jetë VDEKJEPRURËS edhe nëse shenjat qetësohen, me kërpudhat më të rrezikshme njeriu ndihet më mirë për orë të tëra ndërsa mëlçia po dëmtohet. Shko në spital TANI; mos prit të shohësh nëse kalon. MOS e bëj të vjellë. Merr me vete një copë a një foto të kërpudhës."),

    ("ear-insect",
     r"insect.{0,18}ear|(fly|bug|beetle).{0,15}(in|into).{0,10}ear|ear.{0,20}(insect|fly|bug|buzz)",
     r"(insekt|miz[ëe]|mush\w*|buburrec).{0,25}vesh|vesh\w*.{0,25}(insekt|miz[ëe]|zhurm[ëe]|buburrec)",
     "WARNING: Insect in the ear: tilt the head so that ear faces UP and pour in a little lukewarm water or clean oil, the insect floats up and out. Do NOT poke anything into the ear canal. If it does not come out, or pain or bleeding starts, see a health worker. It is not life-threatening.",
     "KUJDES: Insekt në vesh: ktheje kokën me atë vesh LART dhe hidh brenda pak ujë të vakët a vaj të pastër, insekti noton e del. MOS fut asgjë në kanalin e veshit. Nëse nuk del, ose nis dhimbje a gjakderdhje, shko te mjeku. Nuk është rrezik për jetën."),

    ("button-battery",
     r"(swallowed|ate|gulped).{0,22}(button |watch |coin |small round )?batter|batter\w*.{0,22}swallow",
     r"bateri\w*.{0,32}(g[ëe]lltit|h[ëe]ngr|piu|rrumbullak|or[ëe]s|sahati)|g[ëe]lltit\w*.{0,28}bateri",
     "WARNING: A swallowed button battery is an EXTREME emergency, it burns through the food pipe within HOURS, even if the child seems completely fine. Go to hospital NOW, do not wait for symptoms. Nothing to eat or drink, do NOT make them vomit. At the hospital say clearly: 'swallowed a button battery', it needs an X-ray immediately.",
     "KUJDES: Bateria e vogël e rrumbullakët e gëlltitur është urgjencë EKSTREME, djeg gypin e ushqimit brenda ORËSH, edhe nëse fëmija duket krejt mirë. Shko në spital TANI, mos prit simptoma. Asgjë për të ngrënë a pirë, MOS e bëj të vjellë. Në spital thuaj qartë: 'ka gëlltitur bateri ore', duhet radiografi menjëherë."),

    ("pregnancy-fall",
     r"pregnan\w*.{0,32}(fell|fall|hit|slipped|accident)|(fell|fall|slipped).{0,28}pregnan",
     r"shtatz[ëe]n[ëae]?\w*.{0,35}(ra|u rr[ëe]zua|goditje|aksident)|(ra|u rr[ëe]zua).{0,32}shtatz[ëe]n",
     "WARNING: A fall during pregnancy: even with no visible injury the baby can be affected. Lay her on her LEFT side, keep her calm, and have her checked by a health worker TODAY. Go URGENTLY if there is any bleeding, fluid leaking, belly pain or tightening, or the baby moves less than usual.",
     "KUJDES: Rrëzim gjatë shtatzënisë: edhe pa lëndim të dukshëm, foshnja mund të jetë prekur. Shtrije në krahun e MAJTË, mbaje të qetë dhe çoje të kontrollohet te mjeku SOT. Shko URGJENT nëse ka gjakderdhje, rrjedhje lëngu, dhimbje a shtrëngim barku, ose foshnja lëviz më pak se zakonisht."),

    ("wound-infection",
     r"wound.{0,32}(black|smell|stink|pus|rotten)|(blackened|foul.?smell\w*|rotting).{0,22}wound",
     r"plag[ëae]\w*.{0,32}(nxir[ëe]|e zez[ëe]|er[ëe] e keqe|qelb|kalbur)|(nxir[ëe]|er[ëe] e keqe|kalbur).{0,28}plag[ëae]",
     "WARNING: A wound turning black with a foul smell is SEVERE infection, possibly gangrene, which kills if untreated. Get to a hospital TODAY. Keep the area at rest, cover it loosely. Do NOT bandage tightly and NEVER apply a tourniquet for an infection. Air bubbles under the skin or fast-spreading black edges = extreme emergency.",
     "KUJDES: Plaga që nxihet dhe vjen erë e keqe është infeksion i RËNDË, mundësisht gangrenë, që të vret pa u trajtuar. Shko në spital SOT. Mbaje zonën në qetësi, mbuloje lirshëm. MOS e lidh fort dhe KURRË mos vendos rrip shtrëngues për infeksion. Flluska ajri nën lëkurë a zgjerim i shpejtë i të nxirës = urgjencë ekstreme."),

    ("panic",
     r"panic attack|panick\w*|\bpanic\b|anxiety.{0,22}(breath|attack)",
     r"m[ëe] ka z[ëe]n[ëe] panik\w*|kam panik|atak panik\w*|panik\w*.{0,28}(frym|nuk marr)|ankth\w*.{0,28}(frym|zemra)",
     "WARNING: A panic attack feels like you cannot breathe, but your body IS getting enough air. Sit down. Put one hand on your belly. Breathe in slowly through the nose counting to 4, out through the mouth counting to 6, repeat for several minutes. It passes, usually within 20 minutes. Get medical help if there is chest pain spreading to the arm or jaw, or it does not ease.",
     "KUJDES: Ataku i panikut të bën të ndihesh sikur s'merr dot frymë, por trupi PO merr ajër mjaftueshëm. Ulu. Vër njërën dorë mbi bark. Merr frymë ngadalë nga hunda duke numëruar deri në 4, nxirre nga goja duke numëruar deri në 6, përsërite për disa minuta. Kalon, zakonisht brenda 20 minutash. Kërko mjek nëse ke dhimbje gjoksi që shkon te krahu a nofulla, ose nuk po të lehtësohet."),

    ("high-sugar",
     r"high (blood )?sugar|hyperglyc|aceton\w*.{0,15}(breath|smell|mouth)|ketoacid|sugar.{0,18}(400|350|300|very high)",
     r"sheqer\w* (i |t[ëe] )?lart[ëe]|era aceton|hiperglicemi|sheqeri (400|350|300)",
     "WARNING: High blood sugar with acetone-smelling breath, deep breathing, belly pain or drowsiness can be diabetic ketoacidosis, a medical emergency. Do NOT give sugar. Small sips of plain water if fully awake, their own diabetes medicine ONLY as prescribed, and medical help NOW. Drowsiness or confusion = critical.",
     "KUJDES: Sheqeri i lartë me erë acetoni nga goja, frymëmarrje të thellë, dhimbje barku a përgjumje mund të jetë ketoacidozë diabetike, urgjencë mjekësore. MOS i jep sheqer. Gllënjka të vogla ujë të thjeshtë nëse është plotësisht zgjuar, ilaçet e veta të diabetit VETËM siç i ka të përshkruara, dhe ndihmë mjekësore TANI. Përgjumja a hutimi = kritike."),

    ("eye-injury",
     r"(hit|ball|punch|blow|elbow).{0,25}eye|eye.{0,25}(hit|blunt|trauma|punch)|can'?t see.{0,28}(after|hit|blow)",
     r"(goditi|goditje|grusht|top(i)?).{0,28}sy|sy\w*.{0,25}(goditj|grusht)|(goditi|goditje).{0,32}nuk sheh",
     "WARNING: A blow to the eye with any change in vision is urgent. Do NOT press or rub the eye, and put NO drops or ointments in it. Cover it loosely with a rigid shield resting on the bone (a clean paper cup taped in place works). Keep them half-sitting. See an eye doctor URGENTLY, bleeding inside the eye cannot be judged from outside.",
     "KUJDES: Goditja në sy me çfarëdo ndryshimi të shikimit është urgjente. MOS e shtyp dhe mos e fërko syrin, dhe MOS fut pika a pomada. Mbuloje lirshëm me diçka të fortë që mbështetet në kockë (një gotë letre e pastër e ngjitur me leukoplast). Mbaje gjysmë-ulur. Shko URGJENT te okulisti, gjakderdhja brenda syrit nuk gjykohet dot nga jashtë."),

    ("jellyfish",
     r"jellyfish|sea nettle|stung.{0,22}(sea|beach|swimming)",
     r"kandil\w* (i |t[ëe] )?det\w*|m[ëe] dogji kandili|pickim.{0,18}det",
     "WARNING: Jellyfish sting: rinse with SEA water, NOT fresh water, it makes the stingers fire more venom. Scrape off any tentacle pieces with the edge of a card; do not rub with sand or a towel. Then soak in hot (not scalding) water or apply a hot compress for about 20 minutes for the pain. Get help urgently for trouble breathing, chest pain, or stings over a large area.",
     "KUJDES: Djegia nga kandili i detit: shpëlaje me ujë DETI, JO ujë të ëmbël, se i bën thumbat të lëshojnë më shumë helm. Kruaji copëzat e tentakulave me buzën e një karte; mos e fërko me rërë a peshqir. Pastaj zhyte në ujë të nxehtë (jo përvëlues) ose vër kompresë të nxehtë rreth 20 minuta për dhimbjen. Kërko ndihmë urgjente për vështirësi në frymëmarrje, dhimbje gjoksi, ose djegie në sipërfaqe të madhe."),

    ("sea-urchin",
     r"sea urchin|urchin.{0,15}spine|stepped on.{0,15}urchin",
     r"iriq\w* (i |t[ëe] )?det\w*|gjemba\w*.{0,28}(iriq|deti)",
     "WARNING: Sea urchin spines: pull the visible spines out gently with tweezers, do NOT crush them. Soak the foot in hot (not scalding) water for 30-60 minutes; it eases the pain and helps the spines. Spines broken off deep in the skin or near a joint need a health worker. Watch for infection over the next days.",
     "KUJDES: Gjembat e iriqit të detit: hiqi gjembat e dukshëm butë me pincetë, MOS i shtyp. Zhyte këmbën në ujë të nxehtë (jo përvëlues) për 30-60 minuta; ia lehtëson dhimbjen. Gjembat e thyer thellë në lëkurë ose pranë nyjeve duan mjek. Vëzhgo për infeksion ditët në vijim."),

    ("heat-cramps",
     r"(heat|exercise|playing|football).{0,22}cramp|cramp\w*.{0,28}(heat|sun|playing|exercise|football)",
     r"kramp\w*.{0,32}(vap[ëe]|diell|duke luajtur|st[ëe]rvit|futboll)|(vap[ëe]|diell|futboll).{0,30}kramp",
     "WARNING: Heat cramps: stop the activity, rest in the shade, and drink water with a pinch of salt or the rehydration drink. Stretch and gently massage the cramped muscle. Do NOT take salt tablets. If cramps last over an hour, or dizziness and vomiting begin, treat it as heat exhaustion, cool them down and get help.",
     "KUJDES: Krampet nga vapa: ndalo lojën, pusho në hije dhe pi ujë me një majë kripe ose pijen rehidruese. Shtriqe dhe masazho butë muskulin e ngërçuar. MOS merr tableta kripe. Nëse krampet zgjasin mbi një orë, ose nisin marramendje e të vjella, trajtoje si lodhje nga vapa, ftohe dhe kërko ndihmë."),
]


# Absolute-prohibition rules where the LLM has been observed commanding the
# forbidden action anyway. If the body opens with the forbidden imperative,
# it is replaced wholesale by the pre-written safe answer (no MT, no model).
CONTRA = {
    "spinal": (
        r"(^|\n)\s*(\d+\.\s*)?stand behind",
        "Do NOT move him, and keep his head and neck completely still.\n"
        "1. Tell him not to move. Steady his head with your hands if needed.\n"
        "2. Do not let him sit up, stand, or walk.\n"
        "3. Do not bend or twist his neck or back.\n"
        "4. Call emergency medical services immediately, moving him wrongly can cause permanent damage.\n"
        "5. Keep him warm and calm until help arrives.",
        "MOS e l\u00ebviz dhe mbaje kok\u00ebn e qaf\u00ebn krejt t\u00eb pal\u00ebvizura.\n"
        "1. Thuaji t\u00eb mos l\u00ebviz\u00eb. Mbaje kok\u00ebn me duar n\u00ebse duhet.\n"
        "2. Mos e l\u00ebr t\u00eb ulet, t\u00eb ngrihet a t\u00eb ec\u00eb.\n"
        "3. Mos ia p\u00ebrkul dhe mos ia rrotullo qaf\u00ebn a kurrizin.\n"
        "4. Thirr menj\u00ebher\u00eb ndihm\u00ebn mjek\u00ebsore, l\u00ebvizja e gabuar shkakton d\u00ebm t\u00eb p\u00ebrhersh\u00ebm.\n"
        "5. Mbaje ngroht\u00eb dhe t\u00eb qet\u00eb derisa t\u00eb vij\u00eb ndihma.",
    ),
    "poison": (
        r"(^|\n)\s*(\d+\.\s*)?(make|help|get) (him|her|them|the person) (to )?vomit|induce vomiting",
        "Do NOT make them vomit.\n"
        "1. If they vomit on their own, turn them on their side so it drains out.\n"
        "2. Give nothing by mouth unless a poison expert or health worker says so.\n"
        "3. Keep the container or a sample of what was swallowed to show the medics.\n"
        "4. Get medical help now.",
        "MOS e bëni të vjellë.\n"
        "1. Nëse vjell vetë, ktheje në krah që të dalë jashtë.\n"
        "2. Asgjë nga goja pa udhëzimin e një eksperti helmimesh a mjeku.\n"
        "3. Ruani enën ose një mostër të asaj që u gëlltit, t'ua tregoni mjekëve.\n"
        "4. Kërkoni ndihmë mjekësore tani.",
    ),
    "stroke": (
        r"(^|\n).{0,80}(stand behind (him|her|them)|wrap your arms around|abdominal thrust)",
        "This is a possible STROKE, not choking. Do NOT do abdominal thrusts.\n"
        "1. Get emergency medical help immediately, minutes matter.\n"
        "2. Note the exact time the symptoms started and tell the medics.\n"
        "3. Keep him still, seated or lying with head slightly raised.\n"
        "4. Do NOT give food, drink, or any medicine.\n"
        "5. If he becomes drowsy or vomits, turn him gently onto his side.",
        "Kjo mund të jetë GODITJE NË TRU, jo mbytje me ushqim. MOS bëj shtytje barku.\n"
        "1. Kërko menjëherë ndihmë mjekësore urgjente, çdo minutë ka rëndësi.\n"
        "2. Shëno orën e saktë kur nisën shenjat dhe tregojua mjekëve.\n"
        "3. Mbaje të qetë, ulur ose shtrirë me kokën pak të ngritur.\n"
        "4. MOS i jep ushqim, pije a ilaçe.\n"
        "5. Nëse përgjumet ose vjell, ktheje butë në krah.",
    ),
    "drowning": (
        r"heel of (your|the) (lower )?hand on (his|her|their|the) belly|belly.{0,40}upward push|push.{0,30}water out",
        "Keep them on their SIDE in the recovery position, do NOT push on the belly to force water out.\n"
        "1. Lay them on their side, head slightly back.\n"
        "2. Keep them warm and still; remove wet clothes.\n"
        "3. Watch their breathing constantly. If it stops, start CPR.\n"
        "4. Get them to medical care, every drowning patient needs to be checked.",
        "Mbaje në KRAH në pozicionin e shpëtimit, MOS ia shtyp barkun për të nxjerrë ujin.\n"
        "1. Shtrije në krah, me kokën pak prapa.\n"
        "2. Mbaje ngrohtë e të qetë; hiqi rrobat e lagura.\n"
        "3. Vëzhgo frymëmarrjen vazhdimisht. Nëse ndalon, fillo CPR.\n"
        "4. Çoje te mjeku, çdo i mbytur duhet kontrolluar.",
    ),
    "heart-attack": (
        r"epipen|epinephrine|adrenaline",
        "Call emergency help now. Keep him seated, calm and completely still.\n"
        "1. Loosen tight clothing; fresh air if possible.\n"
        "2. If he is fully alert and not allergic, he may slowly chew one aspirin.\n"
        "3. Do NOT give him anyone else's medication.\n"
        "4. Do not let him walk or exert himself. Stay with him.\n"
        "5. If he becomes unresponsive and stops breathing, start chest compressions.",
        "Thirr menjëherë ndihmën mjekësore. Mbaje ulur, të qetë e krejt të palëvizur.\n"
        "1. Liroji rrobat e ngushta; ajër i pastër nëse mundet.\n"
        "2. Nëse është plotësisht i vetëdijshëm dhe jo alergjik, mund të përtypë ngadalë një aspirinë.\n"
        "3. MOS i jep ilaçet e dikujt tjetër.\n"
        "4. Mos e lër të ecë a të lodhet. Rri me të.\n"
        "5. Nëse humb vetëdijen dhe i ndalon fryma, fillo shtypjet e gjoksit.",
    ),
    "rehydration": (
        r"\d/\d.{0,15}(teaspoon|tsp).{0,15}(salt|soda)",
        "Use the recipe above: 1 liter clean water + half a level teaspoon of salt + 8 level teaspoons of sugar.\n"
        "1. Taste it: no saltier than tears.\n"
        "2. Give small sips every few minutes, day and night, even if he vomits.\n"
        "3. Keep giving until he urinates normally.\n"
        "4. Keep offering food (and breast milk for babies).\n"
        "5. If he gets very sleepy, stops drinking, or has blood in the stool, get medical help now.",
        "Përdor recetën më sipër: 1 litër ujë i pastër + gjysmë lugë çaji kripë + 8 lugë çaji sheqer.\n"
        "1. Provoje: të mos jetë më e kripur se lotët.\n"
        "2. Jepi gllënjka të vogla çdo pak minuta, ditë e natë, edhe nëse vjell.\n"
        "3. Vazhdo derisa të urinojë normalisht.\n"
        "4. Vazhdo t'i japësh ushqim (dhe qumësht gjiri për foshnjat).\n"
        "5. Nëse bëhet shumë i përgjumur, nuk pi dot, ose ka gjak në jashtëqitje, kërko ndihmë mjekësore tani.",
    ),
    "fishbone": (
        r"stand behind|wrap your arms|abdominal thrust|heimlich|(back|shoulder) blows",
        "A stuck fish bone in someone who can breathe and talk is NOT choking, no back blows, no abdominal thrusts.\n"
        "1. Have them try a few sips of water or a bite of soft bread.\n"
        "2. Do not poke fingers or objects down the throat.\n"
        "3. If it does not pass, or pain, drooling or swallowing trouble grows, see a health worker.\n"
        "4. Emergency help only if they truly cannot breathe.",
        "Halë peshku e ngecur te dikush që merr frymë e flet NUK është mbytje, pa goditje shpine, pa shtytje barku.\n"
        "1. Le të provojë pak gllënjka ujë ose një kafshatë bukë të butë.\n"
        "2. Mos fut gishta a sende në fyt.\n"
        "3. Nëse nuk kalon, ose shtohet dhimbja, jargët a vështirësia në gëlltitje, shkoni te mjeku.\n"
        "4. Ndihmë urgjente vetëm nëse vërtet nuk merr dot frymë.",
    ),
    "nose-object": (
        r"stand behind|wrap your arms around|abdominal thrust|(back|shoulder) blows|heimlich",
        "This is a foreign object in the NOSE, not choking, no back blows, no abdominal thrusts.\n"
        "1. Have the child breathe calmly through the mouth.\n"
        "2. Do not poke anything into the nostril, it pushes the object deeper.\n"
        "3. Close the free nostril with a finger and have them blow out sharply several times.\n"
        "4. If the object does not come out, see a health worker the same day.\n"
        "5. Get urgent help only if they truly cannot breathe.",
        "Ky është një send në HUNDË, jo mbytje me ushqim, pa goditje shpine, pa shtytje barku.\n"
        "1. Le të marrë fëmija frymë i qetë me gojë.\n"
        "2. Mos fut asgjë në vrimën e hundës, e shtyn sendin më thellë.\n"
        "3. Mbylli me gisht vrimën e lirë dhe le të nxjerrë frymën fort disa herë.\n"
        "4. Nëse sendi nuk del, shkoni te mjeku brenda ditës.\n"
        "5. Kërko ndihmë urgjente vetëm nëse vërtet nuk merr dot frymë.",
    ),
    "tourniquet": (
        r"(^|\n)\s*(\d+\.\s*)?(yes[,.]?\s+)?(you\s+)?(should\s+|can\s+|may\s+|must\s+)?(loosen|release|remove|undo|take\s+(it\s+)?off)\b",
        "Do NOT loosen it. Keep the tourniquet in place until the person reaches medical care.\n"
        "1. Keep the tourniquet tight, do not release it even for a moment.\n"
        "2. Write down the time it was applied and tell the medical team.\n"
        "3. Keep the person warm and calm.\n"
        "4. Get the person to professional medical care as fast as possible.",
        "MOS e lironi. Mbajeni rripin shtr\u00ebngues t\u00eb vendosur derisa personi t\u00eb arrij\u00eb te kujdesi mjek\u00ebsor.\n"
        "1. Mbajeni rripin t\u00eb shtr\u00ebnguar, mos e lironi as p\u00ebr nj\u00eb moment.\n"
        "2. Sh\u00ebnoni or\u00ebn kur u vendos dhe tregojani ekipit mjek\u00ebsor.\n"
        "3. Mbajeni personin ngroht\u00eb dhe t\u00eb qet\u00eb.\n"
        "4. \u00c7ojeni personin te ndihma mjek\u00ebsore sa m\u00eb shpejt.",
    ),
}


# A specific rule suppresses a generic one whose advice would CONTRADICT it
# in that context (e.g. jellyfish says NO fresh water; burn says rinse with it).
_VETO = {
    "jellyfish": ("burn",),
    "high-sugar": ("diabetic",),
    "fishbone": ("choking",),
    "nose-object": ("choking",),
}
# The generic breathing-distress fallback ("get emergency help, back blows if
# choking, CPR if they stop") yields to rules that own the airway/positioning
# protocol or explicitly forbid thrusts, and to any rule whose own text already
# addresses the AIRWAY (CPR, back blows, "not breathing", recovery position).
# It still stacks on rules whose escalation is generic or conditional ("see a
# health worker today", "go urgently if there is bleeding": fever, burn,
# snakebite, hypothermia, poisoning, pregnancy), because there "can't breathe"
# would otherwise get no airway advice at all.
_AIRWAY_OWN = {
    "choking", "not-breathing", "anaphylaxis", "asthma", "panic", "chest-wound",
    "fishbone", "nose-object", "stroke", "seizure", "unconscious", "drowning",
    "spinal", "head-injury",
}
_ESCALATES = re.compile(r"\bCPR\b|chest compression|rescue breath|back blows|abdominal thrust"
                        r"|stops? breathing|not breathing|airway|recovery position", re.IGNORECASE)
_FALLBACK_YIELDS_TO = (_AIRWAY_OWN | {n for n, _, _, w_en, _ in RULES if _ESCALATES.search(w_en)}) - {"breathing-distress"}


def fired_rules(q_raw, q_en, is_sq):
    """Names of triggered rules (same matching as check())."""
    hay_en = (q_en or "").lower()
    hay_sq = (q_raw or "").lower()
    out = []
    for name, p_en, p_sq, w_en, w_sq in RULES:
        if re.search(p_en, hay_en, re.IGNORECASE) or \
           (is_sq and re.search(p_sq, hay_sq, re.IGNORECASE)):
            out.append(name)
    for k, vetoed in _VETO.items():
        if k in out:
            out = [n for n in out if n not in vetoed]
    if "breathing-distress" in out and any(n in _FALLBACK_YIELDS_TO for n in out):
        out = [n for n in out if n != "breathing-distress"]
    return out


def body_guard(names, resp_en, is_sq):
    """Return (body, replaced). Checks the ENGLISH body before translation."""
    for name in names:
        # anaphylaxis co-firing makes epinephrine advice CORRECT, so do not let
        # the heart-attack CONTRA strip it as if this were a plain cardiac case
        if name == "heart-attack" and "anaphylaxis" in names:
            continue
        if name in CONTRA:
            pat, safe_en, safe_sq = CONTRA[name]
            if re.search(pat, resp_en, re.IGNORECASE):
                return (safe_sq if is_sq else safe_en), True
    return resp_en, False


# Sentences that are dangerous AS WRITTEN (they contain their own negation
# of correct care) - removed wherever they appear, any rule context.
_SCRUB_NEG = [
    # the gap may cross a comma ONLY into a list continuation or aside ("do
    # not do anything, including CPR", "mouth-to-mouth, rescue breaths or
    # CPR", "not even CPR"); any other comma starts a new clause and ends it
    # ("do not give water, he needs CPR" / ", if he stops breathing start CPR")
    # ... a comma is crossed only into a continuation that deprecates CPR
    # ("as CPR may cause injury", "no CPR", "not CPR", "CPR will not help") or
    # lists it ("mouth to mouth or CPR"), never into one that orders it
    # ("if he stops breathing start CPR", "he needs CPR", "CPR can take time")
    r"\b(do not|don'?t|never|avoid|shouldn'?t|should not|no need to|it'?s not safe to|it is not safe to) (attempt|attempting|give|giving|start|starting|begin|beginning|do|doing|perform|performing|try|trying|continue|provide|initiate|administer)\b(?:[^.,;:!?\n]|,(?=\s*(?:including|especially|particularly|even\b|not even|not\b|no\b|never\b|or\b|nor\b|and even|such as|like\b|as\b|because\b|since\b|rescue breath|chest compression|mouth.to.mouth|breaths?\b|compressions?\b|artificial|first aid|cpr\s+(?:or|and|,|may|might|could|will not|won'?t|cannot|can'?t|is not|isn'?t|does not|doesn'?t|should not|shouldn'?t)))){0,60}\b(cpr|rescue breath|chest compression)",
    r"\bnot safe to (continue|keep)\b(?:[^.,;:!?\n]|,(?=\s*(?:release|remove|stop|loosen|take\b|let go|lift|ease|reduce|relieve|the pressure|pressure should|even\b|or\b|nor\b))){0,45}\bpressure\b",
    # the 3B model sometimes echoes the system prompt's own classification text
    r"\bEMERGENCY: an injury, illness\b",
    r"\bFollow ALL the emergency rules\b",
    r"^\s*(GENERAL|EMERGENCY)\s*:",
    r"^\s*CLASSIFICATION\s*:",
    r"^\s*(this is a )?(general|emergency) (question|message|situation)\b",
    r"\bI classify this (message|question)\b",
]
# Sentences dangerous UNLESS negated (e.g. "make him vomit" is bad; "do NOT
# make him vomit" is the correct advice and must survive).
# The object may be worded any way ("the injured person", "him or her", "an
# adult"), but the gap between the verb and the danger word must not run
# through a conditional, an auxiliary or a conjunction: "get medical help if
# he vomits", "on his side in case he vomits", "help him and do not make him
# vomit" are NOT instructions to make anyone vomit. The noun sense of help
# ("call for help") is excluded too.
_POS_GAP = (r"(?:(?!\b(?:if|in case|case|when|whenever|before|after|until|unless|should|might|may"
            r"|could|would|will|need|needs|needed|start|starts|started|begin|begins|began|want|wants"
            r"|going|about|does|doesn'?t|not|never|and|but)\b)[^.,;:\n]){0,35}?")
_NOT_NOUN_HELP = r"(?<!for )(?<!call )(?<!seek )(?<!get )(?<!medical )"
_SCRUB_POS = [
    _NOT_NOUN_HELP + r"\b(make|force|help|get)\s+(?!for\b)" + _POS_GAP + r"\b(?:vomit|throw up)",
    r"\binduce vomiting\b",
    r"\bstop the (birth|delivery|labou?r)\b",
    # after a fall with suspected fracture/spinal, models suggest standing
    # the person up against their own keep-still warning
    _NOT_NOUN_HELP + r"\bhelp(?:s|ed|ing)?\s+(?!for\b)" + _POS_GAP + r"\b(?:get|stand)\s+up\b",
    _NOT_NOUN_HELP + r"\bhelp(?:s|ed|ing)?\s+(?!for\b)" + _POS_GAP + r"\bto\s+(?:rise|stand)\b",
    # the model must never INITIATE a tourniquet (observed: advised one for
    # an infected wound); the bleeding/amputation rule texts cover legit use
    r"\bapply (a |the )?tourniquet\b",
    r"\bput (a |the )?tourniquet\b",
]
# Negation SCOPE. A dangerous phrase is protected only when a negation governs
# it. Applied to the text just before the phrase, the negation may be followed
# ONLY by things that stay inside its scope, each named explicitly:
#   * one parenthetical or bracket aside ("never, under any circumstances,
#     ..."; "do not (even if he asks) ...")
#   * an adverbial or -ly adverb ("do not ever ...", "do not forcibly ...",
#     "in no case should you ...", "do not at this stage ...")
#   * a bridge that keeps the negation on the verb ("do not need to ...",
#     "not a good idea to ...", "do NOT try and ...")
#   * a purpose infinitive ("do not use salt water TO induce vomiting", "never
#     use your fingers TO make him vomit")
#   * a short "or" coordination ("do not give salt water or make him vomit")
# Anything else ends the scope: a comma clause ("do not panic, make him
# vomit"), a conditional or subordinate clause ("if he is not unconscious
# make ...", "... until you make ..."), a predicate that flips the meaning
# ("not too late to ...", "not difficult to ...", "except to ...") and
# hesitation idioms ("do not hesitate/wait/delay ... to", "never give up
# trying to"). A bare answer-word "No," is not a negation.
# Shared with the obsolete-doctrine filters in ingest.py and retrieval.py.
NEG_ATTACHED = re.compile(
    r"\b(?:do not|don'?t|never|avoid|should ?not|shouldn'?t|must ?not|mustn'?t|cannot|can'?t"
    r"|not|nothing|no need to|no reason to|need not|needn'?t|unsafe to|rather than|instead of"
    r"|under no circumstances|in no case|on no account|at no point|by no means)\b"
    r"(?:\s*,\s*(?:ever|even|please|now|however|though|i repeat)\b)?"
    r"(?:"
    r"\s*[,—–-]\s*[^,—–-]{0,40}\s*[,—–-]"
    r"|\s*\([^)]{0,40}\)"
    r"|\s+(?:ever|even|please|now|immediately|yourself|yourselves|at all|at any point|at any time"
    r"|at this (?:stage|point|time)|in this (?:case|situation)|for now|right now|yet|here|today"
    r"|under any circumstances|in any case|for any reason|whatever happens|no matter what"
    r"|on your own|by yourself|first|also|either|really|actually|deliberately|intentionally"
    r"|should you|must you|may you|can you|could you)\b"
    r"|\s+(?!(?:only|simply|merely|early|rely|apply|reply|supply|comply|imply|multiply|belly|jelly"
    r"|bully|family|likely|unlikely|holy|ugly|ally|rally|tally|fly)\b)\w{3,}ly\b"
    r"|\s+(?:try and|try to|trying to|attempt to|attempt and|attempting to|want to|wish to|need to|have to|has to"
    r"|be tempted to|be tempted into|be able to|be allowed to|dare to|dare|try|attempt|even think about|think about"
    r"|(?:a )?good idea to|(?:a )?good plan to|advisable to|safe to|recommended to|wise to|sensible to|necessary to"
    r"|right to|okay to|ok to|allowed to|supposed to|meant to|going to|expected to|acceptable to|appropriate to"
    r"|helpful to|useful to|possible to)\b"
    r"|\s+(?!(?:hesitate|hesitating|wait|waiting|forget|fail|delay|neglect|refuse|stop|afraid|scared"
    r"|be afraid|be scared|give up|too|difficult|hard|easy|impossible|late|early|wrong|unusual|uncommon"
    r"|rare|unable|ready|enough|sufficient|sure|certain)\b)(?:\w+\s+){0,6}?(?<!\bexcept )(?<!\bbut )(?<!\bonly )to\b"
    r"|\s+(?!(?:wait|hesitate|delay|stop|sure|certain)\b)(?:\w+\s+){0,7}?(?:or|nor)\b"
    r"){0,6}"
    r"\s*$", re.IGNORECASE)


def _has_unnegated_danger(sent):
    """True if the sentence carries a dangerous imperative that no negation
    governs (see NEG_ATTACHED)."""
    for p in _SCRUB_POS:
        for m in re.finditer(p, sent, re.IGNORECASE):
            if not NEG_ATTACHED.search(sent[:m.start()]):
                return True
    return False


def danger_scrub(resp_en):
    """Drop sentences that contradict life-safety practice (observed model
    failures: 'do not attempt CPR', 'make him vomit' outside poison context,
    'stop the birth', 'not safe to continue applying pressure')."""
    out = []
    for sent in re.split(r"(?<=[.!?\n])", resp_en or ""):
        if any(re.search(p, sent, re.IGNORECASE) for p in _SCRUB_NEG):
            continue
        if _has_unnegated_danger(sent):
            continue
        out.append(sent)
    # collapse consecutive duplicate sentences (model repetition loops)
    dedup, prev = [], None
    for s in out:
        key = s.strip()
        if key and key == prev:
            continue
        prev = key or prev
        dedup.append(s)
    return re.sub(r"\n{3,}", "\n\n", "".join(dedup)).strip()


MED_PATTERN = re.compile(
    r"ampicillin|tetracycl|co-?trimoxazole|sulfonamide|penicillin|ciprofloxacin"
    r"|amoxicillin|erythromycin|metronidazole|doxycycline"
    r"|\bantibiotics?\b|antibiotik\w*"
    r"|antihistamin\w*|promethazin\w*|prometazin\w*|phenergan|fenergan"
    r"|dimenhydrinat\w*|dimenhidrinat\w*|diazepam|codeine|kodein\w*", re.IGNORECASE)
MED_CAUTION_EN = ("WARNING: Do not take prescription medicines without advice "
                  "from a health worker, the wrong drug or dose can cause harm.")
MED_CAUTION_SQ = ("KUJDES: Mos merrni ilaçe me recetë pa këshillën e një punonjësi "
                  "shëndetësor, ilaçi ose doza e gabuar mund të dëmtojë.")


def med_caution(resp_en):
    """True if the English body names prescription antibiotics."""
    return bool(MED_PATTERN.search(resp_en or ""))


def check(q_raw, q_en, is_sq):
    """Return the list of triggered warnings in the output language."""
    names = set(fired_rules(q_raw, q_en, is_sq))
    return [(w_sq if is_sq else w_en)
            for name, p_en, p_sq, w_en, w_sq in RULES if name in names]


if __name__ == "__main__":
    cases = [
        ("my father collapsed and he is not breathing what do i do", None, False, ["not-breathing"]),
        ("my childs clothes caught fire and her arm is badly burned", None, False, ["burn"]),
        ("my brother got stung by a wasp his face is swelling", None, False, ["anaphylaxis"]),
        ("there is a knife stuck in my leg should i pull it out", None, False, ["impaled"]),
        ("he fell from a tree his neck hurts and he cant move his legs", None, False, ["spinal"]),
        ("my daughter swallowed poison should i make her vomit", None, False, ["poison"]),
        ("my friend is unconscious should i give him water", None, False, ["unconscious"]),
        ("shoku im eshte pa ndjenja a duhet ti jap uje", "My friend is unconscious. Should I give him water?", True, ["unconscious"]),
        ("gjarpri me kafshoi ne kembe cfare te bej", "the snake bit me on the foot what to do", True, ["snakebite"]),
        ("femija u dogj me uje te valuar cfare te bej", "The baby was burned with water. What should I do?", True, ["burn"]),
        ("should i loosen the tourniquet", None, False, ["tourniquet"]),
        ("i have a headache", None, False, []),
        ("me dhemb koka", "my head hurts", True, []),
        # 2026-08-31 long-eval misses - colloquial diacritic-free forms:
        ("me kafshoi gjarpri ne mal cfare bej tani", "x", True, ["snakebite"]),
        ("ra nga pema dhe nuk i ndjen kembet fare", "x", True, ["spinal"]),
        ("po dridhet i teri me shkume ne goje dhe nuk ndalon", "x", True, ["seizure"]),
        ("e kapi korrenti ne shtepi dhe eshte ende i kapur pas telit", "x", True, ["electrical"]),
        ("me ka rene nje dhemb nga nje goditje ne fytyre", "x", True, ["dental"]),
        ("u nxeh shume ne diell i vjen rrotull dhe nuk djersit fare", "x", True, ["heatstroke"]),
        ("djali piu gaz ndricues pa dashje a ta bej te vjelle", "x", True, ["poison"]),
        ("me rrjedh shume gjak nga kemba dhe nuk ndalon", "x", True, ["bleeding"]),
        ("po me del gjak nga hundet qe prej gjysme ore", "x", True, []),
        ("e gjetem ne mal te ftohte akull dridhet i teri dhe flet me veshtiresi", "x", True, ["hypothermia"]),
        ("me pickoi akrepi ne dore naten", "x", True, ["anaphylaxis"]),
        # round 7: burn rule must not fire on urination burning
        ("me djeg kur urinoj", "it burns when i urinate", True, []),
        ("it burns when i urinate", None, False, []),
        ("u dogja me vaj te nxehte ne dore", "x", True, ["burn"]),
        # round 8: four new rules + extended patterns
        ("u rrezua me biciklete dhe i doli gjak nga koka", "x", True, ["head-injury"]),
        ("me sperkati zbardhues ne sy", "x", True, ["chemical-eye"]),
        ("ka astme dhe i ka mbaruar pompa nuk merr dot fryme", "x", True, ["asthma"]),
        ("na dhemb koka te gjitheve dhe kemi soben ndezur", "x", True, ["carbon-monoxide"]),
        ("gishtat e kembeve i ka te bardhe dhe te ngrire nga bora", "x", True, ["hypothermia"]),
        ("gjyshja u rrezua dhe nuk ngrihet dot i dhemb vithja", "x", True, ["fracture"]),
        ("me hoqen dhembin dhe nuk po ndalon gjaku", "x", True, ["dental", "bleeding"]),
        ("me ra acid ne krah", "x", True, ["burn"]),
        ("femija ka futur nje kokerr fasule ne hunde", "x", True, ["nose-object"]),
        # round 9: five new rules + extended patterns
        ("i ka prere sharra dy gishta cfare bejme me gishtat", "x", True, ["amputation"]),
        ("ka nje plage ne gjoks qe fishkellen kur merr fryme", "x", True, ["chest-wound"]),
        ("gruaja shtatzene ka gjakderdhje", "x", True, ["pregnancy-bleeding"]),
        ("foshnja dy muajshe ka diarre qe dje", "x", True, ["rehydration", "infant-sick"]),
        ("djali ka dhimbje te forte te herdhet qe erdhi papritur", "x", True, ["testicle-pain"]),
        ("e harruam femijen ne makine ne diell", "x", True, ["heatstroke"]),
        ("i ka dale nje cope kocke nga plaga e kembes", "x", True, ["fracture"]),
        ("te gjithe kemi te vjella pasi hengrem mish ne dasme", "x", True, ["rehydration"]),
        ("i ka zene dora te presa dhe e ka krejt te shtypur", "x", True, ["fracture"]),
        # round 10: six new rules + dialect/regression fixes
        ("e gjetem te varur ne litar cfare bejme", "x", True, ["hanging"]),
        ("i ka ngecur nje hale peshku ne fyt", "x", True, ["fishbone"]),
        ("shkeli ne gozhde te ndryshkur ne oborr", "x", True, ["rusty-nail"]),
        ("i ka ngecur unaza ne gisht dhe gishti po enjtet", "x", True, ["stuck-ring"]),
        ("i eshte ngjitur nje shushunje ne kembe", "x", True, ["leech"]),
        ("hengri kerpudha te egra dhe tani ka dhimbje barku", "x", True, ["poison", "mushroom"]),
        ("po i bie pika nuk leviz dot krahun e djathte", "x", True, ["stroke"]),
        ("u perzhit me hekur duke hekurosur", "x", True, ["burn"]),
        ("femija u skuq keq nga dielli ne plazh", "x", True, ["burn"]),
        ("e theri bleta ne qafe dhe po i skuqet", "x", True, ["anaphylaxis"]),
        # 2026-09-02 full recheck: reworded-form misses
        ("djalit i dhembin herdhet papritur shume forte", "x", True, ["testicle-pain"]),
        ("me hoqen dhembin dhe s ndalon gjaku", "x", True, ["dental", "bleeding"]),
        # round 11: folk-myth traps, run-ons, false-positive probes
        ("ndihme ju lutem djali im 3 vjec ra nga shkallet dhe tani po vjell dhe nuk mban syte hapur cfare te bej ju lutem shpejt",
         "x", True, ["spinal", "head-injury"]),
        ("burri im u dogj ne dore me vaj dhe nga paniku i ra te fiket", "x", True, ["unconscious", "burn"]),
        ("po i bie pika a duhet ti hap gojen me luge", "x", True, ["seizure", "stroke"]),
        ("femijes i hipen temperatura dhe filloi te dridhej i teri", "x", True, ["fever", "seizure"]),
        ("me digjet gjoksi pas ngrenies", "x", True, []),
        ("nena ime piu shume hape gjumi dhe nuk zgjohet", "x", True, ["unconscious", "poison"]),
        ("i ka hyre nje mize ne vesh dhe degjon zhurme", "x", True, ["ear-insect"]),
        # round 12: distinct hazards + first-person/alone scenarios
        ("femija ka gelltitur nje bateri te vogel te rrumbullaket ore", "x", True, ["poison", "button-battery"]),
        ("gruaja shtatzene u rrezua ne shkalle", "x", True, ["spinal", "pregnancy-fall"]),
        ("plaga me eshte nxire dhe vjen ere e keqe", "x", True, ["wound-infection"]),
        ("me ka zene paniku nuk marr dot fryme jam vetem", "x", True, ["panic"]),
        ("femija hengri cigare nga paketa", "x", True, ["poison"]),
        ("gjyshja piu dy here ilacet e zemres sot", "x", True, ["poison"]),
        ("me shkoi gjilpera ne dore duke qepur", "x", True, ["rusty-nail"]),
        # round 13: scenario depth
        ("diabetiku ka sheqer te larte 400 dhe i vjen era aceton nga goja", "x", True, ["high-sugar"]),
        ("e goditi topi ne sy dhe tani nuk sheh mire", "x", True, ["eye-injury"]),
        ("me dogji kandili i detit ne plazh", "x", True, ["jellyfish"]),
        ("shkela mbi iriq deti dhe me kane mbetur gjembat ne kembe", "x", True, ["sea-urchin"]),
        ("djalit i zune krampet ne kembe duke luajtur futboll ne vape", "x", True, ["heat-cramps"]),
        ("me ka rene pika e diellit", "x", True, ["heatstroke"]),
        ("gjyshit i ngeci ilaci ne fyt dhe s po kalon", "x", True, ["fishbone"]),
        ("beme aksident me makine dhe shoferi ka gjak ne koke por flet", "x", True, ["spinal", "head-injury"]),
        # 2026-09-17 code-review fixes: airway phrasings + burn-when-accident
        ("he swallowed a piece of meat and cannot breathe", None, False, ["choking"]),
        ("the baby suddenly cant breathe and is turning blue", None, False, ["breathing-distress"]),
        ("my son got burned when he touched the hot stove", None, False, ["burn"]),
        # regression-review fixes: fallback must yield, choking needs food/object
        # context, burn must still exempt urination slang, "fit" needs seizure context
        ("my son is having a seizure and his lips are turning blue", None, False, ["seizure"]),
        ("she swallowed poison and can't breathe", None, False, ["poison", "breathing-distress"]),
        ("it burns when i piss", None, False, []),
        ("it burns when i go to the bathroom", None, False, []),
        ("he is having fits and foaming at the mouth", None, False, ["seizure"]),
        ("does this shirt fit me", None, False, []),
        # second regression review: choking must keep real obstruction cases,
        # the fallback must still escalate where nothing else does, "fit" and
        # "bathroom" must not over-exempt
        ("he swallowed something and can't breathe", None, False, ["choking"]),
        ("my son swallowed a marble and cannot breathe", None, False, ["choking"]),
        ("meat stuck in his throat, he can't breathe", None, False, ["choking"]),
        ("a piece of meat is stuck and he cannot breathe", None, False, ["choking"]),
        ("my child has had a high fever for 3 days and now is struggling to breathe", None, False, ["fever", "breathing-distress"]),
        ("my son just had another fit", None, False, ["seizure"]),
        ("she is having a violent fit", None, False, ["seizure"]),
        ("the shoes fit and are comfortable", None, False, []),
        ("I got a chemical burn when I was cleaning the bathroom with bleach", None, False, ["burn"]),
        # third regression review: "fit" as a noun in lay phrasing, choking must
        # not fire on non-obstruction "swallowed", poison catches hydrocarbons,
        # urination slang keeps the burn exemption, fallback yields to positioning
        ("my son had a fit in the car and is now very sleepy", None, False, ["seizure"]),
        ("she had a fit that lasted five minutes", None, False, ["seizure"]),
        ("febrile fit in a toddler", None, False, ["seizure"]),
        ("she has fits in her sleep", None, False, ["seizure"]),
        ("the mask does not fit", None, False, []),
        ("is he fit to travel", None, False, []),
        ("one size fits all", None, False, []),
        ("the splint must fit tightly", None, False, []),
        ("my brother is having a seizure i think he swallowed his tongue and can't breathe", None, False, ["seizure"]),
        ("she swallowed paraffin and can't breathe", None, False, ["poison", "breathing-distress"]),
        ("it burns when i use the bathroom", None, False, []),
        ("burns when using the toilet", None, False, []),
        ("it burns when i go to toilet", None, False, []),
        ("it burns when i sit on the toilet", None, False, []),
        ("pregnant, bleeding and can't breathe", None, False, ["breathing-distress", "pregnancy-bleeding"]),
        # fourth regression review: ordinary medication is not poisoning, the
        # fallback must still escalate where the rule text does not, lay
        # seizure phrasing, real bathroom burns, choking objects with adjectives
        ("my mother is diabetic, she took her tablets this morning but did not eat and now she is confused and sweating", None, False, ["diabetic"]),
        ("my diabetic father took his medicine and now is dizzy and sweaty", None, False, ["diabetic"]),
        ("he took his medicine as prescribed and now has a rash", None, False, []),
        ("she took too many pills", None, False, ["poison"]),
        ("a snake bit him and now he can't breathe", None, False, ["snakebite", "breathing-distress"]),
        ("pregnant woman fell down the stairs and now she can't breathe", None, False, ["breathing-distress", "pregnancy-fall"]),
        ("found him freezing in the snow and gasping", None, False, ["breathing-distress", "hypothermia"]),
        ("the fit has stopped but he is not waking up", None, False, ["seizure"]),
        ("the fit lasted two minutes", None, False, ["seizure"]),
        ("his last fit was yesterday", None, False, ["seizure"]),
        ("a long fit", None, False, ["seizure"]),
        ("a two minute fit", None, False, ["seizure"]),
        ("each fit lasts a minute", None, False, ["seizure"]),
        ("this fit was worse", None, False, ["seizure"]),
        ("he might fit again", None, False, ["seizure"]),
        ("went into a fit", None, False, ["seizure"]),
        ("it fits", None, False, []),
        ("i bought a mask and it fits", None, False, []),
        ("the shoe fits", None, False, []),
        ("the splint must fit tightly", None, False, []),
        ("I got a chemical burn when I used the toilet cleaner without gloves", None, False, ["burn"]),
        ("burn when using the bathroom cleaner", None, False, ["burn"]),
        ("my child got a burn when he was in the bathroom", None, False, ["burn"]),
        ("i got a burn when i used the bathroom heater", None, False, ["burn"]),
        ("my son got burns when playing in the bathroom", None, False, ["burn"]),
        ("he swallowed a chicken bone and can't breathe", None, False, ["choking"]),
        ("he swallowed a big piece of meat and can't breathe", None, False, ["choking"]),
        ("she swallowed a whole grape and can't breathe", None, False, ["choking"]),
        ("my son swallowed a small toy and can't breathe", None, False, ["choking"]),
        ("my son swallowed a small coin and can't breathe", None, False, ["choking"]),
        ("he swallowed a hot dog and can't breathe", None, False, ["choking"]),
        ("the baby swallowed a plastic bag and can't breathe", None, False, ["choking"]),
        ("the toddler swallowed a part of the toy and can't breathe", None, False, ["choking"]),
        ("he swallowed one of his toys and can't breathe", None, False, ["choking"]),
    ]
    ok = True
    for raw, en, is_sq, expect in cases:
        got = check(raw, en if en else raw, is_sq)
        names = [RULES[i][0] for i in range(len(RULES))
                 if (RULES[i][4] if is_sq else RULES[i][3]) in got]
        status = "OK " if names == expect else "FAIL"
        if names != expect: ok = False
        print("%s %-55s -> %s (want %s)" % (status, raw[:55], names, expect))
    # danger_scrub: removes the inverted advice, keeps the negated-safe advice
    s1 = danger_scrub("Lay them down. Do not attempt rescue breaths or CPR if the person does not respond. Keep them warm.")
    s2 = danger_scrub("Do NOT make them vomit. Give nothing by mouth.")
    s3 = danger_scrub("If he cannot drink, try to make him vomit by turning him on his side.")
    s4 = danger_scrub("Check her over. Help grandma to get up slowly. Keep her warm.")
    s5 = danger_scrub("Do not panic, make him vomit to bring up the poison.")
    s6 = danger_scrub("You should not start CPR on this person. Keep them warm.")
    s7 = danger_scrub("Is it safe to wait? No, but make him vomit right away.")
    s8 = danger_scrub("Call for help now. Induce vomiting only if the person is not unconscious. Keep them warm.")
    s9 = danger_scrub("Never, under any circumstances, apply a tourniquet to a snakebite. Keep him still.")
    s10 = danger_scrub("Do not do abdominal thrusts if they are breathing; start CPR if they stop breathing.")
    for label, got, want_gone, want_kept in (
            ("scrub-negCPR", s1, "attempt rescue", "Keep them warm"),
            ("scrub-safe-vomit-kept", s2, None, "NOT make them vomit"),
            ("scrub-bad-vomit-gone", s3, "make him vomit", ""),
            ("scrub-standup-gone", s4, "get up", "Keep her warm"),
            ("scrub-neg-shield-clause", s5, "make him vomit", None),
            ("scrub-should-not-cpr", s6, "start CPR", "Keep them warm"),
            ("scrub-question-split", s7, "make him vomit", "Is it safe to wait"),
            ("scrub-midbody-emesis", s8, "Induce vomiting", "Keep them warm"),
            ("scrub-parenthetical-negation-kept", s9, None, "apply a tourniquet"),
            ("scrub-cpr-after-semicolon-kept", s10, None, "start CPR")):
        bad = (want_gone and want_gone in got) or (want_kept and want_kept not in got)
        if bad: ok = False
        print("%s %s" % ("FAIL" if bad else "OK ", label))
    # Negation-scope corpus from the 2026-09-17 regression reviews. BOTH
    # directions matter: a correct prohibition must survive, a dangerous
    # imperative must go. Add a case here for every scrub change.
    scope_cases = (
        # kept: the negation governs the phrase
        ("keep-or-coordination", "Do not give salt water or make him vomit.", None, "make him vomit"),
        ("keep-or-getup", "Do not move him or help him get up.", None, "help him get up"),
        ("keep-or-stand", "Do not move the person or help them to stand.", None, "help them to stand"),
        ("keep-or-tourniquet", "Do not cut the wound or apply a tourniquet.", None, "apply a tourniquet"),
        ("keep-or-venom", "Do not suck out the venom or apply a tourniquet.", None, "apply a tourniquet"),
        ("keep-no-need", "There is no need to make him vomit.", None, "make him vomit"),
        ("keep-do-not-need", "You do not need to make him vomit.", None, "make him vomit"),
        ("keep-not-good-idea", "It is not a good idea to make him vomit.", None, "make him vomit"),
        ("keep-adverbial", "Do not under any circumstances make him vomit.", None, "make him vomit"),
        ("keep-dash-parenthetical", "Never - under any circumstances - make him vomit.", None, "make him vomit"),
        ("keep-try-and", "Do NOT try and make him vomit.", None, "make him vomit"),
        ("keep-however", "Do not, however, make him vomit.", None, "make him vomit"),
        ("keep-never-ever", "You should never, ever make him vomit.", None, "make him vomit"),
        ("keep-but-never", "Do not hesitate to call for help, but never make him vomit.", None, "never make him vomit"),
        ("keep-no-never", "No, never make him vomit.", None, "never make him vomit"),
        # gone: no negation governs the phrase
        ("gone-answer-no-if", "No, if he is awake, make him vomit.", "make him vomit", None),
        ("gone-answer-no-please", "No, please, make him vomit right away.", "make him vomit", None),
        ("gone-answer-no-now", "No, now make him vomit.", "make him vomit", None),
        ("gone-comma-clause", "Do not panic, make him vomit to bring up the poison.", "make him vomit", None),
        ("gone-delay-and", "Do not delay and make him vomit.", "make him vomit", None),
        ("gone-hesitate", "Do not hesitate to make him vomit.", "make him vomit", None),
        ("gone-wait-to", "Do not wait to make him vomit.", "make him vomit", None),
        ("gone-no-time", "If there is no time, make him vomit.", "make him vomit", None),
        ("gone-no-time-getup", "There is no time to lose, help him get up and walk.", "get up", None),
        ("gone-midbody-emesis", "Induce vomiting only if the person is not unconscious.", "Induce vomiting", None),
        # CPR inversions across a list or aside are still caught ...
        ("gone-cpr-including", "Do not do anything, including CPR, until help arrives.", "including CPR", None),
        ("gone-cpr-list", "Do not perform mouth-to-mouth, rescue breaths or CPR.", "rescue breaths", None),
        ("gone-cpr-not-even", "Do not try anything, not even CPR.", "even CPR", None),
        ("gone-pressure-release", "It is not safe to continue, release the pressure.", "release the pressure", None),
        # ... while a new clause that correctly starts CPR survives
        ("keep-cpr-semicolon", "Do not do abdominal thrusts if they are breathing; start CPR if they stop breathing.", None, "start CPR"),
        ("keep-cpr-keep-going", "Do not give up, keep doing CPR.", None, "keep doing CPR"),
        ("keep-cpr-then", "Do not do anything until you check for breathing, then start CPR.", None, "then start CPR"),
        # third review: conditional/subordinate clauses and predicates flip the
        # meaning, so these must still go ...
        ("gone-not-too-late", "It is not too late to make him vomit.", "make him vomit", None),
        ("gone-if-not-unconscious", "If he is not unconscious make him vomit.", "make him vomit", None),
        ("gone-before-you", "Do not give him anything to drink before you make him vomit.", "make him vomit", None),
        ("gone-until-you", "Do not give him milk until you make him vomit.", "make him vomit", None),
        ("gone-never-give-up", "Never give up trying to make him vomit.", "make him vomit", None),
        ("gone-cannot-control", "If you cannot control the bleeding apply a tourniquet above the wound.", "apply a tourniquet", None),
        ("gone-cannot-walk", "If he cannot walk help him get up and carry him.", "help him get up", None),
        ("gone-cannot-reach", "If you cannot reach a hospital stop the birth.", "stop the birth", None),
        ("gone-not-difficult", "It is not difficult to make him vomit.", "make him vomit", None),
        ("gone-except-to", "Do not give anything by mouth except to make him vomit.", "make him vomit", None),
        # ... the dangerous phrase is caught however the object is worded ...
        ("gone-injured-person", "Make the injured person vomit right away.", "vomit", None),
        ("gone-poisoned-person", "You should make the poisoned person vomit.", "vomit", None),
        ("gone-him-or-her", "Make him or her vomit.", "vomit", None),
        ("gone-him-try-to", "Make him try to vomit.", "vomit", None),
        ("gone-an-adult", "Make an adult vomit by giving salt water.", "vomit", None),
        ("gone-force-vomiting", "Force vomiting by putting a finger down his throat.", "vomiting", None),
        ("gone-2-year-old", "Make the 2 year old vomit.", "vomit", None),
        ("gone-elderly-getup", "Help the elderly man to get up.", "get up", None),
        ("gone-injured-standup", "Help the injured person stand up.", "stand up", None),
        ("gone-friend-getup", "Help your injured friend get up.", "get up", None),
        ("gone-old-man-stand", "Help the old man to stand.", "to stand", None),
        # ... while these correct prohibitions survive ...
        ("keep-force-or", "Do not force or make him vomit.", None, "make him vomit"),
        ("keep-ever", "Do not ever make him vomit.", None, "make him vomit"),
        ("keep-must-not-paren", "You must not, under any circumstances, apply a tourniquet.", None, "apply a tourniquet"),
        ("keep-let-sleep-or", "Do not let him sleep or make him vomit.", None, "make him vomit"),
        ("keep-i-repeat", "Do not, I repeat, do not make him vomit.", None, "make him vomit"),
        ("keep-under-no-circumstances", "Under no circumstances make him vomit.", None, "make him vomit"),
        ("keep-in-no-case", "In no case should you make him vomit.", None, "make him vomit"),
        ("keep-bracket-aside", "Do not (even if he asks) make him vomit.", None, "make him vomit"),
        # ... and a comma clause that correctly starts CPR / keeps pressure survives
        ("keep-cpr-if-stops", "Do not give him anything to drink, if he stops breathing start CPR.", None, "start CPR"),
        ("keep-cpr-just-start", "Do not try to feel for a pulse, just start CPR.", None, "start CPR"),
        ("keep-cpr-he-needs", "Do not give water, he needs CPR.", None, "needs CPR"),
        ("keep-cpr-can-take", "Do not give up, CPR can take a long time.", None, "CPR can take"),
        ("keep-cpr-is-needed", "Do not try to wake him, CPR is needed now.", None, "CPR is needed"),
        ("keep-cpr-you-must", "Do not attempt to move him, if he stops breathing you must start CPR.", None, "start CPR"),
        ("keep-cpr-begin", "Do not give him anything, if he is unresponsive begin CPR.", None, "begin CPR"),
        ("keep-pressure-apply", "It is not safe to keep waiting, apply firm pressure and go.", None, "apply firm pressure"),
        ("keep-pressure-maintain", "It is not safe to keep him here, maintain pressure while moving.", None, "maintain pressure"),
        # fourth review: a conditional "if/in case he vomits" is not an
        # instruction, and a negation after "and" governs the later verb ...
        ("keep-escalate-if-vomits", "Get medical help immediately if he vomits, becomes confused or drowsy.", None, "if he vomits"),
        ("keep-side-in-case", "Make sure he is on his side in case he vomits.", None, "in case he vomits"),
        ("keep-help-side-in-case", "Help him onto his side in case he vomits.", None, "in case he vomits"),
        ("keep-doctor-if-vomits", "Get him to a doctor if he vomits.", None, "if he vomits"),
        ("keep-help-if-vomits", "Get help if she vomits.", None, "if she vomits"),
        ("keep-lean-forward", "Help him lean forward if he needs to vomit.", None, "needs to vomit"),
        ("keep-get-help-and-do-not", "Get medical help and do not make him vomit.", None, "do not make him vomit"),
        ("keep-help-and-do-not", "Help him and do not make him vomit.", None, "do not make him vomit"),
        ("keep-lie-down-do-not-get-up", "Help him lie down and do not let him get up.", None, "do not let him get up"),
        ("keep-sit-up-do-not-stand", "Help her sit up but do not let her stand up.", None, "do not let her stand up"),
        ("gone-get-him-to-vomit", "Get him to vomit right away.", "vomit", None),
        ("gone-help-child-to-vomit", "Help the poisoned child to vomit.", "vomit", None),
        # ... CPR inversions with any deprecating continuation are caught ...
        ("gone-cpr-as-may", "Do not attempt to revive her, as CPR may cause further injury.", "CPR may", None),
        ("gone-cpr-because", "Do not attempt to revive her, because CPR could injure her.", "CPR could", None),
        ("gone-cpr-will-not", "Do not try to revive him, CPR will not help.", "will not help", None),
        ("gone-cpr-no", "Do not attempt anything, no CPR.", "no CPR", None),
        ("gone-cpr-never", "Do not attempt anything, never CPR.", "never CPR", None),
        ("gone-cpr-not-not", "Do not do anything, not CPR, not breaths.", "not CPR", None),
        ("gone-cpr-mouth-to-mouth", "Do not attempt resuscitation, mouth to mouth or CPR.", "or CPR", None),
        ("gone-cpr-breaths-or", "Do not attempt mouth to mouth, breaths or CPR.", "or CPR", None),
        ("gone-cpr-compressions-or", "Do not attempt breathing for him, compressions or CPR.", "or CPR", None),
        ("gone-cpr-particularly", "Do not attempt anything, particularly CPR.", "particularly CPR", None),
        ("gone-pressure-take-off", "It is not safe to keep pressing, take the pressure off.", "pressure off", None),
        ("gone-pressure-reduce", "It is not safe to keep pressing, reduce the pressure.", "reduce the pressure", None),
        ("gone-pressure-relieve", "It is not safe to keep pressing, relieve the pressure.", "relieve the pressure", None),
        ("gone-pressure-released", "It is not safe to keep pressing, the pressure should be released.", "released", None),
        # ... a purpose infinitive or adverb stays inside the negation ...
        ("keep-forcibly", "Do not forcibly induce vomiting.", None, "induce vomiting"),
        ("keep-finger-to-make", "Do not put your finger down his throat to make him vomit.", None, "make him vomit"),
        ("keep-ipecac-to-make", "Do not use ipecac to make him vomit.", None, "make him vomit"),
        ("keep-belly-to-stop", "Do not push on the belly to stop the birth.", None, "stop the birth"),
        ("keep-allow-anyone-to", "Do not allow anyone to apply a tourniquet.", None, "apply a tourniquet"),
        ("keep-at-this-stage", "Do not at this stage make him vomit.", None, "make him vomit"),
        # ... but hesitation before "or" does not
        ("gone-wait-or", "Do not wait or make him vomit.", "make him vomit", None),
        ("gone-not-sure-whether", "I am not sure whether to wait or make him vomit.", "make him vomit", None),
    )
    for label, text, want_gone, want_kept in scope_cases:
        got = danger_scrub(text)
        bad = (want_gone and want_gone in got) or (want_kept and want_kept not in got)
        if bad: ok = False
        print("%s %s" % ("FAIL" if bad else "OK ", label))
    print("ALL PASS" if ok else "FAILURES PRESENT")
