# Windows validation run sheet (alpha #12b-2)

> **What this is.** [windows-validation.md](../../windows-validation.md) § *Running order*, rendered as test cases in execution order: what to do, the exact command, what to expect, and where to write the result. **This sheet is the single source of truth for this run.** Record here during the run. Results, raw output and the finding stay here; nothing is copied back into the protocol.
> **Generated:** 2026-09-26, from the protocol at `5d34a46` plus the uncommitted 2026-09-26 edits that introduced run sheets.
> **Protocol.** The steps, commands and pass conditions are copied from the protocol, and this sheet adds none of its own. Step numbers (**S1–S61**) are the protocol's *Running order* numbers. If the protocol changes before the run, generate a new dated sheet instead of editing this one.

**Consoles.** Both are PowerShell in Windows Terminal, in `C:\Users\smara\github\takki`. Never Git Bash.

- **[T]** is the *Takki console*: the launch line only.
- **[2]** is the *second console*: everything else. Typing in [2] pauses Takki. That is expected; Alt+Tab back.

**The launch line**, every time, in [T]:

```powershell
uv run takki; "exit $LASTEXITCODE"
```

**Result values:** `Pass` · `Fail` · `Not run` (say why). Write what you *heard* straight away.
**⛔** marks a stop rule. **↺** marks a restore that must happen before the next step.

---

## Sitting 0: prepare (any day before Sitting 1, ~15 min)

Date:

### RS-00.1 No stray Python processes (S1)

