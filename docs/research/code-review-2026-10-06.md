# Whole-repository review of 2026-10-06 (alpha-plan #12k)

> **Status:** Step 1 (tools) done, triaged, and its agreed gaps closed with tests on 2026-10-07 (commit `3eac0f2`). Step 2: all four passes run and every finding verified. R1 to R4 are fixed. The findings of passes 1 and 3 (E1 to E7, C1 to C7) carry proposals and are **Open** until the developer decides.
> **Date written:** 2026-10-06, at commit `a195912`. Updated 2026-10-07.
> **Scope:** all of `src/takki` and `tests`, except `takki.platform.windows`, `takki.audio.sapi_tts` and `takki.input.pynput_stream`, which cannot run on the dev box and are #12h's to test.

## How Step 1 was run

All three tools were run one-off through `uv`, as decided on 2026-10-02. Nothing was added to `pyproject.toml` or `uv.lock`.

| Tool | Command | Result |
|---|---|---|
| Coverage, with branches | `uv run --with pytest-cov pytest --cov=takki --cov-branch` | 1,404 passed, 1 skipped, 55 deselected. 88% overall. Every module of `takki.lesson`, `takki.persistence` and `session.py` is at 96% or above |
| Mutation testing | `mutmut` 3.8.0 on `takki.lesson` and `takki.persistence`, in a copy of the repository | 2,318 mutants: 2,053 caught, 6 timed out (counted as caught), 252 survived, 7 reached by no test. 88.8% caught. The run took about twelve minutes on two cores |
| Dead-code scan | `uvx vulture`, once over `src` and once over `src` and `tests` together | 13 names unused anywhere, 14 more used only by tests |

Two things about the mutation run:

- **One test was left out of it.** `TestOnlyUtcIsStored::test_every_timestamp_parameter_on_the_protocol_is_covered` lists the methods of the `Store` Protocol, and the tool adds its own copies of each method to the class, so the test fails before any mutant is tried. Its absence does not explain any survivor below: it checks which methods exist, not what they do.
- **The config lived only in the copy.** To repeat the run: copy the repository, add `[tool.mutmut]` with `source_paths = ["src"]`, `only_mutate = ["src/takki/lesson/*", "src/takki/persistence/*"]`, `pytest_add_cli_args_test_selection = ["tests"]` and a `--deselect` for the test above, then `uv run --with mutmut mutmut run`.

## What the survivors said, and where it stands

About half of the 252 survivors changed nothing a test could see. The other half fell into the gaps G1 to G16. In every gap where the code was checked, **the code was right and the test was missing**. Step 1 found no wrong behaviour.

The developer agreed on 2026-10-07 to close the gaps with tests, leaving G14 and G15 for Beta. After that work:

| | Before | After |
|---|---|---|
| Tests | 1,404 | 1,434 (30 added for the gaps; since then two commented out under D1 and 24 added for R1 to R4, counting each store separately, for 1,456) |
| Surviving mutants | 252 | 180 |
| Coverage | 88% | 89% (`main.py` 70% to 98%) |

Each new test was shown to catch its mutants by running them again in the copy. The 180 that remain are the harmless group at the end of this note, G14 and G15, and the few named as left in the rows below. `ruff` is clean and both `pyright` runs report no errors.

## Gaps: behaviour no test pinned

"Mutants" names the function and the mutant numbers from the run, so a row can be checked against the tool's output. Test names are in `tests/`.

