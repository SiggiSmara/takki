# Takki — Alpha Execution Plan

Session-by-session breakdown of [Alpha](roadmap.md#alpha--internaldev-only). Sequencing only — architecture is decided in [architecture.md](architecture.md) and the ADRs. This plan exists so each working session opens here, picks the next unchecked row, does exactly that chunk, commits, and closes.

**Working model:** one session = one chunk = one model = one commit. Strict dependency order; no parallel lanes. Each chunk is a vertical slice — `typing.Protocol` + real implementation + fake in `tests/fakes/` land together (per [ADR-019](adr/0019-testing-strategy-and-io-isolation.md), roadmap line 95). A chunk commits only on green tests.

**How to use this file**
1. Open the session table, find the first unchecked row.
2. Launch a Claude Code session with the **model** named in that row.
3. Implement only that chunk. Check the relevant carry-forward decisions first (see below).
4. Commit on green. Tick the box, fill in the commit SHA, close the session.
5. For Sonnet/Haiku chunks, run `/code-review` (medium/high effort) in-session before committing — same context, no separate review session. Escalate to an Opus pass only if it flags something structural.

**Model strategy.** Opus is reserved for the judgment chunks (the focus state machine and the engine core, #6–#10, plus Windows interpretation #12), where a subtle slip silently corrupts progression math or input handling. Everything else is specced tightly enough by the ADRs for Sonnet; scaffolding goes to Haiku. **Tripwire:** if a Sonnet chunk starts needing real architectural decisions mid-session, that is a signal the ADR underspecified it — stop, tighten the spec (or promote the chunk to Opus) rather than letting the model guess.

---

## Sessions

| # | Session | Model | Commits when | Spec | Done | Commit |
|---|---|---|---|---|---|---|
| 0 | CI + package skeleton — `.github/workflows/ci.yml` (tiers 1–3), flesh out `src/takki/` subpackages, one trivial green test. *(pyproject/markers/ruff/pyright/pre-commit and issue/PR/language-pack templates already exist — do not recreate)* | Haiku | CI green on trivial test | — | ☐ | |
| 1 | Platform interface — `PlatformInterface` Protocol + `DevStubInterface` + `FakePlatformInterface` + `Layout`/`PhysicalKey`/`Grapheme` dataclasses + `COL_TO_FINGER` + `select_platform_interface()`. Windows real impl deferred to #12 | Sonnet | stub + fake unit tests | [ADR-026](adr/0026-platform-interface-abstraction.md) | ☐ | |
| 2 | SQLite persistence — `profiles`, `key_stats`, `key_attempts` (rolling 200-attempt window), session log. Protocol + sqlite3 impl + fake | Sonnet | in-memory sqlite unit tests | [ADR-011](adr/0011-persistence-and-state.md), [ADR-027](adr/0027-key-and-accuracy-state-model.md) | ☐ | |
| 3 | wordfreq language layer — `WordSource` Protocol + `WordfreqSource` + `FixedListSource`; letter-freq ranking, bigram generator, layout-invariant finger map + per-language layout tables (promote spike code) | Sonnet | tests vs `FixedListSource` + real wordfreq (offline) | [ADR-007](adr/0007-language-data-word-frequency.md), [ADR-023](adr/0023-key-introduction-protocol.md) | ☐ | |
| — | **Spike: SAPI/espeak letter-name reliability + TTS interrupt** — feed the 26 isolated letters to pyttsx3+SAPI (Windows) and espeak (Linux); confirm letter names vs article sounds; test `stop()` mid-utterance. You run on Windows, Opus interprets. Resolves A1 and C12 | Opus + you | produces a decision (see carry-forward) | A1, C12 | ☐ | |
| 4 | Audio out — `TTSEngine` (pyttsx3/SAPI) + `RecordingTTS`; `SoundCuePlayer` (`PygameMixerCues`) + `RecordingCues`; sound-cue channel/voice-stealing policy | Sonnet | fake unit tests; real audio behind `audio` marker | [ADR-012](adr/0012-audio-feedback-design.md), spike | ☐ | |
| 5 | Keyboard stream — `KeyEventStream` Protocol + `PynputKeyStream` + `ScriptedKeyStream`; auto-reject on wrong key | Sonnet | `ScriptedKeyStream` unit tests | [ADR-005](adr/0005-keyboard-handling.md) | ☐ | |
| 6 | Focus model — always-on window + focus-gated dispatch + PAUSED state machine + keypress taxonomy; `FocusSource` Protocol + `PygameFocusSource` + `FakeFocusSource` | **Opus** | `FakeFocusSource` transition tests | [ADR-028](adr/0028-composite-input-and-keyboard-ownership.md) | ☐ | |
| 7 | Key & accuracy state model — Active/Known derivation, first-attempt counting, rolling-window queries | **Opus** | pure-logic unit tests | [ADR-027](adr/0027-key-and-accuracy-state-model.md) | ☐ | |
| 8 | Adaptive key introducer — home-row symmetric pairs → frequency-leader-per-hand, spoken intro script, pair handling | **Opus** | pure-logic unit tests | [ADR-023](adr/0023-key-introduction-protocol.md) | ☐ | |
| 9 | Drill generator — four-phase ramp-up, freq-weighted bigrams, rare-key re-exposure, pace-adaptive blocks | **Opus** | pure-logic unit tests | [ADR-024](adr/0024-drill-content-and-lesson-granularity.md), [ADR-028](adr/0028-composite-input-and-keyboard-ownership.md) | ☐ | |
| 10 | Progression thresholds + Bronze milestone detection | **Opus** | pure-logic unit tests | [ADR-010](adr/0010-lesson-structure-and-progression.md), [ADR-027](adr/0027-key-and-accuracy-state-model.md) | ☐ | |
| 11 | Session loop glue — wire all modules, signal handlers, runnable end-to-end on Linux against scripted I/O | Sonnet | scripted integration test green | — | ☐ | |
| 12 | Windows validation — real `WindowsPlatformInterface` (all four functions incl. `detect_screen_reader`), real pynput + window/focus, interactive Bronze run; close/reopen → progress restored | **Opus** (hands-on Windows) | manual run + platform smoke tests | — | ☐ | |

Sessions 7–10 are deliberately contiguous — four engine sessions in the same mental model, all Opus, all pure logic against the fakes that exist by then.

---

## Carry-forward decisions

Lock each before the session it gates. All are small (you + Opus); none needs a new ADR — they are amendments to existing ADRs or one-line scope notes.

| Decision | Gates | Question | Status |
|---|---|---|---|
| **A1** letter names | #3, #9 | Does SAPI/espeak say isolated letter *names* reliably, or do we reintroduce a per-language letter-name map (new scope vs [ADR-009](adr/0009-language-configuration.md))? | open — spike output |
| **C12** TTS interrupt | #4 | Relax the per-utterance interrupt rule on the SAPI path for Alpha, or drive SAPI to support cancellation? | open — spike output |
| **D** Escape | #6 | Tap/hold/double-tap disambiguation for reread-vs-restart, or two distinct keys? | open |
| **D** auto-advance | #9, #10 | Does a Layer-1 timeout *advance* or *re-prompt*, and does a timed-out prompt count in `attempt_count`? | open |
| **D** sound channels | #4 | pygame.mixer channel / voice-stealing policy so fast chimes don't pile up or drop | open |
| **D** Phase A/B counting | #9 | Confirm the differing counting models (A = 10 in succession, reset on error; B = 20 with ≤1 rejection) are intentional | open |
| **A4** pynput pin | #6 | Unpin `pynput` for a Linux-desktop dogfood path, or keep Windows as the only interactive target? Low urgency | open |

---

## Done criteria (from roadmap)

Alpha is done when the core-loop logic runs green on Linux against fakes/scripted I/O, **and** a dev can run a Bronze-level English drill session end-to-end on Windows — close the app, reopen, and see progress restored.