[2]
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId, CommandLine
```
**Expect:** only VS Code language servers. Stop anything else.

- Listed / stopped:
Listed, nothing stopped:
    18908 c:\Users\smara\github\takki\.venv\Scripts\python.exe c:\Users\smara\.vscode\extensions\ms-python.isort-202...
     3368 "C:\Users\smara\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe"  c:\Users\smara\.vs...


### RS-00.2 Has the code changed since T0? (S2)

[2]
```powershell
git diff --stat 6d4a147 -- src tests pyproject.toml uv.lock
```
**Expect:** empty output. Then T0 stands and RS-00.3 is *Not run*.

- Output: empty output

### RS-00.3 Re-run T0 (only if RS-00.2 printed anything)

⛔ **Any failure here: do not start.** File it and fix it in a session first.

[2]
```powershell
uv run pytest
uv run pytest -m windows_only
uv run pytest -m audio
```
**Expect:** all green. `-m audio`: 12 passed, 6 skipped (the Linux pyttsx3 path), ~60 s.

- T0.1 summary line: 604 passed, 2 skipped, 54 deselected in 6.71s
- T0.2 summary line: 43 passed, 617 deselected in 83.90s (0:01:23)
- T0.3 summary line: 12 passed, 6 skipped, 642 deselected in 65.48s (0:01:05)
- **Result:**
All green

### RS-00.4 Fresh data directory, backup folder (S3–S5)

[2]
```powershell
Rename-Item "$env:LOCALAPPDATA\Takki" "Takki.pre-12b"
Remove-Item "$env:USERPROFILE\Documents\Takki"
New-Item -ItemType Directory "$env:LOCALAPPDATA\Takki-backup"
```
- Done: check

### RS-00.5 US layout, environment capture (S6–S7, P4)

1. Win+Space → **English (US)**.
2. [2]
   ```powershell
   uv run python spikes/windows_env_capture.py
   ```
**Expect:** the `A2` and `A3` lines say `pass`. If A3 reports `de`, the switch did not take. Switch again and re-run.

- A2 line: pass
- A3 line: pass

### RS-00.6 Hardware and NVDA (S8–S9)

- Laptop charged (for G2): check
- soundcore Space Q45 paired (for F3): check
- Portable NVDA created (nvaccess.org → run → *Create portable copy*)? If not, G3 and A5 (with NVDA) are *Not run*:

---

## Sitting 1: day 1 (~2 h)

Date:26-09-2026  Start time: 11:58
Commit (`git rev-parse --short HEAD`): c049454

### Part A: three startup refusals

Each launch exits before a window or database exists.

### RS-01 · A3b: refuses on the German layout (S1–S3)

1. Win+Space → **German**.
2. [T] launch line:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
**Expect:** `exit 2` and `Takki cannot start: language 'en' is configured but the active keyboard is 'de'.`, then the Win+Space remedy line.

↺ **Win+Space → English (US).**

- Printed: pygame 2.6.1 (SDL 2.28.4, Python 3.11.15)
Hello from the pygame community. https://www.pygame.org/contribute.html
Takki cannot start: language 'en' is configured but the active keyboard is 'de'.
Set the active Windows keyboard layout to match the lesson language (Win+Space switches between installed layouts), then start Takki again.
- Exit code: 2
- **Result (A3b):**  pass

### RS-02 · A4b: refuses when no voice is installed (S4–S8)

1. Edit `src/takki/config.py` line 13: `LANGUAGE: str | None = None` → `LANGUAGE: str | None = "is"`. Save.
2. Win+Space → **Icelandic**. Both changes are needed: on US the layout check exits 2 before the voice check runs.
3. [T] launch line:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
**Expect:** `exit 3` and `Takki cannot start: no text-to-speech voice is installed for 'is'.`, then the *Settings > Time & language > Speech* line.

↺ **Revert and check**, in [2]:
```powershell
git restore src/takki/config.py
git diff src/takki/config.py
```
The diff must print nothing. ↺ **Win+Space → English (US).**

- Printed: pygame 2.6.1 (SDL 2.28.4, Python 3.11.15)
Hello from the pygame community. https://www.pygame.org/contribute.html
Takki cannot start: no text-to-speech voice is installed for 'is'.
Add one in Windows Settings > Time & language > Speech > Manage voices, then start Takki again.
- Exit code: 3
- Reverted, diff empty: pass
- **Result (A4b, launch half):** pass

### RS-03 · A4c: refuses when no audio output exists (S9–S11)

1. Turn the headset **off**.
2. Settings → System → Sound → *Speakers (Realtek)* → **Don't allow**. The Sound page must list **no** output device. If one is left, the check tests nothing.
3. [T] launch line:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
**Expect:** `exit 4` within ~10 s: `Takki cannot start: the voice cannot play any sound …`.
**Watch for:** a `pygame.error` traceback and `exit 1`. That is a **fail**. Copy the traceback's last line.

↺ **Restore:** Settings → System → Sound → *All sound devices* → Speakers → **Allow**. Headset back on. Play any sound and confirm you hear it.

- Printed (or traceback last line): pygame.error: WASAPI can't find requested audio endpoint: Element not found.
- Exit code: 1
- Time to exit: 9.5 sec
- Audio restored and audible: check
- **Result (A4c):** fail

### Part B: the key trace, no Takki (C1, C2, C4, C5, C6)

Type into **Notepad**, so no keystroke reaches a console.

### RS-04 · Start the trace (S12)

1. Open Notepad.
2. [2]
   ```powershell
   uv run python spikes/pynput_trace_spike.py docs/research/windows-validation-runs/2026-09-26/RS-06.log
   ```
3. Click into Notepad.

### RS-05 · Key gestures (S13–S17)

Do these in order, in Notepad. Pause a second between them so the sections are easy to tell apart in the log.

| Step | Check | Do |
|---|---|---|
| S13 | C1 | Hold `f` for ~2 s, then let go |
| S14 | C2 | Hold Shift. Press `g`. Let go of **Shift first**, then `g` |
| S15 | C4 | `l`, release, `l`, release |
| S16 | C5 | Press `l`, hold ~1 s, let go |
| S17 | C6 | Win+Space → **Icelandic**. Press the key right of `æ` (where US has the apostrophe), then `a`. ↺ **Win+Space → English (US)** |

### RS-06 · Stop the trace and read it (S18)

1. Click into [2] and press **Ctrl+C**.
2. [2] Print the latest section, all of it:
   ```powershell
   $t = Get-Content docs\research\windows-validation-runs\2026-09-26\RS-06.log; $i = ($t | Select-String '=== trace started' | Select-Object -Last 1).LineNumber; $t[($i-1)..($t.Count-1)]
   ```
3. Read it, then judge each row. The raw trace is committed next to this sheet, not pasted here:
   - [RS-06.log](RS-06.log): C1, C2, C4, C5, and C6 as first written (trace started on US).
   - [RS-06is.log](RS-06is.log): the C6 re-run, trace started with Icelandic active.

| Check | Pass condition | Result |
|---|---|---|
| C1 | One `PRESS`, then more `PRESS` lines (repeats), then **one** `RELEASE`. No `RELEASE` between repeats | pass |
| C2 | Press and release report the same key: `char='G'` down and `char='g'` up is a pass. `None` or an unrelated character on release is a fail | pass |
| C4 | `PRESS`/`RELEASE`/`PRESS`/`RELEASE`: two actuations | pass |
| C5 | One `PRESS`, repeats, one `RELEASE`: one actuation | pass |
| C6 | One composed `char='á'` arrives | invalid as written, trace stayed on US mapping while Notepad composed á |

⛔ **S19: C1, C2, C4 or C5 failed → stop.** Do not practise Stage 0. Amend ADR-027 § First-Attempt Counting in a Claude session, then re-run tier C and all of D from a fresh database (RS-00.4 again).

### Part C: first launch, eyes closed (G6, B1–B14)

### RS-07 · Before you close your eyes (S20)

You cannot read this during the run. **Memorise this order**, then record everything in RS-08 straight afterwards.

0. **Start.** Stopwatch in one hand. In [T], press Enter on the launch line and start the stopwatch at the same moment. **Close your eyes.**
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
1. **B1.** The first thing you should hear is the introduction. *"Paused. Takki is not the active window."* first = B1 fail. Alt+Tab to Takki and carry on.
2. **B2.** Stop the stopwatch at the first spoken word.
3. **B3.** The `f` and `j` introduction lines are complete to the last word.
4. **B5.** Answer correctly: chime, then the next letter.
5. **B7.** Press the correct key *while* the letter is still sounding (~1.4 s long). Speech cuts, and the chime comes at once.
6. **B8.** When the drill alternates, answer the current letter and the next one in one quick burst.
7. **B6.** Press **one** wrong key, **once** (deliberate error 1 of 2). Error tone, same letter again.
8. **B9 → B10.** Stay silent: three re-prompts (~45 s). Wait another 15 s. No fourth re-prompt. Then answer correctly.
9. **B11.** Tap Escape quickly: the prompt is read again.
10. **B12.** Hold Escape past 800 ms: one restart at the threshold, key still down.
11. **B13.** Escape at ~700 ms (should re-read), then ~900 ms (should restart).
12. **B14.** Hold Escape 5 s or more: exactly one restart.
13. **G6** ends when you hear the **second** introduction script. Stop there and do not answer the new letter yet. RS-09 starts at that point.

### RS-08 · Record Part C (S21)

| Check | Pass condition | Observed | Result |
|---|---|---|---|
| G6 | Never needed the screen, the console or the mouse, launch → second introduction | | |
| B1 | Window took the foreground without a click. No "Paused" first | | pass |
| B2 | Launch → first word, in seconds (expect ~2 s; note anything past ~5 s) | 3,4 s | pass |
| B3 | `f` and `j` introduction lines complete, in order, before the first prompt | | pass |
| B4 | Letter names, not words: `f` `j` now; `r` `v` `u` `m` fill in by RS-12 | f: j: r: v: u: m: | |
| B5 | Chime, then the next letter; the chime feels immediate | | pass |
| B6 | Error tone, **same** letter asked again, prompt stays open | | pass |
| B7 | Letter cut, chime not delayed | difficult to hit before end of letter | pass |
| B8 | Both keypresses landed and were counted | | pass |
| B9 | Three re-prompts, then quiet with the prompt open. A 4th re-prompt = fail | | pass |
| B10 | The answer after the silence was taken as a first attempt | | pass |
| B11 | Quick Escape tap → prompt read a gain, no restart | | pass |
| B12 | Escape held past 800 ms → one restart, at the threshold, key still down. *Not testable by ear here: In Stage 0's first step a unit is one letter, so a restart replays the letter just asked and sounds exactly like a re-read. Re-tested in RS-11* | heard prompt again | not distinguishable here → RS-11 |
| B13 | 700 → re-read, 900 → restart. How hard was the boundary to hit? *Not testable by ear here, for the same reason as B12. Re-tested in RS-11* | prompt always start if escape is held long but is only repeated once per keypress, holding the escape beyond the repeat does not trigger a second repeat | not distinguishable here → RS-11 |
| B14 | 5 s+ hold → exactly one restart | | pass |

### Part D: quit, reopen, kill (E9, D2, D5, D3, E11)

### RS-09 · D5 + E9: close during an introduction (S22–S23)

1. When the next introduction starts, **close the window with the mouse before answering the new letter.**
   **Expect:** [T] shows `exit 0`.
2. [2]
   ```powershell
   uv run python -m takki.progress_dump
   ```
   **Expect:** the last session has an `ended_at`.

- Letter you quit on:
- Exit code: 0
- Last session `ended_at`: 2026-09-26T16:25:38
- **Result (E9):** pass

### RS-10 · D2 + D5: reopen (S24)

[T]
```powershell
uv run takki; "exit $LASTEXITCODE"
```
**Expect:** `f` and `j` are **not** introduced again (D2). The letter you quit on **is** introduced again (D5).

- Re-introduced: No
- **Result (D2):** pass
- **Result (D5):** pass? what I heard was simply the next letter

### RS-11 · Finish Stage 0 (S25)

Keep practising until all of `r f v u j m` have been introduced and the next introduction names a letter **outside** those six (~360 prompts). Answer correctly. About half way, press **one** wrong key once (deliberate error 2 of 2) and re-check B6. Fill in B4 in RS-08 as the letters arrive.

- Start / end time:
- B6 re-check: pass
- Next letter after the six: d and k

**B12 + B13 re-test, once `r` and `u` have been introduced.** From Stage 0's second step each new letter is drilled right after its anchor, in two-letter units: `f r`, `j u`, then `f v`, `j m`. A restart goes back to the start of the unit, so it can now be heard. Do these while being asked the **second** letter of a unit (`r`, `u`, `v` or `m`, just after `f` or `j`). None of them counts as an attempt.

| Check | Do | Pass condition | Observed | Result |
|---|---|---|---|---|
| B12 | Hold Escape past 800 ms | The **anchor** (`f` or `j`) is asked, while the key is still down. Hearing the same letter again means no restart | | pass |
| B13a | Release Escape at ~700 ms | The **same** letter again (re-read) | | pass |
| B13b | Hold Escape to ~900 ms | The **anchor** (restart), while the key is still down | | pass |
| B13 | How hard was the 800 ms boundary to hit? (tries per side) | Recorded | you quikly get a hang for not pressing to long to get the repeat and simple keep pressing until the reset happens and then release it| pass |

### RS-12 · D1: dump after Stage 0 (S26)

[2]
```powershell
uv run python -m takki.progress_dump
```
**Expect:** six anchor keys (`r f v u j m`) in `key_stats`, and `milestones (none)`.

```text
Profile: dev (id=1, language=en, created 2026-09-26T17:52:40)