| # | Gap | Mutants | Outcome |
|---|---|---|---|
| G1 | **The real store's `limit` on `window_attempts` was untested, and the fake disagreed with it at zero.** `RampUpProgress.member` reads a phase's evidence with `limit=min(since, EVIDENCE_ROWS)`, and every test of that runs on `FakeStore`. `SqliteStore` could ignore `limit` with the suite green, and phase bars would then be judged over presses from before the phase. Group U2 of [code-review-2026-10-01.md](code-review-2026-10-01.md) | `SqliteStore.window_attempts` 7 | **Tested, fake fixed.** `test_persistence.py::TestWindowAttempts::test_a_limit_keeps_the_latest_rows_and_zero_keeps_none`, over both stores. `FakeStore` returned every row at `limit=0` (`attempts[-0:]`) and now returns none |
| G2 | **Nothing tested that the carrier and the partners follow the language's frequencies.** *Corrected 2026-10-07: this row first said "drill content", which was wrong.* Which key a block practises is decided by need (ADR-024 § Steady-state drill generation, #12e), and that is tested. What still follows frequency is narrower: the bigram that carries a planned key (rule 5), the letter a key is paired with when no bigram carries it, and Phase C's partners. Those could be zeroed, reversed or made uniform | `_weight` 1, 5; `_partners` 6, 8, 10, 11; `_carrier` 9, 11, 14, 15, 17; `_phase_c_units` 5, 10, 12, 14, 15, 19, 39; `_choose` 4, 6; `_extend` 17, 19; `_pool` 2 | **Tested.** `test_drills.py::TestLanguageWeights` (three tests) and `TestPhaseCAndD::test_the_partners_are_the_most_frequent_keys_the_child_has`, `test_a_letter_no_bigram_carries_is_paired_with_the_heaviest_partner`, `test_a_trigram_is_two_corpus_bigrams_drawn_by_weight` |
| G3 | **The planner's bar was untested.** `_bar` holds the six Stage 0 keys to `ANCHOR_MIN_ACCURACY` and every other key to `KNOWN_MIN_ACCURACY` (#12f). The condition could be always true, always false or inverted | `_bar` 1, 2, 3; `_need` 8 | **Tested.** `TestSteadyPlan::test_a_stage_0_key_is_planned_against_the_anchor_bar`. `_need` 24 (the floor of one press for a key waiting for its second day) is left. **Open:** whether `_bar` should read from `KnownCriterion`, the second definition of Known that U3 named |
| G4 | **Phase C's trigrams were untested.** The chaining test in `_extend` could be inverted or read the wrong letter | `_extend` 3, 4, 6, 7, 8, 10 | **Tested** by the trigram test under G2. `_extend` 9 is harmless: the unit is two long, so its second letter is its last |
| G5 | **A ramp-up block's length when few presses are owed was untested.** The tests only saw blocks where the target length decided. This is the arithmetic #12d's restart pacing rests on | `remaining` 6, 14, 19, 22; `_cycle_units` 10, 23; `_phase_c_units` 25, 35, 47, 48 | **Tested.** `TestBlockLength::test_a_phase_a_block_is_one_cycle_when_one_press_is_owed`, the same for Phase B and Phase C, and `test_a_phase_c_block_is_filled_to_the_target_and_no_further`. Left: `_phase_c_units` 33, which needs an odd block target to show. `_cycles_owed` 1, 3, 9, 10 and `_remaining` 6 turned out harmless: every inventory `_cycle` builds names a member once, so dividing by the times it is named changes nothing today |
| G6 | **The share-by-need step of `plan_targets` was untested.** The D'Hondt key `needs / (count + 1)` could become `needs * (count + 1)`. The existing worked example gives the same answer either way | `plan_targets` 8, 52, 54 | **Tested.** `TestPlanTargets::test_each_further_slot_goes_to_the_most_need_per_slot_held`, derived by hand, and `test_no_keys_or_no_slots_plans_nothing`. 10, 16 and 23 are harmless |
| G7 | **Anchor-slipping drills were tested with the first anchor only.** Stopping at the first anchor that is not slipping passed, and so did stopping at the first with no reach | `_anchor_drills` 5, 9; `_reach` 10; `_anchor_slipping` 3 | **Tested.** `TestAnchorMaintenance::test_the_second_anchor_slipping_alone_gets_its_drill`, `test_an_anchor_with_no_reach_does_not_cost_the_other_its_drill`, `test_the_sample_floor_is_enough_to_be_slipping` |
| G8 | **The anchor for a new key: same finger on the home row first.** With the preference removed the choice fell to the nearest key on the same hand, and every tested key got the same anchor either way | `_anchor` 11, 12 | **Tested.** `TestAnchorChoice::test_a_new_key_alternates_with_its_own_fingers_home_key`: `t` alternates with `f`, though `r` is nearer |
| G9 | **The speed baseline's path through the generator.** First listed as a gap; on reading, mostly not one | `DrillGenerator._baseline` 3; `_refresh_ramp` 6, 10, 11; `next_block` 14, 16; `KeyStates.slow_keys` 6; `KeyStates._baseline` 12 | **No test needed for the first six.** Asking for the baseline of no key gives the same number for every key but `f` and `j`, and those two are only ever in a ramp-up together, where neither can be more than twice the median of the pair. The other four only change when the baseline is read, not what it is. **Left:** `slow_keys` and `KeyStates._baseline` ignore a custom `KnownCriterion`; nothing in `src` passes one |
| G10 | **The spoken reach never said "down" or "left" in a test.** `describe_location` could say "up" for every row and "right" for every column | `describe_location` 10, 15, 16, 18, 20, 21, 34, 35; `_count` 5, 6, 7; `_spoken` 4 | **Tested.** Five tests in `test_introducer.py::TestScript`, from `test_a_bottom_row_key_is_reached_down` on. `describe_location` 13, 14, 22, 23 are harmless: a move of zero never reaches the line |
| G11 | **Rules at their exact threshold** | `bar_met` 13; `accuracy_bound` 1; `_presses_to_confirm` 7; `_anchor_slipping` 9; `record_attempt` 5; `member` 40; `_target_prompts` 7, 9, 14; `_phase_c_unit` 9 | **One pinned, the rest left.** The anchor's sample floor is under G7. Phase C's bar cannot be met exactly: 85% of 30 presses is 25.5. The others compare a computed fraction for equality or sit on an arbitrary inclusive bound |
| G12 | **The per-key session count** could start at 1 or step by 2 | `record_attempt` 17, 18 | **Tested.** `TestSessionFloor::test_the_floor_is_reached_on_its_last_press_and_not_before`. `_steady_units` 8 and 20 are left; see D5 for the floor itself |
| G13 | **A milestone's timestamp.** `MilestoneDetector` could drop the `now` it was given and let the store stamp the row itself | `MilestoneDetector.__init__` 5; `check` 19, 20, 25, 28 | **Tested.** `test_milestones.py::TestFiringOnce::test_a_rung_is_stamped_by_the_clock_the_detector_was_given` |
| G14 | **`create_profile` can return a `Profile` without its six settings** (voice, rate, talk key, re-read key, restart key, push-to-talk mode). The row is written correctly. Alpha uses none of the six | `SqliteStore.create_profile` 14 to 19, 24 to 29 | **Left for Beta's profile work** (ADR-013), as agreed |
| G15 | **The composite and modifier path.** Whether a mechanism has been taught can be ignored, and a modifier with no spoken name, no location or no mechanism note is never built | `_introduce_modifier` 20, 23; `_composite_clauses` 6, 7, 8; `phase2_slots` 34; `_locate` 6; `resume_step` 5 | **Left for roadmap B8** and the first dead-key language, as agreed. The last three were not read; pass 1 should |
| G16 | **The last fallbacks of `_next_form` never run** (`drills.py` lines 550 to 553), and the hand-tracking behind the return-home guard can lose its side | `_next_form` 24, 25, 26; `_returns_home` 10, 15; `_track` 7 | **No test: no path through the public interface reaches them.** With the inventories `_cycle` builds, some form always returns home. **For pass 1:** a reach before its anchor (`e d`) appears at most once in a block, at its start, in the real code. After `d e` the hand is off home, so only `d e` can follow. The child hears the same `d e d e` either way. Is that what ADR-024 property 1 means by varying direction? |

