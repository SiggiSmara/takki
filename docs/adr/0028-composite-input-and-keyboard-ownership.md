# ADR-028: Composite Input and Keyboard Ownership

**Status:** Accepted  
**Date:** 2026-06-14  
**Revised:** 2026-06-21 — §C8 keyboard ownership reworked: global `suppress=True` replaced by focus-gated dispatch over an always-on window.  
**Amended:** 2026-09-26 — § Event model's premise refuted on hardware (alpha session 12b-2): pynput never delivers a composed character. The capture source is re-decided in alpha #13; see [roadmap A5](../roadmap.md#a-bites-alpha-specifically-the-next-step).
**Amended:** 2026-09-29 — § C8 (alpha #12c and the #12b-2 E2/E3 result): the focus source drains SDL's whole queue every tick; in Alpha the pause announcement names Alt+Tab, and the held-key raise is deferred to Beta.  
**Amended:** 2026-11-01 — § Event model decided (alpha #13, [research/key-capture-source.md](../research/key-capture-source.md)): Takki takes characters and key state from its own window (SDL), not from pynput's hook. Pointers added where § C8 and § Pre-V1 validation assumed pynput. Built in alpha #14.  

> Part of the [Takki architecture](../architecture.md).  
> Closes roadmap issues B5, B7, and C8. Amends [ADR-024](0024-drill-content-and-lesson-granularity.md), and (per the 2026-06-21 revision) [ADR-016](0016-visual-display-design.md) and [ADR-026](0026-platform-interface-abstraction.md). Extends [ADR-005](0005-keyboard-handling.md) and adds the `FocusSource` Protocol to [ADR-019](0019-testing-strategy-and-io-isolation.md).

---

**Decision:** The lesson engine processes only complete characters, which Takki takes from its own window (SDL `TEXTINPUT`); a key's press and release (`KEYDOWN`/`KEYUP`) name the physical key, and a press that produces no character (a dead key arming, AltGr alone) reaches no lesson logic. Composites are drilled as whole graphemes — the modifier is never a drill prompt in isolation. Phase 2 pairs with two typeable characters use interleaved Phase A (L-R-L-R); pairs where one member is a modifier give Phase A/B to the typeable member only. Keyboard ownership is scoped by an always-on focus-owning window, not by global suppression (revised 2026-06-21): key events drive a drill only while Takki holds OS foreground, and Takki pauses the instant focus moves elsewhere — intentional task-switch, focus theft, or OS secure desktop alike. See *Keyboard focus and ownership (C8)* below.

### What ADR-005/023/024 decided, and what was missing

[ADR-005](0005-keyboard-handling.md) established that pynput reports the already-translated character, and that "dead keys and AltGr combinations are handled by Windows before the app sees them." [ADR-023](0023-key-introduction-protocol.md) then made modifier keys (AltGr, dead-key) first-class participants in Phase 2, each with its own introduction step. [ADR-024](0024-drill-content-and-lesson-granularity.md)'s four-phase ramp-up was written for a single typeable key: Phase A is "the child types the new key alone, repeatedly."

Three gaps follow from these decisions taken together (roadmap B5, B7, C8):

- **B5 (composite input):** You cannot type AltGr alone or dead-acute alone and receive a character event. Phase A as written has no meaning for a modifier. ADR-023's composite introduction script ("press the accent key first, then the base letter") implies composites are drilled as units, but the Phase 2 sequence ranks the modifier as a standalone step and expects a drill loop to follow.
- **B7 (pair ramp-up):** Phase 2 introduces two keys per step; ADR-024's ramp-up is written for one. Phase A for two simultaneous new keys is undefined. A Phase 2 step can pair a modifier (no standalone Phase A possible) with a typeable letter, making the "interleave both" path nonsensical.
- **C8 (keyboard ownership):** pynput's listener is a global hook. Without a focused window (audio-only mode, default), every character the child types also reaches whatever app is in the background. No ADR defines a keypress taxonomy — accepted vs wrong vs boundary vs swallowed — nor the listener's suppression policy or lifecycle.

English (Alpha) and German (Beta) both use direct-strike characters exclusively; the composite-input model is confirmed by design but requires no spike until the first dead-key language enters the V1 validation pass. The keyboard-ownership decisions are needed for Alpha.

### Event model

**Takki takes its key events from its own window** ([ADR-005](0005-keyboard-handling.md)). The window that has focus is given the character Windows produced, from its own thread's layout and compose state. Takki counts keys only while that window is its own, so the window holds the authoritative answer. Measured in alpha #13 ([research/key-capture-source.md](../research/key-capture-source.md); **[M]** measured, **[A]** argued):

| Physical input | What the window delivers |
|---|---|
| Regular letter | `KEYDOWN` with its scan code, then `TEXTINPUT` `a`, then later `KEYUP` **[M]** |
| Dead key | `KEYDOWN` with its scan code (Icelandic `´` 52, German `^` 53), and **no** `TEXTINPUT` **[M]** |
| Base letter after it | `KEYDOWN`, then `TEXTINPUT` `á` **[M]** |
| Dead key then Space, itself, or a letter it cannot combine with | `´`, `´´` and `´k`, exactly as Windows composes them. The last is **two** `TEXTINPUT`s from one press **[M]** |
| AltGr + letter | `TEXTINPUT` `@`; AltGr's fake Left Ctrl arrives as a Left Ctrl `KEYDOWN` too **[M]** |
| Enter, Backspace, Tab, Shift, Caps Lock, Ctrl, Alt, Windows, F-keys | `KEYDOWN`/`KEYUP` with scan code, no `TEXTINPUT` **[M]** |
| Space | `KEYDOWN` and `TEXTINPUT` `' '` **[M]**. Space is System by its key, never by its text |
| A held key | one `KEYDOWN`; its `TEXTINPUT` repeats with no fresh `KEYDOWN`, because pygame drops SDL's repeat `KEYDOWN`s **[M]** |
| A layout switch (Win+Space) | `KEYMAPCHANGED` **[M]** |
| Any key while another window has focus | Nothing **[M]** |

`PygameFocusSource.poll()` drains SDL's queue once a tick and hands each event to `WindowKeyReader` (`takki.input.window_keys`), which turns it into `KeyDown(scancode, key)`, `KeyUp(scancode, key)`, `TextTyped(text, scancode, fresh)` or `KeymapChanged()`. pygame's `KEYDOWN.unicode` is never read: it is not the composed character, and reported `^^` for `^` `k` **[M]**.

**A `TEXTINPUT` is fresh exactly when a `KEYDOWN` came since the last one, while that key is down.** That agreed with SDL's own repeat flag for 764 of 764 `TEXTINPUT`s **[M]**. Text with no key down behind it is never fresh. Fresh text is a first press; text that is not fresh is a repeat, which [ADR-027](0027-key-and-accuracy-state-model.md)'s held-key rule says is not an attempt.

**One press that produced two characters is one attempt, judged by its first character.** A dead key followed by a letter it cannot combine with gives `´` then `k` from the one press of `k`. The reader marks the first fresh and the second not, so the engine counts `´` against the prompt, and `k` is a repeat. *Decided by the developer, 2026-11-14 (alpha-plan #14a).*

The lesson engine processes only a `TextTyped` with printable text, folded to lower case at the boundary (ADR-027). It has no concept of "modifier key" or "compose state": `'á'` and `'a'` are equally atomic inputs, and no compose-state management belongs inside the engine. A key's `KEYDOWN` reaches the lesson engine only as the name of a physical key, which nothing in a lesson answers; the keyboard alignment answers it ([ADR-005 § What the keyboard alignment reads from a key](0005-keyboard-handling.md)).

**Compose state at prompt advance.** If a child presses a dead key mid-drill and the engine's auto-advance timeout fires before they press the base letter, the compose state stays armed, 3 s later in the trial **[M]**. The next character the child produces is the composed result. The engine compares it to the current prompt and processes it normally: correct if it matches, auto-reject if not. The stale compose is consumed in either case. No explicit flush at prompt boundaries is needed. Leaving the window clears the armed state too (7 of 7) **[M]**.

**The keyboard alignment does disarm.** A dead key pressed while the alignment runs would compose the first letter typed after it. So every key pressed during the alignment is disarmed once it is up, through the platform function `disarm_dead_key()` ([ADR-026](0026-platform-interface-abstraction.md)), on the window's thread (10 of 10 **[M]**). Lessons never do, because a composite must still compose. The rule and its reasons are in [ADR-005](0005-keyboard-handling.md) and [ADR-033](0033-rest-keys-and-keyboard-alignment.md).

**A layout switch mid-session is not silent.** The window's characters follow the new layout **[M]**, and `KEYMAPCHANGED` reaches the core. What Takki says about it is [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)'s.

**Rejected alternatives for the source:**
- **pynput's global keyboard hook**, the source until alpha #14. Measured in alpha 12b-2 and #13: pynput looks each key up in a table built once, compose state flushed, for the layout its listener started with. So a dead key arrives as its standalone character, the letter after it uncomposed, and a prompted `á` can never be answered **[M]**. After a layout switch its key codes follow the new layout while its table stays on the old one, so it mixes the two **[M]**. It lost Right Shift's release both times the Filter Keys box opened **[M]**.
- **pynput repaired with Windows' own `ToUnicodeEx` on a private thread.** It matched the window in all 68 ordinary steps **[M]**, but only by copying state Windows keeps for the window: the window's layout on every key, the clearing of an armed dead key on every focus change, and keys the window never received, such as the Space of Win+Space **[M]**. That second copy of Windows' state is what failed in pynput itself.
- **Both: the hook for key state, the window for the character.** It pairs two streams: in Takki's 60 Hz loop 14% of presses split across ticks and 0.8% interleave with another key **[A, replayed from measured times]**, and it keeps the hook's mixed layouts and lost releases.
- **Merging a press's two characters into one answer (`´k`)**, #13's first suggestion for the counting rule. From pygame's queue it looks the same as a held key whose first repeat lands in the same drain after a stall of the loop, which it would score as a wrong two-character press.

### Composite ramp-up (B5)

*(2026-11-12, alpha-plan #12m session (6): written in phases, which [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels) replaced with a ladder of Reach, Choose and Travel; see "Built, #12m session (6)" there. Read for the ladder, decided by the developer: **a composite takes Reach** like any letter typed with a key off its finger's rest key. A Reach prompt asks for the whole grapheme, as Phase A did, and the rest cue after it waits for a press on the rest key of **both** fingers it was typed with, the modifier's and the base letter's, in either order: for Icelandic `é`, `æ` and `d`; for `á`, `æ` and `a`, although the left little finger never left `a`. "Rest" means every finger back. Phase B's alternation with the base letter goes with Phase B; Choose and Travel draw a composite like any letter. A composite has no Reach only when its modifier and its base are both rest keys, which needs a dead key as a rest key: [ADR-033](0033-rest-keys-and-keyboard-alignment.md) allows one and nothing can land on one yet, and a rest cue waiting for a dead key cannot be answered today, since its press reaches the engine with no character. Both go with the first dead-key language's alignment work (§ Event model, "Decided").)*

ADR-024's Phase A through D is amended for composite graphemes.

**Phase A — whole grapheme repeated.** "Type the new key alone, repeatedly" becomes "type the whole grapheme repeatedly." The engine prompts `á`; the child presses dead-acute then `a`; the window gives `TEXTINPUT` `á`; the engine records a correct attempt. Ten consecutive correct attempts advance to Phase B. The two-keystroke mechanism is entirely invisible to the engine.

**Phase B — alternate composite with base letter.** The same-finger anchor for a composite is its base letter: for `á`, the anchor is `a`. The child alternates `á ↔ a`. Both use the same physical key, with and without the modifier gesture — this trains the modifier as a contextual overlay on an already-known key rather than a foreign motor pattern. Phase B thresholds from ADR-024 (20 attempts, ≤ 1 rejection) apply unchanged.

**Phases C and D** — unchanged. The composite enters the selection pool on equal footing with direct-strike characters.

This amendment overrides ADR-024's "new key alone" and "same-finger home-row neighbour" phrasing for composite graphemes only. For direct-strike keys ADR-024 stands unmodified.

### Modifier introduction

*(Rewritten 2026-08-23 by [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md), which makes introduction grapheme-led. The superseded version gave the modifier a step of its own at its aggregate-composite-frequency rank; the text below is what replaces it.)*

A modifier key (AltGr, dead-acute, dead-macron, etc.) has **no step of its own and no place in the introduction order**. It is introduced inside the step that introduces the **first composite grapheme requiring it**, which arrives at that grapheme's own frequency rank. When such a step arrives:

1. The engine plays the composite's introduction script (ADR-023 § Composite letters), which carries the modifier inside it: the letter, then how it is typed, then the modifier's name, location and mechanism. For example: *"New letter: á. Press the accent key, then A. The accent key lives one position to the right of Æ, and makes no sound on its own."* All of it comes from the per-language YAML ([ADR-022](0022-localisation-strategy.md)).
2. The modifier does **not** enter Phase A or Phase B, and is never a prompt target. The **composite** runs the four-phase ramp-up like any other new letter — it is a character the child produces, so it is drilled, counted and measured as one.
3. Later composites on the same modifier introduce no key at all and skip the mechanism explanation; they are new letters made of keys the child already has.

**Closed 2026-08-23 by [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md)** *(raised 2026-08-22 by alpha session 7 as [roadmap B8](../roadmap.md#b-places-where-two-accepted-adrs-disagree); sharpened by session 8).* The superseded item 3 tested composite availability against "both modifier and base letter have `key_stats` rows", and a modifier can never acquire one: it is never a prompt target, and [ADR-027](0027-key-and-accuracy-state-model.md) § First-Attempt Counting creates the row on the first counted keystroke. So no composite could ever unlock, and — because the introducer's session-local record could not retire it either — the accent key was re-announced in every session, forever, once the rest of the sequence was exhausted. Grapheme-led introduction removes the state the test asked about rather than adding a second definition of Active: the composite's own introduction is the event, and the composite is a prompt target like any other letter.

The modifier's introduction is therefore one clause inside a letter's introduction, immediately followed by that letter's own four-phase ramp-up (see below).

### Pair ramp-up (B7)

*(2026-11-12, alpha-plan #12m session (6): the per-phase rules below are replaced by [ADR-024](0024-drill-content-and-lesson-granularity.md#pairs)'s "Pairs" for the ladder. At Reach a pair's cycles take turns, left-hand member first, each letter followed by its rest cue, and a member with no Reach is not prompted until the step reaches Choose; at Choose and Travel the members are drawn with the others of the set, not interleaved. The step climbs together, and each member's rule is its own, so "a slow right hand cannot mask a poor left hand" still holds. What the step selects is unchanged: the member count, never the key count.)*

An introduction step carries one or two **graphemes**, left-hand member first (ADR-023 § What an introduction step is; [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md) § Decision 1 for why the member is a grapheme and not a key). The adaptation to ADR-024's single-key phases depends on the step's contents, **not on which stage or ordering produced it** *(generalised 2026-08-23 by [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md): this section previously keyed off "Phase 2", which is now one candidate ordering's internal structure — the rules below apply equally to Stage 0's three pairs and to any future ordering's steps)*.

**Both members are typeable characters (common case):**

- **Phase A:** the engine interleaves prompts — L, R, L, R — until each has 10 consecutive correct responses. The 10-each threshold is per-key, not shared, so a slow right hand cannot mask a poor left hand.
- **Phase B:** four-way alternation — L-anchor, L-new, R-anchor, R-new. Each new key alternates with its own same-finger anchor. If one new key has no same-finger anchor yet (possible for very early steps), use the nearest known key on the same hand. Threshold: 20 attempts each, ≤ 1 rejection per key.
- **Phases C and D:** both keys join the shared pool with no further pair treatment.

**A member is a composite** *(reshaped 2026-08-23 by [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md) — a modifier is no longer a step member of its own, it rides in on a composite):*

- The **composite** is drilled like any other new letter, because that is what it is. Its Phase B anchor is its base letter (§ Phase B above), and the modifier receives its spoken clause inside the introduction and **no drill of its own** — it is never a prompt target.
- **A solo composite step** runs Phase A through D as a solo ramp-up, with no L-R interleaving.
- **A composite paired with a direct-strike letter** takes the common case above unchanged: two typeable characters, interleaved L-R in Phase A and alternated four ways in Phase B. *(Added 2026-08-23, alpha session 8c, which built the first step of this shape. The rule above read as though a composite always ramped up alone, and under ADR-032 that is no longer true: a composite is pooled by the hand of its base stroke and can therefore be the frequency leader of one hand while an ordinary letter leads the other. Real Icelandic produces `á`+`ð` at step 10. Such a step carries two graphemes and **three** physical keys, which is the first time a step's key count and its member count come apart — a consumer that sized anything off the key count would mis-drill it.)*
- Composites enabled by the modifier appear in Phase C/D of the typeable member's ramp-up if prerequisites are met at that point, or in subsequent steady-state drilling.

**What the step selects, and what it does not** *(added 2026-08-23, alpha session 9, which built the consumer.)* The branch table above is read off the step's **members** — one or two, composite or direct — and that is all it is read off. Two things sit next to it and are deliberately not part of it:

- **Physical key count selects nothing.** `á`+`ð` is two members and three keys; a consumer that sized the interleave, the four-way alternation or anything else off the key count would mis-drill it. The member count is the only count this table uses.
- **Stage 0 substitutes Phase A's *content*, and that is a different question from which branch runs.** The pair branch runs for Stage 0's three steps exactly as it does for any other pair — this section's "not on which stage or ordering produced it" stands unqualified. What Stage 0 changes is what Phase A is *made of*: alternation with the column anchor instead of repetition, per [ADR-024](0024-drill-content-and-lesson-granularity.md) § Lesson granularity and [ADR-027](0027-key-and-accuracy-state-model.md) § The Anchor Gate. A step shape this table does not cover is an amendment here; Stage 0 is not one.

**Layer-2 unlock.** ADR-010's "≥ 8 active keys" check fires after each introduction step. Pair introduction advances the count by 2 per step in the typical case *(never 1 for a modifier's sake — from ADR-032 every step member is a typeable grapheme and counts; a solo step advances it by 1 because it is solo)*. On English QWERTY the home-row typeable character count is 9 — A S D F G H J K L; the right-pinky home position `;` is not a letter — so the count goes 2, 4, 6, 7 (step 4 introduces A solo), 9 (G+H). Layer 2 unlocks at count 9, which satisfies the ≥ 8 threshold. Layouts whose home rows yield exactly 8 typeable characters trigger the unlock at the same count. No change to the threshold is needed.

*(Arithmetic superseded 2026-09-10, alpha session 10, which built the predicate. The walk above predates Stage 0 ([ADR-023](0023-key-introduction-protocol.md) § Stage 0, added by session 8b), which sits in front of the strategy and hands it `f`/`j` as already-had. All three Stage 0 steps are pairs, so the shipped English count goes **2, 4, 6, 8** — `f`+`j`, `r`+`u`, `v`+`m`, then the strategy's `d`+`k` — and never passes through 7. The unlock therefore fires one step earlier than this paragraph says, landing on the threshold exactly rather than overshooting it to 9; `a` still arrives solo, but two steps later at count 11. The paragraph's conclusion is what survives, and it anticipated this case in its own last two sentences: no change to the threshold is needed. Both walks are pinned in `tests/test_progression.py::TestLayerTwoUnlock` — the one above as the strategy's own arithmetic, the shipped one against `KeyIntroducer`.)*

**The count is Active, not Known** *(stated 2026-09-10, alpha session 10.)* This paragraph is the authority on that: it fires the check "after each introduction step" and moves the count by the step's member count, which only Active can do — Known needs 90 attempts across two calendar days ([ADR-027](0027-key-and-accuracy-state-model.md) § Key States), so a Known-counted unlock could not move at an introduction at all. [ADR-010](0010-lesson-structure-and-progression.md) § Progression Rules writes it as "≥ 8 keys are known", which is that ADR's pre-ADR-027 vocabulary for *introduced*; [ADR-027](0027-key-and-accuracy-state-model.md) § Milestone Ladder already reads it as "≥ 8 Active keys". `takki.lesson.progression.layer_two_unlocked` counts Active graphemes on the current layout.

**Encouragement framing.** ADR-012's pre-introduction line ("learn your next letter and you'll be able to type X% more everyday words") becomes plural for a two-character pair: *"Your next two letters will let you type X% more everyday words."* X is the combined marginal coverage gain. *(Simplified 2026-08-23, alpha session 8c: the old sentence carved out the case where "one pair member is a modifier" and told the line to quote the typeable member only. There is no such member any more, and the carve-out has inverted — a composite **is** typeable the moment its step lands, so it contributes its own coverage to X like every other letter.)*

### Keyboard focus and ownership (C8)

> **Originally decided (2026-06-14):** pynput started with `suppress=True`, making Takki the exclusive system-wide keyboard owner during a lesson — every keypress consumed, nothing forwarded to the OS or any focused window. The aim was to eliminate input bleed in audio-only mode (no window): without suppression, every character the child types also reaches whatever is focused in the background — a browser address bar, a rename dialog, a search box.
>
> **Revised (2026-06-21):** global suppression is replaced by **focus-gated dispatch over an always-on window.** Suppress prevented the leak but created two worse problems it never addressed. It *trapped* the user: a child or parent could not switch to another app without killing Takki — even Alt+Tab was swallowed. And it was *blind to OS preemption*: on the secure desktop (UAC, Ctrl+Alt+Del, lock, fast-user-switch) a low-level hook receives nothing, so the child typed into silence with no feedback and Takki could not tell it had lost the keyboard. The governing reframe is that the child is not learning to type in a vacuum — navigating the OS is part of what they are learning — so a keystroke that opens the Start menu and pauses the lesson is correct cooperative behaviour, not a leak to be suppressed.

**Always-on focus-owning window.** Takki always creates an OS window — the same SDL/pygame window used for the optional visual display (ADR-016), blank when the visual profile is off. The window is the focus anchor; the child, who navigates by audio, never needs to see it. Keyboard capture is thereby *scoped by focus* instead of by a global suppressing hook.

**The window is the key source; dispatch is focus-gated.** Key events come from the focused window itself ([§ Event model](#event-model)), and are processed as drill input only while Takki's window holds OS foreground. While it does, the focused window consumes the keystrokes, so nothing leaks; while it does not, Takki is paused by definition. A window produces key events only while it has focus **[M]**, so the gate is a backstop rather than the only filter. `suppress=True` is gone with the hook.

**Focus is the single active/paused signal.** Intentional task-switch, a focus-stealing notification, and OS secure-desktop preemption all manifest as the same event: Takki's window is no longer foreground. One mechanism — window focus events (`WINDOWFOCUSGAINED` / `WINDOWFOCUSLOST`) behind the `FocusSource` Protocol (ADR-019) — covers what were three separate problems. On focus loss Takki enters PAUSED and announces it; a foreground poll backs up the event in case a secure-desktop transition does not deliver one.

**The focus source drains SDL's whole queue every tick.** `PygameFocusSource.poll()` takes every queued event in order, hands each key event (`KEYDOWN`, `KEYUP`, `TEXTINPUT`, `KEYMAPCHANGED`) to the key reader and acts on each focus change and `QUIT`, and drops every other type. It once took only focus and `QUIT` and left the rest. Nothing else reads SDL's queue, so mouse motion and key events piled up to SDL's 65,535-event cap, after which SDL refuses every new event, `QUIT` and focus changes included: the close button stopped working after 18–20 minutes of mouse movement (windows-validation E10; confirmed fixed by the fix-verification run's FV-03). **The rule for anything that reads SDL's queue:** one reader drains it whole every tick and hands each type to its consumer. A type-filtered `get()` that leaves other types queued brings the cap back, and a second `get()` would split one ordered stream in two. The order matters: SDL releases every held key just before it reports `WINDOW FOCUS_LOST`, in the same drain **[M]**, and those releases must reach the down-state before the pause.

**Resume: Alt+Tab.** The way back to Takki is Alt+Tab, which Windows handles, and which any running screen reader announces. The pause announcement says so: *"Paused. Press Alt+Tab to come back to Takki."* A `FocusGained` is what resumes, by whatever route focus came back. Beta's voice "resume" intent (ADR-017) needs the talk key to be seen while Takki is unfocused, which the window cannot do (§ Event model); whether Beta gets a narrow global hook or `RegisterHotKey` for the talk key, and whether any raise can get past Windows' foreground-activation lock without elevation, are Beta's.

**No held resume key** (decided by the developer, alpha-plan #14b, 2026-11-14). Rejected, kept here once: a configured key held while PAUSED, seen through the global hook, that asked Windows to raise Takki's window (`SDL_RaiseWindow`, fire-and-forget, with a deadline whose expiry spoke the Alt+Tab hint). On the test laptop the raise never brought Takki back from any app, most likely refused by the foreground-activation lock (windows-validation E2/E3, 2026-09-28), and its F1 sat behind Fn on laptops, so the child ended one window further away. From the window a key pressed while Takki is unfocused never arrives at all **[M]**, so the key could not even be seen.

**The FSM's starting state arrives as an event.** `FocusSource` deliberately exposes no focus *query*, and the focus events are edge-triggered, so a window that comes up **unfocused** would emit nothing and leave the FSM wrongly ACTIVE for the whole run, dispatching another application's keystrokes into the lesson with no pause announcement. `FocusSource` implementations therefore emit their initial state once at construction, before any key event can arrive; the FSM starts ACTIVE and that seed corrects it. A seeded `FocusGained` on the normal path is silently absorbed, since the FSM is already ACTIVE.

This is also why an always-on window is load-bearing beyond focus ownership: without a window there is nothing to hold focus and nothing to read keys from.

**Screen-reader cooperation.** A VI child's machine very likely runs a screen reader (NVDA, JAWS, Narrator), and the focus-owning window cooperates with it rather than fighting it:
- The reader announcing the new foreground app on focus loss is a *second* channel telling the child they have left a drill — reinforcing Takki's own announcement.
- Its keystroke echo would otherwise double Takki's chimes during a drill. Takki is a **self-voicing application**; the intended fix is the reader's own mechanism for that case — NVDA's **sleep mode**, which is scoped to the focused app, so it silences echo *while Takki is focused* yet wakes to announce the moment focus leaves. Takki does not reconfigure the reader from its own process; it detects the reader (`detect_screen_reader()`, ADR-026) and offers a one-time setup suggestion (ADR-013).

**Keypress taxonomy.** The focus model classifies every key event while Takki is foreground (`takki.input.taxonomy.classify`); while it is not, every key event is dropped. A key is named by its SDL scan code; a character by its `TEXTINPUT`.

| Class | Condition | Action |
|---|---|---|
| **Talk key** | `KEYDOWN` of the configured talk key (default Right Ctrl, scan code 228) | Dispatch to voice subsystem (Beta; dropped in Alpha) |
| **Escape** | `KEYDOWN`/`KEYUP` of the re-read and restart keys (default Escape, 41) | Dispatch to lesson controller (re-read / restart per ADR-025) |
| **Expected** | `TEXTINPUT` with printable text matching current prompt | Correct-chime; advance; record correct in `key_attempts` |
| **Wrong** | `TEXTINPUT` with printable text not matching current prompt | Auto-reject sound; re-prompt; record wrong in `key_attempts` |
| **Composing** | A `KEYDOWN` that produces no `TEXTINPUT` (a dead key arming, AltGr alone), or non-printable text | Nothing in a lesson answers it |
| **Boundary** | `KEYDOWN` of Backspace, Tab, Delete, Enter, keypad Enter | Ignore (Backspace disabled per ADR-012) |
| **System** | Every other key, and the space bar's `' '` | Ignore — they reach the OS normally; if one moves focus (Win key → Start menu), the resulting focus-loss pauses the lesson |

Expected and Wrong are one class, `Character`, at the boundary: splitting them needs the prompt, which the lesson engine holds. Every `KEYDOWN` that is no binding is also passed on as the physical key it names (`Pressed`), which only the keyboard alignment answers ([ADR-033](0033-rest-keys-and-keyboard-alignment.md)). A letter's `KEYDOWN` is therefore System by its key, and its character comes as its own `TEXTINPUT`. Composing is not a class of its own for a `KEYDOWN`: nothing at a `KEYDOWN` says whether a `TEXTINPUT` will follow, and no lesson answers a key either way. Every `KEYDOWN` is a new press: pygame passes none for an auto-repeat, and the focus model ignores none.

**The space bar lands in System, deliberately, by its key.** The window gives it the text `' '`, so it is classified by its scan code (44), never by its text, and falls through to *ignore*, which is correct: [ADR-023](0023-key-introduction-protocol.md) § "The space bar is likewise never introduced" scopes it out of the curriculum until the post-V1 full-text stage.

The "wrong" class still handles accidental composites: if the engine prompted `a` and the child produced `á` (stale dead-key state), `á` is a wrong answer for `a`; auto-reject fires, the dead-key state is consumed, re-prompt follows. No special case required. The "suppress from OS" column is gone — Takki no longer swallows system keys, because losing focus to them is now the intended pause trigger rather than a leak.

**No listener.** Keys come from the SDL queue the main thread already drains, so there is no listener thread to start, stop or join ([concurrency-model.md](../concurrency-model.md)). What determines dispatch is the pairing of the lesson engine's active state and the window's focus state.

**App exit.** Removing global suppress makes the conventional paths work again: Alt+Tab away and close, or Task Manager, are always reachable. Signal handlers (`signal.SIGINT`, `signal.SIGTERM`) are still registered at startup for shell and Task-Manager termination, and the voice "stop" intent (ADR-017) remains the primary in-lesson exit. The keyboard-driven emergency exit is correspondingly less acute (see open questions); for Alpha (developer use only) signal handlers plus Task Manager are sufficient.

**Residual leak window.** One keystroke can still land in another app in the gap between focus silently moving and Takki processing the focus-loss event. This is far smaller than the trap it replaces — focus loss is event-driven, not polled — and is double-covered by the screen reader's own focus announcement. Accepted.

### Pre-V1 validation: dead key compose

Run in alpha #13, on Icelandic and German, by hand and injected, against Takki's own window ([research/key-capture-source.md](../research/key-capture-source.md)): the window delivers Windows' own composed character, so the app maintains no compose buffer. What is left before the first dead-key language ships is checked by hand in alpha-plan #14c: a composed `á` at Takki's boundary on a run started on Icelandic, how AltGr, left Ctrl and each dead key arrive in the alignment per language, and the alignment's disarm seen on hardware.

### Open questions

1. **Emergency keyboard exit.** Less acute now that global suppress is gone — Alt+Tab away plus window close, or Task Manager, are always reachable, and the voice "stop" intent remains. A held-key exit detecting the hold duration and calling `os.kill(os.getpid(), signal.SIGTERM)` is still worth defining for Beta as a no-voice, no-mouse fallback, but it no longer compensates for a system-wide trap. Deferred to Beta.

   **It must not be bound to Escape** (flagged 2026-08-22, following the carry-forward **D Escape** decision in [ADR-012 § Recovery](0012-audio-feedback-design.md)). Escape now carries a tap/hold pair — tap re-reads, hold past `RESTART_HOLD_MS` (default 800 ms) restarts the word. This paragraph's original sketch of "hold Escape 5 seconds" would sit on top of that: every exit attempt would fire a word restart in passing at 800 ms, and a child who holds Escape too long while trying to re-read would be walking toward an app exit. Two gestures on one key is already the ceiling; a third is not viable. Beta must pick a different key for the emergency exit, and should prefer one with no lesson meaning at all — the taxonomy's **System** row (every other key) is where an unbound candidate will come from. Whichever key is chosen, the same auto-repeat rule applies: the hold timer starts on the first press and is cleared only by the release.

4. **NVDA app-module auto-sleep.** Optionally ship an NVDA app module that auto-enables sleep mode for the Takki executable, making the self-voicing echo suppression automatic rather than a one-time setup suggestion (ADR-013). NVDA-specific, no admin needed, but adds an installer artifact and touches the user's NVDA add-ons directory. Decide in Beta alongside real NVDA/JAWS coexistence testing.

2. **Per-profile mechanism override for dual-path languages.** Inherited from ADR-023 open question 1: a Latvian adult who already uses dead-key paths may want to keep that motor pattern. Hard-default to AltGr for v1 child learners. No decision needed before Beta (Latvian is not in the Beta language set).

3. **Phase B anchor when base letter is in active ramp-up.** If a composite is first introduced before its base letter has cleared Phase D, Phase B alternation with the base letter would interleave a composite in Phase B with a letter still in Phase A/B. In practice the modifier always ranks later than the base letter in the Phase 2 frequency sequence (ADR-023: Polish AltGr at step 12–15; Icelandic dead-acute at step 18), so the base letter is well past Phase D when the composite's Phase B runs. Verify per-language during V1 spike to confirm no layout places a modifier unusually early.

### Changes

- 2026-11-14, alpha-plan #14b, built from the window: § Event model restated for the window (its table in SDL's terms, the fresh rule, the counting rule for a press with two characters, the alignment's disarm), with pynput, its repair, the two-stream pairing and the merged two-character answer kept once as rejected alternatives. § C8: the window as key source, the one drain handing key events to the reader, Alt+Tab as the way back with no held resume key (kept once as rejected; `request_foreground()` and the request deadline went with it), the taxonomy in SDL's terms with no Resume hold row, the space bar by its key, no listener. § Pre-V1 validation restated as run, with what #14c checks. ADR-033's pending amendment (a press with no character in the alignment, a dead key as a rest key) is made here and in ADR-005.
