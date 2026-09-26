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
- **Result (A4c):** pass

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

**Go:** stopwatch ready. [T] launch line, and start the stopwatch as you press Enter. **Close your eyes.**
```powershell
uv run takki; "exit $LASTEXITCODE"
```

### RS-08 · Record Part C (S21)

| Check | Pass condition | Observed | Result |
|---|---|---|---|
| G6 | Never needed the screen, the console or the mouse, launch → second introduction | | |
| B1 | Window took the foreground without a click. No "Paused" first | | |
| B2 | Launch → first word, in seconds (expect ~2 s; note anything past ~5 s) | | |
| B3 | `f` and `j` introduction lines complete, in order, before the first prompt | | |
| B4 | Letter names, not words: `f` `j` now; `r` `v` `u` `m` fill in by RS-12 | f: j: r: v: u: m: | |
| B5 | Chime, then the next letter; the chime feels immediate | | |
| B6 | Error tone, **same** letter asked again, prompt stays open | | |
| B7 | Letter cut, chime not delayed | | |
| B8 | Both keypresses landed and were counted | | |
| B9 | Three re-prompts, then quiet with the prompt open. A 4th re-prompt = fail | | |
| B10 | The answer after the silence was taken as a first attempt | | |
| B11 | Quick Escape tap → prompt read again, no restart | | |
| B12 | Escape held past 800 ms → one restart, at the threshold, key still down | | |
| B13 | 700 → re-read, 900 → restart. How hard was the boundary to hit? | | |
| B14 | 5 s+ hold → exactly one restart | | |

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
- Exit code: 
- Last session `ended_at`: 
- **Result (E9):** 

### RS-10 · D2 + D5: reopen (S24)

[T]
```powershell
uv run takki; "exit $LASTEXITCODE"
```
**Expect:** `f` and `j` are **not** introduced again (D2). The letter you quit on **is** introduced again (D5).

- Re-introduced: 
- **Result (D2):** 
- **Result (D5):** 

### RS-11 · Finish Stage 0 (S25)

Keep practising until all of `r f v u j m` have been introduced and the next introduction names a letter **outside** those six (~360 prompts). Answer correctly. About half way, press **one** wrong key once (deliberate error 2 of 2) and re-check B6. Fill in B4 in RS-08 as the letters arrive.

- Start / end time: 
- B6 re-check: 
- Next letter after the six: 

### RS-12 · D1: dump after Stage 0 (S26)

[2]
```powershell
uv run python -m takki.progress_dump
```
**Expect:** six anchor keys (`r f v u j m`) in `key_stats`, and `milestones (none)`.

```text
(paste dump here)
```
- **Result (D1):** 

### RS-13 · E1–E8: focus and hostile input (S27)

Nothing here counts as an attempt. Do each with a letter being asked, and come back to Takki after each one.

| Check | Do | Pass condition | Observed | Result |
|---|---|---|---|---|
| E1 | Alt+Tab away mid-prompt, then back | Pause announced when you leave, resume announced when you return, and the prompt asked again *after* the announcement, not over it | | |
| E2 | Alt+Tab away. Hold **F1** for 1 s | Takki raises itself and resumes, keyboard only | | |
| E3 | Hold F1 from several different apps (Notepad, Explorer, browser, [2]) | Where the raise is refused, the Alt+Tab hint is spoken after ~1.5 s. List which apps raised and which gave the hint | | |
| E4 | Press the Windows key (Start menu), then return | Pause, then resume | | |
| E5a | Win+L, log back in | Pause, then resume | | |
| E5b | Ctrl+Alt+Del, then Cancel | Pause, then resume | | |
| E5c | [2]: `Start-Process powershell -Verb RunAs` and answer **No** | Pause, then resume | | |
| E6 | Press Shift 5 times (Sticky Keys dialog), dismiss it | Pause, then resume. No stuck modifier afterwards | | |
| E7 | Mash Backspace, Tab, Enter, Delete, arrows, F-keys, Ctrl+letter, AltGr | Nothing counted, no crash, prompt unchanged | | |
| E8 | Press the space bar repeatedly | Ignored | | |

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

- Chord used: 
- Anything heard: 
- A3 line after switching back: 
- **Result (E12, recorded as a Beta item):** 

### RS-15 · E11: Ctrl+C in the launching console (S29)

1. Click into [T] and press **Ctrl+C**. **Expect:** a clean exit, `exit 0`.
2. [2]
   ```powershell
   uv run python -m takki.progress_dump
   ```
   **Expect:** the session has an `ended_at`.

- Printed in [T]: 
- Exit code: 
- `ended_at` present: 
- **Result (E11):** 

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
- **Result (D3):** 

### RS-18 · A4 on the fresh database; day 1 dump (S35)

[2]
```powershell
uv run python spikes/windows_env_capture.py
uv run python -m takki.progress_dump
```
**Expect (A4):** `%LOCALAPPDATA%\Takki\takki.sqlite`, `journal_mode` `wal`, and **no** `Documents\Takki`.

- A4 line: 
- **Result (A4):** 

```text
(paste day 1 dump here)
```

End time: 

---

## Sitting 2: day 2 (a **later calendar date** than Sitting 1, ~2–2.5 h)

Start after local midnight following Sitting 1. Do not start before midnight and practise across it (that is D6).

Date:  Start time: 

### RS-19 · Day 1 rows present (S36)

[2]
```powershell
uv run python -m takki.progress_dump
```
- Day 1 rows present: 

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
4. When `anchor` appears in `milestones`, practise **one more block**, then dump again. `anchor` must be there **exactly once**.
5. If after 30 min some anchor key still has no row for today, write down which one. That is a finding.

| Time | Keys qualifying today | `anchor` in milestones? |
|---|---|---|
| | | |
| | | |
| | | |
| | | |

- Keys never reached today after 30 min (finding): 
- `anchor` count after the extra block: 
- **Result (D4):** 

```text
(paste the final dump here)
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
(paste full C7 output here)
```
- C3 by ear (normal chime with Caps Lock): 
- **Result (C7):** 
- **Result (C3):** 

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

- Start time / WorkingSet64: 
- Helper finished (minutes of motion): 
- End time / WorkingSet64: 
- Latency drift? Audio degradation? Cue still immediate at the end? 
- **Result (F1):** 
- Close time, exit code: 
- **Result (E10):** 

### RS-23 · Back up day 2 (S51)

[2]
```powershell
New-Item -ItemType Directory "$env:LOCALAPPDATA\Takki-backup\day2"
Copy-Item "$env:LOCALAPPDATA\Takki\takki.sqlite*" "$env:LOCALAPPDATA\Takki-backup\day2\"
```
- Backed up: 

End time: 

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