## Gaps the coverage report added

| # | Gap | Outcome |
|---|---|---|
| G17 | **`main()` was never run past the audio check.** Opening the store, choosing the profile, building `SessionLoop` with the real `WordfreqSource` and `SqliteStore`, and starting it: no test ran these lines. The startup crash confirmed from the 2026-10-01 review ran through this seam | **Tested.** `test_main.py::TestStartup`: a cold start with only the window, the mixer, the voice and the keyboard hook faked speaks exactly the first pair's scripts, stops on SIGINT, and leaves one profile, two introductions and a closed session row. Two more tests run the wrong-keyboard and no-voice stops through `main()` |
| G18 | **No test ran a session to the end of the curriculum** | **Tested.** `test_session.py::TestEndOfTheCurriculum`, on a layout of the six Stage 0 keys. Still not reached: the stop on an empty curriculum (`session.py` 537), the restart key after a block's last prompt (484), and the `begin_step` returns-False branch (633; see D12) |

`progress_dump.py` (86%) misses only its "(none)" lines for empty tables. `clock.py` and `pygame_cues.py` miss what needs a real clock or a real device.

## Dead and stale code

This settles group U3 of the 2026-10-01 note. "Tests only" means the scan found no use in `src`. The developer decided on 2026-10-07 that dead code is commented out for now, not deleted; each commented block carries the date and its row number here.

