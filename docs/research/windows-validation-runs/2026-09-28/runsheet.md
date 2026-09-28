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

## Summary

| Test case | Fix | Result |
|---|---|---|
| FV-01 | #12c (1), by script | Pass |
