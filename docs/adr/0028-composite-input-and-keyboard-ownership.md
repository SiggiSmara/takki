# ADR-028: Composite Input and Keyboard Ownership

**Status:** Accepted  
**Date:** 2026-06-14

> Part of the [Takki architecture](../architecture.md).  
> Closes roadmap issues B5, B7, and C8. Amends [ADR-024](0024-drill-content-and-lesson-granularity.md). Extends [ADR-005](0005-keyboard-handling.md).

---

**Decision:** The lesson engine processes only complete character events from pynput; raw modifier key events (dead-key arm presses, AltGr-alone presses) are filtered at the event consumer before any lesson logic runs. Composites are drilled as whole graphemes — the modifier is never a drill prompt in isolation. Phase 2 pairs with two typeable characters use interleaved Phase A (L-R-L-R); pairs where one member is a modifier give Phase A/B to the typeable member only. pynput runs with `suppress=True`, making the app the exclusive keyboard owner during lessons; all non-lesson keypresses are swallowed.

### What ADR-005/023/024 decided, and what was missing

[ADR-005](0005-keyboard-handling.md) established that pynput reports the already-translated character, and that "dead keys and AltGr combinations are handled by Windows before the app sees them." [ADR-023](0023-key-introduction-protocol.md) then made modifier keys (AltGr, dead-key) first-class participants in Phase 2, each with its own introduction step. [ADR-024](0024-drill-content-and-lesson-granularity.md)'s four-phase ramp-up was written for a single typeable key: Phase A is "the child types the new key alone, repeatedly."

Three gaps follow from these decisions taken together (roadmap B5, B7, C8):

- **B5 (composite input):** You cannot type AltGr alone or dead-acute alone and receive a character event. Phase A as written has no meaning for a modifier. ADR-023's composite introduction script ("press the accent key first, then the base letter") implies composites are drilled as units, but the Phase 2 sequence ranks the modifier as a standalone step and expects a drill loop to follow.
- **B7 (pair ramp-up):** Phase 2 introduces two keys per step; ADR-024's ramp-up is written for one. Phase A for two simultaneous new keys is undefined. A Phase 2 step can pair a modifier (no standalone Phase A possible) with a typeable letter, making the "interleave both" path nonsensical.
- **C8 (keyboard ownership):** pynput's listener is a global hook. Without a focused window (audio-only mode, default), every character the child types also reaches whatever app is in the background. No ADR defines a keypress taxonomy — accepted vs wrong vs boundary vs swallowed — nor the listener's suppression policy or lifecycle.

English (Alpha) and German (Beta) both use direct-strike characters exclusively; the composite-input model is confirmed by design but requires no spike until the first dead-key language enters the V1 validation pass. The keyboard-ownership decisions are needed for Alpha.

### Event model

pynput translates raw key events to characters via `ToUnicodeEx` on Windows before firing `on_press` callbacks. `ToUnicodeEx` maintains a keyboard compose buffer: a dead-key press advances the compose state; the following base-letter press resolves it to a composed character. From the app's perspective:

| Physical input | `on_press` argument | `key.char` |
|---|---|---|
| Regular letter | `KeyCode(char='a')` | `'a'` |
| Dead-key press (armed) | `KeyCode(vk=...)` or variant | `None` or combining char |
| Base letter after dead key | `KeyCode(char='á')` | `'á'` |
| AltGr + letter | `KeyCode(char='ą')` | `'ą'` |
| AltGr alone | `Key.alt_gr` | — not a `KeyCode` |
| Win, F1–F12, Ctrl, etc. | `Key.cmd`, `Key.f1`, … | — not a `KeyCode` |

**The lesson engine processes only events where the argument is a `KeyCode` instance with a non-None printable `char`.** The event consumer checks this before any lesson logic runs. Modifier arm events, dead-key presses, and all `Key.*` specials are discarded at the boundary.

The lesson engine therefore has no concept of "modifier key" or "compose state." `'á'` and `'a'` are equally atomic inputs. No compose-state management belongs inside the engine.

**Compose state at prompt advance.** If a child presses a dead key mid-drill and the engine's auto-advance timeout fires before they press the base letter, the Windows compose buffer stays armed. The next character the child produces is the composed result. The engine receives that character event, compares it to the current prompt, and processes it normally: correct if it matches, auto-reject if not. The stale compose is consumed in either case. No explicit compose-state flush at prompt boundaries is needed; the existing auto-reject model handles spurious composed events without special treatment.