| # | Item | Finding | Proposal | Outcome |
|---|---|---|---|---|
| D1 | `RampUpProgress.step_phase` | Tests only. U3, confirmed | Remove with its tests | **Commented out**, with the two tests in `test_rampup.py` that tested it |
| D2 | `live_run`'s `max_rejections` parameter | No caller passes it. U3, confirmed | Remove the parameter | **Commented out** |
| D3 | `DrillGenerator.record_attempt`'s `correct` parameter | The body never reads it. U3, confirmed | Remove it, or say in ADR-027 why the pair of calls keeps the same shape | **Left.** The session loop and the test fixtures pass the argument, so taking it out changes callers, not just a dead line |
| D4 | `KeyStates.window_attempts` | No caller and no test | Remove | **Commented out** |
| D5 | `DrillGenerator.session_complete` | Tests only. ADR-024's per-key session floor is computed and never acted on. [roadmap § D](../roadmap.md) already files this ("Two engine signals have no consumer") as Beta, and the same section holds the developer's lesson proposal of 2026-09-26, which would make the floor a lesson's end | A decision | **Left for Beta** (the developer, 2026-10-07), after first choosing the single spoken line for Alpha. A simulated first session, every answer right, showed why it needs more thought: the floor is first met after 90 answers, and the next block boundary, at 120, is the one that introduces `r` and `u`, so the line would be followed at once by "New letter:". Held until no letter is being learned, it comes after 613 answers. The floor also predates need-based planning (#12e), so "every Active key at 45" may be rare in later sessions; that part is reasoned, not measured. Recorded in the roadmap entry |
| D6 | `config.SOUND_CORRECT`, `SOUND_ERROR`, `SOUND_BOUNDARY`, `SOUND_CHIRP_ON`, `SOUND_CHIRP_OFF` | Unused anywhere. The cues are synthesised tones | Remove | **Commented out** |
| D7 | `Store.get_profile`, `LanguageSource.bigrams`, `PlatformInterface.detect_screen_reader` | Tests only. Each is on a Protocol for Beta work that has an ADR | Keep | |
| D8 | `TTSWorker.idle` | Tests only: it is how tests wait for the worker | Keep | |
| D9 | `Layout` fields `keystrokes` and `dead_key`; `SqliteStore.create_profile`'s default language | Unused today. The fields describe composite graphemes, which no Alpha language has | Keep the fields; drop the default | **Left, and the proposal was wrong:** about 80 test calls rely on the default language |
| D10 | Stale comment at `milestones.py:131` | Says "wall-clock ISO-8601 local time (ADR-011)". Timestamps are UTC since 2026-09-30. U3, confirmed | Fix the comment | **Fixed** |
| D11 | `prev_char` across a block boundary | `AttemptCounter._previous` is set at construction and after each answer, and never cleared between blocks. ADR-011's schema comment says NULL means the first of a block. Pass 4 measured it: 200 answers over five blocks gave one NULL row, and a restart added one more. So NULL marks the first prompt after a start. Nothing in `src` reads the column | Clear it at the boundary, or change the ADR's sentence | **ADR corrected, code kept** (2026-10-07). ADR-011 now says NULL is the first prompt of a session, and why |
| D12 | The `begin_step` returns-False branch in `SessionLoop._introduce`; multi-paragraph docstrings; duplicated test helpers | Unchanged since U3 | Leave, unless pass 1 finds a path to the branch | |

Three results of the scan are not findings: the `autouse` fixture `headless_sdl`, the `pytestmark` variables, and the unused `item`, `signum` and COM attribute names, which the scan cannot see being used.

## Survivors that change nothing a test could see

No action proposed for any of them.

