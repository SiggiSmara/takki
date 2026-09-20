# Windows validation protocol (alpha session 12b)

> **Status:** Protocol — written before the run, results pasted back in. Grounds the Alpha → Beta go/no-go against [roadmap § What "done" looks like per phase](../roadmap.md#what-done-looks-like-per-phase).
> **Date written:** 2026-09-20. **Date run:** _not yet run._
> **Machine:** the Windows test laptop. The primary dev box is headless Linux with no audio device and a `win32`-pinned `pynput`, so nothing below can run there — this is the whole reason the tier exists.
> **Scope:** the Alpha done-criterion and everything that would invalidate it. *Not* a Beta feature test: no voice, no Piper, no Layer 2, no multi-profile.

Written for whoever sits at the laptop. Record results **in the Result column as you go**, not from memory afterwards — several checks are about what you *heard*, which does not survive an hour.

**Legend.** **+** positive test (the thing should work). **−** negative test (the thing should fail safely, or is expected to expose a known gap).

---

## Before you start

None of this is worth running until all seven are true. *(All seven are true as of 2026-09-20, pending 12a-2 being committed — P1's merge is the only one outstanding.)* All but P1 are [alpha-plan](../alpha-plan.md) carry-forward rows; a run that precedes them tests known-wrong behaviour and has to be repeated.

| # | Precondition | Why it blocks |
|---|---|---|
| P1 | **12a-1 and 12a-2 are both merged and green**, including the `audio` and `windows_only` tiers | Nothing below runs otherwise: without 12a-1 `get_layout_positions()` raises `NotImplementedError` and Takki cannot launch; without 12a-2 it launches mute and truncates anything longer than a letter |
| P2 | **Letter-case decision implemented** | **Done, 2026-09-20: case is ignored.** An upper-case answer counts as correct; folding happens at the taxonomy boundary (ADR-027 § Case is folded at the boundary). Caps Lock is therefore invisible to the run rather than poisoning it |
| P3 | **Data directory decision implemented** | **Done, 2026-09-20.** Resolved via `platformdirs` to the OS convention — on this laptop `%LOCALAPPDATA%\Takki\takki.sqlite`, Local rather than Roaming because the database is WAL-mode. D-tier runs against the final path, so it will not need re-running. `TAKKI_DATA_DIR` is deliberately **not** built; see the note under this table |
| P4 | **Switch the laptop's active keyboard layout to US English before you start** | Measured: the laptop reports `en-150` on a **German QWERTZ** layout (`00000407`), with US (`0x409`) already installed. There is no longer an override to paper over that — Takki now *verifies* language against active layout at startup and **refuses to run** on a mismatch (ADR-025 § Language and layout must agree), so an un-switched laptop will exit non-zero before the window opens. One Win+Space. Doing it this way means the run tests the real path. Stage 0's six anchors were safe either way: `R F V` / `U J M` sit at the same scan codes on QWERTZ |
| P5 | **Progress dump script exists** (`key_stats`, `key_attempts` per calendar day, `milestones`, `sessions`) | **Done, 2026-09-20 (#12a-0):** `src/takki/progress_dump.py`. Alpha passes no `celebrant`, so every milestone is silent. Without the dump, D3's anchor rung is unobservable |
| P6 | **TTS engine is constructed on the worker thread** | **Done, 2026-09-20 (alpha session 12a-2).** `get_fallback_tts(voice_id)` returns a factory and `TTSWorker` builds the engine on its own thread, so no main-thread path can construct one. Windows no longer goes through pyttsx3 at all — `SapiTTS` drives `SAPI.SpVoice` directly (ADR-003), which also removed the truncation that cut every utterance after the first to ~0.9–2.1 s. `-m audio` is green on this laptop and `main()` has run start to finish with speech verified by ear |
| P7 | **Fallback voice is selected by language** | **Done, 2026-09-20 (alpha session 12a-2).** The verified id is now applied — `get_fallback_tts(voice_id)` takes it and the engine sets it before speaking, so B4 passes on the mechanism rather than by luck. `find_voice()` also reads the **OneCore** and HKCU token categories, not just SAPI5, so the remedy `main.py` prints on `EXIT_NO_VOICE` now actually helps. Unchanged on this laptop: `en` → David, `de` → Hedda, `is` → none |

**No environment overrides exist at all** — `TAKKI_DATA_DIR`, `TAKKI_LANG` and `TAKKI_LAYOUT` were all withdrawn on 2026-09-20 (ADR-025 § Alternatives now rejects env-var overrides outright), by decision (alpha-plan carry-forward "`TAKKI_DATA_DIR` override"). Tiers D and G therefore run against the real data directory. Before starting D, **copy `takki.sqlite` aside** so a botched run can be rewound, and note that G5 (read-only data directory) makes the developer's own directory read-only for the duration — undo it immediately afterwards. If that reads as too sharp an edge on the day, run tiers D and G under a throwaway Windows user account — not by re-adding an env var.

Also have ready: the **pynput event trace** (`spikes/pynput_trace_spike.py`, built 2026-09-20 in #12a-0) logging `pressed`, `char`, `name` and a timestamp per event to a file. Tier C is unreadable without it.

---

## A — Environment capture

Do this first and write the answers down. Several later checks are only interpretable against them, and the two-day D tier is expensive to repeat because a precondition turned out to be false.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| A1 + | Windows version, Python version, `pygame`/SDL version, whether OneDrive redirects Documents | Recorded | — |
| A2 + | `get_system_language()` return value | **`en`** — the raw locale is `en-150`, so this checks that the BCP-47 hyphen and the numeric region subtag are both handled | — |
| A3 + | `get_layout_positions()` — grapheme count, and a letter at all six anchor positions (2,4) (3,4) (4,4) / (2,7) (3,7) (4,7) | Six letters present, and `Layout.lang` reports the **keyboard's** language (`en` on the US layout), not the system locale. A raise here is `anchor_keys()` working as designed (#8b), not a bug to catch | — |
| A3b − | With the German layout active (Win+Space), launch Takki | Refuses to start, exits non-zero, and names `y`/`z` and the `ä ö ü ß` as the reason. Switch back to US before continuing. This is the only hand-check of the startup layout guard | — |
| A4 + | Where the database file actually landed | Exactly `%LOCALAPPDATA%\Takki\takki.sqlite`, and **no** stray `Documents\Takki\` created (the pre-2026-09-20 path). Check for `takki.sqlite-wal` / `-shm` beside it — their presence is WAL working as intended | — |
| A4b + | `find_voice()` for `en`, `de` and `is` | `en` and `de` return a `HKEY_LOCAL_MACHINE\...` token id, `is` returns `None`. Then set `config.LANGUAGE = "is"` and launch: Takki must refuse with `EXIT_NO_VOICE` and name the remedy. This is the only hand-check of the graceful-stop path | — |
| A5 + | `detect_screen_reader()` with and without NVDA running | Matches whatever [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr) decided; `None` is fine if it stayed out of Alpha | — |

---

## T0 — The automated tiers, on this machine

The `audio` marker has never run in CI on any platform, and `windows-latest` sets `SDL_VIDEODRIVER=dummy`. So this is the first time several of these execute for real.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| T0.1 + | `uv run pytest` | Green | — |
| T0.2 + | `uv run pytest -m windows_only` | Green — real pynput translation, real SDL window construction | — |
| T0.3 + | `uv run pytest -m audio` | Green (17 tests, ~50 s, as of 2026-09-20). The tier to read is `tests/test_sapi_tts.py`: it drives the real engine from a real worker thread and **asserts utterance durations**, because the defect that hid for eleven sessions was speech being cut short, which every earlier test — `speak("a")` does not raise — would have passed through. Treat a pass as a positive result rather than a formality. Note no GitHub runner has confirmed this tier yet; `windows-audio-probe` in CI is asking that question and is non-blocking until someone reads its first run | — |

---

## B — The core loop, by ear

All of B is run with the screen ignored. If you find yourself looking at it, that is a finding — record it.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| B1 + | Launch. Window appears and takes foreground | Foreground without a click. If not, the seed `FocusLost` fires and B2 is testing the resume path instead — note it | — |
| B2 + | Time from launch to first spoken word | Recorded. Language-table warm is ~1.4 s (en) on the dev box; anything past ~5 s is worth a note | — |
| B3 + | The Stage 0 introduction script for `f` and `j` | Both lines audible and **complete to the last word**, in order, before the first prompt letter. **Listen hard here.** Before 12a, SAPI cut every utterance after the first to ~0.9 s, so the script ended mid-sentence while single letters sounded fine — this row is the check on that fix and the failure is silence, not a wrong noise | — |
| B4 + | All six anchor letters spoken as prompts (`r f v u j m`) | Each intelligible as a *letter name*, not a word or article. This is A1's finding holding on real hardware | — |
| B5 + | Correct keypress | Chime, then the next letter. Chime feels immediate | — |
| B6 − | Wrong keypress | Error tone, **same letter** re-prompted, prompt stays open | — |
| B7 + | Keypress while the letter is still sounding | Whatever the carry-forward "Main-thread `stop()` cost" row decided. A letter is ~0.94 s audible, so pressing inside that window takes deliberate anticipation — press early on purpose. If the decision was "do not interrupt letters", the pass condition is that the letter finishes and the chime is still immediate; if it was "interrupt", speech cuts and **the chime must not be delayed** | — |
| B8 + | Two fast keypresses (type-ahead), answering two prompts | Both land, both counted. Pinned on Linux by `TestTypeAhead`; this is the real-timing version | — |
| B9 − | Wait 10 s in silence, three times over | Three re-prompts, then **quiet with the prompt still open**. A fourth re-prompt is a failure | — |
| B10 + | Type the letter after that silence | Counted as a *first* attempt — the prompt never re-latched | — |
| B11 + | Re-read key (Escape tap, released well under 800 ms) | The open prompt is re-spoken. No restart | — |
| B12 + | Restart key (Escape held past 800 ms) | Fires **once**, at the threshold, with the key still down. The current unit is re-presented | — |
| B13 − | Escape tap at ~700 ms and ~900 ms | 700 → re-read, 900 → restart. Record how hard the boundary is to hit — carry-forward **D Escape** chose one key on purpose, and this is the check on that choice | — |
| B14 − | Hold Escape a long time (5 s+) | Exactly one restart, not a stream of them. Auto-repeat must not re-fire the gesture | — |

---

## C — The two ADR-027 input assumptions

**The highest-value tier.** [ADR-027 § First-Attempt Counting](../adr/0027-key-and-accuracy-state-model.md) rests on two Windows behaviours no Linux test can reach, and the held-key counting rule is wrong if either fails. Run these with the trace tool, then read the log — not by ear.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| C1 + | Hold `f` until the OS auto-repeats several times | **No release event between repeats.** If Windows or pynput synthesises one, every repeat reads as a fresh actuation and the rule silently does nothing — amend ADR-027 and re-run all of D | — |
| C2 + | Press Shift, release it, then press and release a letter quickly | Press and release report the **same** character. The focus model case-folds both sides; `None` or an unrelated char on release leaks a down-entry | — |
| C3 − | Caps Lock on, then type a prompted letter | **Counted correct**, normal chime, prompt advances — indistinguishable from Caps Lock off. The trace will show `char='F'`; the engine sees `f`. Type a few with Caps Lock on and off and confirm the dump's counts do not separate them | — |
| C4 + | Type `ll` **releasing** between the two presses | Two actuations, two counted attempts — a doubled letter is two keystrokes | — |
| C5 − | Type `ll` **holding** through both | One actuation, one counted attempt. C4 and C5 differing is the entire point of the rule | — |
| C6 − | Dead-key composition at the capture boundary (trace tool only, no lesson engine). **The Icelandic layout `0x40f` is already installed on this laptop** — no setup, just switch to it and switch back | One composed `KeyCode(char='á')` arrives. Capture-only by roadmap scope — does not need B8 resolved and does not gate Alpha's English run | — |
| C7 + | A mixed session of ~40 prompts with deliberate errors and retries, trace running | Trace-derived attempt/correct counts **exactly** match the dump's `key_attempts` rows. Any drift means first-attempt accuracy is not what the engine thinks | — |

---

## D — Persistence and the anchor gate

**Needs two calendar days minimum** — `KNOWN_MIN_DISTINCT_DAYS` is 2 and cannot be compressed. Plan D1 and D3 as separate sittings.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| D1 + | Day 1: complete Stage 0 (~360 prompts across the three steps) | All six anchor keys Active. **No rung yet** — one calendar day cannot satisfy the gate | — |
| D2 + | Close the app normally, reopen | Progress restored; the session resumes without re-introducing a completed key | — |
| D3 − | Kill the process mid-write (Task Manager, during typing) | DB intact and readable on reopen. WAL + `synchronous=NORMAL` should survive this | — |
| D4 + | Day 2: practise the anchor keys again to the gate's bar | Anchor rung written **exactly once**, never revoked. It is silent — read it from the dump | — |
| D5 − | Quit mid-introduction, before answering the introduced key | That key is **re-introduced** next session. Its record is session-local by design (ADR-023) | — |
| D6 − | A session crossing local midnight | Counts as two distinct days per ADR-027's `date(attempted_at)`. A child practising at 23:55 and 00:05 should not be handed a rung for one sitting — record whether that feels right | — |

---

## E — Focus, OS preemption, hostile input

Mostly negative tests: Alpha's focus model exists because the OS interrupts.

| ID | Check | Pass condition | Result |
|---|---|---|---|
| E1 + | Alt+Tab away mid-prompt, then back | Pause announced on leaving; resume announced on return; the open prompt is **re-issued behind** the announcement, not over it | — |
| E2 + | While away, hold F1 for 1 s | Takki raises itself and resumes — keyboard only, no mouse | — |
| E3 − | While away, hold F1 where the raise is refused or downgraded to a taskbar flash | Alt+Tab hint spoken after ~1.5 s. Expiry is the only failure signal there is | — |
| E4 − | Windows key (Start menu), then return | Pause/resume. Losing focus to a system key is the *intended* trigger, not a leak | — |
| E5 − | Win+L (lock), Ctrl+Alt+Del, and a UAC prompt | Pause on the way out, resume on the way back. The secure desktop delivers no hook events — the backup focus poll is what catches it | — |
| E6 − | Press Shift five times (Sticky Keys dialog) | Pause/resume like any other focus thief; no stuck modifier afterwards | — |
| E7 − | Mash Backspace, Tab, Enter, Delete, arrows, F-keys, Ctrl+letter, AltGr | Nothing counted, nothing crashes, prompt unchanged. Backspace especially: ADR-012 disables it outright | — |
| E8 − | Press the space bar repeatedly | Ignored. The space bar is never introduced in any phase | — |
| E9 + | Close the window with the mouse | Clean shutdown via the `Quit` path; session row ended | — |
| E10 − | Leave the mouse moving over the window for 15+ minutes, then close it | **Still closes.** `poll()` consumes three event types and the rest accumulate toward SDL's 65,535 cap, after which `QUIT` is refused. This check decides whether to pre-empt with a full drain or leave it | — |
| E11 − | Ctrl+C in the launching terminal | Clean exit via the signal handler; session row ended | — |

---

## F — Endurance

| ID | Check | Pass condition | Result |
|---|---|---|---|
| F1 + | 60–90 minutes of continuous practice | No latency drift, no memory growth, no audio degradation. Cue still feels immediate at the end | — |
| F2 − | Sleep/hibernate the laptop mid-session, then wake | Listener still alive and the loop still responsive. A dead pynput hook surfaces only at `join()`, so the symptom would be a silent keyboard | — |
| F3 − | Unplug headphones / power off a Bluetooth headset mid-lesson | **Expected to fail** — this is roadmap **C14**, scheduled for Beta. Record exactly what happens so C14 is written against observed behaviour rather than a guess | — |

---

## G — Environment and accessibility

| ID | Check | Pass condition | Result |
|---|---|---|---|
| G1 + | Run as a standard (non-admin) Windows user | Works with no elevation, no UAC prompt at any point | — |
| G2 + | Run on battery in power-saver mode | Still responsive. The Whisper matmul benchmark is Beta, but SAPI latency under throttling is worth knowing now | — |
| G3 − | Run with NVDA active | Record the coexistence behaviour — double-speaking, focus stealing, or clean. Drives the ADR-028 open question 4 NVDA decision | — |
| G4 − | Launch a second instance while the first runs | Fails clearly, or both work without corrupting the DB. Silent corruption is the failure | — |
| G5 − | Make the data directory read-only, then launch | Fails with something a person can act on — not a silent crash, and ideally not a stack trace as the only output | — |
| G6 + | **Eyes closed** from launch through one full drill block | Never needing the screen, the console, or a mouse. This is the audio-first invariant, and the only check that tests the actual product claim | — |

---

## Go / no-go

**Hard no-go — any one of these fails:**
T0.1–T0.3 · A3 · A4 · B1–B12 · C1 (or C1 fails, ADR-027 is amended, and D re-runs clean) · C2 · C4 · C5 · C7 · D1–D5 · E1 · E2 · E5 · E9 · E10 · E11 · F1 · F2 · G1 · G6

**Go, with the result recorded as a Beta item:**
F3 (C14, already scheduled) · G3 (NVDA coexistence) · B13's boundary feel · D6's midnight judgement · the silent milestone · the missing F/J nub wording · the restart re-counting hole · ADR-010's slack introduction gate.

**The distinction:** a hard no-go is something that makes the Alpha claim false — the loop does not work with a real person, or the numbers it records are not the numbers it thinks. Everything in the second list is a known, filed gap that a pilot family would meet but a developer can work around, and none of them changes whether the core loop is proven.

---

## Results

_Paste the filled tables, the trace excerpts for tier C, and the progress dump for D here. Then write the one-line finding at the top of this note, the way [tts-letter-pronunciation](tts-letter-pronunciation.md) does, and carry anything that outlives the session into an ADR amendment or [roadmap](../roadmap.md) § D per [alpha-plan](../alpha-plan.md) step 5._
