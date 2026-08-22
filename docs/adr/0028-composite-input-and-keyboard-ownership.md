# ADR-028: Composite Input and Keyboard Ownership

**Status:** Accepted  
**Date:** 2026-06-14  
**Revised:** 2026-06-21 — §C8 keyboard ownership reworked: global `suppress=True` replaced by focus-gated dispatch over an always-on window.

> Part of the [Takki architecture](../architecture.md).  
> Closes roadmap issues B5, B7, and C8. Amends [ADR-024](0024-drill-content-and-lesson-granularity.md), and (per the 2026-06-21 revision) [ADR-016](0016-visual-display-design.md) and [ADR-026](0026-platform-interface-abstraction.md). Extends [ADR-005](0005-keyboard-handling.md) and adds the `FocusSource` Protocol to [ADR-019](0019-testing-strategy-and-io-isolation.md).

---

**Decision:** The lesson engine processes only complete character events from pynput; raw modifier key events (dead-key arm presses, AltGr-alone presses) are filtered at the event consumer before any lesson logic runs. Composites are drilled as whole graphemes — the modifier is never a drill prompt in isolation. Phase 2 pairs with two typeable characters use interleaved Phase A (L-R-L-R); pairs where one member is a modifier give Phase A/B to the typeable member only. Keyboard ownership is scoped by an always-on focus-owning window, not by global suppression (revised 2026-06-21): pynput key events drive a drill only while Takki holds OS foreground, and Takki pauses the instant focus moves elsewhere — intentional task-switch, focus theft, or OS secure desktop alike. See *Keyboard focus and ownership (C8)* below.

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

> **Originally decided (2026-06-14):** pynput started with `suppress=True`, making Takki the exclusive system-wide keyboard owner during a lesson — every keypress consumed, nothing forwarded to the OS or any focused window. The aim was to eliminate input bleed in audio-only mode (no window): without suppression, every character the child types also reaches whatever is focused in the background — a browser address bar, a rename dialog, a search box.
>
> **Revised (2026-06-21):** global suppression is replaced by **focus-gated dispatch over an always-on window.** Suppress prevented the leak but created two worse problems it never addressed. It *trapped* the user: a child or parent could not switch to another app without killing Takki — even Alt+Tab was swallowed. And it was *blind to OS preemption*: on the secure desktop (UAC, Ctrl+Alt+Del, lock, fast-user-switch) a low-level hook receives nothing, so the child typed into silence with no feedback and Takki could not tell it had lost the keyboard. The governing reframe is that the child is not learning to type in a vacuum — navigating the OS is part of what they are learning — so a keystroke that opens the Start menu and pauses the lesson is correct cooperative behaviour, not a leak to be suppressed.

**Always-on focus-owning window.** Takki always creates an OS window — the same SDL/pygame window used for the optional visual display (ADR-016), blank when the visual profile is off. The window is the focus anchor; the child, who navigates by audio, never needs to see it. Keyboard capture is thereby *scoped by focus* instead of by a global suppressing hook.

**pynput stays the key source; dispatch is focus-gated.** pynput remains the keyboard interface (ADR-005) and the event model above is unchanged — `ToUnicodeEx` translation, the `KeyCode`-with-printable-`char` filter, and composite handling all stand. What changes is that `on_press` processes an event as drill input **only while Takki's window holds OS foreground.** While it does, the focused window consumes the keystrokes, so nothing leaks; while it does not, Takki is paused by definition. `suppress=True` is dropped entirely.

**Focus is the single active/paused signal.** Intentional task-switch, a focus-stealing notification, and OS secure-desktop preemption all manifest as the same event: Takki's window is no longer foreground. One mechanism — window focus events (`WINDOWFOCUSGAINED` / `WINDOWFOCUSLOST`) behind the `FocusSource` Protocol (ADR-019) — covers what were three separate problems. On focus loss Takki enters PAUSED and announces it; a foreground poll backs up the event in case a secure-desktop transition does not deliver one.

**Resume — three converging paths:** the voice "resume" intent (ADR-017), a configurable held-key (works if the mic is unreliable), and simply Alt+Tab back to Takki (native, and announced by any running screen reader). The first two attempt a programmatic re-foreground; Windows' foreground-activation lock may downgrade that to a taskbar flash, in which case the spoken hint falls back to "press Alt+Tab to come back to Takki." The held-key and voice triggers are seen even while unfocused because pynput's hook is global.

