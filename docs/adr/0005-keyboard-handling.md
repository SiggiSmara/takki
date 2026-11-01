# ADR-005: Keyboard Handling

**Status:** Accepted  
**Date:** 2026-05-17  
**Amended:** 2026-11-01 — key capture moves from `pynput` to Takki's own window (alpha #13); see § Key capture moves to Takki's window.

> Part of the [Takki architecture](../architecture.md).  
> **Amendment pending from [ADR-033](0033-rest-keys-and-keyboard-alignment.md) (2026-10-10):** what the keyboard alignment needs from key events; a dead key as a rest key waits on the key-capture decision. Not yet made here ([alpha-plan](../alpha-plan.md) #12m). *(2026-11-01: the key-capture decision is made, and it answers the dead-key half; see below.)*

---

**Decision:** Use `pynput` for key capture. Rely entirely on Windows to report the correct character for the active keyboard layout. No custom layout definitions maintained by the app. *(The first sentence is superseded on 2026-11-01: key events come from Takki's own window. The second and third stand, and hold better than they did; see § Key capture moves to Takki's window.)*

### Rationale

Windows handles keyboard layout translation transparently. When a user presses a key, `pynput` reports the already-translated character — so on a German QWERTZ keyboard, the key in the Z position reports `y`, and the `ü` key reports `ü`. The app never needs to know which physical key was pressed, only which character was produced.

This means:
- No layout definition files to maintain
- No layout detection logic beyond reading the Windows locale
- Automatic correct behaviour for all QWERTY, QWERTZ, AZERTY, and national variant layouts
- Dead keys and AltGr combinations are handled by Windows before the app sees them *(true for the window that has focus, false for the pynput hook; see below)*

`pynput` is chosen over the `keyboard` library because it does not require elevated privileges on Windows for standard key capture.

The push-to-talk key (ADR-020) is captured via the same `pynput` pipeline as any other key; the lesson engine consumes character events and ignores the talk key, while the voice subsystem subscribes to talk-key events and ignores character keys.

### Case is discarded (added 2026-09-20)

This ADR puts Shift and capitalisation out of scope but never said what happens to the character that arrives when Shift or Caps Lock *is* held — and Windows translates it before `pynput` sees it, so `F` genuinely arrives. **It is folded to lower case at the taxonomy boundary and the lesson engine never sees the difference.** Takki teaches which key a letter lives on; which case that key produced is a fact about a modifier the curriculum does not teach. The reasoning, the `str.lower()`-not-`str.casefold()` constraint, and the counting consequences are in [ADR-027 § Case is folded at the boundary](0027-key-and-accuracy-state-model.md).

Shift and Caps Lock themselves remain `System` in the ADR-028 taxonomy — they produce no character event and are ignored, not swallowed.

### Focus-gated dispatch (added 2026-06-21, per ADR-028)

`pynput` remains the key source, but it no longer runs with `suppress=True`. Key events are processed as drill input only while Takki's window holds OS foreground; while it does not, the OS routes keys to whatever is focused and Takki is paused. The character-translation behaviour above is unchanged — only *when* an event counts as lesson input is now gated on focus. See [ADR-028 §C8](0028-composite-input-and-keyboard-ownership.md) for the full ownership model and the `FocusSource` Protocol.

### What the hook actually reports (added 2026-09-26)

Measured in alpha session 12b-2 ([windows-validation](../research/windows-validation.md) C6): pynput does not report "the character produced" in two cases this ADR assumed it did. A dead key arrives as its own standalone character (`'´'`) and the letter after it arrives uncomposed (`'a'`), because pynput never composes; and after a mid-session layout switch it goes on translating with the layout it started under. Both are pynput's design, not a bug to wait out. [ADR-028 § Event model](0028-composite-input-and-keyboard-ownership.md) carries the detail, and [roadmap A5](../roadmap.md#a-bites-alpha-specifically-the-next-step) the candidates for where Takki captures keys instead; the choice is alpha-plan #13's. Neither case occurs on US English, so Alpha's measurements stand. *(2026-11-01: measured again in alpha #13. After a switch, the hook does not stay on the old layout cleanly. Its key codes follow the new layout while its table stays on the old one, so it mixes the two. The capture decision is in the next section.)*

### Key capture moves to Takki's window (added 2026-11-01)

Decided in alpha #13, against measurement ([research/key-capture-source.md](../research/key-capture-source.md); **[M]** measured, **[A]** argued). Built in #14. **Takki reads keys from its own window:**
- the character from SDL's `TEXTINPUT`;
- press, release, repeat and which key from `KEYDOWN`/`KEYUP`, identified by scan code.

pynput leaves the input path.

**This is the Rationale above, applied where it is true.** "Windows reports the correct character" is true for the window that has focus, and that window's thread composes dead keys and follows the active layout. Takki's own window is the one Takki counts keys in. Measured on Icelandic and German, the window delivered Windows' own result in every case **[M]**:
- `á`, `ê`, `å`, and `ü` from `¨`;
- a dead key followed by Space, by itself, or by a letter it cannot combine with;
- AltGr+`q`;
- the same keys after a mid-session switch from US to German and back.

The hook did not:
- it reports a dead key as a plain character and the next letter uncomposed;
- after a layout switch it mixes the old table with the new layout's key codes (German `ö` read as `` ` ``) **[M]**.

**What changes for this ADR's other sections:**
- **§ Case is discarded stands.** Caps Lock gives `TEXTINPUT` `A`, which is folded as before **[M]**. Shift and Caps Lock arrive as `KEYDOWN`/`KEYUP` with no text, so they stay System.
- **ADR-027's held-key rule is fed from the window.**
  - pygame passes one `KEYDOWN` per physical press, and the repeats show as `TEXTINPUT`s with no fresh `KEYDOWN`: 764 of 764 agreed with SDL's own repeat flag **[M]**.
  - Down-state is keyed on scan code, so the release side needs no character at all.
- **§ Focus-gated dispatch stands.** The window simply delivers nothing while unfocused **[M]**.
- **The push-to-talk paragraph above no longer holds in the background.** In Alpha the talk key has nothing behind it. In Beta, inside Takki, it is a window key like any other. A talk key or resume key that must work while another application has focus needs a narrow global hook or `RegisterHotKey` for those keys alone, with no character translation **[A]**. Beta decides it, with the raise question [ADR-028 § C8](0028-composite-input-and-keyboard-ownership.md) defers.
- **A dead key as a rest key** ([ADR-033](0033-rest-keys-and-keyboard-alignment.md)) is answered:
  - the dead key's `KEYDOWN` names it by scan code;
  - the compose state it leaves armed can be cleared from the window's thread (10 of 10) **[M]**;
  - the alignment does that; lessons do not.
- **A mid-session layout switch is announced.** SDL's `KEYMAPCHANGED` arrives on the queue Takki already drains **[M]**. Roadmap § D's "A layout switched mid-session is not detected" becomes a question of what Takki says.
- **The `keyboard` library alternative below** was about privilege for a global hook. A window needs no privilege at all.

### Alternatives Considered

- **Custom layout definition files (JSON):** Rejected. Unnecessary duplication of information Windows already has. Maintenance burden. Risk of mismatch between app definition and actual system layout.
- **`keyboard` library:** Viable alternative but requires more careful privilege handling. `pynput` is cleaner for this use case.
