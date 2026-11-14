# ADR-005: Keyboard Handling

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Takki takes its key events from its own window: the character from SDL's `TEXTINPUT`, and press, release and which key from `KEYDOWN`/`KEYUP`, identified by scan code. Rely entirely on Windows to report the correct character for the active keyboard layout. No custom layout definitions maintained by the app.

### Rationale

Windows handles keyboard layout translation for the window that has focus. That window's thread composes dead keys and follows the active layout, so the character it is given is the one the child produced: on a German QWERTZ keyboard the key in the Z position gives `y`, the `ü` key gives `ü`, and Icelandic's dead acute then `a` gives `á`. Takki counts keys only while its own window has focus ([ADR-028](0028-composite-input-and-keyboard-ownership.md) § C8), so its own window holds the authoritative answer.

This means:
- No layout definition files to maintain
- No layout detection logic beyond reading the Windows locale
- Automatic correct behaviour for all QWERTY, QWERTZ, AZERTY, and national variant layouts
- Dead keys and AltGr combinations are composed by Windows before Takki sees them

Measured on Icelandic and German in alpha #13 ([research/key-capture-source.md](../research/key-capture-source.md); **[M]** measured, **[A]** argued), the window delivered Windows' own result in every case **[M]**:
- `á`, `ê`, `å`, and `ü` from `¨`;
- a dead key followed by Space, by itself, or by a letter it cannot combine with;
- AltGr+`q`;
- the same keys after a mid-session switch from US to German and back.

Reading the window needs no elevated privileges and no thread of its own: `PygameFocusSource.poll()` already drains SDL's queue on the main thread every tick, and hands each key event to `takki.input.window_keys.WindowKeyReader` from that one drain ([concurrency-model.md](../concurrency-model.md)). pygame's `KEYDOWN.unicode` is never read: it is not the composed character, and reported `^^` for `^` `k` **[M]**.

### How a key arrives