key_stats (lifetime)
  key  attempts  correct  accuracy  last_practised_at
  f         201      198    98.5%  2026-09-26T18:11:31
  j         175      174    99.4%  2026-09-26T18:11:32
  m          32       32   100.0%  2026-09-26T18:11:43
  r          74       73    98.6%  2026-09-26T18:11:44
  u          61       61   100.0%  2026-09-26T18:11:35
  v          32       32   100.0%  2026-09-26T18:11:46

key_attempts by calendar day
  key  day        attempts  correct  accuracy
  f    2026-09-26      200      197    98.5%
  j    2026-09-26      175      174    99.4%
  m    2026-09-26       32       32   100.0%
  r    2026-09-26       74       73    98.6%
  u    2026-09-26       61       61   100.0%
  v    2026-09-26       32       32   100.0%

milestones
  (none)

sessions
    id  started_at           ended_at
     1  2026-09-26T17:52:41  2026-09-26T18:12:06
```
- **Result (D1):** pass

### RS-13 · E1–E8: focus and hostile input (S27)

Nothing here counts as an attempt. Do each with a letter being asked, and come back to Takki after each one.

| Check | Do | Pass condition | Observed | Result |
|---|---|---|---|---|
| E1 | Alt+Tab away mid-prompt, then back | Pause announced when you leave, resume announced when you return, and the prompt asked again *after* the announcement, not over it | | pass |
| E2 | Alt+Tab away. Hold **F1** for 1 s | Takki raises itself and resumes, keyboard only | | |
| E3 | Hold F1 from several different apps (Notepad, Explorer, browser, [2]) | Where the raise is refused, the Alt+Tab hint is spoken after ~1.5 s. List which apps raised and which gave the hint | did not manage to raise anywhere, did hear the alt0+tab hint sometimes | not sure|
| E4 | Press the Windows key (Start menu), then return | Pause, then resume | works as expected| pass |
| E5a | Win+L, log back in | Pause, then resume | | |
| E5b | Ctrl+Alt+Del, then Cancel | Pause, then resume | | pass |
| E5c | [2]: `Start-Process powershell -Verb RunAs` and answer **No** | Pause, then resume | returns back to powershell not to Takki | fail? |
| E6 | Press Shift 5 times (Sticky Keys dialog), dismiss it | Pause, then resume. No stuck modifier afterwards | | pass |
| E7 | Mash Backspace, Tab, Enter, Delete, arrows, F-keys, Ctrl+letter, AltGr | Nothing counted, no crash, prompt unchanged | | pass |
| E8 | Press the space bar repeatedly | Ignored | | pass |

### RS-14 · E12: layout switch mid-lesson (S28)

1. With a letter being asked, press **Alt+Shift** (or Win+Space) once to move to German. Listen. Does Takki say anything?
2. Answer only if the letter is one of `r f v u j m`.
3. ↺ Switch back to **English (US)**. [2]:
   ```powershell
   uv run python spikes/windows_env_capture.py
   ```
   The **A3** line must say `pass`.
4. Alt+Tab to Takki.

**Expected (a known gap):** nothing is said, and the lesson carries on.

- Chord used: Win+Space
- Anything heard: No
- A3 line after switching back: pass
- **Result (E12, recorded as a Beta item):** pass

### RS-15 · E11: Ctrl+C in the launching console (S29)

1. Click into [T] and press **Ctrl+C**. **Expect:** a clean exit, `exit 0`.
2. [2]
   ```powershell
   uv run python -m takki.progress_dump
   ```
   **Expect:** the session has an `ended_at`.

- Printed in [T]: Nothing
- Exit code: no exit code
- `ended_at` present: yes
- **Result (E11):** fail?

### RS-16 · Back up (S30)

Takki must be closed. [2]:
```powershell
Copy-Item "$env:LOCALAPPDATA\Takki\takki.sqlite*" "$env:LOCALAPPDATA\Takki-backup\"
Get-ChildItem "$env:LOCALAPPDATA\Takki-backup"
```
*Restore, if D3 requires it:* close Takki, delete the files in `%LOCALAPPDATA%\Takki`, and copy these back.

- Backed up:

### RS-17 · D3: kill mid-write (S31–S34)

1. [T] launch:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
2. [2] type and press Enter:
   ```powershell
   Start-Sleep 30; Get-Process | Where-Object MainWindowTitle -eq 'Takki' | Stop-Process -Force
   ```
3. Alt+Tab to Takki and keep answering steadily until it goes silent.
4. **Before relaunching** (a relaunch replays the WAL and destroys the evidence), [2]:
   ```powershell
   uv run python spikes/db_integrity_check.py
   ```
   **Expect:** `D3: PASS` (integrity ok, `key_stats` and `key_attempts` consistent, exactly one unended session).

⛔ **D3 fails → stop.** Restore the backup (RS-16) and record the no-go.

5. [T] relaunch. The progress must still be there. Answer 3 prompts, then close with the mouse.
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```

