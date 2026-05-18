# ADR-013: Onboarding and Profile Selection

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Detect language automatically from Windows locale on first run and begin communicating immediately in that language. If detection fails or the detected language is not supported, rotate spoken welcomes through the top 5 languages by global speaker population until the user responds or selects a language.

### Rationale

The first-run experience must itself be fully accessible — a visually impaired parent or child should not face a silent or text-only setup screen. The Windows locale is the most reliable available signal and is almost always correct. Acting on it immediately, without asking, satisfies the minimal setup friction principle.

The fallback rotation handles the edge cases: unsupported locale, locale not set, or a system configured by a school IT department in a different language than the child's home language. Rotating through the top 5 languages (by speaker population among supported languages — likely English, Spanish, French, German, Arabic or similar) with a short spoken greeting in each gives the user a natural moment to respond in their language, which `faster-whisper` then detects.

### Behaviour

1. App starts → query Windows locale → look up in hardcoded config
2. If found: immediately speak welcome in that language, proceed to profile setup
3. If not found: speak a short greeting in each of the top 5 supported languages in rotation, pausing 3 seconds between each for a voice response
4. On voice response: detect language from response via `faster-whisper`, confirm with user, proceed
5. If no response after one full rotation: default to English with a spoken explanation

### Profile Selection at Session Startup

After language is established, the app loads the child's profile.

**Single profile case:** If only one profile exists on the installation, it is loaded automatically with no further interaction.

**Multiple profile case:** The app speaks the available profiles — *"Who's practicing today? I have Lisa and John."* — and the child responds with their name. The standard intent recognition pipeline (ADR-017) fuzzy-matches the spoken response against the profile name list. The selected profile is confirmed audibly — *"Hi Lisa! Ready to practice?"* — before loading. The child can dissent ("no", "wait") to restart selection.

No verification beyond the name match is performed. Profile selection trusts the child to identify themselves correctly. This is sufficient for the typing tutor use case; data integrity stakes are low (worst case is some lost progress for one session) and stronger verification (passwords, biometrics, voice ID) is incompatible with the audio-first, low-friction design. If usage patterns later reveal a need for verification, an opt-in question/answer mechanism can be added per profile without breaking the existing data model.

### Profile Name Uniqueness

Profile names must be unique within an installation. Comparison is case-insensitive and accent-insensitive (so "Lisa", "lisa", and "Lísa" all collide — they sound identical at voice-selection time).

At creation:

1. If the new name is unique, accept it.
2. If it collides with an existing profile, the app prompts: *"There's already a Lisa on this computer. What should I call this one?"* The parent provides a distinguishing addition — "Lisa B", "Big Lisa", "Lisa from school", or anything else that works for that family.
3. If the proposed name still collides after the addition, the app re-prompts. The new profile is not created until a unique name is provided.
4. The original profile is never modified.

This invariant — every profile name in the system is unique — means selection-time fuzzy matching always resolves to exactly one profile. No tiebreaking logic is needed downstream.

### Alternatives Considered

- **Ask the user to choose from a spoken list of all 40 languages:** Rejected. Listening to 40 language names is not a good first experience.
- **Require a text/click setup before first use:** Rejected. Breaks the audio-first principle for visually impaired users.
