# Windows validation protocol (alpha sessions 12b-1 and 12b-2)

> **Status:** Protocol and playbook. The protocol was written before the run. Each run is recorded in its own dated run sheet (§ Runs), never in this note. **T0, the automated A rows and G1's token half were recorded here before run sheets existed (2026-09-24, #12b-1). The hands-on tiers have not been run yet (#12b-2).**
> **Date written:** 2026-09-20. **Updated:** 2026-09-24 (#12b-1): brought up to date with 12a-1 and 12a-2; *Running order* added; scripts built. **Date run:** T0, A (automated) and G1's token half: 2026-09-24. Hands-on: _not yet run._
> **Machine:** the Windows test laptop. The primary dev box is headless Linux with no audio device and a `win32`-pinned `pynput`, so nothing below can run there. That is the whole reason this tier exists.
> **Scope:** the Alpha done-criterion and everything that would invalidate it. *Not* a Beta feature test: no voice, no Piper, no Layer 2, no multi-profile.

Written for whoever sits at the laptop. Record results **as you go**, in the run's run sheet (below), not from memory afterwards. Several checks are about what you *heard*, and that does not survive an hour.

**How this note is laid out.** *Running order* says what to do, sitting by sitting. The tier tables below it (A–G) define each check. Check IDs link the two. When a step says "B7", the pass condition is in B7's row. The tier tables' Result columns hold only #12b-1's automated results, from before run sheets existed; later results are in the run sheets.

**At the laptop, use a run sheet.** A run sheet is *Running order* rendered as test cases: each step with its exact command, its pass condition copied from the tier row, and a place to write the result. **Generate a new one for every run**, named `windows-validation-runsheet-YYYY-MM-DD.md` after the date it was generated, and add it to § Runs. **The run sheet is the single source of truth for its run.** Results are recorded there and stay there: nothing is copied back into this note. This note is the source of truth for the *protocol*, and a sheet adds no steps or pass conditions of its own. A sheet generated before this note last changed is stale; generate a new one rather than editing an old one.

**The instruction for an agent generating a run sheet:** render *Running order* as one test case per step or step group, in the same order and with the same step numbers (S1–S61). Repeat the full command in every test case, even when it is the launch line. Copy the pass condition from the check's tier row. Give each record field a line to fill in, and add a block to paste raw output into (trace sections, C7 output, dumps). Carry the stop rules and restores inline. Record the generation date and the commit of this note in the sheet's header. End with a summary table of every check ID, hard no-go checks marked, and a line for the run's one-line finding.

**Legend.** **+** positive test (the thing should work). **−** negative test (the thing should fail safely, or is expected to expose a known gap).

---

## Running order

Four sittings across at least two calendar days, plus one optional late-night check. Sitting 1 and sitting 2 **must fall on different calendar dates** (see Sitting 2).

### Ground rules — read once

1. **The Takki console.** Use PowerShell in Windows Terminal, in the repo folder `C:\Users\smara\github\takki`. Do not use Git Bash: it does not pass Ctrl+C to Windows programs as a console signal, and E11 depends on that. Every launch in this note is exactly this line:

   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```

   Takki's stderr prints in this same window: the refusal messages, and `TTS engine failed on utterance N` (F3). The line after Takki ends is its exit code. Copy both into the run sheet. *(Decided 2026-09-24: console plus exit code, no log file.)*
2. **The second console** runs everything else: traces, dumps and scripts, from the same folder. Typing in it takes the focus away from Takki. You will hear *"Paused. Takki is not the active window."* That is expected. Alt+Tab back to Takki and it says *"Back in Takki"* and asks the letter again.
3. **Do not answer wrong on purpose until the anchor rung is in the dump (D4, sitting 2)**, except where a step says to. The anchor bar is 95% accuracy over each key's last 200 attempts, and every wrong *first* press counts against the letter that was asked. Stage 0 only ever asks anchor letters, so ten deliberate errors on `f` can hold the rung off for days. This is why C3 and C7 are in sitting 2.
4. **Listen for letters before you answer them.** A key pressed while an introduction script is still speaking is dropped by design (no prompt is open). That is harmless, except during C7, where it breaks the comparison.
5. **The keyboard layout is checked at startup and never again.** Three steps switch layouts on purpose (A3b, A4b, C6), and each is followed by a switch back. A forgotten switch-back is loud at the next launch: Takki exits 2. Switch, then relaunch. A switch *during* a lesson is silent: Win+Space, or Alt+Shift (Windows' other default switching chord, easy to hit by accident). Nothing notices it (E12, roadmap § D). If you hear an answer you know was right being rejected, check the layout before recording anything. `uv run python spikes/windows_env_capture.py` names the active layout on its A3 line.
6. **The commands used below, in one place:**

   | What | Command (second console) |
   |---|---|
   | Progress dump | `uv run python -m takki.progress_dump` |
   | Environment capture (A) | `uv run python spikes/windows_env_capture.py` |
   | Key trace (C) | `uv run python spikes/pynput_trace_spike.py spikes/results/trace_12b2.log`, then Ctrl+C in that console to stop it. Each run appends a new section. |
   | Trace vs dump (C7) | `uv run python spikes/c7_trace_vs_dump.py spikes/results/trace_12b2.log` |
   | Post-kill check (D3) | `uv run python spikes/db_integrity_check.py` |
   | Mouse for E10 | `uv run python spikes/sdl_queue_soak.py drive --minutes 25` |
   | Kill Takki (D3) | `Get-Process \| Where-Object MainWindowTitle -eq 'Takki' \| Stop-Process -Force` |

### Stop rules

Every hard no-go (§ Go / no-go) falls into one of two groups. Decide which one you are in before carrying on.

**Stop the run.** Later checks would test known-wrong behaviour, so continuing wastes the sitting.

- **T0.1–T0.3 fails.** Do not start. File it and fix it in a session first.
- **A3 or A4 fails.** Stop. Everything after these depends on the layout and on the data path.
- **B3 or B4 fails** (the script is cut short, or the letters are not heard as letter names). Stop the sitting. Every check done by ear depends on the voice.
- **C1, C2, C4 or C5 fails. Stop before any Stage 0 practice.** The held-key counting rule is wrong on real input, so every number D would record would be wrong. Amend [ADR-027 § First-Attempt Counting](../adr/0027-key-and-accuracy-state-model.md) in a Claude session, then re-run tier C and **all of D from a fresh database** (Sitting 0 step 3 again). This is why sitting 1 runs C before Takki is ever launched for practice.
- **C7 fails.** First read the divergence block the script prints. If it points at something you did (you typed during an introduction script, left the window, or pressed Escape near 800 ms), run C7 again. If it does not, stop: the dump's numbers are not what the engine thinks they are, and D's are suspect too.
- **D3 fails** (integrity check not ok, or `key_stats` / `key_attempts` torn). Stop, restore the backup (Sitting 1 step 30) and record the no-go.

**Record and continue.** It is a no-go, but nothing later depends on it: B1, B2, B5–B12, D1, D2, D4, D5, E1, E2, E5, E9, E10, E11, F1, F2, G1 and G6. The same applies to every item in the *Go, with the result recorded as a Beta item* list.

### Sitting 0 — prepare (any day before sitting 1, about 15 minutes)

1. Check no stray Python programs are running: `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId, CommandLine`. Only VS Code's language servers should be listed. *(On 2026-09-24 a spike left over from a 12a-2 session had been hung for four days.)*
2. Check whether the code or its dependencies have changed since T0 was recorded: `git diff --stat 6d4a147 -- src tests pyproject.toml uv.lock`. `6d4a147` is the commit T0 ran against, not the latest one, so later commits are expected. Empty output means T0's results below still stand. Anything else means re-run T0.1–T0.3 and record the results again.
3. Move the old database aside so D1 starts from a cold profile: `Rename-Item "$env:LOCALAPPDATA\Takki" "Takki.pre-12b"`. The folder holds an empty `dev` profile and four sessions that 12a-2 never ended.
4. Delete the empty leftover from before 2026-09-20: `Remove-Item "$env:USERPROFILE\Documents\Takki"`. A4 then checks that nothing new appears there.
5. Make a backup folder: `New-Item -ItemType Directory "$env:LOCALAPPDATA\Takki-backup"`.
6. Press Win+Space and pick **English (US)** (P4).
7. Run the environment capture. The A2 and A3 lines must say `pass`. If A3 reports `de`, the switch in step 6 did not take.
8. Charge the laptop (G2 runs on battery later). Check that the soundcore Space Q45 headset is paired (F3).
9. NVDA is **not installed** on this laptop. For G3 and the NVDA half of A5, make a portable copy (download from nvaccess.org, run it, choose *Create portable copy*; no admin needed). Otherwise mark both *not run*.

### Sitting 1 — day 1 (about 2 hours)

**Part A — three startup refusals.** Each launch exits before a window or database exists.

1. **A3b.** Press Win+Space and pick **German**.
2. Launch. Expect `exit 2` and: `Takki cannot start: language 'en' is configured but the active keyboard is 'de'.`, followed by the Win+Space line.
3. Record A3b. **Press Win+Space and pick English (US).**
4. **A4b, launch half.** Open `src/takki/config.py`. Change line 13 from `LANGUAGE: str | None = None` to `LANGUAGE: str | None = "is"`. Save.
5. Press Win+Space and pick **Icelandic**. Both changes are needed: the layout check runs before the voice check, so `"is"` on a US keyboard exits 2 and never reaches the voice.
6. Launch. Expect `exit 3` and: `Takki cannot start: no text-to-speech voice is installed for 'is'.`, followed by the *Settings > Time & language > Speech* line.
7. Record A4b. **Revert:** change line 13 back to `= None` and save. `git diff src/takki/config.py` must print nothing.
8. **Press Win+Space and pick English (US).**
9. **A4c.** Turn the headset off. Then open Settings → System → Sound → *Speakers (Realtek)* → **Don't allow**. The Sound page must show no output device at all. If one is left, Windows plays through it and the check tests nothing.
10. Launch. Expect `exit 4` within about 10 s: `Takki cannot start: the voice cannot play any sound …`. **Watch for a `pygame.error` traceback and `exit 1` instead.** The mixer starts *before* the voice probe (`main.py` line 128), with nothing to catch a failure. CI proved exit 4 with `SDL_AUDIODRIVER=dummy`, which cannot show this. A traceback is a fail. Record its last line.
11. **Restore:** Settings → System → Sound → *All sound devices* → Speakers → **Allow**. Turn the headset back on. Play any sound to confirm you can hear it.

**Part B — the key trace, no Takki (C1, C2, C4, C5, C6).** Open Notepad and type into it, so no keystroke reaches a console.

12. In the second console, start the key trace. Click into Notepad.
13. **C1.** Hold `f` for about 2 seconds, then let go.
14. **C2.** Hold Shift. Press `g`. Let go of **Shift first**, then `g`.
15. **C4.** Type `l`, release, `l`, release.
16. **C5.** Press `l` and hold it for about 1 second, then let go.
17. **C6.** Press Win+Space and pick **Icelandic**. Press the key right of `æ` (the dead acute, where US has the apostrophe). Then press `a`. **Press Win+Space and pick English (US).**
18. Press Ctrl+C in the trace console. Read the new section with `$t = Get-Content spikes\results\trace_12b2.log; $i = ($t | Select-String '=== trace started' | Select-Object -Last 1).LineNumber; $t[($i-1)..($t.Count-1)]`. The C1 hold alone can produce more than 60 repeat lines, so `-Tail 60` would cut it off. Record C1, C2, C4, C5 and C6, and paste the section into the run sheet.
19. **Stop rule:** if C1, C2, C4 or C5 failed, stop here (§ Stop rules).

**Part C — first launch, eyes closed (G6, B1–B12).**

20. Have a stopwatch ready. Press Enter on the launch line and start the stopwatch at the same moment. **Close your eyes.** G6 runs from here until you hear the *second* introduction script.
    - **B1:** the first thing you hear should be the introduction. *"Paused. Takki is not the active window."* first means B1 failed. Alt+Tab to Takki and carry on.
    - **B2:** stop the stopwatch at the first spoken word.
    - **B3:** the `f` and `j` introduction lines must be complete to the last word.
    - **B5:** answer correctly. You should hear a chime, then the next letter.
    - **B7:** press the correct key *while* the letter is still sounding (about 1.4 s long). Speech cuts, and the chime comes at once.
    - **B8:** when the drill alternates, answer the current letter and the next one in one quick burst.
    - **B6:** press one wrong key, **once**. That is deliberate error 1 of 2.
    - **B9 → B10:** stay silent for three re-prompts (about 45 s), wait another 15 s, then answer.
    - **B11–B14:** Escape gestures. None of them count as attempts.
21. Record G6 and B1–B14 (B4 fills in as `r v u m` are heard in later steps).

**Part D — quit, reopen, kill (E9, D2, D5, D3, E11).**

22. **D5 + E9.** When the next introduction starts (Stage 0's second step), close the window with the mouse **before** answering the new letter. Expect `exit 0`.
23. Run the dump. The last session must have an `ended_at` (E9).
24. Relaunch. **D2:** `f` and `j` are not introduced again. **D5:** the key you quit on *is* introduced again.
25. Practise until the end of Stage 0: all of `r f v u j m` have been introduced, and the next introduction names a letter outside those six. Answer correctly. That is D1's ~360 prompts. Mid-way, press one wrong key once (deliberate error 2 of 2) to re-check B6.
26. Run the dump and record **D1**: six anchor keys in `key_stats`, `milestones (none)`.
27. **E1–E8** now. They are focus and hostile-input checks, and nothing in them counts as an attempt. For E5's UAC prompt, run `Start-Process powershell -Verb RunAs` in the second console and answer **No**.
28. **E12.** With a letter being asked, press **Alt+Shift** (or Win+Space) once to move to German. Listen: does Takki say anything? Answer the letter only if it is one of `r f v u j m`, which sit on the same keys in both layouts. Switch back to English (US). In the second console, run the environment capture and check its A3 line says `pass`, which proves you are back on US. Alt+Tab to Takki.
29. **E11.** Click into the Takki console and press Ctrl+C. Expect a clean exit and `exit 0`. Run the dump: the session has an `ended_at`.
30. **Back up** (Takki is closed): `Copy-Item "$env:LOCALAPPDATA\Takki\takki.sqlite*" "$env:LOCALAPPDATA\Takki-backup\"`. To restore later: close Takki, delete the files in `%LOCALAPPDATA%\Takki`, and copy these back.
31. **D3.** Relaunch. In the second console, type this and press Enter: `Start-Sleep 30; Get-Process | Where-Object MainWindowTitle -eq 'Takki' | Stop-Process -Force`
32. Alt+Tab to Takki and keep answering prompts steadily until Takki goes silent.
33. **Before relaunching**, run the post-kill check and record the `D3:` line. Relaunching replays the WAL and destroys the evidence.
34. Relaunch. The progress must still be there: answer 3 prompts, then close with the mouse.
35. Run the environment capture again and record the **A4** line (this confirms the fresh database). Also paste the dump into the run sheet as *day 1*.

### Sitting 2 — day 2 (a later calendar date than sitting 1; about 2–2.5 hours)

**Any time after local midnight following sitting 1: the next day or later.** The anchor gate counts `date(attempted_at)`, so the same evening does not count. Do not start before midnight and practise across it; that is D6, and it would make D4 trivially satisfied.

36. Run the dump. It should show day 1's rows.
37. **D4.** Launch and practise, answering correctly. Stage 0 is over, so the engine mixes the anchors in with newer letters.
38. Every ~10 minutes, run the dump. You need each of `r f v u j m` to have a row dated **today**, at least 25 attempts, and at least 95% accuracy.
39. The rung is checked at block boundaries, so it appears in `milestones` as `anchor` after the block in which the last key qualifies. When it appears, practise one more block and dump again: `anchor` must still be there **exactly once**.
40. If after 30 minutes some anchor key still has no row for today, record which one. That is a finding: the rung cannot be reached without targeted practice.
41. **C7 + C3.** With a letter being asked, **do not answer it.** In the second console, start the key trace (Takki pauses). Alt+Tab back to Takki.
42. From now until step 45: **do not leave the window and do not press Escape.** Answer about 40 prompts. Mix in:
    - correct first answers;
    - about 8 wrong-then-right answers;
    - two held keys (hold the correct letter about 1 s);
    - two Shift+letter answers;
    - about 10 prompts with **Caps Lock on** (C3), then Caps Lock off.
43. Answer only after hearing the letter. At an introduction, wait for it to finish.
44. **C3 by ear:** Caps Lock answers get the normal chime.
45. Close Takki with the mouse. Press Ctrl+C in the trace console.
46. Run the trace-vs-dump comparison. Record its `C7:` line. **C3** passes if C7 passes and the trace line reports upper-case actuations above zero: the engine counted them as the plain letter. Paste the full output into the run sheet.
47. **F1 + E10 (60–90 minutes).** Launch. In the second console, start the mouse helper for E10, then Alt+Tab to Takki. The cursor circles inside Takki's window for 25 minutes of motion. It pauses while another window is in front, and stops if you move the mouse yourself.
48. Note Takki's memory at the start and the end: `Get-Process | Where-Object MainWindowTitle -eq 'Takki' | Select-Object WorkingSet64`. Take the start reading *before* starting the mouse helper in step 47, because the helper occupies the second console for 25 minutes.
49. Practise the whole time. After 60–90 minutes, record F1.
50. **E10:** close Takki with the mouse. It must close within a couple of seconds. If it does not, press Ctrl+C in the Takki console and record the fail.
51. Back up again, to `Takki-backup\day2\`: `New-Item -ItemType Directory "$env:LOCALAPPDATA\Takki-backup\day2"`, then `Copy-Item "$env:LOCALAPPDATA\Takki\takki.sqlite*" "$env:LOCALAPPDATA\Takki-backup\day2\"`.

### Sitting 3 — changes to the machine (any day after sitting 2, about 1 hour)

Each check changes something about the laptop. Each restore comes straight after its check.

52. **F3.** Connect the headset and make it the output. Launch and practise. Turn the headset **off** mid-lesson. Keep answering for a minute. Watch the Takki console for `TTS engine failed on utterance N`. Listen for whether speech moves to the speakers. Turn the headset back on. Record: did prompts keep coming, and did SAPI reroute?
53. **F2.** Practise, then Start → Power → **Sleep**. Wake the laptop and log in. Alt+Tab to Takki and answer 5 prompts. Each should chime. Close with the mouse and watch the Takki console: a traceback at exit is a pynput listener that died during sleep.
54. **G2.** Unplug the charger. Settings → System → Power & battery → Power mode **Best power efficiency**, and turn Energy saver **on**. Practise for 10 minutes. **Restore** the power mode and plug the charger back in.
55. **G4.** With Takki running, run the launch line in the second console. Record what the second instance does. Close both, then run the post-kill check: it reads the integrity result on a database two processes had open.
56. **G5.** With Takki closed, remove your own write access:

    ```powershell
    icacls "$env:LOCALAPPDATA\Takki" /deny "${env:USERNAME}:(OI)(CI)(W,D,DC)"
    ```

    A folder's read-only *attribute* does not stop Windows writing into it; a deny rule does. (Tested on a scratch folder 2026-09-24: SQLite then reports `unable to open database file`, and the restore below returns the folder to its inherited permissions.)
57. Launch. Record everything printed and the exit code. If the window stays up doing nothing, close it; if that hangs, press Ctrl+C.
58. **Restore immediately:** `icacls "$env:LOCALAPPDATA\Takki" /remove:d $env:USERNAME`. Then run `icacls "$env:LOCALAPPDATA\Takki"`: no line may contain `(DENY)`. Launch once to confirm Takki starts, then close it.
59. **G3 + A5** (portable NVDA only). Start NVDA. Run the environment capture and record its A5 line. Launch Takki and practise for 5 minutes. Record the behaviour. Quit NVDA (Insert+Q).
60. **G1**, the remaining half. The token half passed on 2026-09-24 (G1's row). Record whether any UAC prompt appeared at any point in sittings 1–3. None is a pass; one that Takki caused is a fail.

### Optional — D6, a night after sitting 2

61. Start practising at about 23:50 and carry on to about 00:10. The dump then shows that sitting's rows split across two dates. Record whether that feels right for a child.

---

## Before you start

None of this is worth running until all seven are true. **All seven are true as of 2026-09-24:** 12a-1 and 12a-2 are merged, and CI is green (run 36045115800, commit `9976890`). All but P1 are [alpha-plan](../alpha-plan.md) carry-forward rows; a run before them would test known-wrong behaviour and have to be repeated.

| # | Precondition | Why it blocks |
|---|---|---|
| P1 | **12a-1 and 12a-2 are both merged and green**, including the `audio` and `windows_only` tiers | **Done, 2026-09-24.** Without 12a-1, `get_layout_positions()` raises and Takki cannot launch. Without 12a-2, the voice was cut short after the first utterance and an engine error killed the TTS worker. Since 12a-2, startup also refuses (`EXIT_NO_AUDIO`) rather than launching mute. |
| P2 | **Letter-case decision implemented** | **Done, 2026-09-20: case is ignored.** An upper-case answer counts as correct; the folding happens at the taxonomy boundary ([ADR-027 § Case is folded at the boundary](../adr/0027-key-and-accuracy-state-model.md)). Caps Lock is therefore invisible to the run instead of poisoning it. |
| P3 | **Data directory decision implemented** | **Done, 2026-09-20.** Resolved via `platformdirs` to the OS convention: on this laptop `%LOCALAPPDATA%\Takki\takki.sqlite`. Local rather than Roaming, because the database is in WAL mode. D runs against the final path, so it will not need re-running. `TAKKI_DATA_DIR` is deliberately **not** built; see the note under this table. |
| P4 | **Switch the laptop's active keyboard layout to US English before you start** | Measured: the laptop reports locale `en-150` on a **German QWERTZ** layout (`00000407`, first in the Preload list), with US (`0x409`) and Icelandic (`0x40f`) also installed. Takki *verifies* the language against the active layout at startup and **refuses to run** on a mismatch ([ADR-025 § Language and layout must agree](../adr/0025-configuration-system.md)), so an unswitched laptop exits 2 before the window opens. One Win+Space. The environment capture's A3 line confirms it. |
| P5 | **Progress dump script exists** | **Done, 2026-09-20 (#12a-0):** `uv run python -m takki.progress_dump`. Alpha passes no `celebrant`, so every milestone is silent, and without the dump D4's anchor rung cannot be observed. |
| P6 | **TTS engine is constructed on the worker thread** | **Done (12a-2).** `get_fallback_tts(voice_id)` returns a factory and `TTSWorker` builds the engine on its own thread. Windows no longer goes through pyttsx3 at all: `SapiTTS` drives `SAPI.SpVoice` directly ([ADR-003](../adr/0003-text-to-speech.md)). That removed the truncation and pins the speaking rate to `Rate=0`, so a letter is now **~1.36 s** and the introduction script ~7.4 s, not the ~0.94 s / ~4.2 s quoted before 12a-2. The worker survives an engine exception and reports it as a `"failed"` utterance. Startup speaks one silent letter and exits 4 if the voice cannot sound. |
| P7 | **Fallback voice is selected by language** | **Done (12a-2).** The verified id is applied: `get_fallback_tts(voice_id)` takes it, and the engine sets it before speaking. `find_voice()` reads the SAPI5 and OneCore token categories in both HKLM and HKCU. On this laptop (measured 2026-09-24, A4b): `en` → David, `de` → Hedda, `is` → none. |

**No environment overrides exist at all.** `TAKKI_DATA_DIR`, `TAKKI_LANG` and `TAKKI_LAYOUT` were all withdrawn on 2026-09-20; [ADR-025 § Alternatives](../adr/0025-configuration-system.md) now rejects env-var overrides outright (alpha-plan carry-forward "`TAKKI_DATA_DIR` override"). Tiers D and G therefore run against the real data directory, and *Running order* handles the backup (Sitting 0 step 3, Sitting 1 step 30) and G5's restore (step 58) as explicit steps. If that feels too sharp on the day, run tiers D and G under a throwaway Windows user account. Do not re-add an env var. *(`spikes/listener_coexistence_spike.py` patches `database_path` in its own process to rehearse against a throwaway file. That is a spike harness; it is not a way to run this protocol.)*

**Scripts** (all in `spikes/`, built 2026-09-24 in #12b-1 unless noted; each prints one line ready to paste into the run sheet):

| Script | For | Notes |
|---|---|---|
| `pynput_trace_spike.py` (#12a-0) | tier C | Real `PynputKeyStream`. Logs `pressed`, `char`, `name` and an offset per event. The header now carries a millisecond wall-clock start. |
| `windows_env_capture.py` | A1–A5 | Read-only. Reads the active layout exactly as `main()` does. That is deliberate, so it cannot force a layout, only report one. A non-US reading prints **P4 not met**, and a layout that changes during the capture marks A3 **INVALID**. Also lists every installed layout, with what `verify_layout` would answer for it. |
| `c7_trace_vs_dump.py` | C7 | Its docstring defines "trace-derived" (four rules taken from `classify`, `FocusModel`, `AttemptCounter` and `_on_restart`). Negative-tested: fails on a flipped `correct` flag, an extra counted repeat, and a lost attempt. |
| `db_integrity_check.py` | D3 (also G4) | Read-only. `integrity_check`, `foreign_key_check`, `key_stats` against `key_attempts` (each attempt is two commits, so a kill between them tears the pair without corrupting anything), unended sessions, then the dump. |
| `sdl_queue_soak.py` | E10 | `measure` gave the queue's fill rate; `drive` moves the mouse for the hands-on run. |
| `listener_coexistence_spike.py` | C7 design | Settled that the trace and Takki can listen at the same time (C7's row). Rerun it if pynput or Windows changes. Its expected characters are US English, and it **never changes the layout.** Activating a layout on a thread that owns the foreground window switches the whole session: a first version did that and left the developer on US (2026-09-24). Instead, Takki's startup check is handed a US reading inside the harness process, so Takki never refuses to start because of the developer's layout. Before every keystroke, the target window's actual layout must type the script's letters on the same keys as US, and must not have changed mid-run; otherwise the spike aborts. Proven 2026-09-24 with the session on German: both modes pass, and the session is still German afterwards. |

---

## A — Environment capture

Do this first and write the answers down. Several later checks can only be read against them, and the two-day D tier is expensive to repeat because a precondition turned out to be false. **A1, A2, A3, A4, A5 (without NVDA) and A4b's `find_voice` half come from `spikes/windows_env_capture.py`; A3b, A4b's launch half and A4c are by hand (Sitting 1, Part A).**

| ID | Check | Pass condition | Result |
|---|---|---|---|
| A1 + | Windows version, Python version, `pygame`/SDL version, whether OneDrive redirects Documents; account type (for G1) | Recorded | **2026-09-24:** Windows 11 Home 25H2 (build 26200.9457); Python 3.11.15; pygame 2.6.1 / SDL 2.28.4; Documents = `C:\Users\smara\Documents` (not OneDrive-redirected); administrator, not elevated (filtered token); commit `6d4a147` |
| A2 + | `get_system_language()` return value | **`en`**. The raw locale is `en-150`, so this checks that the BCP-47 hyphen and the numeric region subtag are both handled | **Pass (2026-09-24):** `en` from raw locale `en-150` |
| A3 + | `get_layout_positions()`: grapheme count, and a letter at all six anchor positions (2,4) (3,4) (4,4) / (2,7) (3,7) (4,7) | Six letters present, and `Layout.lang` reports the **keyboard's** language (`en` on the US layout), not the system locale. A raise here is `anchor_keys()` working as designed (#8b), not a bug to catch | **Pass (2026-09-24, US layout active):** `Layout.lang` = `en` (locale `en-150`); 26 graphemes, 26 keys; anchors (2,4)=r (3,4)=f (4,4)=v (2,7)=u (3,7)=j (4,7)=m; `verify_layout('en')` = None. *(The first capture that day ran with German still active and correctly reported `de` and a refusal. A fresh process follows the currently selected layout, not the Preload default.)* |
| A3b − | With the German layout active (Win+Space), launch Takki | Refuses to start with **exit 2** and `Takki cannot start: language 'en' is configured but the active keyboard is 'de'.`, then the Win+Space remedy. *(Updated 2026-09-24: since 12a-1 the reader reports the keyboard's own language, so the refusal names the language rather than listing `y`/`z` and `ä ö ü ß`. The capture predicts this exact message.)* Switch back to US before continuing. This is the only hand-check of the startup layout guard | — |
| A4 + | Where the database file actually landed | Exactly `%LOCALAPPDATA%\Takki\takki.sqlite`, `journal_mode` `wal`, and **no** `Documents\Takki\` created by this build (the pre-2026-09-20 path). *(Updated 2026-09-24: the `-wal`/`-shm` files exist only while a connection is open, because a clean close checkpoints and deletes them. So their absence proves nothing, and the script asks SQLite for the journal mode instead.)* | **Pass (2026-09-24, against 12a-2's database):** `C:\Users\smara\AppData\Local\Takki\takki.sqlite`; journal_mode `wal`; a `Documents\Takki` exists but is empty and was created 2026-09-20 14:08, before the database: a leftover, deleted in Sitting 0 step 4. **Re-confirm on the fresh database at Sitting 1 step 35.** |
| A4b + | `find_voice()` for `en`, `de` and `is`; then the launch refusal | `en` and `de` return a `HKEY_LOCAL_MACHINE\...` token id, `is` returns `None`. Then launch with `config.LANGUAGE = "is"` **and the Icelandic layout active** (Sitting 1 steps 4–8, including the revert). Takki must refuse with **exit 3** (`EXIT_NO_VOICE`) and name the remedy. *(Updated 2026-09-24: with the US layout active this exits 2 at the layout check and never reaches the voice. The capture confirms `is` passes its own layout table, so exit 3 is reachable.)* This is the only hand-check of the graceful-stop path | **`find_voice` half, pass (2026-09-24):** `en` → `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\TTS_MS_EN-US_DAVID_11.0`; `de` → `…\TTS_MS_DE-DE_HEDDA_11.0`; `is` → `None`. Launch half: — |
| A4c − | Disable every audio output, then launch (Sitting 1 steps 9–11) | Takki exits **4** (`EXIT_NO_AUDIO`) within ~10 s: `Takki cannot start: the voice cannot play any sound …` on stderr. Not a hang, and not a running app that says nothing. **Watch for:** a `pygame.error` traceback and exit 1. `PygameMixerCues()` runs before the voice probe and is not guarded, and CI's exit-4 proof ran under `SDL_AUDIODRIVER=dummy`, which cannot show this (found 2026-09-24, #12b-1, by reading `main.py`, not by running it). Re-enable the device before continuing | — |
| A5 + | `detect_screen_reader()` with and without NVDA running | Matches whatever [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr) decided; `None` is fine if it stayed out of Alpha | **Without NVDA (2026-09-24):** `None`. With NVDA: — (NVDA is not installed; Sitting 0 step 9) |

---

## T0 — The automated tiers, on this machine

CI cannot run SAPI speech (a runner has no audio output) or a real window (`SDL_VIDEODRIVER=dummy`), so T0.2 and T0.3 are the **only** verification those two get ([ADR-019 § Headless audio/video](../adr/0019-testing-strategy-and-io-isolation.md), closed 2026-09-24).

| ID | Check | Pass condition | Result |
|---|---|---|---|
| T0.1 + | `uv run pytest` | Green | **Pass (2026-09-24, `6d4a147`):** 604 passed, 2 skipped, 54 deselected in 4.5 s |
| T0.2 + | `uv run pytest -m windows_only` | Green: real pynput translation, real SDL window construction. *(Until 2026-09-24 `conftest.py` forced the dummy video driver here, so the "real driver" window tests had never opened a real window. A pass before that date proved nothing about the window.)* | **Pass (2026-09-24):** 43 passed in 58.8 s; no `SDL_*` variable in the environment, and `pygame.display.get_driver()` = `windows` in this venv |
| T0.3 + | `uv run pytest -m audio` | Green: **12 passed, 6 skipped, about 60 s** (as of 2026-09-24). The 6 skips are `tests/test_fallback_tts.py`, the Linux-only pyttsx3 dev path. The tier to read is `tests/test_sapi_tts.py`: it drives the real engine from a real worker thread and **brackets utterance durations**, because the defect that hid for eleven sessions was speech cut short, which `speak("a")` does not raise on. Treat a pass as a positive result, not a formality: **this run is the only thing that verifies `tests/test_sapi_tts.py`.** CI runs the mixer half of the tier and cannot run the SAPI half | **Pass (2026-09-24):** 12 passed, 6 skipped (all `FallbackTTS`, "Linux dev path") in 57.4 s. Slowest: `test_every_utterance_after_the_first_is_full_length` 19.2 s |

---

## B — The core loop, by ear

All of B is run with the screen ignored (Sitting 1, Part C, eyes closed). If you find yourself looking at the screen, that is a finding. Record it.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| B1 + | Launch. Window appears and takes foreground | Foreground without a click. The tell by ear: *"Paused. Takki is not the active window."* before anything else means the seed `FocusLost` fired, and B2 is then testing the resume path instead. Note it | — |
| B2 + | Time from launch to first spoken word | Recorded. Expect language-table warm (~1.4 s for `en` on the dev box) plus the silent startup voice probe (0.58 s measured, 12a-2). Anything past ~5 s is worth a note | — |
| B3 + | The Stage 0 introduction script for `f` and `j` | Both lines audible and **complete to the last word**, in order, before the first prompt letter (3.81 s and 6.73 s at `Rate=0`, 12a-2). Before 12a-2, SAPI cut every utterance after the first short, so the script ended mid-sentence while single letters sounded fine. This row checks that fix, and the failure is silence, not a wrong noise | — |
| B4 + | All six anchor letters spoken as prompts (`r f v u j m`) | Each intelligible as a *letter name*, not a word or article. Stage 0 asks `f j` first; the other four arrive in its later steps, so this row completes by D1. This is A1's finding holding on real hardware | — |
| B5 + | Correct keypress | Chime, then the next letter. The chime feels immediate | — |
| B6 − | Wrong keypress | Error tone, **same letter** asked again, prompt stays open. *(Twice at most before D4; Ground rule 3)* | — |
| B7 + | Keypress while the letter is still sounding | **The letter is cut and the chime is not delayed.** Decided and measured in 12a-2 (alpha-plan carry-forward "Main-thread `stop()` cost"): a keypress that answers a prompt still stops the letter, and the call costs the caller **0.000 ms**, with the audio stopping ~0.2 s later. A letter is ~1.36 s long at `Rate=0`, so press early on purpose. Fail: the letter plays to the end, or the chime waits for it | — |
| B8 + | Two fast keypresses (type-ahead), answering two prompts | Both land, both counted. Pinned on Linux by `TestTypeAhead`; this is the real-timing version | — |
| B9 − | Wait 10 s in silence, three times over | Three re-prompts, then **quiet with the prompt still open**. A fourth re-prompt is a failure | — |
| B10 + | Type the letter after that silence | Counted as a *first* attempt: the prompt never re-latched | — |
| B11 + | Re-read key (Escape tap, released well under 800 ms) | The open prompt is spoken again. No restart | — |
| B12 + | Restart key (Escape held past 800 ms) | Fires **once**, at the threshold, with the key still down. The current unit is presented again | — |
| B13 − | Escape tap at ~700 ms and ~900 ms | 700 → re-read, 900 → restart. Record how hard the boundary is to hit. Carry-forward **D Escape** chose one key on purpose, and this is the check on that choice | — |
| B14 − | Hold Escape a long time (5 s+) | Exactly one restart, not a stream of them. Auto-repeat must not fire the gesture again | — |

---

## C — The two ADR-027 input assumptions

**The highest-value tier.** [ADR-027 § First-Attempt Counting](../adr/0027-key-and-accuracy-state-model.md) rests on two Windows behaviours no Linux test can reach, and the held-key counting rule is wrong if either fails. C1–C6 run with the trace alone, typing into Notepad (Sitting 1, Part B), **before any Stage 0 practice**, so a failure costs no D work. Read the log, not your ears.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| C1 + | Hold `f` until the OS auto-repeats several times | **No release event between repeats**: one `PRESS`, then more `PRESS` lines, then one `RELEASE`. If Windows or pynput adds a release, every repeat reads as a fresh actuation and the rule silently does nothing. **Stop rule:** amend ADR-027, then re-run all of D | — |
| C2 + | Hold Shift, press a letter, **let go of Shift first**, then the letter | Press and release report the **same** key: `char='G'` down and `char='g'` up is a pass, because case is folded on both sides. `None` or an unrelated character on release is a fail: it leaks a down-entry. *(Corrected 2026-09-24: the step used to say "press Shift, release it, then press and release a letter", which never produces the mismatch the check is for. Injected input in #12b-1 shows `'F'` down / `'f'` up, so the shape is right; this row is the hardware confirmation.)* | — |
| C3 − | Caps Lock on, then type a prompted letter (Sitting 2, inside C7) | **Counted correct**, normal chime, prompt advances: indistinguishable from Caps Lock off. The trace shows `char='F'`; the engine sees `f`. Pass when C7 passes with a non-zero upper-case count | — |
| C4 + | Type `ll` **releasing** between the two presses | Two actuations: `PRESS`/`RELEASE`/`PRESS`/`RELEASE`. A doubled letter is two keystrokes | — |
| C5 − | Type `ll` **holding** through both | One actuation: one `PRESS`, repeats, one `RELEASE`. C4 and C5 differing is the entire point of the rule | — |
| C6 − | Dead-key composition at the capture boundary (trace only, no lesson engine). **The Icelandic layout `0x40f` is already installed.** The dead acute is the key right of `æ` (position (3,11), US apostrophe) | One composed `char='á'` arrives. Capture only, by roadmap scope: does not need B8 resolved and does not gate Alpha's English run | — |
| C7 + | A mixed session of ~40 prompts with deliberate errors, retries, held keys, Shift and Caps Lock, with the trace running (Sitting 2 steps 41–46) | `spikes/c7_trace_vs_dump.py` prints `C7: PASS`: trace-derived attempt and correct counts **exactly** match the `key_attempts` rows, per key and in sequence, with every attempt within 2 s of its row. Any drift means first-attempt accuracy is not what the engine thinks. **Settled 2026-09-24 (#12b-1): the trace and Takki can listen at the same time.** Two trace processes plus real Takki (three low-level hooks) under 82–123 injected events, including 5 ms bursts, held-key repeats and Shift-release-first, each logged every event identically to what was sent. Takki's rows matched the trace-derived counts exactly (28 attempts / 22 correct, 10 repeats removed, 2 folded). Injected input goes through the same hook chain as a real keyboard; it cannot reproduce Windows' own auto-repeat timing, which is C1's job. **Start the trace while Takki is already running**; otherwise the letters of the launch command count as answers | — |

---

## D — Persistence and the anchor gate

**Needs two calendar days minimum.** `KNOWN_MIN_DISTINCT_DAYS` is 2 and cannot be compressed. D1–D3 and D5 run in sitting 1; D4 needs sitting 2 on a **later calendar date**; D6 is optional and comes after D4.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| D1 + | Day 1: complete Stage 0 (~360 prompts across the three steps) | All six anchor keys Active (rows in `key_stats`). **No rung yet**: one calendar day cannot satisfy the gate | — |
| D2 + | Close the app normally, reopen | Progress restored; the session resumes without re-introducing a completed key | — |
| D3 − | Kill the process mid-write (timed kill while typing, Sitting 1 steps 31–34) | `spikes/db_integrity_check.py` **before relaunch** prints `D3: PASS`: `integrity_check` ok, `key_stats` and `key_attempts` consistent, exactly one unended session. Then the database is readable on reopen. WAL + `synchronous=NORMAL` should survive this. *(The kill-by-window-title command was checked on 2026-09-24 against a throwaway-database Takki: it kills the `python.exe` that owns the window, and the `uv` launcher exits with it.)* | — |
| D4 + | Day 2: practise the anchor keys again to the gate's bar | Anchor rung written **exactly once**, never revoked. It is silent; read it from the dump's `milestones`. The bar is each of `r f v u j m` with ≥ 25 attempts, ≥ 95% accuracy over its last 200, and practice on ≥ 2 dates. It is evaluated at block boundaries | — |
| D5 − | Quit mid-introduction, before answering the introduced key | That key is **introduced again** next session. Its record is session-local by design ([ADR-023](../adr/0023-key-introduction-protocol.md)) | — |
| D6 − | A session crossing local midnight (optional, after D4) | Counts as two distinct days per ADR-027's `date(attempted_at)`. A child practising at 23:55 and 00:05 should not be handed a rung for one sitting. Record whether that feels right | — |

---

## E — Focus, OS preemption, hostile input

Mostly negative tests: Alpha's focus model exists because the OS interrupts. None of them counts an attempt, so they can run before D4.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| E1 + | Alt+Tab away mid-prompt, then back | Pause announced on leaving; resume announced on return; the open prompt is **asked again after** the announcement, not over it | — |
| E2 + | While away, hold F1 for 1 s | Takki raises itself and resumes, keyboard only, no mouse | — |
| E3 − | While away, hold F1 where the raise is refused or downgraded to a taskbar flash | Alt+Tab hint spoken after ~1.5 s. Expiry is the only failure signal there is. Windows decides which of E2/E3 you get; try F1 from a few different apps and record which raise and which get the hint | — |
| E4 − | Windows key (Start menu), then return | Pause/resume. Losing focus to a system key is the *intended* trigger, not a leak | — |
| E5 − | Win+L (lock), Ctrl+Alt+Del, and a UAC prompt (`Start-Process powershell -Verb RunAs`, answer No) | Pause on the way out, resume on the way back. The secure desktop delivers no hook events; the backup focus poll is what catches it | — |
| E6 − | Press Shift five times (Sticky Keys dialog) | Pause/resume like any other focus thief; no stuck modifier afterwards | — |
| E7 − | Mash Backspace, Tab, Enter, Delete, arrows, F-keys, Ctrl+letter, AltGr | Nothing counted, nothing crashes, prompt unchanged. Backspace especially: ADR-012 disables it outright | — |
| E8 − | Press the space bar repeatedly | Ignored. The space bar is never introduced in any phase | — |
| E9 + | Close the window with the mouse | Clean shutdown via the `Quit` path, exit 0; the dump shows the session row ended | — |
| E10 − | Keep the mouse moving over the window for **at least 25 minutes** (`sdl_queue_soak.py drive`), then close it with the mouse | **Still closes.** `poll()` takes three event types off the queue and the rest accumulate toward SDL's 65,535 cap, after which `QUIT` is refused. This check decides whether to pre-empt that with a full drain or leave it. *(Duration corrected 2026-09-24, #12b-1: Windows gives at most one mouse-move per message pump, and Takki pumps at `TICK_HZ` = 60, so the queue fills at **56–60 events/s** (measured) and reaches the cap after **18–20 minutes**. The old "15+ minutes" could pass without ever reaching it.)* | — |
| E11 − | Ctrl+C in the launching terminal (PowerShell, not Git Bash) | Clean exit via the signal handler, exit 0; the session row ended | — |
| E12 − | Mid-lesson layout switch: Alt+Shift or Win+Space to German, then back (Sitting 1 step 28) | **Known gap, record what happens.** Takki verifies the layout at startup only ([ADR-025 § Language and layout must agree](../adr/0025-configuration-system.md), roadmap § D "A layout switched mid-session is not detected"), so the expected result is that nothing is said and the lesson carries on against the German keyboard. Anchor keys are unaffected; `y`/`z` and the umlaut keys would not be. Record which chord switched and whether anything was heard; if Takki *does* notice, that is news for the roadmap line. *(Added 2026-09-24, #12b-1, after the developer pointed out that a layout can change during or before a run without anyone meaning to.)* | — |

---

## F — Endurance

| ID | Check | Pass condition | Result |
|---|---|---|---|
| F1 + | 60–90 minutes of continuous practice (Sitting 2, alongside E10) | No latency drift, no memory growth (compare `WorkingSet64` at start and end), no audio degradation. The cue still feels immediate at the end | — |
| F2 − | Sleep the laptop mid-session, then wake it | Listener still alive and the loop still responsive. A dead pynput hook surfaces only at `join()`, so the symptom would be a silent keyboard, then a traceback at exit | — |
| F3 − | Turn the Bluetooth headset (soundcore Space Q45) off mid-lesson | **The app must survive; the child's experience is still C14's (Beta).** Since 2026-09-24 an engine exception costs one utterance, not the TTS worker. Look for `TTS engine failed on utterance N` in the Takki console, and for prompts still being asked (cues still sound if the mixer reroutes). A frozen loop is a **fail**: no more prompts, and no more cues after the headset is back. Also record whether SAPI reroutes to the speakers on its own, so C14 and roadmap § D's repeated-`failed` line are written against observed behaviour | — |

---

## G — Environment and accessibility

| ID | Check | Pass condition | Result |
|---|---|---|---|
| G1 + | Run as a standard (non-admin) Windows user | Works with no elevation and no UAC prompt at any point. **Decided 2026-09-24: run on this account's filtered token.** It is an administrator, but a non-elevated process gets a limited token at Medium integrity, the same privilege a standard account has, with the Administrators group present as deny-only. What remains for 12b-2 is to watch for any UAC prompt across the whole run (Sitting 3 step 60) | **Pass (2026-09-24, #12b-1, filtered token).** Real `main()` against the real data directory (only the layout reading pinned to US, so the German session was left alone): Takki's process token `TokenElevation=0`, elevation type *limited (filtered)*, integrity **Medium**. The full startup ran (window, mixer, voice probe, store in `%LOCALAPPDATA%\Takki`, listener), no `consent.exe` appeared during the run, and a window close exited 0 with the session row ended. UAC across the hands-on run: — |
| G2 + | Run on battery in power-saver mode | Still responsive. The Whisper matmul benchmark is Beta, but SAPI latency under throttling is worth knowing now | — |
| G3 − | Run with NVDA active (portable copy) | Record the coexistence behaviour: double-speaking, focus stealing, or clean. Drives the ADR-028 open question 4 NVDA decision | — |
| G4 − | Launch a second instance while the first runs | Fails clearly, or both work without corrupting the database (`db_integrity_check.py` afterwards). Silent corruption is the failure | — |
| G5 − | Deny yourself write access to the data directory (Sitting 3 steps 56–58, `icacls`), then launch | Fails with something a person can act on: not a silent crash, and ideally not a stack trace as the only output. *Predicted from the code, not run (#12b-1):* the store opens after the window, the mixer and the voice have started, and nothing catches its error, so expect a `sqlite3.OperationalError: unable to open database file` traceback and exit 1. The TTS worker is a daemon thread, so the process should not hang. A traceback as the only output is the "ideally not" case: record it | — |
| G6 + | **Eyes closed** from launch through one full drill block (Sitting 1, Part C, until the second introduction script) | Never needing the screen, the console, or a mouse. This is the audio-first invariant, and the only check that tests the actual product claim | — |

---

## Go / no-go

**Hard no-go: any one of these fails.** § Running order → *Stop rules* says, for each, whether to stop the run or record and continue.
T0.1–T0.3 · A3 · A4 · B1–B12 · C1 (or C1 fails, ADR-027 is amended, and D re-runs clean) · C2 · C4 · C5 · C7 · D1–D5 · E1 · E2 · E5 · E9 · E10 · E11 · F1 · F2 · G1 · G6

**Go, with the result recorded as a Beta item:**
F3 (C14, already scheduled) · E12 (mid-lesson layout switch, roadmap § D) · G3 (NVDA coexistence) · B13's boundary feel · D6's midnight judgement · the silent milestone · the missing F/J nub wording · the restart re-counting hole · ADR-010's slack introduction gate.

**The distinction:** a hard no-go makes the Alpha claim false: either the loop does not work with a real person, or the numbers it records are not the numbers it thinks. Everything in the second list is a known, filed gap that a pilot family would meet but a developer can work around, and none of it changes whether the core loop is proven.

**A4c, A3b and A4b sit in neither list**, as before. If A4c exits 1 with a traceback (its *Watch for*), that is a real startup defect but not an Alpha no-go by this list. Record it and let the reading session file it.

---

## Runs

One line per run sheet, newest last. Results, raw output and the run's one-line finding live in the sheet, not here. Anything that outlives the run goes into an ADR amendment or [roadmap](../roadmap.md) § D, per [alpha-plan](../alpha-plan.md) step 5.

| Run sheet | Generated | Run (#) | Outcome |
|---|---|---|---|
| [windows-validation-runsheet-2026-09-26.md](windows-validation-runsheet-2026-09-26.md) | 2026-09-26 | #12b-2 | _not yet run_ |

## Results (before run sheets)

_Kept as recorded in #12b-1. New runs record in their run sheet (§ Runs)._

### #12b-1 automated runs (2026-09-24)

**Environment capture**, `uv run python spikes/windows_env_capture.py` with the US layout active (A rows above). Its installed-layouts block, which predicts A3b and A4b:

```
Installed layouts (read by HKL, nothing activated):
  HKL 04070407  lang=de  36 graphemes  own table: 'unexpected dead-acute'
      as 'en': "language 'en' is configured but the active keyboard is 'de'"
  HKL 04090409  lang=en  26 graphemes  own table: 'matches'
  HKL 040f040f  lang=is  36 graphemes  own table: 'matches'
```

The `de` line is the known `build_de()` gap (alpha-plan carry-forward, 12a-1: the reader finds a dead acute that the table lacks). It means Takki cannot start with `LANGUAGE = "de"` on this laptop, which is why A4b goes through `is`.

**Listener coexistence**, `uv run python spikes/listener_coexistence_spike.py` (C7's row):

```
two trace hooks:            trace_a 123 events, trace_b 123 events, identical to the 123 sent
two trace hooks + Takki:    trace_a 82, trace_b 82, identical to the 82 sent; Takki exit 0 (WM_CLOSE)
C7 over trace_a + Takki DB: PASS -- 28 prompts; trace-derived 28 / 22, dump 28 / 22;
                            10 held repeats, 2 upper-case, 0 retries, 0 restarts; skew +0..+0 s
```

**SDL queue fill rate**, `uv run python spikes/sdl_queue_soak.py measure` (E10's row): 59.5, 55.6 and 55.7 queued events/s over three short runs, all `MouseMotion` apart from one `WindowEnter` and one `ActiveEvent`. Each run was cut short by a hand on the touchpad, but the rate agrees with the 60 Hz pump bound.