- `D3:` line:
- Progress still there after relaunch:
- **Result (D3):** pass

### RS-18 · A4 on the fresh database; day 1 dump (S35)

[2]
```powershell
uv run python spikes/windows_env_capture.py
uv run python -m takki.progress_dump
```
**Expect (A4):** `%LOCALAPPDATA%\Takki\takki.sqlite`, `journal_mode` `wal`, and **no** `Documents\Takki`.

- A4 line:
- **Result (A4):** pass

```text
config.LANGUAGE = None (resolved language: 'en')

Installed layouts (read by HKL, nothing activated):
  HKL 04070407  lang=de  36 graphemes  own table: 'unexpected dead-acute'
      as 'en': "language 'en' is configured but the active keyboard is 'de'"
      as 'is': "language 'is' is configured but the active keyboard is 'de'"
  HKL 04090409  lang=en  26 graphemes  own table: 'matches'
      as 'de': "language 'de' is configured but the active keyboard is 'en'"
      as 'is': "language 'is' is configured but the active keyboard is 'en'"
  HKL 040f040f  lang=is  36 graphemes  own table: 'matches'
      as 'en': "language 'en' is configured but the active keyboard is 'is'"
      as 'de': "language 'de' is configured but the active keyboard is 'is'"

Result column, one row per line:

A1: Windows 11 Home 25H2 (build 26200.9550); Python 3.11.15; pygame 2.6.1 / SDL 2.28.4; Documents = `C:\Users\smara\Documents` (not OneDrive-redirected); administrator, not elevated (filtered token); commit b3fd7b4 (modified tracked files)
A2: `en` from raw locale `en-150` -- pass
A3: pass -- `Layout.lang` = `en` (locale `en-150`); 26 graphemes, 26 keys; anchors (2,4)=r (3,4)=f (4,4)=v (2,7)=u (3,7)=j (4,7)=m; verify_layout('en') = None (would start)
A4: pass -- `C:\Users\smara\AppData\Local\Takki\takki.sqlite` (77824 bytes); journal_mode `wal`; -wal present, -shm present; stray Documents\Takki: none
A4b: find_voice: pass -- `en` -> `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\TTS_MS_EN-US_DAVID_11.0`; `de` -> `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\TTS_MS_DE-DE_HEDDA_11.0`; `is` -> `None`. Launch half: by hand
A5: `None` (NVDA not running at capture)

Profile: dev (id=1, language=en, created 2026-09-26T17:52:40)

key_stats (lifetime)
  key  attempts  correct  accuracy  last_practised_at
  f         201      198    98.5%  2026-09-26T18:11:31
  j         175      174    99.4%  2026-09-26T18:11:32
  m          32       32   100.0%  2026-09-26T18:11:43
  r          74       73    98.6%  2026-09-26T18:11:44
  u          61       61   100.0%  2026-09-26T18:11:35
  v          32       32   100.0%  2026-09-26T18:11:46

key_attempts by calendar day
  key  day        attempts  correct  accuracy
  f    2026-09-26      200      197    98.5%
  j    2026-09-26      175      174    99.4%
  m    2026-09-26       32       32   100.0%
  r    2026-09-26       74       73    98.6%
  u    2026-09-26       61       61   100.0%
  v    2026-09-26       32       32   100.0%

milestones
  (none)

sessions
    id  started_at           ended_at
     1  2026-09-26T17:52:41  2026-09-26T18:12:06
```

End time: 18:12:06 **with a lot of interruptions due to investigations**

---

### Sitting 1 notes (recorded at the end of 2026-09-26)

