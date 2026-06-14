# Planning note: word-source strategy (ADR-008 supersede)

> **Status:** Planning / pre-ADR (feeds the ADR that supersedes [ADR-008](../adr/0008-word-list-strategy.md))
> **Date:** 2026-06-14
> **Inputs:** [anchor-and-introduction-order.md](anchor-and-introduction-order.md); spikes `source_validation_spike.py`, `intro_order_comparison_spike.py`, `word_list_reality_spike.py` (results in `../../spikes/results/`); the project memory note on the vocabulary paradigm.

**One-line:** Move the word list from *negative filtering* (take everything wordfreq has, subtract junk) to *positive curation* (start from a vetted child vocabulary), with an affix-aware dictionary as the long-tail fallback and a per-language blocklist for appropriateness. Validated GO by the source spike.

---

## 1. What we're committing to

- **Positive curation as the early-band source.** Validation was decisive: on English, a curated list (Dolch) front-loads concrete, picturable words (`big/blue/jump/play/red/run/yellow`) while wordfreq front-loads abstract grammatical glue (`that/which/would/their`) — and the dictionary fallback is *identical to wordfreq-only in ordering*, so a dictionary alone cannot fix engagement. Curated also had 0 appropriateness hits vs wordfreq's `god` in the top-200.
- **The dictionary is a long-tail backstop, not the early-band fix.** wordfreq's top band is already ~99–100% real words; the gate earns its keep deeper down (German real-word rate 99%→89% from top-200 to top-3000) and as a safety net.
- **Two orthogonal gaps stay separate:** Gap A real-word selection (dictionary) and Gap B appropriateness (blocklist). The dictionary keeps `god` (it's a real word); only the blocklist removes it.

## 2. Scope guardrail

- **[ADR-007](../adr/0007-language-data-word-frequency.md) STANDS** — wordfreq remains the sole source for frequency / letter / bigram data. We are not abandoning wordfreq; we change how the word *list* is selected.
- This supersedes the selection decision in **[ADR-008](../adr/0008-word-list-strategy.md)** and folds in the two previously-pending tasks (real-word/dictionary filter; default appropriateness blocklist).

## 3. The pipeline (the contract)

Per language, build the drill pool by:

```
core   = curated_list                       # preferred tier (acquisition-ordered), where licensed
extend = wordfreq(rank) ∩ dictionary_gate    # universal fallback / long tail
pool   = core ++ [w in extend if w not in core]     # seed-then-extend
pool   = pool − default_blocklist − family_exclude  # appropriateness (Gap B)
pool   = pool ++ family_add                  # explicit human intent — BYPASSES the gate (names: oma, luna)
```

Rules: the blocklist applies to the curated list too (defense in depth); `family_add` bypasses the dictionary gate (names aren't in any dictionary), preserving ADR-008's "values stay with the family" principle.

## 4. The fallback — dictionary gate (the three failure modes, baked in)

The source spike proved a naive `wordfreq ∩ dictionary` gate is wrong in three concrete ways. The fallback **must** specify all three:

1. **Affix-aware, not a flat wordset.** A base-form/headword list rejects inflections — English `has / years / women`, German `war / kann / muss` — i.e. the commonest words. Use hunspell + an affix-aware engine (`spylls` validated this). A plain `set` membership test is disqualified.
2. **Casing-tolerant.** wordfreq is lowercased; capitalised-noun languages break under a literal lookup (`haus`→reject, `Haus`→accept). The gate must accept if `lookup(w) or lookup(w.capitalize())`. Affects German and any capitalised-noun orthography.
3. **Locale / spelling-variant tolerant.** A single locale dictionary false-rejects valid regional spellings — `centre / colour` under en_US, `weiss / gross` (ß↔ss) under de. **Policy to decide:** match the dictionary to the profile locale, *and/or* treat the gate as **advisory** rather than hard — a high-frequency wordfreq word the gate rejects should be flagged for review, not silently dropped (prevents the gate eating real words it simply doesn't know).

Two non-responsibilities to state explicitly so the gate isn't over-trusted: it does **not** handle appropriateness (Gap B) and does **not** reorder (curation owns ordering). Because it only matters in the long tail, don't over-engineer it.

## 5. The curated tier

- **Format:** per-language list, file/YAML in the [ADR-022](../adr/0022-localisation-strategy.md) per-language pattern. File order = acquisition order.
- **English:** Dolch sight words (public domain, validated). Fry (1000) later, pending a copyright check.
- **German:** the **union of all Bundesländer** Grundwortschatz lists. Inter-Land contestedness is a non-issue (differences are emphasis, not conflicting words), and the **count of Länder including a word doubles as the cross-regional consensus introduction order** (on all → core-first; on 1–2 → long tail). This "union for membership + (overlap-count × wordfreq) for ordering" is the reusable pattern for any language with multiple competing lists.
- **Ordering co-design with [ADR-023](../adr/0023-key-introduction-protocol.md):** a curated word is only usable once its keys are introduced. The lesson engine intersects the curated pool with currently-typeable keys; the curated acquisition order and the key-introduction order must be designed together, not bolted on.

## 6. Gap B — appropriateness (in this ADR)

- A **default per-language blocklist** (the C9 finding: `god / sex / kill` appear early and short — contradicting ADR-008's "contested words tend to be longer and lower-frequency").
- Per-language contribution surface, same shape as the intent/encouragement YAML ([ADR-022](../adr/0022-localisation-strategy.md)). Applies after the pool is built, to curated + fallback alike.
- Keep it minimal and defensible (it is values-laden) and always pair it with the family override — consistent with ADR-008's "values with the family."

## 7. Per-language source matrix (Beta-first)

| lang | curated tier | dictionary (fallback) | default blocklist |
|---|---|---|---|
| en | Dolch ✓ (PD) | hunspell SCOWL-based | to author |
| de | Grundwortschatz union (to source) | igerman98 (GPL — see §8) | to author |
| es/fr/is/fi/pl/… | fallback only initially | hunspell per language | per-language contribution |

## 8. Licensing — the real homework (and a project-precedent fix)

- **Curated:** Dolch public domain ✓. Fry — check compilation copyright. Grundwortschatz — per-Land sources + redistribution clearance.
- **Dictionaries vs Takki's licence:** **RESOLVED (2026-06-14) — Takki is now GPLv3** (`GPL-3.0-or-later`; dependency tree audited compatible). The GPL dictionaries (igerman98) and GPL lexicons (childLex) therefore bundle cleanly; the English SCOWL dict is permissive (fine). Separate distribution ([ADR-015](../adr/0015-piper-voice-model-distribution.md) pattern) is **no longer required for licensing** — it may still be used to keep the binary slim. **NC/academic data (MANULEX etc.) remains excluded** even under GPL.
  - Alternatives if separate distribution is unwanted: find a permissively-licensed German wordlist (hard — most de hunspell dicts are GPL/OpenOffice), or a CC-BY-SA Wiktionary-derived list (attribution + share-alike on the data).
- **Bundling size:** dicts are sub-MB to ~1 MB — negligible for the PyInstaller offline bundle either way.

## 9. Ripple / cross-refs

- **[ADR-007](../adr/0007-language-data-word-frequency.md)** — stands; note explicitly that this change does not touch it.
- **[ADR-023](../adr/0023-key-introduction-protocol.md)** — curated order × key-introduction order co-design.
- **[ADR-010](../adr/0010-lesson-structure-and-progression.md)** — gate Layer-2 unlock on real-word *availability*, not just key count (the earlier C13 finding).
- **[ADR-022](../adr/0022-localisation-strategy.md)** — curated lists + blocklists as per-language data assets / contribution surface.
- **[ADR-025](../adr/0025-configuration-system.md)** — make source selection (curated / fallback / both) configurable per profile/language.
- **[ADR-015](../adr/0015-piper-voice-model-distribution.md)** — dictionary distribution pattern (see §8).
- Update `architecture.md` and `roadmap.md`.

## 10. Open decisions to confirm before writing the ADR

1. **ADR mechanics:** new ADR superseding ADR-008's selection decision *(recommended)* vs amend ADR-008 in place. (Note: project has no "Superseded" status precedent yet.)
2. **Gap B placement:** the default blocklist in this same ADR *(recommended)* vs a sibling ADR.
3. **Gate locale policy (§4.3):** hard-drop vs advisory-flag for gate-rejected high-frequency words.
4. **German dictionary licence (§8):** separate-distribution (ADR-015 pattern) vs permissive alternative.

## 11. Sequence

1. Confirm §10.
2. Licensing pass — English done; German Grundwortschatz sourcing + the GPL-dictionary call.
3. Source and assemble the German Bundesländer union (with consensus counts).
4. Write the ADR (mechanics per §10.1).
5. Ripple updates (§9).
