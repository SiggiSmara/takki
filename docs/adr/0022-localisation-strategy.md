# ADR-022: Localisation Strategy

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).  
> **Amended for [ADR-033](0033-rest-keys-and-keyboard-alignment.md):** the keyboard alignment's strings, and "rest" in place of "home" in child-facing text, in [§ The keyboard alignment's strings](#the-keyboard-alignments-strings).

---

**Decision:** All localisation surfaces use YAML files per language. This applies uniformly to runtime UI strings, the encouragement phrase bank (ADR-012), intent definitions (ADR-017), and the voice catalog (ADR-015). No gettext, no `.po`/`.mo` workflow, no translation platform integration in v1.

### Rationale

The conventional choice for Python application localisation is gettext. For Takki specifically, gettext is a poor fit:

- **Every UI string is spoken, not displayed.** Gettext's strengths — handling display length, layout, RTL/LTR, character set quirks — do not apply. The visual display in Takki shows only the typing prompt and typed characters (ADR-016), no localised labels.
- **Multi-variant phrases are first-class.** The encouragement bank (ADR-012) requires multiple variants per phrase with random selection for natural variety. Many UI strings benefit from the same treatment ("Welcome back, Lisa" / "Hi Lisa! Ready to practice?" / "Hello Lisa, let's go" — picked at random keeps repeated sessions from sounding scripted). Gettext does not handle multi-variant naturally; YAML lists do.
- **Existing localisation surfaces already use YAML.** Intent definitions (ADR-017) and voice catalog (ADR-015) are YAML by design. Adding gettext for one surface fragments the contribution pattern; YAML across the board is one mental model.
- **Contributor audience.** Native-speaker volunteers (teachers, linguists, parents) edit YAML directly via PRs. They are not running professional localisation workflows. `.po`/`.mo` tooling is unnecessary friction.
- **Native-speaker review is more effective on a single readable file.** The language pack PR template requires a native-speaker review; a reviewer scanning one YAML file catches phrasing issues that a scattered `.mo` review would miss.

### Schema

Four files per language, each in its own directory:

```
strings/{lang}.yaml          # Runtime UI strings (this ADR)
encouragement/{lang}.yaml    # Encouragement phrase bank (ADR-012)
intents/{lang}.yaml          # Voice command intents (ADR-017)
voice_catalog/{lang}.yaml    # Curated Piper voice metadata (ADR-015)
```

UI strings (`strings/{lang}.yaml`) — single string or list of variants per key:

```yaml
ready_to_practice: "Ready to practice."

language_detected: "Language detected: {language}."

profile_loaded:
  - "Hi {name}! Ready to practice?"
  - "Welcome back, {name}."
  - "Hello {name}, let's go."

milestone_silver:
  - "You've reached Silver! You know one third of the alphabet now."
  - "Silver milestone! That's a third of your alphabet mastered."

didnt_catch_that:
  - "I didn't catch that — try again."
  - "Sorry, can you say that again?"
```

A list-valued key triggers random selection at lookup time. Single-value keys are returned verbatim.

### The keyboard alignment's strings

Child-facing text says "rest", never "home" (ADR-033 § Vocabulary). The alignment uses the terms of the rest letter's script, "the bump" and "where that finger rests" ([ADR-023 § The key introduction script](0023-key-introduction-protocol.md#the-key-introduction-script)), so the child hears one vocabulary from placing the hands to the introduction of a letter. A change to one changes both.

The strings, as placeholder English in `takki.lesson.alignment` until the YAML tier exists:

| Key | English |
|---|---|
| `alignment_first_lesson` | Before we type, we find where your fingers rest. Two keys have a small bump, and your index fingers rest on them. |
| `alignment_hands_off` | Take your hands off the keyboard. |
| `alignment_ask_bump` | Find the bump with your {finger}. Press it and let go. |
| `alignment_ask_rest` | Put your {finger} down where it rests. Press and let go. |
| `alignment_question` | Where should your {finger} rest? It landed on {keys}. Press the key you want, and let go. |
| `alignment_off_bump` | That was not the key with the bump. |
| `alignment_elsewhere` | That key is for another finger. |
| `alignment_let_go` | Let go of the key. |
| `alignment_closing` | Well done. Finding the bumps takes practice. That is all for today. Next time we will start with the bumps again. |

- **The first lesson** is said before a session's first round until the profile has landed once. **The hands come off** before every round (ADR-033).
- **The question names keys** (`{keys}`, a list joined with "and"): a letter by itself, a modifier by its name ("the accent key"), and any other cell by a spoken name per language ("semicolon", "apostrophe"). The sentence naming them is left out when the finger has no landing in the session.
- **Finger names** are the introduction script's.
- **The closing line** is said when the alignment reaches its cap with an index finger not ready, so that no letter may come and nothing is Active: only in a child's first sessions.

### Pluralisation

For languages with rich plural categories (Polish, Russian, Arabic, etc.), explicit forms by CLDR plural category:

```yaml
keys_known:
  one: "You know one key now."
  few: "You know {count} keys now."
  many: "You know {count} keys now."
  other: "You know {count} keys now."
```

The string resolver picks the appropriate form using CLDR plural rules. The `babel` library (pure Python, widely available) provides the plural-rule lookup; `babel` is added as a runtime dependency when the localisation module lands.

A pluralised key may itself contain a list of variants per form:

```yaml
clean_words_today:
  one:
    - "One clean word today!"
    - "You typed one perfectly today."
  other:
    - "{count} clean words today!"
    - "You typed {count} perfectly today."
```

### Loading and Runtime Behaviour

- At app start, the active language's YAML files are loaded into memory. Files are small (kilobytes); the cost is negligible.
- A `tr(key, **params)` function returns the appropriate string. Multi-variant keys randomise per call.
- Format strings use Python's `str.format` style (`{name}`, `{count}`).
- Missing keys fall back to English (`en`) with a logged warning. The user-facing failure mode is "the app speaks English for this one phrase," not a crash.

**The rest cue's strings** *(dated note, 2026-11-12, alpha-plan #12m session (6b).)* Three strings, placeholder English in `takki.lesson.introducer` beside the introduction script's until this tier exists: the cue's word, *"Rest."*; the script's line about it ([ADR-023](0023-key-introduction-protocol.md), "The script's line about the rest cue"), with "finger" or "fingers"; and the guidance, which names the fingers still owed by the bump ([ADR-012](0012-audio-feedback-design.md), the note on the rest cue). The guidance is assembled in code from English pieces: an index finger's sentence, "find the bump" for one hand or "the bumps" for both, the fingers to put back, and "press" or "press both keys". That is English grammar, and a translator cannot rebuild it from fragments. When this tier lands, each shape the guidance takes is a key of its own holding a whole sentence, with the finger names as placeholders: one index finger; one other finger; two fingers on two hands; two on one hand; an index finger and another finger of the same hand. Two more shapes are composed by the code but were never worded with the developer, because no layout has a composite that needs them: two index fingers, and an index finger with a finger of the other hand. They are worded when a layout first needs them. "Finger" or "fingers" in the script's line is a choice of shape, not a CLDR count, so it is two keys and not a pluralised one. The word "rest" in all three is ADR-033's "rest, never home".

### Contribution Path

1. A contributor (native speaker or working with a native-speaker reviewer) forks the repo
2. They add or edit the four YAML files for their language
3. They open a PR using the language pack template (`.github/ISSUE_TEMPLATE/language_pack.md`)
4. Native-speaker review is required for merge
5. No build step — YAML is read at runtime; the change is live in the next session

### Alternatives Considered

- **Gettext (`.po` / `.mo`).** Rejected. See rationale. Mature ecosystem, but mismatched with audio-first delivery and multi-variant requirements; adds compilation step and tooling burden for no benefit in this project.
- **Fluent (Mozilla).** Promising — natively handles plural categories, grammatical gender, and selectors. Adds `fluent.runtime` as a dependency. Reserved as a future option if YAML proves insufficient for languages with very complex morphology. The cost is a learning curve for contributors who don't already know Fluent.
- **Weblate / Crowdin integration.** Both support YAML in addition to .po. No integration at v1 scope — contributors edit YAML via PRs. Possible future addition without changing the file format.
- **Mixed approach (gettext for UI strings, YAML for everything else).** Rejected. Fragmenting the contribution pattern for one surface adds friction with no proportionate benefit.

### Changes

- 2026-11-13, alpha-plan #12m session (7): § The keyboard alignment's strings added, for ADR-033.
