# Where Takki takes its key events from

> **Question:** should Takki take its characters and key state from pynput's global hook, from its own window (SDL), or from both? ([alpha-plan](../alpha-plan.md) #13; [roadmap A5](../roadmap.md#a-bites-alpha-specifically-the-next-step).)
> **Answer (2026-11-01):** from its own window. The character is SDL's `TEXTINPUT`, and physical key state is SDL's `KEYDOWN`/`KEYUP`, identified by scan code. pynput leaves the lesson's input path. Recorded in [ADR-028 § Event model](../adr/0028-composite-input-and-keyboard-ownership.md) and [ADR-005](../adr/0005-keyboard-handling.md); built in #14.
> **Measured on:** the Windows test laptop, Windows 11 Home 10.0.26300, Python 3.11.15, pygame 2.6.1 / SDL 2.28.4, pynput 1.8.2. Layouts installed: en-US `0x409`, de-DE `0x407`, Icelandic `0x40f`. Keyboard repeat delay setting 1 (500 ms nominal), repeat speed 31. Sticky Keys and Filter Keys shortcuts both on (the Windows defaults).
> **Marks:** **[M]** measured in the runs below, with the log named; **[A]** argued, not measured. Nothing here is marked [M] without a log line behind it.

## The mechanism, first

A key press reaches a Windows program in two places, at two different moments:

