# Fix verification run sheet (alpha #12c onwards)

> **What this is.** [windows-validation.md](../../windows-validation.md) § *Fix verification*, rendered as test cases: what to do, the exact command, what to expect, and where to write the result. **This sheet is the single source of truth for this run.**
> **Generated:** 2026-09-28, from the protocol at `d3fe52e` plus the uncommitted 2026-09-28 edit that added § Fix verification.
> **One sheet for the series.** Unlike a Running-order sheet, this one grows: when a fix lands, its step goes into the protocol's § Fix verification first and is then added here as a new test case with the same ID. Earlier test cases are not edited once their result is recorded.

**Consoles.** PowerShell in Windows Terminal, in `C:\Users\smara\github\takki`. Never Git Bash. **[2]** is the console that runs the command.

**Result values:** `Pass` · `Fail` · `Not run` (say why).

---

## FV-01 · #12c (1): the late-stop race, by script

**Fix under test** (`87d028f`): `TTSWorker.run_one()` clears the engine's cancel flag after `get()`, then re-checks `_cancel_through` before speaking. Before the fix it cleared the flag before `get()`, so a `stop()` aimed at a letter that had already ended survived into the next letter.

1. Hands off the machine for the whole run. The bot sends real keypresses.
2. [2] `uv run python spikes/flag_race_sweep.py --minutes 15 --out docs/research/windows-validation-runs/2026-09-28/FV-01-sweep.txt`

**Pass:** **0 SILENT** in every bin and both controls, **and** the `race hit` line shows ≥ 1 trial with 0 SILENT (the race occurred and nothing went silent).

Date: 2026-09-28
Report: [FV-01-sweep.txt](FV-01-sweep.txt) · per-trial data: [FV-01-sweep.csv](FV-01-sweep.csv)

- Trials: 647. **SILENT: 0**, in every 2 ms bin from −60 to +30 ms.
- Controls: mid-letter 0 SILENT of 65, +150 ms 0 SILENT of 71.
- Race hit: **80** trials (key dispatched before `finished`, letter not cut), **0 SILENT**. This run's report was written before the sweep printed the `race hit` line, so the count is taken from the CSV. It matches the report's rule line: 189 − 109 = 80.
- End-of-letter prediction: median +0.1 ms, sd 4.6 ms (n = 303). Send → key dispatched: median 10.1 ms, max 29.6 ms. Same conditions as 2026-09-26 RS-22c.
- Limit: "not SILENT" means `speak()` did not start with the flag set. The sweep does not measure how long the letter sounded. Accepted: RS-22b matched every silence heard to a FLAG letter, one for one, so no separate check by ear (decided 2026-09-28).

**Result:** Pass

---

## FV-02 · #12c (2): no audio device exits 4, not a traceback

**Fix under test** (uncommitted working tree on `983f17d`, committed as `0cce9e7`): `PygameMixerCues()` raises `CueOutputError` in place of SDL's `pygame.error`, and `main()` catches it in the same guard as the voice probe: remedy on stderr, `EXIT_NO_AUDIO`.

1. Turn the headset **off**.
2. Settings → System → Sound → *Speakers (Realtek)* → **Don't allow**. The Sound page must list **no** output device. If one is left, the check tests nothing.
3. [T] launch line, and start timing when you press Enter:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```

↺ **Restore:** Settings → System → Sound → *All sound devices* → Speakers → **Allow**. Headset back on. Play any sound and confirm you hear it.

**Pass:** Takki exits **4** (`EXIT_NO_AUDIO`) within ~10 s, with `Takki cannot start: …` on stderr followed by the remedy line (`Check that speakers or headphones are connected …`). **No traceback, no exit 1.** The first line names the sound cues or the voice, whichever fails first; with no device it is the cues.

Date: 2026-09-28

- Printed (both lines):
  ```
  Takki cannot start: the sound cues cannot play any sound (WASAPI can't find requested audio endpoint: Element not found.).
  Check that speakers or headphones are connected and selected as the Windows sound output, then start Takki again.
  ```
- Traceback: no
- Exit code: 4
- Time to exit: not timed. About 10 s by estimate, similar to RS-03's timed 9.5 s.
- Audio restored and audible: yes. With the speakers allowed again, Takki plays sound as before.

**Result:** Pass

---

## FV-03 · #12c (3): the close button still works after SDL's queue would have filled (E10)

**Fix under test** (`1ac6689`): `PygameFocusSource.poll()` takes every event off SDL's queue with one unfiltered `get()` and ignores all but focus-gained, focus-lost and `QUIT`. Before the fix it took only those three, and everything else stayed queued up to SDL's 65,535 cap, after which `QUIT` was refused.

1. [T] launch line:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
2. [2] start the mouse helper:
   ```powershell
   uv run python spikes/sdl_queue_soak.py drive --minutes 25 --close
   ```
3. Alt+Tab to Takki. The cursor circles inside Takki's window. It pauses while another window is in front, and stops if you move the mouse yourself.
4. Leave it for **at least 25 minutes** of motion (the helper prints one line per minute). Practising meanwhile is fine. Wait for the first one or two minute lines before leaving it unattended.
5. The helper then closes Takki itself: it posts `WM_CLOSE`, which is what the close button sends, and waits up to 10 s for the window to go. If Takki is still open, press Ctrl+C in [T] and record the fail.

**Pass:** **Still closes**, within a couple of seconds: the helper prints `CLOSED in … s`, not `STILL OPEN`.

Date: 2026-09-28, run overnight (result read 2026-09-29)

- Minutes of motion (the helper's last progress line): 25. The helper posts `WM_CLOSE` only after the full `--minutes` of motion, and an early stop returns without closing, so the close line below implies all 25.
- Helper stopped early (you moved the mouse, or anything else): no
- Helper's close line (`CLOSED in … s` or `STILL OPEN …`): `CLOSED in 0.05 s after WM_CLOSE.`
- Exit code ([T]): 0

**Result:** Pass

---

## FV-04 · E2/E3 follow-up: the pause announcement names the way back (E1)

**Change under test** (`1a33006`): the pause announcement is now *"Paused. Press Alt+Tab to come back to Takki."* In Alpha, Alt+Tab is the resume path, and the held-key raise (E2/E3) moved to Beta ([ADR-028 § C8](../../../adr/0028-composite-input-and-keyboard-ownership.md), *Resume in Alpha*; [roadmap C18](../../../roadmap.md#c-genuinely-unhandled-corner-cases-mostly-voicebeta-but-cheap-to-decide-now)).

1. [T] launch line:
   ```powershell
   uv run takki; "exit $LASTEXITCODE"
   ```
2. While a letter is being asked, Alt+Tab to another window. Listen.
3. Alt+Tab back to Takki. Listen.

**Pass:** On leaving, *"Paused. Press Alt+Tab to come back to Takki."* On returning, *"Back in Takki."*, then the open prompt **asked again after** the announcement, not over it.

Date: 2026-09-29

- Heard on leaving: *"Paused. Press Alt+Tab to come back to Takki."*
- Heard on returning: *"Back in Takki."*
- Prompt asked again after the announcement, not over it: yes

(Recorded as a pass on the pass condition's wording; the developer reported the result as a pass rather than word for word.)

**Result:** Pass

---

## Summary

| Test case | Fix | Result |
|---|---|---|
| FV-01 | #12c (1), by script | Pass |
| FV-02 | #12c (2), by hand | Pass |
| FV-03 | #12c (3), E10 | Pass |
| FV-04 | E2/E3 follow-up, E1 by ear | Pass |
