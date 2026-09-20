# ADR-006: Language and Keyboard Layout Scope

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Support Latin-script languages with direct-input keyboard layouts only. Explicitly exclude IME-based languages (Chinese, Japanese, Vietnamese) from scope.

### Rationale

**On keyboard layout families:**

Research confirmed three categories of Latin-script keyboard layouts:
1. **Structurally different base layouts** (QWERTZ, AZERTY) — letter positions differ from QWERTY
2. **QWERTY with dedicated special-character keys** (Nordic languages, Polish, Romanian, etc.) — base positions unchanged, some keys repurposed for native characters
3. **QWERTY with dead keys / AltGr only** (Dutch, Spanish, Italian, etc.) — base QWERTY essentially intact

All three categories are handled transparently by the Windows + pynput approach in ADR-005. No special handling is needed per category.

**On native vs. English layout for learning:**

Pedagogical consensus is clear: children should learn on their native language keyboard layout, not on US QWERTY first. Native layouts exist for linguistic reasons (letter frequency optimisation) and switching later means learning twice. The app teaches on whatever layout Windows reports as active.

*(Amendment 2026-09-20.)* "Whatever layout Windows reports as active" stands, and is now load-bearing: Takki never selects or overrides a layout, and a proposal to let one be set by environment variable was withdrawn for contradicting this sentence. But the sentence assumes one installed layout, and a machine with several is ordinary — the Windows test laptop carries German, US and Icelandic. The active layout can therefore disagree with the *language* the lesson is configured for, which is a separate axis this ADR does not govern. Resolved in [ADR-025 § Language and layout must agree](0025-configuration-system.md): the language is configuration, the layout is the machine's, and Takki verifies the two match at startup rather than teaching a curriculum against a keyboard it does not fit. Alpha reports and stops; a graceful in-app resolution is Beta's, with onboarding ([ADR-013](0013-onboarding-and-profile-selection.md)).

**On IME languages:**

Chinese, Japanese, and Vietnamese use Input Method Editors — the user types Latin keystrokes that are converted by IME software into native characters. This is architecturally a different problem: the "typing" is a two-stage process, and the child is effectively learning QWERTY regardless of their native language. This is out of scope for v1. The Windows + pynput approach would receive IME-converted characters in some configurations, creating unpredictable behaviour.

**Direct-script non-Latin languages** (Arabic, Russian/Cyrillic, Greek, Korean, Thai) are architecturally compatible — the input model is the same as European languages — but are not targeted in v1 due to TTS voice availability and lesson content requirements. The architecture does not preclude adding them later.