- **About an hour went on key-capture investigation** after RS-06 (C2 and C6; see [RS-06.log](RS-06.log), [RS-06is.log](RS-06is.log), roadmap A5, alpha-plan #13 and #14).
- **The database was recreated this evening, before Sitting 2.** Quitting and restarting Takki introduced a new key at every start (alpha-plan #12d), so the first database had fingers well beyond Stage 0. D4 needs two dates in one database, so a fresh one was made today. Stage 0 was then practised in **one continuous session** through `v` and `m`, ending at the next introduction. Its dump: **nine keys** in `key_stats`, the six anchors all present, lowest accuracy **98.5%**, `milestones (none)`. D1 above refers to this database, and D4 runs on it.
- **Letters sometimes went unspoken** (B5, F1): silence until the B9 re-prompt or an Escape tap, even with deliberately slow typing, and apparently more often with more keys. Cause not settled; see alpha-plan #12c and `spikes/silent_prompt_spike.py` (not yet run).
- **Findings filed during the sitting** (not results of this run, but raised by it): alpha-plan #12c (silent letter, A4c traceback), #12d (a new key at every start), #12e (practice weighted by English frequency); roadmap § D entries on `n` versus `m`, the ramp-up autopilot, the J introduction and the script-to-prompt hand-over, chime overlap, lessons and breaks, untaught recovery keys, the Takki key, and the Layer-1 restart.

## Sitting 2: day 2 (a **later calendar date** than Sitting 1, ~2–2.5 h)

Start after local midnight following Sitting 1. Do not start before midnight and practise across it (that is D6).

Date:  27-09-2026 Start time: 08:15

### RS-19 · Day 1 rows present (S36)

[2]
```powershell
uv run python -m takki.progress_dump
```
- Day 1 rows present: **yes**, all six anchors have a `2026-09-26` row. *Taken 08:25, after RS-20 had started (Takki launched 08:16, session 2 in progress), so day-2 rows are already present too.* `f`'s day-1 row shows 180, where RS-12/RS-18 showed 200. This is the 200-attempt rolling window (`ATTEMPT_WINDOW`, [sqlite_store.py](../../../../src/takki/persistence/sqlite_store.py) prunes each key's oldest rows): 180 + 20 today = 200. `key_stats` is lifetime and unpruned (221). Expected, not data loss. Sitting 1 notes say "nine keys"; the database on disk had six at the end of day 1, as the RS-12/RS-18 dumps show.
- **Result (RS-19):** pass

```text
Profile: dev (id=1, language=en, created 2026-09-26T17:52:40)

key_stats (lifetime)
  key  attempts  correct  accuracy  last_practised_at
  d          70       67    95.7%  2026-09-27T08:23:51
  f         221      217    98.2%  2026-09-27T08:18:06
  j         195      194    99.5%  2026-09-27T08:18:06
  k          62       62   100.0%  2026-09-27T08:23:48
  l          11       11   100.0%  2026-09-27T08:23:50
  m          38       38   100.0%  2026-09-27T08:23:10
  r         121      119    98.3%  2026-09-27T08:23:07
  s          11       11   100.0%  2026-09-27T08:23:46
  u          91       89    97.8%  2026-09-27T08:23:12
  v          32       32   100.0%  2026-09-26T18:11:46

key_attempts by calendar day
  key  day        attempts  correct  accuracy
  d    2026-09-27       70       67    95.7%
  f    2026-09-26      180      177    98.3%
  f    2026-09-27       20       19    95.0%
  j    2026-09-26      175      174    99.4%
  j    2026-09-27       20       20   100.0%
  k    2026-09-27       62       62   100.0%
  l    2026-09-27       11       11   100.0%
  m    2026-09-26       32       32   100.0%
  m    2026-09-27        6        6   100.0%
  r    2026-09-26       74       73    98.6%
  r    2026-09-27       47       46    97.9%
  s    2026-09-27       11       11   100.0%
  u    2026-09-26       61       61   100.0%
  u    2026-09-27       30       28    93.3%
  v    2026-09-26       32       32   100.0%

milestones
  (none)

sessions
    id  started_at           ended_at
     1  2026-09-26T17:52:41  2026-09-26T18:12:06
     2  2026-09-27T08:16:37  (in progress)
```

### RS-20 · D4: the anchor rung (S37–S40)

1. Win+Space → check it is on **English (US)**.
2. [T] launch and practise, answering correctly:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
3. Every ~10 minutes, [2]:
   ```powershell
   uv run python -m takki.progress_dump
   ```
   Each of `r f v u j m` needs a row dated **today**, ≥ 25 attempts, ≥ 95% accuracy.
   > **Sheet error, corrected 2026-09-27 during the run.** The protocol's D4 row and `ANCHOR_CRITERION` ([milestones.py](../../../../src/takki/lesson/milestones.py)) define the bar as ≥ 25 attempts and ≥ 95% accuracy **over the key's last 200 attempts, across both days**, plus practice on **≥ 2 dates**. A row dated today proves the second date, and any number of attempts counts. "Qualifying" in the table below uses this reading. The bar is checked at block boundaries.
4. When `anchor` appears in `milestones`, practise **one more block**, then dump again. `anchor` must be there **exactly once**.
5. If after 30 min some anchor key still has no row for today, write down which one. That is a finding.

| Time | Keys qualifying today | `anchor` in milestones? |
|---|---|---|
| 08:25 | `r f u j m` (window: r 98.3%, f 98.0%, u 97.8%, j 99.5%, m 100%, all on 2 dates). **`v` not yet**: 32 attempts at 100%, but no attempt today. `d k l s` introduced since 08:16 | no |
| 08:29 | Unchanged: `r f u j m` (window: r 98.4%, u 98.1%, f/j/m untouched since 08:18/08:23). **`v` still no attempt today.** No new letter since `s`; this stretch went to `d k l s u r` | no |
| | | |
| | | |
| | | |

- Keys never reached today after 30 min (finding): *(confirmed from the code at ~08:33, before the 30 minutes were up)* **`v`**, with zero prompts since 08:16. [session.py](../../../../src/takki/session.py) `_begin_block` runs `_introduce()` before `next_block()`. So the boundary where one ramp-up ends starts the next step's ramp-up, and no steady-state block runs between steps. This is a within-session form of #12d, not only the restart form. Mechanism, from [drills.py](../../../../src/takki/lesson/drills.py) `next_block`: spaced re-exposure (`_reexpose`) is the path that serves a key not practised this session, rarest first. That would be `v`. It only runs on steady-state blocks, and ramp-up blocks skip it. Session 2 has done nothing but ramp-ups (`d`, `k`, `l`, `s` introduced in ~7 min, alpha-plan #12d). Phase C's partners are the 2–3 most frequent Active keys, which never includes `v` (#12e). So `v` cannot be asked until introductions stop. Consequence for D4: **the anchor rung is blocked by the introduction pacing, not by the child's accuracy.** Five of six anchors already meet the bar.
- `anchor` count after the extra block: 0. The rung never fired, so step 4 was never reached.
- **Result (D4):** **Fail**, recorded 08:38 at the developer's call. The rung is unreachable in this build because introductions starve `v`. Persistence and the gate itself did not fail: five of six anchors meet the bar over two dates. **Design decision reopened** (developer, 2026-09-27): whether the curriculum waits for the anchor rung. Learning six keys in one day is realistic only for a child already used to a keyboard or with exceptional motor skills, so the day-one cost that decided "does not wait" is smaller than assumed. See roadmap § D *Does the curriculum wait for the anchor gate?* and alpha-plan #12d. **D4 must be re-run** after #12d/#12e.

```text
Taken 08:38; no attempts since 08:29:19.

Profile: dev (id=1, language=en, created 2026-09-26T17:52:40)

key_stats (lifetime)
  key  attempts  correct  accuracy  last_practised_at
  d          92       89    96.7%  2026-09-27T08:29:13
  f         221      217    98.2%  2026-09-27T08:18:06
  j         195      194    99.5%  2026-09-27T08:18:06
  k          81       81   100.0%  2026-09-27T08:28:03
  l          49       48    98.0%  2026-09-27T08:29:19
  m          38       38   100.0%  2026-09-27T08:23:10
  r         125      123    98.4%  2026-09-27T08:28:46
  s          45       44    97.8%  2026-09-27T08:29:16
  u         103      101    98.1%  2026-09-27T08:29:18
  v          32       32   100.0%  2026-09-26T18:11:46

key_attempts by calendar day
  key  day        attempts  correct  accuracy
  d    2026-09-27       92       89    96.7%
  f    2026-09-26      180      177    98.3%
  f    2026-09-27       20       19    95.0%
  j    2026-09-26      175      174    99.4%
  j    2026-09-27       20       20   100.0%
  k    2026-09-27       81       81   100.0%
  l    2026-09-27       49       48    98.0%
  m    2026-09-26       32       32   100.0%
  m    2026-09-27        6        6   100.0%
  r    2026-09-26       74       73    98.6%
  r    2026-09-27       51       50    98.0%
  s    2026-09-27       45       44    97.8%
  u    2026-09-26       61       61   100.0%
  u    2026-09-27       42       40    95.2%
  v    2026-09-26       32       32   100.0%

milestones
  (none)

sessions
    id  started_at           ended_at
     1  2026-09-26T17:52:41  2026-09-26T18:12:06
     2  2026-09-27T08:16:37  (in progress)
```

### RS-21 · C7 + C3: trace against dump (S41–S46)

1. With a letter being asked, **do not answer it.** [2]:
   ```powershell
   uv run python spikes/pynput_trace_spike.py docs/research/windows-validation-runs/2026-09-26/RS-21.log
   ```
   Takki pauses. Alt+Tab back to Takki.
2. **From here until step 5: do not leave the window, and do not press Escape.** Answer only after hearing the letter, and wait for introductions to finish. Answer about 40 prompts, mixing in:

   | Kind | Target | Tally |
   |---|---|---|
   | Correct first answers | the rest | |
   | Wrong, then right | ~8 | |
   | Held correct key (~1 s) | 2 | |
   | Shift + letter | 2 | |
   | **Caps Lock on** (C3), then turn it off | ~10 | |

3. **C3 by ear:** Caps Lock answers get the normal chime.
4. Close Takki with the mouse.
5. Click into [2] and press **Ctrl+C** to stop the trace.
6. [2]
   ```powershell
   uv run python spikes/c7_trace_vs_dump.py docs/research/windows-validation-runs/2026-09-26/RS-21.log
   ```
   **Expect:** `C7: PASS`. **C3** passes if C7 passes *and* the trace line reports upper-case actuations above zero.

⛔ **C7 fails:** read the divergence block first. If it points at something you did (typed during an introduction, left the window, pressed Escape near 800 ms), run RS-21 again. If not, stop: the dump's numbers are not what the engine thinks.

```text
Trace: docs\research\windows-validation-runs\2026-09-26\RS-21.log section 1 of 1, started 2026-09-27 10:45:52.702
DB:    C:\Users\smara\AppData\Local\Takki\takki.sqlite profile 1; 53 key_attempts rows in [10:45:52, 10:50:56]

Trace: 553 presses, 96 releases; 122 named-key events; 408 held-key repeats removed (rule 2); 59 actuations, 18 of them upper case (rule 1); 0 releases reported a different case than their press
Walk:  53 attempts derived; 0 retry presses; 0 restarts abandoning an answered prompt, 0 on an unanswered one; 0 actuations after the last row

  key  trace att  trace ok  dump att  dump ok
  d            7         6         7        6
  l           14        13        14       13
  r            7         6         7        6
  s           15        13        15       13
  u           10         9        10        9
  all         53        47        53       47

C7: PASS -- 53 prompts; trace-derived 53 attempts / 47 correct, dump 53 / 47; 408 held repeats, 18 upper-case, 0 retries, 0 restarts; attempt-to-row skew +0..+0 s
```
- C3 by ear (normal chime with Caps Lock):
- **Result (C7):** pass
- **Result (C3):** pass

### RS-22 · F1 + E10: endurance and the mouse soak (S47–S50)

1. [T] launch:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
2. [2] Memory at the start. Take it **before** step 3, because the helper occupies [2] for 25 minutes:
   ```powershell
   Get-Process | Where-Object MainWindowTitle -eq 'Takki' | Select-Object WorkingSet64
   ```
3. [2] Start the mouse helper, then Alt+Tab to Takki:
   ```powershell
   uv run python spikes/sdl_queue_soak.py drive --minutes 25
   ```
   The cursor circles inside Takki's window. It pauses while another window is in front, and stops if you move the mouse.
4. Practise the whole time, 60–90 minutes.
5. At the end, [2] (the helper has finished by then):
   ```powershell
   Get-Process | Where-Object MainWindowTitle -eq 'Takki' | Select-Object WorkingSet64
   ```
6. **E10:** close Takki with the mouse. It must close within a couple of seconds. If it does not, press Ctrl+C in [T] and record a fail.

> **Deviation: F1 was run by a bot, not by hand** (developer's decision, 2026-09-27). `spikes/silent_prompt_spike.py --minutes 60` ran the real Takki: real SAPI voice, window, mixer, pynput hook and `SendInput` keys. It used a **copy** of the database, so the real one was not written. A bot answered every prompt correctly, only after the letter had finished and a 0.4–1.2 s pause. What that leaves out: wrong answers (the error tone), held keys, and typing over speech. The spike also keeps its log in memory, so a slope of about 1–3 MB is its own. The developer listened for sound quality. Memory was sampled every minute from [2]: [RS-22-memory.csv](RS-22-memory.csv), with both `WorkingSet64` (the protocol's measure) and private bytes. Full speech/cue log: [RS-22-silent-prompt.log](RS-22-silent-prompt.log).

- Start time / WorkingSet64: 11:59:03, 82.2 MB (private 561.4 MB). **12:00:03, after start-up: 117.5 MB (private 592.5 MB)**, the baseline used.
- Helper finished (minutes of motion): not started (E10 not run, see below). Step 3 skipped.
- Mid-run readings (added, not in the protocol; every minute, excerpt), `WorkingSet64` / private:

  | Time | Working set | Private |
  |---|---|---|
  | 12:00 | 117.5 | 592.5 |
  | 12:09 | 119.3 | 593.8 |
  | 12:29 | 121.4 | 594.9 |
  | 12:39 | 84.6 | 595.0 |
  | 12:49 | 60.8 | 596.2 |
  | 12:59 | 60.0 | 596.2 |

- End time / WorkingSet64: 12:59:04, **60.0 MB** (private **596.2 MB**). Private memory grew 3.7 MB over 1,894 answers (~2 KB each), in steps that stopped rising after 12:49. That is consistent with the spike's in-memory log (~11,500 lines plus 1,895 speech records) plus 16 introductions' worth of drill state, and not with a per-prompt leak. The working set's fall after 12:35 is Windows trimming the working set, not Takki releasing memory. The protocol's measure alone would read as a 57 MB *drop*.
- Latency drift? Keypress to cue, from the log (1,894 pairs; values are quantised by Windows' ~15.6 ms clock):

  | Minutes | n | Median | p95 | Max |
  |---|---|---|---|---|
  | 0–10 | 309 | 16 ms | 32 ms | 63 ms |
  | 10–20 | 313 | 16 ms | 32 ms | 47 ms |
  | 20–30 | 322 | 16 ms | 31 ms | 32 ms |
  | 30–40 | 311 | 16 ms | 32 ms | 32 ms |
  | 40–50 | 320 | 16 ms | 32 ms | 32 ms |
  | 50–60 | 317 | 16 ms | 32 ms | 32 ms |

  No drift. Audio degradation: **none heard** (developer). Cue still immediate at the end: yes, 16 ms median in the last 10 minutes.
- Speech path (#12c (1), run as part of this): **1,895 letters spoken, 1,895 AUDIBLE**, with no FLAG, SHORT, CUT or MISSING, and no B9 timeouts. With no keypress overlapping speech, no letter was lost in Takki's speech path over an hour. **By ear:** the developer listened only for about the first and last minute and heard nothing missing. A loss on the output side during the other 58 minutes would not have been noticed, and the spike cannot see one. **Contrast:** letters went unspoken *often* during this sitting's hand practice (RS-20, RS-21), on the same machine and the same day. The bot presses only 0.4–1.2 s *after SAPI returns*, so it never pressed at the moment a letter ends. That moment turned out to be the cause: see RS-22b.
- Side observation: the copy introduced **16 letters in 60 minutes** (`a`, then pairs roughly every 7.5 min, to `z`). With a perfect bot the pacing gates are legitimately open, so this is not by itself #12d. But it is the rhythm an accurate child would get.
- **Result (F1):** **pass**, run by a bot, as the deviation note says.
- Close time, exit code: not a mouse close: the bot stopped Takki through the session loop at 60:04. `takki exit 0`.
- **Result (E10):** **Not run**, the developer's decision, 2026-09-27. The overflow is visible in the code, so a run would only confirm it. [focus.py](../../../../src/takki/display/focus.py) `poll()` takes three event types off SDL's queue and nothing else reads it, so every other event accumulates to the 65,535 cap, after which `QUIT` is dropped. Treated as an architectural flaw to fix, not a behaviour to measure: alpha-plan #12c item (3). E10 becomes that fix's regression check in #14's re-run.

### RS-22b · Silent letters, by hand (added 2026-09-27; not a protocol step)

Why: the bot run (RS-22) lost no letters, while this sitting's hand practice lost them often. [2] `uv run python spikes/silent_prompt_spike.py --manual --out docs/research/windows-validation-runs/2026-09-26/RS-22b-manual.log`: the same instrumented Takki on a copy of the database, no bot. The developer typed as usual and tapped Escape the moment a letter went unspoken. The spike logs each key with whether it landed inside `speak()`. Memory: [RS-22b-memory.csv](RS-22b-memory.csv), private 592.6 → 592.9 MB over 5 min, flat. Report: [RS-22b-manual.log](RS-22b-manual.log).

- About 5 min, 270 keypresses, 275 letters spoken or queued. No B9 timeouts.
- **Escape taps: 4. FLAG letters: 4. Stops issued after `speak()` had already returned (`worker_speaking=False`): 4.** They are the same four events, one to one:

  The sequence immediately before each tap:

  | Tap | Previous letter's `speak()` | It ended | Key | Key minus end | Next letter |
  |---|---|---|---|---|---|
  | 72.4 s | `l`, from 68.094 s, 1219 ms | 69.313 s | `l` 69.313 s | 0 ms | `a`: FLAG, 0 ms, "completed" |
  | 108.0 s | `s`, from 104.516 s, 1281 ms | 105.797 s | `s` 105.797 s | 0 ms | `a`: FLAG, 0 ms |
  | 263.0 s | `s`, from 259.547 s, 1266 ms | 260.813 s | `s` 260.813 s | 0 ms | `h`: FLAG, 0 ms |
  | 305.3 s | `a`, from 302.110 s, 1093 ms | 303.203 s | `a` 303.203 s | 0 ms | `s`: FLAG, 0 ms |

  Each key arrived in the same clock reading as SAPI's return (Windows' clock resolution is ~16 ms).

- **Mechanism:** alpha-plan #12c (1)'s race, confirmed on hardware. The press reaches `Speaker.interrupt()` after SAPI has returned but before the `finished` event has been dispatched, so the Speaker still believes the letter is sounding. `stop()` sets the cancel flag with nothing left to cancel. The worker has already cleared it and is blocked in `get()`. The next letter's id is above `_cancel_through`, so it is spoken, but `SapiTTS.speak()` finds the flag set and returns at once, and the worker reports it `completed`. Silence until Escape or B9.
- **The window is one clock tick at the letter's end.** A press anywhere inside the letter is harmless. The developer deliberately pressed into speech during the predictable patterns, and none of those presses caused a silence. A press after the `finished` event has been handled is harmless too. 4 in 270 presses (~1.5%) is what presses landing in a ~16 ms window by chance would give, which is several per ten minutes of practice. The bot never hit it because it pressed 0.4–1.2 s after the return.
- **Not silences:** 152 CUT (a press cutting the letter it answers, as designed) and 32 MISSING. The MISSING came from the deliberate presses into the predictable `f g j h` ramp-up cycle, where letters were answered before they started and were cancelled in the queue. No tap followed any of them.
- **Result:** cause of the silent letters found. The output side is cleared: every silence is accounted for by FLAG.

### RS-22c · The window, mapped by script (added 2026-09-27; not a protocol step)

[2] `uv run python spikes/flag_race_sweep.py --minutes 15 --out docs/research/windows-validation-runs/2026-09-26/RS-22c-sweep.txt`. A bot presses the prompted letter at a random offset from its predicted end: −60 to +30 ms, plus controls at −400 ms and +150 ms. It records whether the next letter enters `speak()` with the cancel flag set. Real Takki on a copy of the database. Report [RS-22c-sweep.txt](RS-22c-sweep.txt), per-trial data [RS-22c-sweep.csv](RS-22c-sweep.csv).

**Prediction written before the run**, from `TTSWorker.run_one()` (`speak()` returns → `put(finished)` → `clear_cancel()` → `get()`) and `SessionLoop.tick()` (drains the inbound queue every 1/60 s, in order): a key that reaches the queue before the letter ends but is drained after it is dispatched ahead of `finished`. Its `stop()` sets a flag nothing will clear, and the next letter is silent. So the window is at most one tick (16.7 ms) wide, ends at the letter's end, and moves earlier by the hook latency. There should be no silences outside it.

- 596 trials, **61 SILENT**, all inside **−20.5 to −3.1 ms** of the letter's end (send time). Rate by 2 ms bin: 1/10 at −22, rising to 13/15 at −6 to −4, then **0 from −2 ms on**.
- Controls: mid-letter 0/54, +150 ms 0/58. The 41 bins outside the window: 0 SILENT.
- Rule "SILENT iff the key was dispatched before `finished` and the letter was not cut": **held on 190 of 190** trials where both dispatch times were captured. The other 406 were cut letters or presses after `finished` was dispatched, all clean.
- End-of-letter prediction: median −0.2 ms, sd 3.6 ms (n = 284). Send → key dispatched: median 10.2 ms, max 29.9 ms.
- **Result:** prediction confirmed. The window is one loop tick just before a letter ends, exactly as the code implies.

### RS-23 · Back up day 2 (S51)

[2]
```powershell
New-Item -ItemType Directory "$env:LOCALAPPDATA\Takki-backup\day2"
Copy-Item "$env:LOCALAPPDATA\Takki\takki.sqlite*" "$env:LOCALAPPDATA\Takki-backup\day2\"
```
- Backed up: **yes**, 2026-09-27 ~13:05, to `%LOCALAPPDATA%\Takki-backup\day2\`. `takki.sqlite` 106,496 bytes (last written 10:50:48, the end of RS-21), `-wal` empty, `-shm` 32,768 bytes. The hash of the copied `takki.sqlite` matches the live one. No Takki process was running. RS-22's bot ran on a copy, so this is the database as RS-21 left it.

End time: ~13:05

---

## Sitting 3: changes to the machine (any day after Sitting 2, ~1 h)

Each check changes something about the laptop. Each restore comes straight after its check.

Date:  Start time:

### RS-24 · F3: headset off mid-lesson (S52)

1. Connect the headset and make it the output.
2. [T] launch and practise:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
3. Turn the headset **off**. Keep answering for a minute. Watch [T] for `TTS engine failed on utterance N`. Listen: does speech move to the speakers?

↺ Turn the headset back on.

**Fail:** a frozen loop (no more prompts, and no cues after the headset is back).

- `TTS engine failed` lines (count, N):
- Prompts kept coming:
- SAPI rerouted to the speakers by itself:
- Cues after the headset was back:
- **Result (F3, recorded as a Beta item):**

### RS-25 · F2: sleep and wake (S53)

1. Practise, then Start → Power → **Sleep**.
2. Wake the laptop, log in, Alt+Tab to Takki, and answer 5 prompts. Each should chime.
3. Close with the mouse. Watch [T]: a traceback at exit means the pynput listener died during sleep.

- 5 prompts chimed:
- [T] output at exit, exit code:
- **Result (F2):**

### RS-26 · G2: battery and power saving (S54)

1. Unplug the charger. Settings → System → Power & battery → Power mode **Best power efficiency**, Energy saver **on**.
2. [T] launch and practise for 10 minutes:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
↺ Restore the power mode, turn Energy saver off, and plug the charger in.

- Responsiveness, speech latency:
- **Result (G2):**

### RS-27 · G4: second instance (S55)

1. [T] launch:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
2. [2] with Takki running, launch a second one:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
3. Record what the second instance does. Close both.
4. [2]
   ```powershell
   uv run python spikes/db_integrity_check.py
   ```
**Pass:** it fails clearly, or both work, and the integrity check is clean. Silent corruption is the failure.

- Second instance behaviour, exit code:
- Integrity check line:
- **Result (G4):**

### RS-28 · G5: data directory not writable (S56–S58)

1. Takki closed. [2]:
   ```powershell
   icacls "$env:LOCALAPPDATA\Takki" /deny "${env:USERNAME}:(OI)(CI)(W,D,DC)"
   ```
2. [T] launch. If the window stays up doing nothing, close it. If that hangs, press Ctrl+C.
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
   *Predicted:* a `sqlite3.OperationalError: unable to open database file` traceback and `exit 1`.

↺ **Restore immediately**, [2]:
```powershell
icacls "$env:LOCALAPPDATA\Takki" /remove:d $env:USERNAME
icacls "$env:LOCALAPPDATA\Takki"
```
No line may contain `(DENY)`. Then [T] launch once to confirm Takki starts, and close it:
```powershell
uv run takki; "exit $LASTEXITCODE"
```

- Everything printed (last line of any traceback):
- Exit code:
- Could a person act on it?
- Restored, no `(DENY)`, Takki starts:
- **Result (G5):**

### RS-29 · G3 + A5: NVDA (S59; only with portable NVDA)

1. Start NVDA.
2. [2]
   ```powershell
   uv run python spikes/windows_env_capture.py
   ```
3. [T] launch and practise for 5 minutes:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
4. Quit NVDA (Insert+Q).

- A5 line:
- Double speaking / focus stealing / clean:
- **Result (A5, with NVDA):**
- **Result (G3, recorded as a Beta item):**

### RS-30 · G1: UAC across the whole run (S60)

Did any UAC prompt appear at any point in Sittings 1–3, *other than* the one you raised on purpose in E5c? None is a pass. One that Takki caused is a fail.

- **Result (G1, hands-on half):**

End time:

---

## Optional: D6, a night after Sitting 2

### RS-31 · D6: practise across midnight (S61)

1. Start at about 23:50 and carry on until about 00:10.
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
2. [2]
   ```powershell
   uv run python -m takki.progress_dump
   ```
**Expect:** that sitting's rows split across two dates.

- Split seen:
- Does that feel right for a child?

---

## Summary

**Finding (one line):**

Fill in from the Result lines above. **Hard no-go** checks are in bold.

| Check | Result | Check | Result | Check | Result |
|---|---|---|---|---|---|
| A3b | | **B8** | | **E1** | |
| A4b (launch) | | **B9** | | **E2** | |
| A4c | | **B10** | | E3 | |
| **A4** (fresh DB) | | **B11** | | E4 | |
| A5 (NVDA) | | **B12** | | **E5** | |
| **B1** | | B13 | | E6 | |
| **B2** | | B14 | | E7 | |
| **B3** | | **C1** | | E8 | |
| **B4** | | **C2** | | **E9** | |
| **B5** | | C3 | | **E10** | |
| **B6** | | **C4** | | **E11** | |
| **B7** | | **C5** | | E12 | |
| | | C6 | | **F1** | |
| **D1** | | **C7** | | **F2** | |
| **D2** | | | | F3 | |
| **D3** | | **G1** | | G4 | |
| **D4** | | G2 | | G5 | |
| **D5** | | G3 | | **G6** | |
| D6 | | | | | |

When the run is done, update only this sheet's row in [windows-validation.md](../../windows-validation.md) § Runs: set its *Outcome* to go or no-go. Carry anything that outlives the run into an ADR amendment or roadmap § D.
