# ADR-007: Language Data — Word Frequency and Letter Frequency

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Use the `wordfreq` Python library as the sole source for word frequency, letter frequency, and bigram/trigram patterns. Derive all three at application startup from the bundled `wordfreq` data. No external download required at runtime.

### Rationale

`wordfreq` provides:
- Word frequency data for 40+ languages
- Data bundled within the package — no internet needed after installation
- Multiple sources combined per language (Wikipedia, subtitles, news, books, web, Twitter) for accuracy
- `pip install wordfreq` — integrates naturally into the Python stack

From the word frequency data, the app derives:
- **Letter frequency ranking** — computed by iterating over frequency-weighted words, restricted to characters present on the keyboard layout, determines the order in which new keys are introduced in lessons
- **Bigram and trigram frequencies** — computed from the same source, drives character pair and sequence generation in Layer 1 drills
- **Filtered word list** — top N words by frequency meeting length and character criteria; words containing characters absent from the keyboard layout are excluded (see Layer 2 below)

**Native alphabet definition** — The authoritative set of characters in the language's alphabet comes from the keyboard layout, not from wordfreq. The platform interface (scan code enumeration via `get_home_row_keys()` extended to all alphabetic positions) returns exactly the characters the physical keyboard can produce; this is the native key set. Characters present in wordfreq only through loanwords — e.g. é in English, from café and résumé — are absent from the keyboard layout and excluded from the native set.

Two consequences:
- The letter frequency ranking (which key to introduce next) uses wordfreq `char_weight`, restricted to characters in the native key set. Loanword-only characters are never in the ordering.
- The Layer 2 word list excludes any word containing a character not in the native key set. Loanwords are dropped entirely — from the lesson and from the coverage denominator.

In the spike script (`spikes/wordfreq_coverage_spike.py`), native alphabet membership is approximated statistically: a character is native if it appears in words totalling ≥0.1% of 3+ character alphabetic text (`MIN_NATIVE_COVERAGE = 0.001`). This correctly separates genuine alphabet members (Icelandic ð, þ; German ü, ä, ö) from loanword-only characters. The real implementation uses the keyboard layout, which is authoritative.

**Startup cost (measured across 20 Latin-script languages):**
- `get_frequency_dict()` load: 25–400ms for most languages. Polish (1.2s) and Finnish (0.8s) are outliers due to large word counts (450k and 725k words respectively). On Windows, file I/O is slower — lazy loading on first language access is preferred over loading all at startup.
- Letter frequency ranking: sub-100ms for any language — just a weighted sum over the frequency dict. **Not reproducible on slower hardware** (added 2026-08-22): ~620 ms for the ranking alone on the Celeron G555 dev box, and the full derived-table cold build is ~767 ms (en) / ~1,977 ms (de) against a 16 ms frame budget. These figures are hardware-dependent in a way this ADR does not state, which is why the tables are warmed before the core loop starts rather than built lazily inside it — see [concurrency-model.md § Startup](../concurrency-model.md).
- Full coverage curve (all 26 steps): 200ms–14s depending on word count. **Never compute the full curve at startup.** The app only needs the letter ordering (cheap) at startup; coverage for the child's current key set is computed incrementally as keys are mastered.

This approach avoids cache invalidation complexity. If lazy loading is insufficient for the Polish/Finnish case, a pre-computed letter ordering can be bundled as a small static file alongside the language config.

**Limitation:** `wordfreq` data is a snapshot through approximately 2021 and is no longer actively updated. For a children's typing tutor using common vocabulary, this is entirely acceptable — high-frequency common words do not change significantly over time.

### Alternatives Considered

- **FineFreq (HuggingFace):** Covers 1900+ languages from 96 trillion characters — impressive but requires download and is overkill for this use case. Retained as a fallback reference for languages not in `wordfreq`.
- **Per-language static CSV files:** Rejected. Creates a maintenance burden and requires manual updates when language data improves.
- **Deriving from Wikipedia dumps:** Rejected. Single source, biased toward encyclopedic vocabulary, significant processing overhead.
