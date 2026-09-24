# ADR-019: Testing Strategy and I/O Isolation

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** All external-world interfaces are defined as `typing.Protocol` classes. Application logic depends on the Protocol, never on the concrete implementation. Tests use fake implementations by default. Hardware- and model-dependent tests are isolated via pytest markers and run on dedicated CI tiers via GitHub Actions.

### Rationale

The project has many awkward-to-test dependencies: Piper TTS (model download, Windows-confirmed), `faster-whisper` (model download, audio in), `pynput` (keyboard hardware), `pygame.mixer` (sound card), Windows locale and keyboard APIs (Windows-only). Without architectural discipline, testing the lesson engine, intent pipeline, and progression rules would require setting up these dependencies — slow, flaky, and incompatible with the headless Linux dev environment.

The fix is to push every external interface behind a `Protocol` boundary. The pattern is already proven by the three Windows-specific platform interfaces (ADR-005, ADR-006, ADR-013) — this ADR generalises it to every external interface in the system.

`typing.Protocol` is preferred over abstract base classes:
- No inheritance required — implementations are structurally typed
- No mocking framework overhead — fakes are trivial Python classes
- Static type checkers verify conformance
- The plugin architecture (optional cloud TTS in the component overview, downstream fork adapters) naturally drops in as alternative Protocol implementations

### Protocol Catalog

Each protocol is introduced when its consuming component is first built. Real implementations live in their domain module (`src/takki/audio/`, `src/takki/voice/`, etc.). Fakes live in `tests/fakes/`.

| Protocol | Real implementation(s) | Fake |
|---|---|---|
| `TTSEngine` | `PiperTTS`; `SapiTTS` (Windows fallback, SAPI driven directly); `FallbackTTS` (pyttsx3/espeak, the Linux dev path only — ADR-003) | `FakeTTSEngine` |
| `SoundCuePlayer` | `PygameMixerCues` | `FakeSoundCues` |
| `KeyEventStream` | `PynputKeyStream` | `ScriptedKeyStream` |
| `VoiceTranscriber` | `WhisperTranscriber` | `ScriptedTranscriber` |
| `WordSource` | `WordfreqSource` | `FixedListSource` |
| `Clock` | `SystemClock` | `FakeClock` |
| `HardwareProbe` | `RealHardwareProbe` | `FixedHardwareProbe` |
| `FocusSource` | `PygameFocusSource` (always-on SDL window; emits foreground gained/lost, handles re-acquire requests) | `FakeFocusSource` |

`HardwareProbe` runs the CPU microbenchmark that auto-selects the Whisper model (ADR-002). An `LLMRunner` Protocol was originally catalogued here; it was removed with LLM integration ([ADR-031](0031-no-llm-integration.md)).

The platform functions bundled in `PlatformInterface` (`get_system_language`, `get_layout_positions`, `find_voice`, `get_fallback_tts`, and `detect_screen_reader` — ADR-026) are the Windows-specific instances of this same pattern.

**The Protocol boundary is also the plugin boundary.** Any third-party or community-contributed alternative — a different TTS engine, an alternative wake-word handler, a cloud-LLM adapter forked downstream — is a new Protocol implementation drop-in. There is no separate plugin framework; the Protocol set above is the public extension surface.

### Test Pyramid

Default `uv run pytest` runs only Tiers 1 and 2 — fast, deterministic, no models, no hardware.

| Tier | Scope | Where | Trigger | Cost |
|---|---|---|---|---|
| 1. Unit | Logic against fakes — lesson engine, progression rules, intent layers 1–3, milestone gates, encouragement selection | Linux | every PR | seconds; ~80% of suite |
| 2. Integration (stubbed I/O) | SQLite in-memory, `wordfreq` for 2 languages, pygame headless, Whisper on WAV fixtures. *(pyttsx3+espeak is `audio`-marked and runs on the dev box only.)* | Linux | every PR | ~1 minute |
| 3. Platform smoke | Windows platform interfaces (every shipped keyboard layout, via `LoadKeyboardLayout`), `pynput`, pyright's Windows pass with Windows dependencies installed, `pygame.mixer` cues, the no-audio-output startup refusal, Piper. **Not SAPI speech** — a runner has no audio output; see § Headless audio/video | `windows-latest` | every PR | a few minutes |
| 4. Slow integration | Full Whisper corpus, all `wordfreq` languages | matrix | nightly | longer; off critical path |
| 5. Release | PyInstaller bundle + `.exe` smoke test | `windows-latest` | on tag (from Beta pre-releases onward — the unsigned bundle ships in Beta per [roadmap.md](../roadmap.md)) | rare |

