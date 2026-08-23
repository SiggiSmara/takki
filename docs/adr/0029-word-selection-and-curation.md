# ADR-029: Word Selection and Vocabulary Curation

**Status:** Accepted  
**Date:** 2026-06-14

> Part of the [Takki architecture](../architecture.md). Supersedes the word-*selection* decision of [ADR-008](0008-word-list-strategy.md) (its family-override file mechanism is retained). Does **not** change [ADR-007](0007-language-data-word-frequency.md) (`wordfreq` remains the frequency/letter/bigram source).

---

**Decision:** Select drill words by **positive curation**, not by filtering wordfreq. A tiered, per-language pipeline:

```
core   = curated children's / sight-word list       # preferred tier, where licensed; acquisition-ordered
extend = wordfreq(rank) ∩ dictionary_gate            # universal fallback / long tail
pool   = core ++ [w in extend if w not already in core]      # seed-then-extend
pool   = pool − default_blocklist − family_exclude           # appropriateness (orthogonal to real-word gate)
pool   = pool ++ family_add                          # explicit human intent — BYPASSES the dictionary gate
```

The **dictionary gate** is a real-word membership test that MUST be **affix-aware** (hunspell via an affix engine, not a flat wordset), **casing-tolerant** (accept `w` or `w.capitalize()`), and **locale/spelling-variant tolerant** and **advisory** (a high-frequency wordfreq word the gate does not recognise is *flagged for review*, not silently dropped). The gate handles real-vs-non-word only; it does **not** judge appropriateness and does **not** reorder.

Words are **vehicles for keystroke practice, not a vocabulary curriculum** (Takki teaches touch typing). The pool is therefore sized for **per-key and per-bigram repetition**, not vocabulary breadth — empirically a few hundred to ~1,600 common words covers every key with ≥10 repetitions per language (exact thresholds live in config per [ADR-025](0025-configuration-system.md)).

### Rationale

**Why the change (negative → positive curation).** ADR-008 derived the list from `wordfreq` (top-N, 3–6 letters) and defended it only on age-appropriateness grounds, implicitly trusting wordfreq to contain *words*. Spikes falsified that:
- `source_validation_spike.py`: with a real dictionary, only **~11%** of wordfreq's 3-letter strings are real words. More decisively, on the early band a curated list (Dolch) front-loads concrete, picturable, rewarding words (`big/blue/jump/play/red/run`) while wordfreq front-loads abstract grammatical glue (`that/which/would/their`) — and the `wordfreq ∩ dictionary` fallback is **identical to wordfreq-only in ordering**. So a dictionary alone cannot fix engagement; only curation does.
- Curated lists also had **zero** appropriateness hits vs wordfreq's `god` already inside the top-200.

This is sharper for visually-impaired children: the word is heard via TTS with no visual sanity check, so a junk or inappropriate "word" is actively miseducative.

**Touch typing, not vocabulary.** Because words are drill vehicles, "cover the keyboard meaningfully" means enough material **per key and per key-transition** (feeds [ADR-024](0024-drill-content-and-lesson-granularity.md)'s bigram phase), not lexical coverage. This keeps the pool small and makes the dictionary a *quality gate*, not a vocabulary engine.

**Two orthogonal gaps.** (A) real-word selection → the dictionary gate; (B) appropriateness → the default blocklist. They are independent: the dictionary keeps `god` (a real word); only the blocklist removes it. ADR-008's claim that "contested words tend to be longer and lower-frequency" is wrong for the band Layer 2 starts in (`god`, `sex`, `kill` are short and high-frequency — the roadmap C9 finding). Hence a **default, per-language, minimal appropriateness blocklist** (a contribution surface in the [ADR-022](0022-localisation-strategy.md) YAML pattern), composed on top of — not replacing — ADR-008's family override file.

**The gate's three failure modes** (each caught by the spike, each now a requirement above): a flat wordset rejects inflections (`has`, `years`, German `war`, `kann`); literal lookup rejects lowercased German nouns (`haus`→`Haus`); a single locale dictionary false-rejects valid regional spellings (`centre/colour`, ß-variants). Advisory handling prevents the gate from eating real words it simply does not know.

**Per-language source tiering.**

| lang | curated tier | fallback dictionary | appropriateness |
|---|---|---|---|
| en | Dolch (public domain) | hunspell SCOWL (permissive) | default blocklist to author |
| de | Grundwortschatz union (§5 UrhG; childLex for enrichment) | igerman98 (GPL) | default blocklist to author |
| fi | TCBLex (CC-BY) | hunspell | per-language contribution |
| es/fr/is/pl/cs/… | fallback only initially | hunspell per language | per-language contribution |

**Licensing.** Takki is **GPLv3** ([relicensed from MIT, 2026-06-14](../research/lexicon-sources.md)) precisely so the best lexical data — childLex (GPL-3.0) and the igerman98 dictionary (GPL-2/3) — can be bundled cleanly. **Non-commercial / academic-only** data (e.g. MANULEX, CLARIN ACA/RES) is excluded under any app licence and is not used. German curricular Grundwortschätze are **amtliche Werke (§5 UrhG)** = not copyright-protected, giving a licence-clean curated basis. See [lexicon-sources.md](../research/lexicon-sources.md) and [vocabulary-source-plan.md](../research/vocabulary-source-plan.md).

### Consequences

- Curated lists and blocklists become per-language data assets / contribution surfaces ([ADR-022](0022-localisation-strategy.md)); source selection is configurable ([ADR-025](0025-configuration-system.md)).
- The curated acquisition order must be co-designed with the introduction order ([ADR-023](0023-key-introduction-protocol.md), [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md)) — which orders **graphemes**, not keys, so a word containing `á` needs `á` itself to have been introduced, not merely the two keys that produce it *(clarified 2026-08-23)* — a word is only usable once its keys are taught; the engine intersects the pool with currently-typeable keys.
- [ADR-010](0010-lesson-structure-and-progression.md): Layer 2 should unlock on real-word *availability*, not key count alone (roadmap C13).
- Beta (en + de) is covered by confirmed-usable sources.

### Supersedes

Replaces ADR-008's decision "*algorithmic default derived from wordfreq (top N, 3–6 letters)*" with the tiered curation pipeline above. **Retained from ADR-008:** the plain-text family override file (add/exclude), "no LLM for filtering", and "no values decisions on the family's behalf" (now realised as a minimal default blocklist + family override rather than no default at all).

### Deferred (tracked in [vocabulary-source-plan.md](../research/vocabulary-source-plan.md))

Bigram/transition coverage analysis; assembling the Bundesländer Grundwortschatz union; authoring the per-language default blocklists; confirming remaining lexicon licences; exact pool-size thresholds (to config).