### Composite ramp-up (B5)

ADR-024's Phase A through D is amended for composite graphemes.

**Phase A — whole grapheme repeated.** "Type the new key alone, repeatedly" becomes "type the whole grapheme repeatedly." The engine prompts `á`; the child presses dead-acute then `a`; pynput fires `KeyCode(char='á')`; the engine records a correct attempt. Ten consecutive correct attempts advance to Phase B. The two-keystroke mechanism is entirely invisible to the engine.

**Phase B — alternate composite with base letter.** The same-finger anchor for a composite is its base letter: for `á`, the anchor is `a`. The child alternates `á ↔ a`. Both use the same physical key, with and without the modifier gesture — this trains the modifier as a contextual overlay on an already-known key rather than a foreign motor pattern. Phase B thresholds from ADR-024 (20 attempts, ≤ 1 rejection) apply unchanged.

**Phases C and D** — unchanged. The composite enters the selection pool on equal footing with direct-strike characters.

This amendment overrides ADR-024's "new key alone" and "same-finger home-row neighbour" phrasing for composite graphemes only. For direct-strike keys ADR-024 stands unmodified.

### Modifier introduction

A modifier key (AltGr, dead-acute, dead-macron, etc.) enters Phase 2 at its aggregate-composite-frequency rank per ADR-023. When its step arrives:

1. The engine plays a spoken introduction for the modifier: its name, key location, and mechanism. For example: *"New key: the accent key. It lives to the right of the letter P. It adds an accent to the next letter you press — it will not make a sound on its own."* The description comes from the per-language YAML ([ADR-022](0022-localisation-strategy.md)).
2. The modifier does **not** enter Phase A or Phase B. No drill loop runs for the modifier in isolation.
3. Every composite grapheme whose prerequisites are now fully Active (both modifier and base letter have `key_stats` rows) becomes typeable. The first time drill content surfaces such a composite, the engine plays the composite introduction script from ADR-023.

The modifier's "introduction step" is therefore a spoken announcement, immediately followed by the four-phase ramp-up for its typeable pair partner (see below).

### Pair ramp-up (B7)

Phase 2 introduces one left-hand key and one right-hand key per step (ADR-023). The adaptation to ADR-024's single-key phases depends on the pair contents.

**Both members are typeable characters (common case):**

- **Phase A:** the engine interleaves prompts — L, R, L, R — until each has 10 consecutive correct responses. The 10-each threshold is per-key, not shared, so a slow right hand cannot mask a poor left hand.
- **Phase B:** four-way alternation — L-anchor, L-new, R-anchor, R-new. Each new key alternates with its own same-finger anchor. If one new key has no same-finger anchor yet (possible for very early steps), use the nearest known key on the same hand. Threshold: 20 attempts each, ≤ 1 rejection per key.
- **Phases C and D:** both keys join the shared pool with no further pair treatment.

**One member is a modifier:**

- The typeable member runs Phase A through D as a solo ramp-up (no L-R interleaving).
- The modifier receives its spoken introduction and no drill.
- Composites enabled by the modifier appear in Phase C/D of the typeable member's ramp-up if prerequisites are met at that point, or in subsequent steady-state drilling.

**Layer-2 unlock.** ADR-010's "≥ 8 active keys" check fires after each introduction step. Pair introduction advances the count by 2 per step in the typical case (or 1 if one member is a modifier). On English QWERTY the home-row typeable character count is 9 — A S D F G H J K L; the right-pinky home position `;` is not a letter — so the count goes 2, 4, 6, 7 (step 4 introduces A solo), 9 (G+H). Layer 2 unlocks at count 9, which satisfies the ≥ 8 threshold. Layouts whose home rows yield exactly 8 typeable characters trigger the unlock at the same count. No change to the threshold is needed.

**Encouragement framing.** ADR-012's pre-introduction line ("learn your next letter and you'll be able to type X% more everyday words") becomes plural for a two-typeable-character pair: *"Your next two letters will let you type X% more everyday words."* X is the combined marginal coverage gain. When one pair member is a modifier, the framing refers to the typeable member only — composites enabled by the modifier are not yet typeable at the time of the announcement.

### Keyboard focus and ownership (C8)

**pynput starts with `suppress=True`.** All keypresses are consumed by the app and not forwarded to the OS message queue or any focused window. This is necessary in audio-only mode (no app window): without suppression, every character the child types also reaches whatever is focused in the background — a browser address bar, a desktop rename dialog, a file search box. Suppress eliminates the bleed entirely. The Windows key cannot open the Start menu mid-lesson; F-keys cannot trigger OS shortcuts; nothing typed during a drill leaks.