Pytest markers control inclusion: `audio`, `model`, `windows_only`, `slow`, `release`. `pyproject.toml` declares them so they're recognised. Default invocation:

    uv run pytest -m "not (audio or model or windows_only or slow or release)"

### GitHub Actions Strategy

CI covers the bits Linux dev cannot:

- **OS matrix.** `windows-latest` runs platform smoke tests every PR. `ubuntu-latest` runs the bulk of the suite. No macOS runner until ADR-006 scope expands.
- **Model caching.** `actions/cache` keyed on Piper and Whisper model URLs. First run downloads; subsequent runs hit cache. Integration tests against real models cost seconds after warm-up.
- **Headless audio/video.** `SDL_AUDIODRIVER=dummy` and `SDL_VIDEODRIVER=dummy` let `pygame` initialise without a sound card or display. Catches code-path regressions; humans verify quality.

  **Amendment (2026-09-20, pre-alpha-session-12a review): the dummy drivers plus the excluded `audio` marker left a hole that hid a mute-on-first-utterance bug for three months, and this is what it cost.** Both CI jobs exclude `audio`, and `windows-latest` sets `SDL_VIDEODRIVER=dummy`, so no job on any platform had ever run the real SAPI engine, the pyttsx3-on-a-worker-thread path, or a real window. The first hand-run of `uv run pytest -m audio` on the Windows laptop — 2026-09-20, eleven green sessions in — **failed**: `TestTTSWorkerWithRealEngine::test_real_thread_start_and_join` never receives its `SpeechFinished`, because a SAPI engine constructed on one thread and spoken from another never returns from `runAndWait()` — the finished-event is delivered to the creating thread's message queue and the worker pumps its own, so it waits forever (mechanism and proof in [concurrency-model.md § The engine belongs to the thread that creates it](../concurrency-model.md)). It is the arrangement `main.py` uses, so Takki would have been mute on its first utterance on the only platform it ships to.

  Three things this changes for the strategy. (1) and (2) are alpha session 12a-1's, alongside the layout reader; (3) is a lesson rather than a task. (1) **A tier that never runs is not a tier.** `audio` was declared in tier 2 of the pyramid and executed nowhere; the marker documented an intention. Decide what a GitHub runner can actually execute — `windows-latest` has SAPI voices installed and no sound card, which is enough for `runAndWait()` to complete against the null device — and if the answer is "it can", the marker stops being opt-out-by-default in CI. (2) **The dummy video driver is not free either.** The two `windows_only` focus tests construct a dummy-driver window, so nothing has exercised a real one; a second `windows-latest` job without `SDL_VIDEODRIVER` is the cheap half of the fix. (3) **Fakes cannot catch thread affinity.** `FakeTTSEngine` appends to a list; it has no COM event sink and no message queue, so it behaves identically whichever thread built it and whichever thread calls it. Every default-tier test therefore passes under an arrangement the real engine rejects, and no amount of fake fidelity would have helped — the property that breaks is one a fake does not have. That is the generalisable lesson and not a reason to weaken Protocol+fake: it is a reason the marker-gated tiers must actually execute somewhere on a schedule, because they are the only thing that tests the half of a real implementation a fake cannot model. The type-checking version of this same blind spot was closed the same week — pyright had inferred its platform from the host and so had never checked a line of Windows code; pre-commit now runs it for both platforms explicitly.

  **Follow-up (2026-09-20, alpha session 12a-2).** Running `-m audio` by hand a second time, after the thread-affinity fix, found a *worse* defect the first run had masked: SAPI truncating every utterance after the first, which no test asserted because every existing `audio` test spoke a single letter and a letter is shorter than the cutoff. Two consequences for this strategy. (a) **The `audio` tier now asserts durations, not absence of exceptions.** `tests/test_sapi_tts.py` speaks a 15-word line as a second, third and fourth utterance and fails if any returns early; the previous tests (`speak("a")` does not raise) would pass against an engine that spoke nothing at all. **And the assertion is a bracket, not a floor** — a lower bound alone went green against an utterance the engine had *abandoned* after 60 s, since 60 satisfies "longer than 3.5". A duration test needs both ends or it reports working speech on a silent machine, which is the same false green one level up from the one this amendment is about. This is the same lesson as session 6a's, one layer down — assert what was produced, not that something was. (b) **Part (1) above is asked, not answered.** `.github/workflows/ci.yml` gained a `windows-audio-probe` job that runs `-m audio` with `continue-on-error: true`, plus a step printing the runner's installed voice tokens. The guess recorded above — that `windows-latest` has SAPI voices and no sound card, "which is enough for `runAndWait()` to complete against the null device" — is still a guess, and `SapiTTS` no longer uses `runAndWait()` at all, so it does not even describe the current path. **Read the first run of that job, then either make it blocking or delete it and record here that the tier is laptop-only.** A probe left permanently on `continue-on-error` is the same thing as a tier that never runs.

  **A third instance of the same blind spot, found by the first push (2026-09-20).** `pyright --pythonplatform Windows` **run on Linux cannot resolve Windows-only dependencies**, because they are not installed there. `comtypes` is `sys_platform == 'win32'` in `pyproject.toml`, so the Linux CI job's Windows pass failed with two `reportMissingImports` errors on `src/takki/audio/sapi_tts.py` — a file that had been green in both passes on the Windows laptop, where comtypes *is* installed. The flag says Windows; the environment is still Linux, and the two are independent. Fixed with targeted `# pyright: ignore[reportMissingImports]` on the two imports, verified by hiding the installed package and re-running (0 errors, down from 2). **But the suppression is not the interesting part — the residue is.** Where an import cannot resolve, pyright degrades that module to `Unknown` and type-checks nothing through it: every call into `comtypes` in that file reports as an unknown-member *warning* rather than being checked. So **the Windows pass on Linux is strictly weaker than the same pass on Windows**, and a real type error in Windows-only code reached through a Windows-only dependency would pass CI. This is the same shape as the two failures above — a check that appears to cover a platform and does not — and it was invisible on the laptop for the same structural reason the `audio` tier was: the developer's machine has the thing CI lacks. `pynput` hides the equivalent problem only by luck, because pyright bundles stubs for it and so downgrades it to `reportMissingModuleSource`. **The fix that would actually close it is to run pyright on the `windows-latest` job too**, where the Windows-only dependencies are installed — cheap, and the only arrangement in which the Windows pass checks what it claims to. Not done here; decide it with the `windows-audio-probe` question, since both are "what can a runner actually prove".

  **The probe's first run, and it did not fail — it hung (2026-09-20).** Partial answer, and the partial part is the useful part. `pygame.mixer` cue tests **pass** on a `windows-latest` runner under `SDL_AUDIODRIVER=dummy`, so the mixer half of the `audio` tier is runnable in CI. The TTS half never got an answer, because the job stalled on `tests/test_fallback_tts.py::TestFallbackTTS::test_speak_does_not_raise` — the first test that actually speaks — and was cancelled by hand at 8.5 minutes. Engine *construction* had passed; `runAndWait()` simply never returned. With no usable audio endpoint SAPI accepts the text and never fires the completion event pyttsx3's loop is polling for, which is the same "waiting at a mailbox nothing is delivered to" shape as § The engine belongs to the thread that creates it, arriving by a different route.

  **Two defects, one of them in shipped code.** (1) Those tests exercise `FallbackTTS`, which is the *Linux dev path* (ADR-003) — running them on Windows tested a path Takki does not ship, and they now skip there. (2) **`SapiTTS.speak()` had the same unbounded wait**, so the identical hang was reachable in production by a child unplugging a USB headset mid-utterance: the TTS worker would never return, no `SpeechFinished` would ever be posted, the core's `Speaker` would stay busy and the loop would stop issuing prompts — the app silently inert, which is the worst failure this project has. It now abandons an utterance after 60 s (8× the longest thing the curriculum says) and logs. **A hardware-boundary timeout is not error handling for something that cannot happen**, which is the rule this would otherwise sit awkwardly against; CI demonstrated it happening.

  **That is the strongest argument yet for the tier existing.** A GitHub runner is not a worse version of the laptop — it is a machine with *different* hardware missing, and it therefore reaches states the laptop cannot. The probe is now bounded (`timeout-minutes: 10`) so asking the question can never again cost a job slot.

  **Answered on the fourth run (2026-09-20). A GitHub runner cannot execute the TTS half of this tier, and the reason is worth more than the verdict.** It does not hang and it does not quietly pass: `SpVoice::Speak` raises `_ctypes.COMError 0x8004503A`, a SAPI-private HRESULT for which Windows has no description. Exactly where it fires is the informative part. `installed_voices()` on the runner returns `{'en': ...TTS_MS_EN-US_DAVID_11.0}`, so **the voice token exists and resolves**; `SapiTTS.__init__` succeeds, so **COM initialises, the MTA is granted, and the token is applied**; and only then does the first `Speak` fail. So this is an **audio-output** failure, not a voice or COM-apartment failure: `windows-latest` has SAPI and no device to render to, and `SDL_AUDIODRIVER=dummy` does nothing for SAPI, which does not go through SDL.

  **The runs before it were consumed by defects in the test file, not by the question**, and that is its own lesson about probes. Run 1 hung on `FallbackTTS` (the Linux dev path, now skipped on Windows). Run 2 failed slowly and said nothing: `_voice()` ran on the *worker* thread, where `pytest.skip()` raises and kills the thread rather than skipping. Run 3 failed fast twice then stalled two minutes: a worker dying before `handle.put(engine)` left the main thread on a queue nothing could reach. Only run 4 — with `-x --tb=long`, because pytest prints failures at the *end* and no earlier run had got there — showed the exception. **An earlier reading of runs 1-3 concluded "durations are not portable, split the `audio` marker"; it was wrong, and acting on it would have encoded a guess into the test taxonomy.**

  **What this tier can and cannot prove in CI, then.** The `pygame.mixer` cue tests pass on a runner and should become a blocking check. The SAPI tests cannot run there at all, and no marker split rescues them — it is not that timing is unreliable, it is that `Speak` raises. They stay laptop-only, and the honest record is that **`tests/test_sapi_tts.py` is verified by hand on Windows hardware and by nothing else**.

  **And the probe found a bug in shipped code, which is the strongest argument for having run it.** `SapiTTS.speak()` raising propagates through `TTSWorker.run_one()` and out of `run()`, **killing the TTS worker thread** — no `SpeechFinished` is ever posted, the core's `Speaker` stays busy, the loop stops issuing prompts, and Takki is silently inert. That is the *third* route to that same failure this session has found (construction, the unbounded wait, and now an exception mid-run), and the first two are fixed while this one is not. It is reachable off a runner: any Windows machine with a voice in the registry and no usable output — a disabled device, a disconnected Bluetooth headset, an RDP session — passes `find_voice()` at startup and then raises on every utterance. **The fix is that no engine exception may kill the worker**: catch around `engine.speak()`, log, and post the `SpeechFinished` the core is waiting for, so the child loses that utterance rather than the whole session. Startup should arguably also prove the voice can *speak* rather than merely exist, since `find_voice()` is a registry read and cannot see this.

  **Closed (2026-09-24, alpha session 12a-2).** What was left open above is now decided and built, and the probe job is gone — a question answered is not a reason to keep asking it.
  - **The worker survives any engine exception.** `TTSWorker.run_one()` catches around `engine.speak()`, logs, and posts `SpeechFinished(id, "failed")` — a third status, so the event says what happened rather than calling an unheard utterance `completed`; a cancel outranks it. `SapiTTS`'s 60 s abandon now *raises* `SpeechOutputError` for the same reason, instead of returning into a `completed`. Pinned by `tests/test_tts_worker.py::TestTTSWorkerSurvivesEngineFailure` and `tests/test_session.py::TestSpeechEvents::test_a_failed_utterance_does_not_stall_the_session`, all four of which fail against the old worker.
  - **Startup proves the voice can sound, and stops if it cannot.** "Arguably" was settled as *critical*: an audio-first app with no audio has nothing to offer. `SapiTTS` construction speaks one letter at volume 0 and maximum rate through a second `SpVoice` (so the voice Takki speaks through is never left silent), turns a `COMError` or a 10 s non-completion into `SpeechOutputError`, and `TTSWorker.start()` already carries build failures back to `main()`, which exits `EXIT_NO_AUDIO` (4) with the remedy on stderr. Nothing short of speaking can tell — the runner showed the failure arrives only at `Speak`. Cost measured on the laptop: 0.58 s, once, before the loop.
  - **The runner's missing device is now a test, not an obstacle.** `tests/test_no_audio_output.py`, marker `no_audio_output`, drives the production path (`get_fallback_tts` → `TTSWorker.start()`) and asserts `SpeechOutputError`. It runs only on `windows-latest`, the one machine that reproduces "a voice and no output"; on the laptop it fails by design (`DID NOT RAISE`), which is also the proof the check passes a healthy machine. **If it ever fails on the runner, GitHub gave the runner a sound device** — the test has lost its machine, not found a bug.
  - **CI's Windows job now proves what a runner can:** the `pygame.mixer` cue tests (blocking), pyright's Windows pass with comtypes installed (closing the "third instance" above), and the startup refusal. **`tests/test_sapi_tts.py` is verified by hand on Windows hardware and by nothing else**, and that is the permanent answer, not a gap awaiting a runner.
  - **A fourth instance of the pattern, found while closing this.** `tests/conftest.py` forced the dummy SDL drivers on every test not marked `audio`, so `test_pygame_focus_source.py`'s two `…_on_a_real_driver` tests had **never opened a real window anywhere, the laptop included**; part (2) of the first amendment was unreachable even by hand. `windows_only` now opts out as `audio` does. CI still sets dummy at job level, so a real window remains laptop-verified — [windows-validation.md](../research/windows-validation.md) T0.2 and tier E.