**Re-acquire has no synchronous answer** (added 2026-08-22, from session 6a implementation). The paragraph above says the re-foreground attempt "may be downgraded to a taskbar flash," which reads as though the caller learns which happened. It does not, and cannot. `SDL_RaiseWindow` — the mechanism behind `FocusSource.request_foreground()` — is asynchronous: it posts an activation request to the OS and returns before Windows has ruled on it. Querying focus immediately afterwards reads the *pre-call* state, which while PAUSED is always "not focused," so a success-boolean would report failure even on the raises that worked.

`request_foreground()` therefore returns nothing. Re-acquire is a **request plus a deadline**, resolved by the same tick-checked mechanism as every other timed behaviour ([concurrency-model](../concurrency-model.md) § Timers):

1. Call `request_foreground()`; set a deadline.
2. A `FocusGained` arriving before the deadline **is** the success signal — no separate confirmation exists or is needed, and it arrives by the same path as a manual Alt+Tab, so both resume routes converge on one code path.
3. Deadline expiry is the failure signal, and is what triggers the spoken *"press Alt+Tab to come back to Takki"* fallback.

The consequence for the taxonomy's **Resume hold** row is that the held key initiates a request; it does not itself resume. Only the returning `FocusGained` does. Implementing this is [session 6b](../alpha-plan.md); the boundary it builds on landed in 6a.

This is also why an always-on window is load-bearing beyond focus ownership: without a window there is nothing to raise, and the resume paths would have no mechanism at all.

**Screen-reader cooperation.** A VI child's machine very likely runs a screen reader (NVDA, JAWS, Narrator), and the focus-owning window cooperates with it rather than fighting it:
- The reader announcing the new foreground app on focus loss is a *second* channel telling the child they have left a drill — reinforcing Takki's own announcement.
- Its keystroke echo would otherwise double Takki's chimes during a drill. Takki is a **self-voicing application**; the intended fix is the reader's own mechanism for that case — NVDA's **sleep mode**, which is scoped to the focused app, so it silences echo *while Takki is focused* yet wakes to announce the moment focus leaves. Takki does not reconfigure the reader from its own process; it detects the reader (`detect_screen_reader()`, ADR-026) and offers a one-time setup suggestion (ADR-013).

**Keypress taxonomy.** The `on_press` handler classifies every event while Takki is foreground; while it is not, every event is ignored and the OS routes keys to whatever now holds focus.

| Class | Condition | Action |
|---|---|---|
| **Talk key** | Matches configured PTT key (default: Right Ctrl) | Dispatch to voice subsystem |
| **Escape** | `Key.esc` | Dispatch to lesson controller (re-read / restart per ADR-025) |
| **Resume hold** | Configured held-key, while PAUSED | Re-acquire foreground; resume |
| **Expected** | `KeyCode` with printable `char` matching current prompt | Correct-chime; advance; record correct in `key_attempts` |
| **Wrong** | `KeyCode` with printable `char` not matching current prompt | Auto-reject sound; re-prompt; record wrong in `key_attempts` |
| **Composing** | `KeyCode` with `char is None` or non-printable | Discard silently — compose in progress |
| **Boundary** | `Key.backspace`, `Key.tab`, `Key.delete`, `Key.enter` | Ignore (Backspace disabled per ADR-012) |
| **System** | All remaining `Key.*` events | Ignore — they reach the OS normally; if one moves focus (Win key → Start menu), the resulting focus-loss pauses the lesson |

The "wrong" class still handles accidental composites: if the engine prompted `a` and the child produced `á` (stale dead-key state), `á` is a wrong answer for `a`; auto-reject fires, the dead-key state is consumed, re-prompt follows. No special case required. The "suppress from OS" column is gone — Takki no longer swallows system keys, because losing focus to them is now the intended pause trigger rather than a leak.

**Listener lifecycle.** The pynput listener is still created once at startup and runs until exit — now without `suppress`. What determines dispatch is the pairing of the lesson engine's active state and the window's focus state, not the listener's configuration.