**Listener lifecycle.** The pynput listener is created once at application startup and runs until the application exits. It is not paused or restarted between lessons. What determines how an event is dispatched is the lesson engine's active state, not the listener's configuration.

**Keypress taxonomy.** The `on_press` handler classifies every event before dispatching:

| Class | Condition | Action |
|---|---|---|
| **Talk key** | Matches configured PTT key (default: Right Ctrl) | Dispatch to voice subsystem; suppress from OS |
| **Escape** | `Key.esc` | Dispatch to lesson controller (re-read / restart per ADR-025) |
| **Expected** | `KeyCode` with printable `char` matching current prompt | Correct-chime; advance; record correct in `key_attempts` |
| **Wrong** | `KeyCode` with printable `char` not matching current prompt | Auto-reject sound; re-prompt; record wrong in `key_attempts` |
| **Composing** | `KeyCode` with `char is None` or non-printable | Discard silently — compose in progress |
| **Boundary** | `Key.backspace`, `Key.tab`, `Key.delete`, `Key.enter` | Suppress and ignore (Backspace disabled per ADR-012) |
| **System** | All remaining `Key.*` events | Suppress and ignore |

The "wrong" class handles accidental composites: if the engine prompted `a` and the child produced `á` (stale dead-key state from a previous sequence), `á` is a wrong answer for `a`; auto-reject fires, the dead-key state is consumed, re-prompt follows. No special case required.

**App exit.** With `suppress=True` and no display window, the conventional close paths (Ctrl+C at the terminal on Windows, Alt+F4 with no window) may not reach the app. The app must register OS signal handlers (`signal.SIGINT`, `signal.SIGTERM`) at startup so Task Manager and shell termination work correctly. The primary in-lesson exit is the voice "stop" intent (ADR-017), which remains available via the talk key. Whether a secondary keyboard-driven emergency exit is needed (e.g., hold Escape for 5 seconds) is an open question deferred to Beta; for Alpha (developer use only) signal handlers plus Task Manager are sufficient.

### Pre-V1 validation: dead key + suppress

The event model above relies on pynput's `ToUnicodeEx` threading dead-key compose state correctly through the low-level keyboard hook (`WH_KEYBOARD_LL`) under `suppress=True`. English (Alpha) and German (Beta) use direct-strike characters only; no dead-key behavior is exercised. Before adding the first dead-key language (Icelandic, French, Czech, or similar in the V1 validation pass), run a one-session spike:

1. On Windows, configure a dead-key layout (e.g., US International with dead keys, or Icelandic).
2. Start a pynput `keyboard.Listener(suppress=True)`.
3. Print `type(key)` and `key.char` for every `on_press` event while typing `dead-acute + a`, `dead-acute + e`, and AltGr + a.
4. Confirm: dead-key arm event has `char=None` (or is otherwise filtered by the `KeyCode` + printable check); composed result has the correct `char`.

If `ToUnicodeEx` does not thread compose state through the suppressing hook, the app must maintain its own compose buffer using layout data from `get_layout_positions()`. That would require a follow-up amendment to this ADR and to ADR-005.

### Open questions

1. **Emergency keyboard exit.** Define a held-key exit for Beta (e.g., hold Escape for 5 seconds, configurable in `takki_config.yaml`) so a parent can close the app if voice control is unavailable. The exit must bypass `suppress=True` by detecting the hold duration in the listener itself and calling `os.kill(os.getpid(), signal.SIGTERM)`.

2. **Per-profile mechanism override for dual-path languages.** Inherited from ADR-023 open question 1: a Latvian adult who already uses dead-key paths may want to keep that motor pattern. Hard-default to AltGr for v1 child learners. No decision needed before Beta (Latvian is not in the Beta language set).

3. **Phase B anchor when base letter is in active ramp-up.** If a composite is first introduced before its base letter has cleared Phase D, Phase B alternation with the base letter would interleave a composite in Phase B with a letter still in Phase A/B. In practice the modifier always ranks later than the base letter in the Phase 2 frequency sequence (ADR-023: Polish AltGr at step 12–15; Icelandic dead-acute at step 18), so the base letter is well past Phase D when the composite's Phase B runs. Verify per-language during V1 spike to confirm no layout places a modifier unusually early.