- **Synthetic audio fixtures.** A small WAV corpus committed to the repo covers common intents in each Beta-supported language. Whisper transcription is deterministic given a fixed model and fixed input — accuracy regressions on Whisper version bumps are visible.

  *Source of the corpus:* the fixtures are generated by TTS (Piper at varied rates and voices) and supplemented with adult-recorded clips read by maintainers and contributors. We do **not** collect or commit recordings of children's speech — both for ethical reasons and because we have no consent framework that could make it appropriate. The synthetic corpus catches regressions in transcription and intent resolution, but it does not represent the variability of real child speech. Evaluating recognition quality on actual children is therefore deferred to the Beta friends/family pilot, where informed parental consent and an appropriate testing protocol can be arranged per family.

### What CI Cannot Verify

- Audio quality and naturalness of Piper voices
- Keyboard latency feel
- Whether intent recognition resolves well on real child speech (high variability, disfluencies)
- Visual display readability across vision conditions
- SAPI speech of any kind — hosted runners have a voice and no audio output (§ Headless audio/video). Verified on Windows hardware by `-m audio`
- A real SDL window and real focus transitions — CI runs the dummy video driver. Verified on Windows hardware by `-m windows_only` and the hand-run protocol

These require human testing. The Beta friends/family pilot in [roadmap.md](roadmap.md) is the venue.

### Alternatives Considered

- **Mocking framework (`unittest.mock` patching):** Rejected. Encourages patching at import time, which leaves real implementations available as accidental coupling vectors. Protocol+fake is more explicit and works with static type checking.
- **Dependency injection container:** Rejected. Overkill at this codebase size. Direct constructor injection of Protocol implementations is sufficient.
- **No isolation, real I/O in tests:** Rejected. Slow tests get skipped; skipped tests rot.
- **Abstract base classes instead of Protocols:** Rejected. Forces inheritance, blocks structural typing, more verbose for no benefit.
