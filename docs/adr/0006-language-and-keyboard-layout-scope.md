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

**On IME languages:**

Chinese, Japanese, and Vietnamese use Input Method Editors — the user types Latin keystrokes that are converted by IME software into native characters. This is architecturally a different problem: the "typing" is a two-stage process, and the child is effectively learning QWERTY regardless of their native language. This is out of scope for v1. The Windows + pynput approach would receive IME-converted characters in some configurations, creating unpredictable behaviour.

**Direct-script non-Latin languages** (Arabic, Russian/Cyrillic, Greek, Korean, Thai) are architecturally compatible — the input model is the same as European languages — but are not targeted in v1 due to TTS voice availability and lesson content requirements. The architecture does not preclude adding them later.
