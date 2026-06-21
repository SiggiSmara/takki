# ADR-019: Testing Strategy and I/O Isolation

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** All external-world interfaces are defined as `typing.Protocol` classes. Application logic depends on the Protocol, never on the concrete implementation. Tests use fake implementations by default. Hardware- and model-dependent tests are isolated via pytest markers and run on dedicated CI tiers via GitHub Actions.

### Rationale

The project has many awkward-to-test dependencies: Piper TTS (model download, Windows-confirmed), `faster-whisper` (model download, audio in), `pynput` (keyboard hardware), `pygame.mixer` (sound card), Windows locale and keyboard APIs (Windows-only), `llama-cpp-python` (GB-scale models). Without architectural discipline, testing the lesson engine, intent pipeline, and progression rules would require setting up these dependencies — slow, flaky, and incompatible with the headless Linux dev environment.

The fix is to push every external interface behind a `Protocol` boundary. The pattern is already proven by the three Windows-specific platform interfaces (ADR-005, ADR-006, ADR-013) — this ADR generalises it to every external interface in the system.

`typing.Protocol` is preferred over abstract base classes:
- No inheritance required — implementations are structurally typed
- No mocking framework overhead — fakes are trivial Python classes
- Static type checkers verify conformance
- The plugin architecture (LLM, optional cloud TTS in component overview) naturally drops in as alternative Protocol implementations

### Protocol Catalog

Each protocol is introduced when its consuming component is first built. Real implementations live in their domain module (`src/takki/audio/`, `src/takki/voice/`, etc.). Fakes live in `tests/fakes/`.

| Protocol | Real implementation(s) | Fake |
|---|---|---|
| `TTSEngine` | `PiperTTS`, `FallbackTTS` (pyttsx3/SAPI) | `RecordingTTS` |
| `SoundCuePlayer` | `PygameMixerCues` | `RecordingCues` |
| `KeyEventStream` | `PynputKeyStream` | `ScriptedKeyStream` |
| `VoiceTranscriber` | `WhisperTranscriber` | `ScriptedTranscriber` |
| `WordSource` | `WordfreqSource` | `FixedListSource` |
| `Clock` | `SystemClock` | `FakeClock` |
| `LLMRunner` | `LlamaCppRunner` | `ScriptedLLMRunner` |
| `HardwareProbe` | `RealHardwareProbe` | `FixedHardwareProbe` |
| `FocusSource` | `PygameFocusSource` (always-on SDL window; emits foreground gained/lost, handles re-acquire requests) | `FakeFocusSource` |

The platform functions bundled in `PlatformInterface` (`get_system_language`, `get_layout_positions`, `get_fallback_tts`, and `detect_screen_reader` — ADR-026) are the Windows-specific instances of this same pattern.

**The Protocol boundary is also the plugin boundary.** Any third-party or community-contributed alternative — a different TTS engine, an alternative wake-word handler, a cloud-LLM adapter forked downstream — is a new Protocol implementation drop-in. There is no separate plugin framework; the Protocol set above is the public extension surface.

### Test Pyramid

Default `uv run pytest` runs only Tiers 1 and 2 — fast, deterministic, no models, no hardware.

| Tier | Scope | Where | Trigger | Cost |
|---|---|---|---|---|
| 1. Unit | Logic against fakes — lesson engine, progression rules, intent layers 1–3, milestone gates, encouragement selection | Linux | every PR | seconds; ~80% of suite |
| 2. Integration (stubbed I/O) | SQLite in-memory, `wordfreq` for 2 languages, pyttsx3+espeak, pygame headless, Whisper on WAV fixtures | Linux | every PR | ~1 minute |
| 3. Platform smoke | Windows platform interfaces, `pynput`, Piper, SAPI | `windows-latest` | every PR | a few minutes |
| 4. Slow integration | Full Whisper corpus, all LLM tiers, all `wordfreq` languages | matrix | nightly | longer; off critical path |
| 5. Release | PyInstaller bundle + `.exe` smoke test | `windows-latest` | on tag | rare |

Pytest markers control inclusion: `audio`, `model`, `windows_only`, `slow`, `release`. `pyproject.toml` declares them so they're recognised. Default invocation:

    uv run pytest -m "not (audio or model or windows_only or slow or release)"

### GitHub Actions Strategy

CI covers the bits Linux dev cannot:

- **OS matrix.** `windows-latest` runs platform smoke tests every PR. `ubuntu-latest` runs the bulk of the suite. No macOS runner until ADR-006 scope expands.
- **Model caching.** `actions/cache` keyed on Piper, Whisper, and LLM model URLs. First run downloads; subsequent runs hit cache. Integration tests against real models cost seconds after warm-up.
- **Headless audio/video.** `SDL_AUDIODRIVER=dummy` and `SDL_VIDEODRIVER=dummy` let `pygame` initialise without a sound card or display. Catches code-path regressions; humans verify quality.
- **Synthetic audio fixtures.** A small WAV corpus committed to the repo covers common intents in each Beta-supported language. Whisper transcription is deterministic given a fixed model and fixed input — accuracy regressions on Whisper version bumps are visible.

  *Source of the corpus:* the fixtures are generated by TTS (Piper at varied rates and voices) and supplemented with adult-recorded clips read by maintainers and contributors. We do **not** collect or commit recordings of children's speech — both for ethical reasons and because we have no consent framework that could make it appropriate. The synthetic corpus catches regressions in transcription and intent resolution, but it does not represent the variability of real child speech. Evaluating recognition quality on actual children is therefore deferred to the Beta friends/family pilot, where informed parental consent and an appropriate testing protocol can be arranged per family.

### What CI Cannot Verify

- Audio quality and naturalness of Piper voices
- Keyboard latency feel
- Whether intent recognition resolves well on real child speech (high variability, disfluencies)
- Visual display readability across vision conditions

These require human testing. The Beta friends/family pilot in [roadmap.md](roadmap.md) is the venue.

### Alternatives Considered

- **Mocking framework (`unittest.mock` patching):** Rejected. Encourages patching at import time, which leaves real implementations available as accidental coupling vectors. Protocol+fake is more explicit and works with static type checking.
- **Dependency injection container:** Rejected. Overkill at this codebase size. Direct constructor injection of Protocol implementations is sufficient.
- **No isolation, real I/O in tests:** Rejected. Slow tests get skipped; skipped tests rot.
- **Abstract base classes instead of Protocols:** Rejected. Forces inheritance, blocks structural typing, more verbose for no benefit.