1. **The low-level hook (`WH_KEYBOARD_LL`) sees the key before any translation.** It gets a virtual-key code and a scan code. There is no character yet. pynput builds the character itself by looking the key up in a table. It builds that table once, for the layout its own thread started with, and it never calls `ToUnicodeEx` per key, because that would disturb the compose state of the program that has focus. ([ADR-005 § What the hook actually reports](../adr/0005-keyboard-handling.md), [roadmap A5](../roadmap.md#a-bites-alpha-specifically-the-next-step).)
2. **The window that has focus gets the key as messages.** Its thread calls `TranslateMessage`, which turns the key into characters (`WM_CHAR`), using *that thread's* keyboard layout and *that thread's* compose state. A dead key arms the compose state, and the next key resolves it. SDL's message pump does this for Takki's window and turns the result into `KEYDOWN`/`KEYUP` (the key) and `TEXTINPUT` (the characters).

So "which character did the child produce" has one authoritative answer: what `TranslateMessage` produced in the window that had focus. Takki counts keys only while its own window has focus (ADR-028's focus gate), so the window *is* that window. Every result below follows from this. The hook has to reconstruct the answer from outside, while the window receives it.

## How it was measured

**Scripts** (all in `spikes/`, run with `uv run python`):

- `key_capture_source_spike.py` opens a window like `PygameFocusSource`'s. It runs a pynput listener beside it (except in the `window` run) and logs every key on one clock, from three places:
  - **hook:** pynput's `KeyCode` char, `is_dead` and vk, the raw scan code and flags from the hook, and what production `translate()` makes of it;
  - **raw:** SDL's events, read by an SDL event filter installed in front of pygame's, so the auto-repeat `KEYDOWN`s that pygame drops are still seen;
  - **pg:** what `pygame.event.get()` returns, which is what Takki would read.

  Steps are shown in the window and advanced by mouse click. Steps marked FLUSH call `ToUnicodeEx(VK_SPACE)` on the window thread when a dead key's `KEYDOWN` arrives.
- `key_capture_source_analyse.py` turns a log into a per-step report (`<log>.txt`). The report covers:
  - the text each candidate would hand the engine;
  - per-key holds and repeat timing;
  - press/release balance;
  - hook-to-SDL pairing and lag;
  - a replay of the recorded times through a 60 Hz loop.
- `key_capture_source_inject.py` drives the `auto` run with injected scan codes (`SendInput`). Windows maps them with the active layout, exactly as it does real keys, and they pass the same hook chain (windows-validation C7, 2026-09-24). Injection cannot produce Windows' auto-repeat, so held keys were always pressed by hand.
- `key_capture_source_replay.py` replays every recorded hook key through **candidate (1) repaired**: pynput's events composed with Windows' own `ToUnicodeEx` on a private thread, with the layout the window was using. It compares the result with the window's `TEXTINPUT`.

**Runs** (raw logs and reports in `spikes/results/key_capture_source/`):

| Log | Layout | Input | What |
|---|---|---|---|
| `is-20261101-212330` | Icelandic | by hand | 27 steps: dead-key cases, flush, holds, `ll`, Shift order, focus, non-character keys, Caps Lock, Sticky/Filter Keys. Steps 18–19 (focus mid-hold) failed: the touchpad is disabled while a key is held, so the mouse could not move focus. Steps 15–16 typed Shift+`I`, not `l`, because the instruction font made `l` look like `I` |
| `redo-20261101-213647` | Icelandic | by hand | Steps 18–19 again with Alt+Tab; `ll` with lower-case L; drumming `a s d f` |
| `de-20261101-213939` | (Icelandic) | — | False start on the wrong layout, closed after one step. Not used |
| `de-20261101-213951` | German | by hand | First 8 German steps; restarted. Agrees with the full run |
| `de-20261101-214041` | German | by hand | 13 steps: `^` and `´`/`` ` `` cases, AltGr+q, held `^`, flush |
| `switch-20261101-214340` | US → German → US | by hand | Four keys (US `z`, `y`, `;`, `'`) per layout. The Alt+Shift step pressed Left Alt+Ctrl instead, so Alt+Shift is not measured there. Step 3 also logged, through the hook, a chat message the tester typed into VS Code while the window was in the background |
| `window-20261101-214817` | Icelandic | by hand | No hook: dead-key cases, holds, roll |
| `auto-20261101-215656` | Icelandic → German → US → Icelandic | injected | Dead-key cases; dead key, Alt+Tab out and back, letter (×3 per layout); flush (×5 per layout); four keys per layout; Enter/Backspace/Tab/Shift taps. Its first step's fourth key (Icelandic `´`) armed a dead key that shifted the next step's results, a spike bug that also demonstrates the stale-compose problem. `.inject.txt` has the injector's own record |
| `confirm-20261101-220021` | Icelandic | by hand | Held dead key then `a` (×4); focus lost mid-hold (×2); focus gained mid-hold (×2); Filter Keys again; Right Ctrl while unfocused |
| `replay-candidate1-repaired.txt` | — | replay | The repaired candidate (1) against every log above |

## Results

### 1. Does `TEXTINPUT` carry the composed letter?

**Yes, in every case, with no setup.** **[M]**

- Text input is on from the moment the window exists: `SDL_IsTextInputActive()` was true at startup in every log, and nothing called `start_text_input()`.
- No IME composition happened. Every `TEXTEDITING` event in every log is empty. One arrives at each focus loss and each layout switch, which reads as SDL resetting a composition that was never started. The tester saw no candidate window or other popup while typing dead keys (confirmed on 2026-11-01, after the runs).

| Keys | Windows (window `TEXTINPUT`) | Today (`translate()`) | (1) pynput `join()` | Log |
|---|---|---|---|---|
| Icelandic `´` `a` | `á` | `´` `a` | `á` | is 2, window 1 |
| `´` `e` | `é` | `´` `e` | `é` | is 3 |
| `´` Space | `´` | `´` | `´` | is 4, window 2 |
| `´` `´` | `´´` | `´´` | **`´`** | is 5, window 3 |
| `´` `k` | `´k` | `´k` | **`ḱ`** | is 6, window 4 |
| Shift+top-left (`¨`) `u` | `ü` | `¨u` | `ü` | is 7 |
| top-left (`°`) `a` | `å` | `°a` | **`°a`**: pynput does not flag `°` as dead (no "COMBINING DEGREE SIGN" exists) | is 8 |
| German `^` `e` | `ê` | `^e` | `ê` | de 2 |
| `^` Space / `^` `^` / `^` `k` | `^` / `^^` / `^k` | — | `^` / **`^`** / **`k̂` (two code points)** | de 3–5 |
| `´` `e`, Shift+`´` `a` | `é`, `à` | — | `é`, `à` | de 6–7 |
| `´` Space / `´` `´` / `´` `k` | `´` / `´´` / `´k` | — | `´` / **`´`** / **`ḱ`** | de 8–10 |
| AltGr+`q` | `@` | `@` | `@` | de 11 |

The injected `auto` run reproduces the Icelandic and German rows. **[M]**

**The dead key's `KEYDOWN` is followed by no `TEXTINPUT`**, and the next key's `KEYDOWN` is followed by the composed result. When the next key cannot combine, as in `´k`, **one `KEYDOWN` is followed by two `TEXTINPUT`s** (`´`, `k`). **[M]** (`auto`, and the dead-key rows above.)

**pygame's `KEYDOWN.unicode` is not usable for the character.** For `^` `k` it reported `^` twice; for `´` `´` it reported one `´`. **[M]** (de 4–5, is 5.) The character comes from `TEXTINPUT` only.

### 2. Can SDL's key events carry ADR-027's held-key rule?

**Yes.** **[M]**

- **Auto-repeat is distinguishable from a fresh press.**
  - SDL itself flags every repeat (`repeat=1`), and pygame drops those `KEYDOWN`s: one `KEYDOWN` per physical press, every time (all logs, the "holds" sections).
  - `TEXTINPUT` does repeat, once per OS repeat.
  - Counting a `TEXTINPUT` as fresh exactly when a pygame `KEYDOWN` has arrived since the previous `TEXTINPUT` agreed with SDL's own repeat flag for **764 of 764** `TEXTINPUT`s across all logs.
  - Every `TEXTINPUT` came directly after a `KEYDOWN`: 185 after a fresh one, 579 after a repeat. There was never a `KEYUP` between them, and they were never more than 0.61 ms apart (median 0.05 ms).
- **`ll` with a release between** gives two `KEYDOWN`/`KEYUP` pairs and two fresh `TEXTINPUT`s. **`ll` held** gives one `KEYDOWN`, 25 repeat `TEXTINPUT`s and one `KEYUP`. **[M]** (redo 3–4; the same on the `I` key in is 15–16.)
- **A press and its release identify the same key by scan code**, including when Shift is released first: `KEYDOWN` sc 10, `TEXTINPUT` `G`, `KEYUP` sc 10. **[M]** (is 17.) ADR-027's second Windows assumption is about the character on release. A scan code makes it irrelevant, because a down-state keyed on the physical key never sees a character on the release side.
- **There is a `KEYUP` for every `KEYDOWN`**, in every step of every log (the "balance" sections). **[M]**
  - **Focus lost while a key is held:** SDL sends its own `KEYUP` for every held key, in the same millisecond as `WINDOW FOCUS_LOST` and just before it. The release is not the finger's: in three trials the finger came up 1.0 s, 4.8 s and 2.0 s later. **[M]** (redo 1, confirm 2 ×2.)
  - **Focus gained while a key is held:** the window reports nothing for that key, neither a press nor its later release. **[M]** (redo 2, confirm 3 ×2.) The key's auto-repeat had already stopped, because Alt+Tab is a press of another key.
  - **The hook, by contrast, lost a release.** Right Shift held about 8.5 s opens the Filter Keys box. The hook then recorded 248 and 249 presses of Right Shift and **no release**, in both trials, while SDL gave the window its `KEYUP` at the focus loss. **[M]** (is 27, confirm 4.)
- **Time to the first repeat** was 505–512 ms in both sources (34 held keys through the hook, 30 through SDL), with repeats every 32–33 ms. **[M]** This matches the machine's repeat-delay setting of 500 ms nominal. The delay is a user setting, from 250 to 1000 ms. **[A]**

### 3. The dead key itself (ADR-033's stored worry)

- **The dead key produces a `KEYDOWN` that says which key it was.** **[M]**

  | Layout | Key | Scan code | Key code (`sym`) |
  |---|---|---|---|
  | Icelandic | dead acute | 52 | 180 `´` |
  | Icelandic | top-left key | 53 | 176 `°` |
  | German | `^` | 53 | 94 `^` |
  | German | `´` | 46 | 180 `´` |

  The scan code is the physical key, which is what a rest key is. Which of a key's two dead characters it was (Icelandic `°` or, with Shift, `¨`) is the key code plus the Shift bit in `mod`. **[M]** (`dead` column in the pg `KeyDown` lines; is 7–8.)
- **It leaves armed compose state behind.** The next letter is composed with it, however long the wait: 3 s in is 9. **[M]** In the alignment, a dead-key landing would therefore change the next letter the child types. This is ADR-033's worry, and it is real.
- **Takki can clear it.** Calling `ToUnicodeEx(VK_SPACE, …, wFlags=0)` on the window's thread, after the dead key's `KEYDOWN`, returns the dead character and disarms it. The next letter then arrives plain. **[M]** That held in 10 of 10 injected trials (Icelandic and German, `auto` 5 and 10), plus is 12–13 and de 13 by hand. After a cleared dead key, Space gives `' '` and `k` gives `k`. The call needs nothing but the window's layout (`GetKeyboardLayout(0)` on the main thread).
- **Leaving the window clears it too.** Dead key, then Alt+Tab out and back (or a click away and back), then the letter: the letter arrived plain in **7 of 7** trials. **[M]** (is 10, `auto` 4 and 9.)
- **A held dead key leaves the state armed if and only if it produced an odd number of presses** (the first press plus OS repeats). Each pair of presses prints a pair of accents and disarms. This was seen in all 6 holds:
  - odd, next letter composed: 25, 29;
  - even, next letter plain: 20, 22, 30, 42.

  It also holds for the unheld sequences (three presses then `k` in is 5–6 and de 4–5).

  **[M]** (is 11, de 12, confirm 1.) What a held dead key does to the next letter is effectively random, so the alignment has to flush after a dead-key landing whether or not the key was held. **[A]**

**Answered in Alpha, so it does not go to Beta as a question.** The window says which dead key was pressed, the armed state is real, and Takki can clear it. *Building* the clear waits for the first dead-key language, because English has no dead key. **[A]** It belongs to the alignment and not to lessons: a composite like `á` must still compose when the child types it (ADR-028 § Composite ramp-up).

### 4. Ordering and timing, and pairing two streams (candidate 3)

- **Within SDL**, `KEYDOWN` comes first, then its `TEXTINPUT`s, then later the `KEYUP` (§2). **[M]**
- **The hook event leads the SDL event for the same press by 1.5 to 13.3 ms** (median 2.1, p95 4.2, p99 5.4, over 1,733 matched pairs). In the raw streams there was not one inversion of order. **[M]** The spike polled SDL every 1 ms; Takki's loop polls every 16.7 ms.
- **Replayed through Takki's 60 Hz loop** (SDL pumped first, then the queue, averaged over four tick phases):
  - 975 of 6,936 placements (14.1%) put a press's hook event and SDL event in **different ticks**;
  - 53 (0.8%) had **another key's event delivered between them**: 5.3% while drumming, at most two events between.

  **[A, from measured times]** Pairing is possible, but only by physical key (scan code) and order, never by adjacency.
- **The hook sees keys the window never gets:** the Tab of Alt+Tab, the Space of Win+Space, every key while unfocused, and AltGr's fake Left Ctrl (scan `0x21D`), which SDL reports as a Left Ctrl `KEYDOWN` too. **[M]**

### 5. Layout switched mid-session

- **The window follows the switch.** The same four keys gave `zy;'` on US, `yzöä` after Win+Space to German, and `zy;'` again back on US. **[M]** (switch 1, 3, 5; `auto` 2, 7, 12.)
- **SDL announces the switch.** A `KEYMAPCHANGED` event arrives when the layout changes: one per manual Win+Space, up to three per injected switch. The `KEYDOWN` key code follows the new layout too (scan 51: `sym` 59 `;` on US, 246 `ö` on German). **[M]**
- **Win+Space did not take focus from the window**, so it would not pause a lesson. **[M]** (switch 2, one trial.)
- **pynput does worse than "stays on the old layout".** The hook's vk follows the new layout, but pynput's table is the old one, so it mixes the two:
  - started on US, switched to German: `y z ` ' ` where German typed `y z ö ä` (switch 3);
  - started on Icelandic, switched to German: `y z æ ´` (`auto` 7);
  - on US: `z y ' ´` where US typed `z y ; '` (`auto` 12);
  - the German `^` key came through as Icelandic `°`, not flagged as a dead key (`auto` 8).

  **[M]** The hook thread's own layout never changed (`thread_hkl` in every hook line).
- **Alt+Shift: not measured.** By hand, the tester pressed Left Alt+Left Ctrl. Injected Left Alt+Left Shift did not switch the layout, so the injector fell back to Win+Space (`auto.inject.txt`). Whether a physical Alt+Shift switches on this machine is not known.

### 6. The resume key, and what dropping the hook loses

- **While another window has focus, Takki's window receives no key event at all**, while the hook sees every key. Right Ctrl (×2), Escape, `f` and Ctrl+F were pressed in Notepad: zero window key events. **[M]** (is 21, confirm 5.)
- **Now (Alpha): nothing is lost.**
  - Alpha's way back is Alt+Tab, which Windows handles ([ADR-028 § Resume in Alpha](../adr/0028-composite-input-and-keyboard-ownership.md)).
  - The held-key raise is the only thing the hook feeds while unfocused, and it never brought Takki back on this laptop (windows-validation E2, 2026-09-28). The talk key has nothing behind it in Alpha. **[M for E2, A for the rest]**
- **Beta: the talk key and any unfocused resume key.**
  - Push-to-talk inside Takki works from the window, because the window has focus.
  - The voice "resume" intent spoken while Takki is *unfocused* needs the talk key to be seen while unfocused, and so does a held resume key. A window cannot see either.
  - Beta needs a narrow global hook, or `RegisterHotKey`, for those keys only. It never needs character translation. **[A]**
  - Whether either is worth having depends on the raise question ADR-028 already defers to Beta: a raise that cannot get past the foreground lock leaves an unfocused trigger nothing to do but speak a hint.

### 7. ADR-033's three Windows checks

- **A landing on Enter, Backspace, Shift (either), Tab or Caps Lock** arrives as a `KEYDOWN`/`KEYUP` pair with its scan code (40, 42, 225/229, 43, 57) and **no `TEXTINPUT`**. **[M]** (is 22, 24; `auto` 1.) SDL produces no `TEXTINPUT` for control characters (Enter, Tab, Backspace). The window can therefore say *which* non-character key was pressed. Whether such a press counts as a landing is ADR-033's call (#12m), not a capture limitation.
- **Keys with side effects:**
  - **Caps Lock** toggles the case of what follows (`A`, `F` in is 23). Case is folded at the boundary, so scoring is unaffected. The state outlives the session, and `KEYDOWN`'s `mod` carries it (bit `0x2000`). **[M]**
  - **Tab** did nothing in Takki's window: no focus change, no text. **[M]**
  - **Left Shift pressed five times** opened the Sticky Keys box, and the window lost focus 0.58 s after the fifth release. **[M]** (is 26, one trial.)
  - **Right Shift held for about 8.5 s** opened the Filter Keys box, and the window lost focus. **[M]** (is 27, confirm 4, two trials.)

  Both boxes are Windows accessibility shortcuts, on by default. Each pauses a lesson with a dialog a blind child cannot see, though a screen reader would read it. A resting little finger on Shift is exactly the press that triggers them. The alignment's "let go" (next point) comes long before the 8 s Filter Keys threshold. Five separate Shift landings in quick succession would not be caught that way. **[A]**
- **A held key is caught in time to say "let go".** The first OS repeat arrives 505–512 ms after the press in both sources (§2). In the window:
  - a character key repeats its `TEXTINPUT` with no fresh `KEYDOWN`;
  - a non-character key (Shift, Enter) shows nothing between its `KEYDOWN` and `KEYUP` at the pygame level, because pygame drops the repeats.

  So the alignment should detect a hold as **a `KEYDOWN` with no `KEYUP` after a set time**, a deadline checked every tick like every other timer ([concurrency-model § Timers](../concurrency-model.md)). That works for every key and does not depend on the user's repeat-delay setting. **[A]**

## The candidates against the measurements

| | (1) pynput + `join()` | (1r) pynput + `ToUnicodeEx` on a private thread | (2) Takki's window | (3) hook for key state + window for character |
|---|---|---|---|---|
| Composed character | **Wrong** for `´´`, `´k`, `^^`, `^k`, `°a` **[M]** | Matches the window in all 68 ordinary steps **[M]**, but has to copy Windows' rules for keeping compose state: clear on focus change (Windows does, 7/7 **[M]**), and track keys the window never got (Space of Win+Space) **[M]** | Windows' own result, by construction **[M]** | as (2) |
| Layout switch | Mixed layouts **[M]** | Must ask the window's layout on every key **[A]** | Follows it, and `KEYMAPCHANGED` announces it **[M]** | Character follows; the hook side mixes layouts **[M]** |
| Held-key rule | Tier C's evidence (2026-09-26) | as (1) | Fresh `KEYDOWN` vs repeat: 764/764 **[M]** | Hook, as (1) |
| Release for every press | Lost under Filter Keys, 2/2 **[M]** | as (1) | Always, synthesised at focus loss **[M]** | as (1) |
| Dead key: which, and clearing it | Char and `is_dead` from a stale table **[M]** | Clear its own state, and the window's separately **[A]** | Scan code; clear on the window thread, 10/10 **[M]** | as (2) |
| Keys while unfocused | Yes **[M]** | Yes | **No** **[M]** | Yes |
| Streams to pair | One | One | One | Two: 14% split ticks, 0.8% interleaved **[A, from measured times]** |
| Threads | Hook thread | Hook thread + layout polling | None added: SDL's pump already runs on the main thread | Both |

## The decision

**Candidate (2): Takki takes characters and physical key state from its own window.** The character comes from `TEXTINPUT`. Key identity, press, release and repeat come from `KEYDOWN`/`KEYUP`, keyed on scan code. In Alpha, pynput is removed from Takki's input path.

What it rests on:

- **The character is Windows' own answer, not a reconstruction.** That is measured for every dead-key case, after layout switches, and after focus changes.
- **Candidate (1) repaired can match the composition** (68 of 68 ordinary steps). It can do so only by copying the window's state from outside: its layout on every key, its compose-state clearing on focus change, and keys it never received. Each of those rules was found here only by measuring a difference. That is the same failure as pynput's own, a second copy of state that Windows keeps, which goes wrong silently when the two disagree.
- **(2) never leaks a down-state.** The hook lost two Right Shift releases.
- **(2) turns roadmap § D's silent layout switch into an event** on a queue Takki already drains.
- **(3) buys nothing (2) lacks in Alpha.** It costs a second stream that must be paired by key, and it keeps the hook's lost releases and mixed layouts.
- **What (2) loses is the unfocused key, which Alpha does not use** (Alt+Tab is the way back) and Beta needs only for a talk or resume key, never for characters.

## What #14 has to build or re-check, from this note

- **One reader for SDL's queue.**
  - `PygameFocusSource.poll()` already drains the whole queue every tick (ADR-028 § C8). `KEYDOWN`, `KEYUP`, `TEXTINPUT` and `KEYMAPCHANGED` must reach the key reader from that one drain, never through a second `get()`.
  - The key events are then produced on the main thread, not on a listener thread.
- **`KeyEvent` changes shape.** It needs the scan code, the SDL key code (for named keys and bindings), and the text, as a separate event or attached to its press. The "fresh since the last `TEXTINPUT`" rule distinguishes a repeat (§2).
- **One press can carry two characters** (`´k`). The capture layer needs a rule for it, most simply "the press's text is everything its `KEYDOWN` produced", leaving the engine to treat a two-character press as wrong. **[A]**
- **Space now produces a `TEXTINPUT`** (`' '`). Today pynput reports Space as `Key.space`, which is System. The taxonomy must keep Space System, decided from the key and not the text. Enter, Tab and Backspace produce no text (§7).
- **Bindings are pynput key names today** (`ctrl_r`, `esc`, `f1` in `config.py`). They need SDL equivalents, or a mapping.
- **The focus model's down-state should be keyed on scan code, not on the folded character.**
  - SDL's synthesised `KEYUP` at focus loss means no down entry leaks across a focus change.
  - A key still held when focus returns is invisible to the window (§2) until it is released and pressed again.
- **The tier C trace tools read pynput** (`spikes/pynput_trace_spike.py`, `spikes/c7_trace_vs_dump.py`). Re-running tier C against the new source needs a trace taken from the window.
- **The pynput listener and its thread go.** [concurrency-model.md](../concurrency-model.md)'s thread inventory and its reason for an unbounded queue (the hook timeout) change with it.
- **Not measured, for #14 to check:**
  - **A key whose auto-repeat is still running when focus returns.** No trial produced it, because Alt+Tab stops the repeat. SDL might report its next repeat as a fresh press. **[A]**
  - **Physical Alt+Shift** as a layout switch on this machine.

## Limits

- **One laptop, one keyboard.**
- **The hook-to-window lag** was measured with the spike polling SDL every 1 ms, not inside Takki's loop. The 60 Hz figures are a replay of those times.
- **Sticky Keys** is one trial.
- **The replay of (1r) assumes the layout stays fixed within a step.** It therefore mis-replays the keys typed after the in-step switch in switch 5. That is a limit of the replay, not of (1r).
