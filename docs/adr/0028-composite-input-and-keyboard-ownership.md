# ADR-028: Composite Input and Keyboard Ownership

**Status:** Accepted  
**Date:** 2026-06-14  
**Revised:** 2026-06-21 — §C8 keyboard ownership reworked: global `suppress=True` replaced by focus-gated dispatch over an always-on window.  
**Amended:** 2026-09-26 — § Event model's premise refuted on hardware (alpha session 12b-2): pynput never delivers a composed character. The capture source is re-decided in alpha #13; see [roadmap A5](../roadmap.md#a-bites-alpha-specifically-the-next-step).
**Amended:** 2026-09-29 — § C8 (alpha #12c and the #12b-2 E2/E3 result): the focus source drains SDL's whole queue every tick; in Alpha the pause announcement names Alt+Tab, and the held-key raise is deferred to Beta.  
**Amended:** 2026-11-01 — § Event model decided (alpha #13, [research/key-capture-source.md](../research/key-capture-source.md)): Takki takes characters and key state from its own window (SDL), not from pynput's hook. Pointers added where § C8 and § Pre-V1 validation assumed pynput. Built in alpha #14.  

> Part of the [Takki architecture](../architecture.md).  
> **Amendment pending from [ADR-033](0033-rest-keys-and-keyboard-alignment.md) (2026-10-10):** what the keyboard alignment needs from key events; a dead key as a rest key waits on the key-capture decision. Not yet made here ([alpha-plan](../alpha-plan.md) #12m). *(2026-11-01: the key-capture decision is made, and it answers the dead-key question; see § Event model, "Decided". What the alignment does with the answer is still #12m's amendment.)*
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

> **Refuted on hardware (2026-09-26, alpha session 12b-2, [windows-validation](../research/windows-validation.md) C6).** The event model above does not hold for a pynput hook. On the Icelandic layout, the dead acute then `a` arrive as:
>
> | Physical input | What the hook delivers | What this section says |
> |---|---|---|
> | Dead-key press | `KeyCode(char='´', is_dead=True)`; `translate()` keeps only `'´'` | `None` or a combining character, discarded as *Composing* |
> | Base letter after it | `KeyCode(char='a')` | `KeyCode(char='á')` |
>
> pynput does not call `ToUnicodeEx` per keypress, because calling it from the hook would disturb the compose state of the application that has focus. It looks each key up in a table built once, compose state flushed, for the layout its listener thread started with. So the compose buffer this section relies on is never consulted, and the Windows application with focus is the only place `á` exists. Consequences under the code as built: `'´'` is printable, `classify()` returns it as a `Character`, and a prompted `á` can never be answered. The "Compose state at prompt advance" paragraph falls with it. **Nothing here changes Alpha**, whose English has no dead key. The capture source is re-decided in [alpha-plan](../alpha-plan.md) #13, with the candidates in [roadmap A5](../roadmap.md#a-bites-alpha-specifically-the-next-step); this section is rewritten when that decision lands, not before.

> **Decided (2026-11-01, alpha #13).** **Takki takes its key events from its own window.**
> - The character is SDL's `TEXTINPUT`.
> - Physical key state (press, release, repeat, which key) is SDL's `KEYDOWN`/`KEYUP`, identified by scan code.
> - pynput leaves Takki's input path.
>
> The measurements are in [research/key-capture-source.md](../research/key-capture-source.md). There, **[M]** marks a claim backed by a recorded log and **[A]** one that is argued. Built in [alpha-plan](../alpha-plan.md) #14, which rewrites the table at the top of this section and the taxonomy's conditions in SDL's terms. Until then, both still read as pynput.
>
> **Why the window.** The low-level hook sees a key before Windows turns it into a character. The window that has focus gets the character Windows produced, from its own thread's layout and compose state. Takki counts keys only while that window is its own, so the window holds the authoritative answer, and the hook can only reconstruct it.
>
> **What the window delivers:**
>
> | Physical input | What the window delivers |
> |---|---|
> | Dead key | `KEYDOWN` with its scan code (Icelandic `´` 52, German `^` 53), and **no** `TEXTINPUT` **[M]** |
> | Base letter after it | `KEYDOWN`, then `TEXTINPUT` `á` **[M]** |
> | Dead key then Space, itself, or a letter it cannot combine with | `´`, `´´` and `´k`, exactly as Windows composes them. The last is **two** `TEXTINPUT`s from one press **[M]** |
> | AltGr + letter | `TEXTINPUT` `@`; AltGr's fake Left Ctrl arrives as a Left Ctrl `KEYDOWN` **[M]** |
> | Enter, Backspace, Tab, Shift, Caps Lock | `KEYDOWN`/`KEYUP` with scan code, no `TEXTINPUT` **[M]** |
> | Space | `KEYDOWN` and `TEXTINPUT` `' '` **[M]**. Unlike pynput's `Key.space`, so #14 keeps Space System by its key, not its text |
> | Any key while another window has focus | Nothing **[M]** |
>
> pygame's `KEYDOWN.unicode` is not the character and must not be read; it reported `^^` for `^` `k` **[M]**.
>
> **Against the other candidates:**
> - **Composing from pynput's `is_dead` with `KeyCode.join()`** gets `´´`, `´k`, `^^`, `^k` and `°a` wrong **[M]**.
> - **Repaired with Windows' own `ToUnicodeEx` on a private thread**, it matched the window in all 68 ordinary steps **[M]**. It does so only by copying state Windows keeps for the window:
>   - the window's layout, on every key;
>   - the clearing of an armed dead key on every focus change, which Windows does in 7 of 7 trials **[M]**;
>   - keys the window never received, such as the Space of Win+Space **[M]**.
>
>   That second copy of Windows' state is what failed in pynput itself.
> - **Using both** (the hook for key state, the window for the character) pairs two streams. In Takki's 60 Hz loop, 14% of presses split across ticks and 0.8% interleave with another key **[A, replayed from measured times]**. It also keeps the hook's two defects:
>   - the hook mixes layouts after a switch **[M]**;
>   - the hook lost Right Shift's release both times the Filter Keys box opened **[M]**.
>
> **What this does to the rest of this section:**
> - **The held-key rule ([ADR-027](0027-key-and-accuracy-state-model.md)) carries over.**
>   - pygame passes one `KEYDOWN` per physical press and drops SDL's repeats, while `TEXTINPUT` repeats.
>   - "A `TEXTINPUT` is fresh exactly when a `KEYDOWN` arrived since the previous one" agreed with SDL's own repeat flag for 764 of 764 `TEXTINPUT`s **[M]**.
>   - Every `KEYDOWN` had its `KEYUP`. On focus loss, SDL synthesises the release for every held key, just ahead of `WINDOW FOCUS_LOST`, so no down-state leaks **[M]**.
>   - A key already held when focus returns is invisible until it is released and pressed again **[M]**.
> - **"Compose state at prompt advance" above holds again**, with the window as the source.
>   - An armed dead key waits, and composes the next letter, 3 s later in the trial **[M]**.
>   - A stale composite is then an ordinary wrong answer.
>   - Two additions:
>     - leaving the window clears the armed state **[M]**;
>     - a dead key followed by a letter it cannot combine with gives one press with two characters, which #14 has to give a counting rule (most simply: wrong) **[A]**.
> - **§ Composite ramp-up is unaffected:** `á` arrives as one `TEXTINPUT`.
> - **A dead key as a rest key ([ADR-033](0033-rest-keys-and-keyboard-alignment.md)'s stored worry) is answered.**
>   - The dead key's `KEYDOWN` names it by scan code **[M]**.
>   - It leaves state armed for the next letter, or not, by the parity of its presses when held **[M]**.
>   - Takki can disarm it by calling `ToUnicodeEx(VK_SPACE)` on the window's thread: 10 of 10 trials **[M]**.
>   - That call belongs to the alignment, never to lessons, where `á` must still compose. It is a platform call behind a Protocol ([ADR-019](0019-testing-strategy-and-io-isolation.md)). Building it waits for the first dead-key language, because English has none. The question does not go to Beta.
> - **A layout switch mid-session stops being silent.**
>   - The window's characters follow the new layout **[M]**.
>   - SDL posts `KEYMAPCHANGED` onto the queue the focus source already drains **[M]**.
>   - [Roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)'s entry becomes a question of what to say, not of how to notice.
> - **Keys typed into other applications no longer pass through Takki at all.** The hook delivered every key system-wide to Takki's process. In the spike it logged a message the tester typed into another program **[M]**.
> - **Unfocused keys are lost** (§ C8, *Resume*).
>   - In Alpha this costs nothing: Alt+Tab is the way back, and the held-key raise it fed never worked on the laptop (windows-validation E2).
>   - In Beta, the talk key and any resume key that must work while Takki is in the background need a narrow global hook or `RegisterHotKey` for those keys alone. Neither needs character translation **[A]**.

### Composite ramp-up (B5)

*(2026-11-12, alpha-plan #12m session (6): written in phases, which [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels) replaced with a ladder of Reach, Choose and Travel; see "Built, #12m session (6)" there. Read for the ladder, decided by the developer: **a composite takes Reach** like any letter typed with a key off its finger's rest key. A Reach prompt asks for the whole grapheme, as Phase A did, and the rest cue after it waits for a press on the rest key of **both** fingers it was typed with, the modifier's and the base letter's, in either order: for Icelandic `é`, `æ` and `d`; for `á`, `æ` and `a`, although the left little finger never left `a`. "Rest" means every finger back. Phase B's alternation with the base letter goes with Phase B; Choose and Travel draw a composite like any letter. A composite has no Reach only when its modifier and its base are both rest keys, which needs a dead key as a rest key: [ADR-033](0033-rest-keys-and-keyboard-alignment.md) allows one and nothing can land on one yet, and a rest cue waiting for a dead key cannot be answered today, since its press reaches the engine with no character. Both go with the first dead-key language's alignment work (§ Event model, "Decided").)*

ADR-024's Phase A through D is amended for composite graphemes.

**Phase A — whole grapheme repeated.** "Type the new key alone, repeatedly" becomes "type the whole grapheme repeatedly." The engine prompts `á`; the child presses dead-acute then `a`; pynput fires `KeyCode(char='á')`; the engine records a correct attempt. Ten consecutive correct attempts advance to Phase B. The two-keystroke mechanism is entirely invisible to the engine.

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

**pynput stays the key source; dispatch is focus-gated.** pynput remains the keyboard interface (ADR-005) and the event model above is unchanged — `ToUnicodeEx` translation, the `KeyCode`-with-printable-`char` filter, and composite handling all stand. What changes is that `on_press` processes an event as drill input **only while Takki's window holds OS foreground.** While it does, the focused window consumes the keystrokes, so nothing leaks; while it does not, Takki is paused by definition. `suppress=True` is dropped entirely.

*(Superseded for the source on 2026-11-01, alpha #13. Key events now come from Takki's own window; see § Event model, "Decided". Focus gating stands. A window produces key events only while it has focus [M], so the gate stops being the only filter and becomes a backstop. One ordering to keep: SDL's synthesised `KEYUP`s for held keys arrive just before `WINDOW FOCUS_LOST`, and must still reach the down-state.)*

**Focus is the single active/paused signal.** Intentional task-switch, a focus-stealing notification, and OS secure-desktop preemption all manifest as the same event: Takki's window is no longer foreground. One mechanism — window focus events (`WINDOWFOCUSGAINED` / `WINDOWFOCUSLOST`) behind the `FocusSource` Protocol (ADR-019) — covers what were three separate problems. On focus loss Takki enters PAUSED and announces it; a foreground poll backs up the event in case a secure-desktop transition does not deliver one.

**The focus source drains SDL's whole queue every tick** *(added 2026-09-29, alpha #12c (3))*. `PygameFocusSource.poll()` takes every queued event, acts on each focus change and `QUIT` in order, and drops every other type. It used to take only those three types and leave the rest. Nothing else reads SDL's queue, so mouse motion and key events piled up to SDL's 65,535-event cap, after which SDL refuses every new event, `QUIT` and focus changes included: the close button stopped working after 18–20 minutes of mouse movement (windows-validation E10; confirmed fixed by the fix-verification run's FV-03). **The rule for anything that later reads SDL's queue:** one reader drains it whole every tick and hands each type to its consumer. A type-filtered `get()` that leaves other types queued brings the cap back. This bears on alpha #13 directly: if Takki takes characters from its own window, `KEYDOWN`, `TEXTINPUT` and `KEYUP` must reach the key reader instead of being dropped here. *(2026-11-01: #13 decided it does. `KEYDOWN`, `KEYUP`, `TEXTINPUT` and `KEYMAPCHANGED` go to the key reader from this one drain, in #14.)*

**Resume — three converging paths:** the voice "resume" intent (ADR-017), a configurable held-key (works if the mic is unreliable), and simply Alt+Tab back to Takki (native, and announced by any running screen reader). The first two attempt a programmatic re-foreground; Windows' foreground-activation lock may downgrade that to a taskbar flash, in which case the spoken hint falls back to "press Alt+Tab to come back to Takki." The held-key and voice triggers are seen even while unfocused because pynput's hook is global. *(2026-11-01: not after alpha #14. With key events taken from the window, nothing is seen while unfocused [M]. Alpha's way back is Alt+Tab (below). Beta decides whether the talk key and a resume key get a narrow global hook or `RegisterHotKey`; see § Event model, "Decided".)*

**Re-acquire has no synchronous answer** (added 2026-08-22, from session 6a implementation). The paragraph above says the re-foreground attempt "may be downgraded to a taskbar flash," which reads as though the caller learns which happened. It does not, and cannot. `SDL_RaiseWindow` — the mechanism behind `FocusSource.request_foreground()` — is asynchronous: it posts an activation request to the OS and returns before Windows has ruled on it. Querying focus immediately afterwards reads the *pre-call* state, which while PAUSED is always "not focused," so a success-boolean would report failure even on the raises that worked.

`request_foreground()` therefore returns nothing. Re-acquire is a **request plus a deadline**, resolved by the same tick-checked mechanism as every other timed behaviour ([concurrency-model](../concurrency-model.md) § Timers):

1. Call `request_foreground()`; set a deadline.
2. A `FocusGained` arriving before the deadline **is** the success signal — no separate confirmation exists or is needed, and it arrives by the same path as a manual Alt+Tab, so both resume routes converge on one code path.
3. Deadline expiry (`RESUME_REQUEST_TIMEOUT_MS`) is the failure signal, and is what triggers the spoken *"press Alt+Tab to come back to Takki"* fallback.

The consequence for the taxonomy's **Resume hold** row is that the held key initiates a request; it does not itself resume. Only the returning `FocusGained` does. Implemented in [session 6b](../alpha-plan.md) (`FocusModel`); the boundary it builds on landed in 6a.

**Resume in Alpha: Alt+Tab, named in the pause announcement** *(added 2026-09-29, from alpha #12b-2's E2/E3 result)*. On the test laptop the held-key raise never brought Takki back, from any app. The `request_foreground()` request is refused, most likely by Windows' foreground-activation lock, which a process that only sees the key through a global hook does not get past (not measured). The key itself fails on laptops too: F1 sat behind Fn there, plain F1 dimmed the screen or muted, and Fn+F1 opened help or Edge in the app in front. So the child ended one window further away, not "past a window Takki is about to raise past anyway" as `config.RESUME_KEY`'s rationale assumed. The Alt+Tab hint followed only some attempts, probably because plain F1 never reaches Takki as F1 (not traced). **Decision for Alpha:** Alt+Tab (E1, which passed) is the way back, and the pause announcement says so: *"Paused. Press Alt+Tab to come back to Takki."* The held-key path stays in the code as it is. Its hard-no-go check E2 moves to the Beta list in windows-validation. **Deferred to Beta:** whether any raise can get past the foreground lock without elevation (a spike on the laptop; SDL's force-raise option is one candidate), whether a held key is worth keeping if the raise cannot work (all it could then add is the hint the announcement already gives), and which key, if any, since F1 is a chord on many laptops.

**The FSM's starting state arrives as an event** (added 2026-08-22, session 6b). `FocusSource` deliberately exposes no focus *query* — the paragraph above is why one would mislead — and the focus events are edge-triggered, so a window that comes up **unfocused** would emit nothing and leave the FSM wrongly ACTIVE for the whole run, dispatching another application's keystrokes into the lesson with no pause announcement. `FocusSource` implementations therefore emit their initial state once at construction, before any key event can arrive; the FSM starts ACTIVE and that seed corrects it. A seeded `FocusGained` on the normal path is silently absorbed, since the FSM is already ACTIVE.

This is also why an always-on window is load-bearing beyond focus ownership: without a window there is nothing to raise, and the resume paths would have no mechanism at all.

**Screen-reader cooperation.** A VI child's machine very likely runs a screen reader (NVDA, JAWS, Narrator), and the focus-owning window cooperates with it rather than fighting it:
- The reader announcing the new foreground app on focus loss is a *second* channel telling the child they have left a drill — reinforcing Takki's own announcement.
- Its keystroke echo would otherwise double Takki's chimes during a drill. Takki is a **self-voicing application**; the intended fix is the reader's own mechanism for that case — NVDA's **sleep mode**, which is scoped to the focused app, so it silences echo *while Takki is focused* yet wakes to announce the moment focus leaves. Takki does not reconfigure the reader from its own process; it detects the reader (`detect_screen_reader()`, ADR-026) and offers a one-time setup suggestion (ADR-013).

**Keypress taxonomy.** The `on_press` handler classifies every event while Takki is foreground; while it is not, every event is ignored and the OS routes keys to whatever now holds focus.

| Class | Condition | Action |
|---|---|---|
| **Talk key** | Matches configured PTT key (default: Right Ctrl) | Dispatch to voice subsystem |
| **Escape** | `Key.esc` | Dispatch to lesson controller (re-read / restart per ADR-025) |
| **Resume hold** | `RESUME_KEY` held for `RESUME_HOLD_MS`, while PAUSED ([ADR-025](0025-configuration-system.md), added 2026-08-22) | Request foreground; the returning `FocusGained` is what resumes |
| **Expected** | `KeyCode` with printable `char` matching current prompt | Correct-chime; advance; record correct in `key_attempts` |
| **Wrong** | `KeyCode` with printable `char` not matching current prompt | Auto-reject sound; re-prompt; record wrong in `key_attempts` |
| **Composing** | `KeyCode` with `char is None` or non-printable | Discard silently — compose in progress |
| **Boundary** | `Key.backspace`, `Key.tab`, `Key.delete`, `Key.enter` | Ignore (Backspace disabled per ADR-012) |
| **System** | All remaining `Key.*` events | Ignore — they reach the OS normally; if one moves focus (Win key → Start menu), the resulting focus-loss pauses the lesson |

*(2026-11-01: the conditions above are written in pynput's terms: `KeyCode`, `Key.*`, `char is None`. Alpha #14 restates them for SDL events. Text comes from `TEXTINPUT` and named keys from `KEYDOWN`. **Composing** becomes "a `KEYDOWN` that produced no `TEXTINPUT`". Space must stay System by its key, because the window gives it the text `' '`.)*

**The space bar lands in System, deliberately.** pynput reports it as `Key.space`, so it falls through to *ignore* — which is correct: [ADR-023](0023-key-introduction-protocol.md) § "The space bar is likewise never introduced" scopes it out of the curriculum until the post-V1 full-text stage (pointer added 2026-08-22, session 6b, so the taxonomy is not re-derived each time it is implemented).

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

*(Run, and superseded, 2026-11-01. The composition half ran on 2026-09-26: the hook never composes, as recorded in § Event model. Alpha #13 then ran the whole question against Takki's own window, on Icelandic and German, by hand and injected ([research/key-capture-source.md](../research/key-capture-source.md)). The window delivers Windows' own composed character. No compose buffer is built, and none is needed. What is left for the first dead-key language is #14's check at the new boundary, and the alignment's disarming call (§ Event model, "Decided").)*

### Open questions

1. **Emergency keyboard exit.** Less acute now that global suppress is gone — Alt+Tab away plus window close, or Task Manager, are always reachable, and the voice "stop" intent remains. A held-key exit detecting the hold duration and calling `os.kill(os.getpid(), signal.SIGTERM)` is still worth defining for Beta as a no-voice, no-mouse fallback, but it no longer compensates for a system-wide trap. Deferred to Beta.

   **It must not be bound to Escape** (flagged 2026-08-22, following the carry-forward **D Escape** decision in [ADR-012 § Recovery](0012-audio-feedback-design.md)). Escape now carries a tap/hold pair — tap re-reads, hold past `RESTART_HOLD_MS` (default 800 ms) restarts the word. This paragraph's original sketch of "hold Escape 5 seconds" would sit on top of that: every exit attempt would fire a word restart in passing at 800 ms, and a child who holds Escape too long while trying to re-read would be walking toward an app exit. Two gestures on one key is already the ceiling; a third is not viable. Beta must pick a different key for the emergency exit, and should prefer one with no lesson meaning at all — the taxonomy's **System** row (all remaining `Key.*`) is where an unbound candidate will come from. Whichever key is chosen, the same auto-repeat rule applies: the hold timer starts on the first press and is cleared only by the release.

4. **NVDA app-module auto-sleep.** Optionally ship an NVDA app module that auto-enables sleep mode for the Takki executable, making the self-voicing echo suppression automatic rather than a one-time setup suggestion (ADR-013). NVDA-specific, no admin needed, but adds an installer artifact and touches the user's NVDA add-ons directory. Decide in Beta alongside real NVDA/JAWS coexistence testing.

2. **Per-profile mechanism override for dual-path languages.** Inherited from ADR-023 open question 1: a Latvian adult who already uses dead-key paths may want to keep that motor pattern. Hard-default to AltGr for v1 child learners. No decision needed before Beta (Latvian is not in the Beta language set).

3. **Phase B anchor when base letter is in active ramp-up.** If a composite is first introduced before its base letter has cleared Phase D, Phase B alternation with the base letter would interleave a composite in Phase B with a letter still in Phase A/B. In practice the modifier always ranks later than the base letter in the Phase 2 frequency sequence (ADR-023: Polish AltGr at step 12–15; Icelandic dead-acute at step 18), so the base letter is well past Phase D when the composite's Phase B runs. Verify per-language during V1 spike to confirm no layout places a modifier unusually early.
