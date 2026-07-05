# ADR-017: Voice Command and Intent Recognition

**Status:** Accepted  
**Date:** 2026-05-17. Amended 2026-07-05 by [ADR-031](0031-no-llm-integration.md): the Layer 4 LLM fallback is removed; the pipeline is Layers 1–3 rule-based only.

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Layered intent recognition pipeline running on top of Whisper transcriptions. Context-aware active intent sets per interaction mode. Confirmation-over-inference for setup. Rule-based only — three layers ([ADR-031](0031-no-llm-integration.md) removed the formerly-planned LLM fallback layer).

### Rationale

Whisper gives the app a text transcription of what the child said. The intent recognition layer maps that transcription to an actionable command. This is a distinct problem with established patterns in open source voice interfaces (Mycroft Adapt/Padatious, Rhasspy, voice2json, Picovoice Rhino) and recent child-accessibility research (MEOWCROPHONE for Scratch, which demonstrated baseline free-speech recognition at 46.4% versus a layered pipeline at 82.8% — a 36-point accuracy gain critical for children's speech).

Children's speech is harder to recognize than adult speech: physiological differences in the vocal tract, lower pronunciation clarity (especially in younger children), higher intra-speaker and inter-speaker variability, and higher rates of disfluencies. Whisper handles these better than most engines but still imperfectly. A robust intent layer is what bridges the gap between transcription and action.

### The Layered Pipeline

For each utterance, the pipeline tries layers in order and returns on the first match above a confidence threshold:

**Layer 1 — Exact and synonym keyword match.** Intents are defined with keyword groups per language. "Faster" intent in English matches `{"faster", "speed up", "more speed", "quicker"}`; in German `{"schneller", "schneller bitte", "schnell"}`. This catches the majority of cases instantly with no inference cost.

**Layer 2 — Phonetic match.** When Whisper produces something close-but-wrong ("vaster" instead of "faster", "schnüller" instead of "schneller"), a phonetic algorithm (Metaphone, Double Metaphone, or language-appropriate equivalent) finds the intended keyword. This is the layer that gave MEOWCROPHONE its largest accuracy gain for child speech.

**Layer 3 — Fuzzy string match.** For transcription errors that are spelling-similar but not phonetically similar. Standard Levenshtein distance with a configurable per-intent threshold.

**Layer 4 — LLM fallback: removed** *(2026-07-05, [ADR-031](0031-no-llm-integration.md))*. This layer was an optional, hardware-gated LLM pass for genuinely flexible phrasing ("can you slow down a bit"). It is gone: the pipeline ends at Layer 3. Its failure mode is already handled by the explicit no-match response below and, on repeated failure, the simpler-path fallback (three failed attempts → spoken-number selection, see Setup Failure Modes). A downstream fork can reinstate an equivalent behind the intent-resolution Protocol boundary (ADR-019).

If all three layers fail, the app responds with a clear "I didn't catch that — try again" — better than guessing wrong.

### Context-Aware Intent Sets

The active set of intents the pipeline considers varies by application state. The app knows what step of setup or interaction it's at, and only intents valid at that step are matched. For example:

- **At "choose background color"**, active intents are: COLOR_NAME, POSITION_REFERENCE, REPEAT, GO_BACK, START_OVER, HELP. All other intents are inactive.
- **At "type the spoken word"**, active intents are: REPEAT, READ_AGAIN, GO_BACK, RESTART_WORD, HELP, EXIT_SESSION.
- **At "select a profile"**, active intents are: PROFILE_NAME (one per existing profile), CREATE_NEW, REPEAT, HELP.

This dramatically improves accuracy because the pipeline is more aggressive within a smaller candidate set. "I think she said sky" wouldn't match a color outside color-selection context, but within it confidently resolves to Blue.

This pattern is borrowed from Rhasspy and voice2json's "scoping" model.

### Setup Interaction Modes

Setup is architecturally distinct from steady-state operation. The interaction modes:

**Mode 1 — Constrained choice (yes/no, color from palette, voice from catalog).**
Closed set, well-known synonyms per language. Fuzzy-match against the closed set. Yes-intent synonyms include "yes", "yeah", "okay", "sure", "go ahead", "fine", and equivalents in each language. Color palette entries each have 5–10 synonyms per language (e.g. "navy"/"dark blue" → Navy; "ivory"/"off-white" → Cream). Synonym lists are a contribution path for native-speaker contributors.

**Mode 2 — Free-form input (name).**
No closed set. The app captures Whisper's transcription, reads it back for confirmation — *"I heard Lukas — is that right?"* — and proceeds on affirmative response. On dissent, the app offers to spell the name letter-by-letter via voice, which doubles as familiar typing-tutor interaction.

**Mode 3 — Selection from a list (text size, voice catalog).**
Supports both name reference ("Large", "Amy") and position reference ("the second one", "number two"). Both are recognized at equal priority.

**Mode 4 — Universal escape commands (always active).**
"Repeat", "go back", "start over", "skip", "help" are recognized at the highest priority regardless of current mode. The pipeline checks these before any context-specific intent set.

### Setup Failure Modes to Avoid

- **Silent failure.** Every utterance must produce immediate audible acknowledgment — either the matched intent or a clear "I didn't quite catch that."
- **Wrong-match success.** Setup biases heavily toward confirmation over inference. A misheard color is corrected by the live preview (ADR-016); a misheard name is corrected by the read-back step.
- **Cascading confusion.** "Go back" and "start over" commands are available at every step via Mode 4 universal escapes.
- **Frustration loops.** After three failed attempts at the same step, the app offers a simpler path — for selection from a list, switch from name matching to spoken-number selection ("press 1, 2, or 3").

### Per-Language Intent Definitions

Intent definitions live in `intents/{lang}.yaml` files — one per language. The format is simple enough for non-programmer contributors. An English example:

    INCREASE_RATE:
      keywords:
        - faster
        - speed up
        - more speed
        - quicker
    DECREASE_RATE:
      keywords:
        - slower
        - slow down
        - less speed
    REPEAT:
      keywords:
        - repeat
        - say again
        - again
        - what

A contributor adding a new language provides a single YAML file. No code changes. This is the primary contribution path for language coverage of voice commands.

### Alternatives Considered

- **Whisper transcription + raw string equality:** Rejected. Fails on the predictable Whisper errors that the layered pipeline catches.
- **LLM-only intent recognition:** Rejected. Latency and hardware dependency; ADR-031 subsequently removed LLM use from the pipeline entirely.
- **Single-mode pipeline (no context-aware intent sets):** Rejected. Loses meaningful accuracy gains for closed-set interactions like setup.
- **Picovoice Rhino:** High accuracy but proprietary; doesn't fit open-source-first stance.
- **Rhasspy as runtime dependency:** Considered but adds significant complexity for a project this size. Its intent definition patterns are borrowed; the runtime is not.