- **A press of a key that types** is a `KEYDOWN`, then a `TEXTINPUT` with the character, then later a `KEYUP`. The `TEXTINPUT` is fresh exactly when a `KEYDOWN` came since the last one; an OS auto-repeat is a `TEXTINPUT` with no fresh `KEYDOWN`, because pygame passes none for a repeat (764 of 764 against SDL's own repeat flag **[M]**). That is what [ADR-027](0027-key-and-accuracy-state-model.md)'s held-key rule reads.
- **A press of a key that types nothing** (Shift, Enter, Tab, Caps Lock, Backspace, an arming dead key) is a `KEYDOWN`/`KEYUP` pair with its scan code and no `TEXTINPUT` **[M]**.
- **The space bar** types `' '`, and is System by its key in [ADR-028](0028-composite-input-and-keyboard-ownership.md)'s taxonomy, never by its text.
- **Down-state is keyed on scan code**, so a release needs no character, and Shift released before the letter cannot leave the letter down **[M]**. Every `KEYDOWN` has its `KEYUP`: on a focus loss SDL releases every held key just before it reports the focus lost **[M]**.
- **While another window has focus, nothing arrives** **[M]**.
- **A mid-session layout switch is announced.** SDL's `KEYMAPCHANGED` arrives on the same drain **[M]**. What Takki says about it is [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)'s.

### Case is discarded

This ADR puts Shift and capitalisation out of scope, and Windows translates the case before Takki sees it, so `F` genuinely arrives, from Shift or from Caps Lock **[M]**. **It is folded to lower case at the taxonomy boundary and the lesson engine never sees the difference.** Takki teaches which key a letter lives on; which case that key produced is a fact about a modifier the curriculum does not teach. The reasoning, the `str.lower()`-not-`str.casefold()` constraint, and the counting consequences are in [ADR-027 § Case is folded at the boundary](0027-key-and-accuracy-state-model.md).

Shift and Caps Lock themselves are `System` in the ADR-028 taxonomy: they produce no character and are ignored, not swallowed.

### Focus-gated dispatch

Key events are processed as drill input only while Takki's window holds OS foreground; while it does not, the OS routes keys to whatever is focused and Takki is paused. The window delivers nothing while unfocused, so the gate is a backstop. See [ADR-028 § C8](0028-composite-input-and-keyboard-ownership.md) for the ownership model and the `FocusSource` Protocol, which carries the key events.

### What the keyboard alignment reads from a key

The alignment ([ADR-033](0033-rest-keys-and-keyboard-alignment.md)) asks for a finger and answers the key it lands on, never the character that key types.

- **Every press is named by its scan code.** A landing is a row and a column, so the alignment takes a press's cell from its scan code, through the layout's own cells, whether or not the key types anything. Nothing at `KEYDOWN` says whether a `TEXTINPUT` will follow, so the press is answered at its `KEYDOWN` and its text is ignored.
- **A key that is no cell** (Shift, Enter, Tab, Caps Lock, the space bar, Ctrl, Alt, AltGr, the function keys) arrives the same way and is no landing: the finger is guided as for a press outside its column.
- **A dead key is a cell, and a press on it is a landing.** Icelandic's dead acute is cell (3, 11), SDL scan code 52 **[M]**.
- **A dead key leaves a composition armed** for the next letter, and a held one leaves it armed or not by the parity of its presses **[M]**. So every key pressed while the alignment runs, asked or not, is disarmed once it is up, through the platform function `disarm_dead_key()` ([ADR-026](0026-platform-interface-abstraction.md)): Space through `ToUnicodeEx` on the window's thread, which is the main thread (10 of 10 **[M]**). Every key and not only the layout's dead cells, because a dead key can lie off the grid (Icelandic's key left of `1`) or behind a modifier (AltGr), and a disarm with nothing armed changes nothing. Lessons never disarm: a composite must still compose when the child types it.

### Push-to-talk

The push-to-talk key ([ADR-020](0020-voice-input-trigger-push-to-talk.md)) is a window key like any other, bound by scan code (Right Ctrl, 228). In Alpha it has nothing behind it. A talk key or resume key that must work while another application has focus cannot come from the window; it needs a narrow global hook or `RegisterHotKey` for those keys alone, with no character translation **[A]**. Beta decides it, with the raise question [ADR-028 § C8](0028-composite-input-and-keyboard-ownership.md) defers.

### Alternatives Considered

- **Custom layout definition files (JSON):** Rejected. Unnecessary duplication of information Windows already has. Maintenance burden. Risk of mismatch between app definition and actual system layout.
- **`pynput`'s global keyboard hook:** Takki's key source until alpha #14. Rejected on measurement (alpha 12b-2 and #13): the hook sees a key before Windows composes it, so it reports a dead key as a plain character and the next letter uncomposed, and after a mid-session layout switch it mixes the old layout's table with the new layout's key codes (German `ö` read as `` ` ``) **[M]**. It also lost Right Shift's release when the Filter Keys box opened, in both trials **[M]**. Repairing it with `ToUnicodeEx` on a private thread matched the window only by copying state Windows keeps for the window. What it alone gave, keys while unfocused, Alpha does not use.
- **`keyboard` library:** A global hook like pynput's, with more careful privilege handling on top. Rejected with pynput; a window needs no privilege at all.

### Changes

- 2026-06-21: § Focus-gated dispatch added (ADR-028): no global `suppress`.
- 2026-09-20: § Case is discarded added.
- 2026-09-26, alpha session 12b-2: the hook's reports measured: no dead-key composition, the old layout after a switch.
- 2026-11-01, alpha #13: key capture decided for Takki's own window.
- 2026-11-14, alpha-plan #14b: restated as built. The decision names the window; § How a key arrives and § What the keyboard alignment reads from a key added (ADR-033's amendment: a press with no character, a dead key as a rest key, the disarm); push-to-talk bound by scan code; pynput kept once as a rejected alternative.