**App exit.** Removing global suppress makes the conventional paths work again: Alt+Tab away and close, or Task Manager, are always reachable. Signal handlers (`signal.SIGINT`, `signal.SIGTERM`) are still registered at startup for shell and Task-Manager termination, and the voice "stop" intent (ADR-017) remains the primary in-lesson exit. The keyboard-driven emergency exit is correspondingly less acute (see open questions); for Alpha (developer use only) signal handlers plus Task Manager are sufficient.

**Residual leak window.** One keystroke can still land in another app in the gap between focus silently moving and Takki processing the focus-loss event. This is far smaller than the trap it replaces — focus loss is event-driven, not polled — and is double-covered by the screen reader's own focus announcement. Accepted.

### Pre-V1 validation: dead key compose

The event model above relies on pynput's `ToUnicodeEx` threading dead-key compose state correctly through the low-level keyboard hook (`WH_KEYBOARD_LL`). Dropping `suppress=True` removes one variable from this spike — there is no longer a suppressing hook to thread compose state through — but the compose behaviour itself still needs confirming. English (Alpha) and German (Beta) use direct-strike characters only; no dead-key behavior is exercised. Before adding the first dead-key language (Icelandic, French, Czech, or similar in the V1 validation pass), run a one-session spike:

1. On Windows, configure a dead-key layout (e.g., US International with dead keys, or Icelandic).
2. Start a pynput `keyboard.Listener()` (no `suppress`), with Takki's window focused.
3. Print `type(key)` and `key.char` for every `on_press` event while typing `dead-acute + a`, `dead-acute + e`, and AltGr + a.
4. Confirm: dead-key arm event has `char=None` (or is otherwise filtered by the `KeyCode` + printable check); composed result has the correct `char`.

If `ToUnicodeEx` does not thread compose state correctly, the app must maintain its own compose buffer using layout data from `get_layout_positions()`. That would require a follow-up amendment to this ADR and to ADR-005.

### Open questions

1. **Emergency keyboard exit.** Less acute now that global suppress is gone — Alt+Tab away plus window close, or Task Manager, are always reachable, and the voice "stop" intent remains. A held-key exit detecting the hold duration and calling `os.kill(os.getpid(), signal.SIGTERM)` is still worth defining for Beta as a no-voice, no-mouse fallback, but it no longer compensates for a system-wide trap. Deferred to Beta.

   **It must not be bound to Escape** (flagged 2026-08-22, following the carry-forward **D Escape** decision in [ADR-012 § Recovery](0012-audio-feedback-design.md)). Escape now carries a tap/hold pair — tap re-reads, hold past `RESTART_HOLD_MS` (default 800 ms) restarts the word. This paragraph's original sketch of "hold Escape 5 seconds" would sit on top of that: every exit attempt would fire a word restart in passing at 800 ms, and a child who holds Escape too long while trying to re-read would be walking toward an app exit. Two gestures on one key is already the ceiling; a third is not viable. Beta must pick a different key for the emergency exit, and should prefer one with no lesson meaning at all — the taxonomy's **System** row (all remaining `Key.*`) is where an unbound candidate will come from. Whichever key is chosen, the same auto-repeat rule applies: the hold timer starts on the first press and is cleared only by the release.

4. **NVDA app-module auto-sleep.** Optionally ship an NVDA app module that auto-enables sleep mode for the Takki executable, making the self-voicing echo suppression automatic rather than a one-time setup suggestion (ADR-013). NVDA-specific, no admin needed, but adds an installer artifact and touches the user's NVDA add-ons directory. Decide in Beta alongside real NVDA/JAWS coexistence testing.

2. **Per-profile mechanism override for dual-path languages.** Inherited from ADR-023 open question 1: a Latvian adult who already uses dead-key paths may want to keep that motor pattern. Hard-default to AltGr for v1 child learners. No decision needed before Beta (Latvian is not in the Beta language set).

3. **Phase B anchor when base letter is in active ramp-up.** If a composite is first introduced before its base letter has cleared Phase D, Phase B alternation with the base letter would interleave a composite in Phase B with a letter still in Phase A/B. In practice the modifier always ranks later than the base letter in the Phase 2 frequency sequence (ADR-023: Polish AltGr at step 12–15; Icelandic dead-acute at step 18), so the base letter is well past Phase D when the composite's Phase B runs. Verify per-language during V1 spike to confirm no layout places a modifier unusually early.
