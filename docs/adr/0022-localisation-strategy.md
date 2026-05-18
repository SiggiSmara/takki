# ADR-022: Localisation Strategy

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

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
