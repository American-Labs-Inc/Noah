# The safety layer (medical branch)

Noah is a general assistant, but when a question is a genuine medical or first aid one, it goes to a grounded branch guarded by a deterministic layer in [`safety.py`](../software/safety.py) that sits between the model and a person in an emergency. This layer runs only for medical questions, so everyday questions never touch it. It was built the hard way across **13 rounds of adversarial testing**, with hundreds of Albanian and English questions and every failure fixed and locked down with a regression test. It is a safety feature we kept, not the point of the product.

## Layers

1. **50 rules.** Each rule is `(name, english_pattern, albanian_pattern,
   english_warning, albanian_warning)`. Patterns run over both the raw
   question and its translation; a hit prepends a pre-written warning block
   before anything the model says. Coverage includes CPR/not-breathing,
   choking (with an explicit "coughing = don't interfere" clause), stroke
   (incl. folk idioms), poisoning (chemicals, pills, mushrooms, cigarettes,
   button batteries), bleeding, tourniquets, burns (thermal/chemical/sun),
   anaphylaxis, spinal, head injury, seizures, febrile seizures, diabetic
   low AND high sugar, hypothermia, frostbite, heatstroke, heat cramps,
   carbon monoxide, hanging, drowning, chest wounds, amputation, pregnancy
   (bleeding and falls), infants, testicular torsion, eye injuries (blunt
   and chemical), jellyfish, sea urchins, panic attacks, and more.
2. **9 CONTRA bodies.** For failure modes where the model was observed
   *commanding* the forbidden action (loosen the tourniquet, make them
   vomit, Heimlich for a stroke or a nose object), the entire model answer
   is replaced by a pre-written safe answer.
3. **danger_scrub.** Sentence-level deletion of known-dangerous model output
   regardless of context: negated-CPR advice, non-negated "make him vomit",
   "stop the birth", model-initiated tourniquets, "help them stand up"
   after falls, prompt echoes, plus a repetition-loop collapse.
4. **Veto map.** A specific rule silences a generic one that contradicts it.
   For example jellyfish beats burn (sea water, not fresh water), ketoacidosis
   beats hypoglycemia (no sugar, not give sugar), and a fishbone or an object in
   the nose beats choking.
5. **Medication caution.** Any answer naming prescription drugs gets a
   bilingual "not without a health worker" line appended.

## The regression matrix

`python3 safety.py` runs a 260-case matrix: real user phrasings (including
dialect, diacritic-free typing, reversed word order, first-person forms)
against expected rule sets, plus scrubber unit tests proving that safe
advice ("do NOT make them vomit") survives while dangerous advice is
deleted. **All changes must keep it at ALL PASS.** The matrix has caught
bugs in its own new rules before deployment more than once.

## Notable catches from the audit rounds

These are real outputs the layers now prevent. They are kept here as a reminder
of why the floor exists:

- "Loosen the tourniquet to let the blood circulate" (model, 3 of 3 runs)
- Heimlich maneuver for a stroke, a fish bone, and a bean in the nose
- "Do not attempt CPR if the person does not respond" (drowning)
- Glucose tablets for blood sugar 400 with acetone breath
- A tourniquet for an infected wound
- Drowning "float on your back" steps for a panic attack
- EpiPen advice for a heart attack
- Fresh-water rinse for a jellyfish sting
- "The device can't help, find somebody to talk to" for "I feel sick"

## Limits and honesty

The layer lowers the risk, but it cannot remove it. Under a correct warning the
model's own text can still be clumsy or off topic, translations still slip up
now and then, and there is no rule yet for cases nobody has tested. Every
transcript in `software/eval/` deserves a read from a medical professional. If
you build on this, keep the audit loop going.