- **`cast(...)` with another type** (about 40, all in `sqlite_store.py`). `typing.cast` does nothing at run time.
- **SQL keywords and names in another case** (about 30). SQLite ignores case there.
- **The text of an error message** (6: `utc_stamp`, `_migrate`). The tests assert the error type.
- **A first value that is overwritten before it is read** (about 25: `AttemptCounter.__init__` and `start_prompt`, `DrillGenerator.__init__`, `begin_step`). These were classified from the diff alone. `start_prompt` setting `_timed` or `_unheard` to true was not traced through every caller.
- **Another search that finds the same answer** (`_presses_to_confirm` 12, 13, 18, 23).
- **Defaults on the `Store` Protocol itself** (3, reached by no test, since a Protocol's body never runs).
- **`MemberProgress` built with a wrong field when the member has no evidence** (`member` 16, 17, 18, 41; `advance` 2). The fields are not read on that path.
- **Found harmless while writing the tests:** the ones named in G4, G5, G6, G9 and G10.
- **Not checked, believed harmless:** `append_attempt` 24 (`excess > 0` against `>= 0`), `key_stats` 27 (a NULL `last_practised_at`), `_spread` 6 and 7.

## Step 2: the agent passes

Each pass was one Opus agent with one question and a named list of files, read-only. Every finding below was then checked inline, by running a repro or by reading the lines named.

| Pass | Question | Cost | Result |
|---|---|---|---|
| 2 | Does each fake behave like the real implementation of its Protocol? | 136k tokens, 25 tool calls, 5.5 minutes | 10 differences, none reachable through the engine today |
| 4 | What survives a restart? | 190k tokens, 32 tool calls, 11 minutes | 5 findings, all low; the resume path held at every quit point |
| 1 | Does the engine do what ADR-010, ADR-024 and ADR-027 say? | 242k tokens, 33 tool calls, 14 minutes | 7 findings: one small code fault, two design questions, the rest the ADRs promising more than the code does |
| 3 | Do the session loop, the speaker, the TTS worker and the focus model match [concurrency-model.md](../concurrency-model.md)? | 190k tokens, 31 tool calls, 11 minutes | 3 behaviour findings, all at the edges (quit, restart key); 2 of stale text; the thread and cancellation rules hold |

### Pass 2: fakes against the real implementations

Pass 2 was not told about G1 and found it (F2). Each difference is one guard away from mattering: a fake that is more forgiving lets a test pass on code the real implementation would stop.

| # | Difference | Reachable today? | Proposal | Outcome |
|---|---|---|---|---|
| F1 | `FakeLetterAudioSource.stop()` cancels only its own letter. The real source calls `TTSWorker.stop()`, which cancels everything queued, speech included | No: `_advance` issues no letter while the speaker is busy, and `Speaker._stop_audible` stops the letter first. The default session harness uses the fake, so a break in that gate would pass there | Hand to pass 3, which reads the speaker and the worker | **Open** |
| F2 | `window_attempts(limit=0)`: the fake returned everything, the real store nothing | No | Fixed under G1. A negative limit still differs and is not modelled | **Fixed** |
| F3 | The fake accepts writes for a profile that does not exist. The real store raises `IntegrityError` | No: `main` always creates the profile | Leave. `test_milestones.py` writes to profile 1 without creating it, so aligning the fake means changing those tests first | **Open** |
| F4 | A second `play()` on the fake drops the first letter's finish. The real worker reports both | No: `Speaker.letter` stops before replaying | Hand to pass 3 with F1 | **Open** |
| F5 | `end_session` on an unknown id: nothing in the real store, `KeyError` in the fake | No | Leave | |
| F6 | Order where the query has no total order: `achieved_milestones` with equal stamps, and the `key_stats` and `phase_records` dicts. The real store sorts by key, the fake keeps insertion order | No: every caller uses `set`, `sorted`, `.get` or `in` | Sort the fake's three results the way the real store does; it is three lines | **Open** |
| F7 | Constraints and coercion exist only in the real store: `rate=None` raises there, `latency_ms=12.0` comes back as `12`, `correct=1` as `True` | No | Leave | |
| F8 | `SqliteStore` raises when called from another thread; the fake answers | No: the store is used on the main thread only | Leave | |
| F9 | `ScriptedKeyStream` emits whether or not it was started. `FakeFocusSource` does not queue the first focus event, which the real window's constructor always does | Harmless. G17's test had to queue that event itself | Leave | |
| F10 | `FakePlatformInterface.get_fallback_tts` hands back one engine built in advance, from a factory that cannot raise. `find_voice("is")` is `None` on the fake and `"is"` on the dev stub | The raising path is tested by replacing the factory (`TestNoAudioOutput`) | Leave | |

Compared and found to agree: profiles and sessions, key stats, the window's cap and eviction order, `window_stats` and its local-day counting, introductions, phase records, letter lengths, milestones, the UTC check on every write, `FakeTTSEngine`'s cancel order against `SapiTTS`, the clock, the frame limiter, the cues and `FixedListSource`. Not covered: `PynputKeyStream`, `SapiTTS` and `PygameFocusSource.poll` were read for their contract only, and `progress_dump.py` reads the database outside the Protocol.

### Pass 4: what survives a restart

| # | Finding | Evidence | Proposal | Outcome |
|---|---|---|---|---|
| R1 | **The lifetime count and the attempt row are two commits.** `AttemptCounter` calls `upsert_key_stat`, then `append_attempt`. A kill between them leaves the count one ahead of the rows for good, and a phase's evidence is "the rows since the count at its start" | Repro: ten Phase A answers, two Phase B answers, then the count written without the row. After reopening, `key_stats` says 13, the window holds 12, and Phase B's evidence is 3 rows, one of them from Phase A. A bar can be met one answer early | One transaction for the pair. It is a change to the `Store` Protocol or to how `SqliteStore` commits | **Fixed.** `Store.count_attempt` writes both in one transaction and `AttemptCounter` calls only that. `test_persistence.py::TestCountedAttempt` (a failure between the two writes leaves neither) and `test_attempts.py::TestOneWritePerAttempt`. This was already in [roadmap § D](../roadmap.md) since 2026-09-24 as Beta's; #12j's phase records gave it a consumer that matters. ADR-011 amended, roadmap entry closed |
| R2 | **After a kill, `takki.sqlite` alone is not the profile.** The store runs in WAL mode and `main()` never closes it. ADR-011 says the file is the profile and can be copied | Repro: 13 answers, then the main file copied while the connection was open. The main file was 4,096 bytes, and the copy opened with no profiles. Reopening in place loses nothing | Close the store at shutdown, and say in ADR-011 that the file is complete once Takki has exited | **Fixed.** `main()` closes the store on the way out, and `TestStartup`'s cold start asserts that only `takki.sqlite` is left in the data directory. ADR-011 now says to copy the file after Takki has exited |
| R3 | **A SIGINT or SIGTERM during `start()` is discarded.** The handlers are installed before `loop.start()`, and `start()` ends with `running = True` whatever happened before | Read: `main.py` 181 to 184, `session.py` 196. Ctrl+C during the corpus warm-up is lost and a second is needed | `start()` leaves `running` alone if `stop()` has been called. A small fix with a test | **Fixed.** `stop()` is remembered, and `start()` returns before its first block if one came. `test_session.py::TestShutdown::test_a_stop_during_startup_is_not_lost`, which fails on the old code |
| R4 | **An exception inside a tick skips `shutdown()`.** `run()` has no `try`/`finally`. The session row keeps `ended_at` NULL for good, the block's unwritten letter lengths are dropped, and the worker threads are not joined | Read: `session.py` 218 to 221. The next start adds a new session row and leaves the orphan | `try`/`finally` in `run()`. What to do with orphan session rows is Beta's, with the reports that read them | **Fixed** for the shutdown: `run()` shuts down in a `finally`. `TestShutdown::test_an_exception_in_a_tick_still_shuts_down`, which fails on the old code. Orphan rows from a kill are still Beta's |
| R5 | **`prev_char` NULL marks a start of the program, not the first of a block** | The same as D11 | See D11 | See D11: ADR corrected |

Walked through and found sound, each by reopening a real database file: a cold profile; a step recorded but its script cut before any answer (the whole script is spoken again); one member of a pair answered (only the other's script is spoken); a quit in the middle of Phase A, B and C; a pair with one member ahead; a bar met and the app killed before the completion was written; a kill between a completion and the next phase's start; a day change; a changed voice (lengths start again, as designed); the window evicting rows a recorded phase was based on; a signal arriving during a write; and the two older database shapes `_migrate` refuses.

One note from pass 4 that is not a finding: `latency_ms` is not keyed by voice or rate, so after a change the speed baseline mixes both. Nothing fails at Alpha's fixed rate. It matters when Beta makes the rate adjustable.

### Pass 1: the engine against ADR-010, ADR-024 and ADR-027

Run on 2026-10-07 at commit `3eac0f2`. Every ADR number was checked against `config.py` and agrees. So do the slot gate, Known and its speed term, the milestone ladder, first-attempt counting, the phase bars and the need-based block plan.

| # | Finding | Evidence | Proposal | Outcome |
|---|---|---|---|---|
| E1 | **Ramp-up blocks are still mostly a fixed cycle.** ADR-024 property 1 says the previous prompt does not determine the next. Property 5 (no prompt follows itself) over two single-prompt units leaves only strict alternation, and the code keeps property 5. The roadmap entry "ADR-028's L-R interleave and ADR-024's unpredictability now disagree" says #12d removed the strict alternation; for Phase A it did not | Repro: a pair's Phase A is `k d k d k d`, each prompt the same as two earlier 100% of the time. A solo reach's Phase B (`j d e j d e`) was 89% in one block; the pass measured 99.7% over three languages and four seeds, and 73% to 80% for pair and Stage 0 reach steps | A decision, and it bears on #12h: its run sheet reads the dump's first-press accuracy by answer time as evidence of whether #12d's shuffled content stops pattern presses. For most of a ramp-up the content is not shuffled. Correct ADR-024's property 1 and the roadmap entry to say what is delivered, and decide whether more is wanted | **Open** |
| E2 | **A reach unit is never reversed in Phase B in a real session.** ADR-024 says a unit may be emitted in either direction. After `d e` the hand is off home, so only `d e` can follow, and the hand's position is carried from Phase A into Phase B | Repro: with Phase A's block really generated and answered, the next Phase B block is ten `(d, e)` and no `(e, d)`. The pass counted 0 of 320, and 0 of 960 for Stage 0. `test_rampup.py::test_both_directions_of_a_unit_are_used` passes because it writes Phase A's answers without generating Phase A's blocks, so the hand reads as home. This answers G16: the last two fallbacks of `_next_form` cannot be reached with any real inventory (34,520 selections, first loop only) | With E1. The test should generate Phase A as a session does, and then it fails; fix the test with whatever E1 decides | **Open** |
| E3 | **The first step's Phase C drills each letter against itself.** Each member's alphabet leaves out the other new letter, and `f` and `j` have no partners yet, so with real English the pool for `f` is `ff` alone | Repro with `WordfreqSource`: `fff jj fff jjj fff jjj ff jj`. About thirty presses each, mostly a key following itself, and those rows are in the window the anchor rung reads. With the test corpus, which has no `ff`, the same step alternates `f j f j`, which is what the session tests see | A decision. The ADR is silent on a step with no partners. Alternating the two members, as the test corpus happens to produce, looks like the intent. For #12h's ear either way | **Open** |
| E4 | **200 presses of one key in a day take away its Known until tomorrow.** Known's practice days are counted over the 200-row window (ADR-027's own query), and ADR-027 calls the days "a fact about the calendar". `config.py` says the window cannot be filled in one sitting | Repro on `SqliteStore`: `f` with three earlier days has 2 days in its window after 199 presses today and 1 after the 200th. It then needs a slot again, and the "waiting for a day" press does not apply because it was pressed this session. The pass measured `f` at 204 presses after Stage 0 in one sitting | A decision: count the days outside the window, or accept it. It can hold back the next letter for the rest of a long day | **Open** |
| E5 | **The introduction script's length is charged to the child's pace.** `next_block` stamps the time the block was built, and the session builds it right after queuing the script, so the first answer's gap includes the script. ADR-024: pace is measured over the gaps between answers | Repro: thirty answers at 2 s each give a next block of 50 prompts; with 12 s before the first answer, 42; with 25 s, 36 | Fix: the first answer of a block opens the pace measure and is not a gap. Small, with a test | **Open** |
| E6 | **A bar landed on exactly is decided by float rounding.** ADR-024 says a perfect run clears 90% after 9 presses | `accuracy_bound(9, 9)` is 0.8999999999999999, so it takes 10. `accuracy_bound(19, 19)` is 0.9500000000000001 and passes 95%. ADR-027's table agrees with the code | Change ADR-024's 9 to 10 | **Open** |
| E7 | **Stale sentences with no effect on behaviour.** ADR-010 lines 26 and 58 give Known as raw 90%; ADR-024 line 78 says bars are read "as best achieved"; ADR-024 line 181 puts `CONFIDENCE_Z` in `drills.py`, and line 175 of the same ADR says `key_state.py` | Line 181 against 175 checked; the others read by the pass | Correct the three | **Open** |

The handed-over questions: G16 is answered under E2. For G15, `stuck` in `phase2_slots` only feeds an error message, and the `<=` in `resume_step` cannot differ from `<` for a real step. `same_finger` in `_locate` matters for exactly one key per layout: without it `h` is located from `g` and not from `j`, and no test pins `h`. For D12, the `begin_step` returns-False branch cannot be reached with the shipped strategy.

### Pass 3: the loop, the speaker and the worker against the concurrency model

Run on 2026-10-07 at commit `3eac0f2`. Found to match: which thread owns what, no blocking call on the main thread but the frame wait, every deadline a clock comparison, the worker's cancellation in all three orders, stale finishes dropped by id, a failed utterance advancing like a completed one, PAUSED dropping keys and re-speaking on resume, and the startup and shutdown order.

| # | Finding | Evidence | Proposal | Outcome |
|---|---|---|---|---|
| C1 | **Shutdown never cancels speech.** It queues `Shutdown` behind whatever is speaking and joins for `WORKER_JOIN_SECONDS`. Quitting with more than two seconds of speech left holds the window open with the voice still talking, then abandons the worker | Repro on a real worker thread with a six-second utterance: `shutdown()` took 2.00 s and the engine's `stop` was never called | Stop the speaker before queuing `Shutdown`. Small, with a test | **Open** |
| C2 | **Events queued behind a quit in the same tick are still handled.** `_dispatch` returns on `Quit` and the drain loop carries on | Repro: `Quit`, a key press and a focus loss in one drain. The press is counted with its chime, and "Paused. Press Alt+Tab to come back to Takki." is queued. With C1 it is spoken during the join. Whether Windows sends a real focus loss beside the quit is #12h's | Stop draining once `running` is false. Small, with a test | **Open** |
| C3 | **The restart key can leave two letters outstanding.** `_on_restart` does not interrupt. If the unit's first letter has no measured length, it is sent as one that cannot be cut while the current letter is still sounding. ADR-012: the two are never outstanding together | Read: `session.py` `_on_restart`, then `_speak_prompt`'s uncuttable branch. The pass ran it: on the real source both letters wait at the worker and a 1,200 ms letter is stored as 1,400 ms; on the fake the first finish is dropped. It needs an earlier failed or cut letter, so it is unlikely | Interrupt in `_on_restart`, as every other path that abandons a prompt does. Small, with a test on the real source | **Open** |
| C4 | **`concurrency-model.md` describes letters as they were before #12l.** It says `play()` returns `int \| None` and that letters are never sequenced and do not make the speaker busy | Read: line 51 against `letters.py:22` and `speech.py` | Rewrite the paragraph from ADR-012, which was updated | **Open** |
| C5 | **Three smaller stale statements.** The roadmap entry "One cancellation window is narrowed rather than closed" describes a window that `clear_cancel` has since closed. The model says default tests never start a thread; four tests in `test_tts_worker.py` do. The model's worst tick of about 1.5 ms predates the 95 ms block boundary the roadmap records | Read: `sapi_tts.py` `speak`, `tts.py` `clear_cancel`, `test_tts_worker.py` lines 272 to 364 | Close the roadmap entry and correct the two sentences | **Open** |
| C6 | **The gate behind F1 and F4 is airtight and untested on the real worker.** `Speaker.letter()` is reached only through `_advance`, which holds while the speaker is busy; C3 is the one leak. But in the fifteen session tests that use the real letter source, no letter ever replaces an outstanding one | The pass changed the re-read key in memory to re-speak an open prompt at once: 172 of 172 tests passed. On the real source two taps over "Back in Takki." cancel the announcement | One test on `Harness(synthetic_letters=True)`: the re-read key during "Back in Takki." leaves the announcement whole. This settles F1 and F4 | **Open** |
| C7 | **Two residuals in the changes of 2026-10-07.** A signal between `start()`'s check and `running = True` is still lost, because `run()` tests only `running`. And `shutdown()` does its SQLite work first, so if that raises, the worker and the listener are not stopped (both threads are daemons, so the process still exits) | Read | `run()` also tests the stop flag; `shutdown()` stops the threads in a `finally` of its own | **Open** |

Not covered by pass 3, for #12h: SAPI and COM, real focus events, pynput on Windows, and `keys.stop()` straight after `keys.start()` on the early-return path.
