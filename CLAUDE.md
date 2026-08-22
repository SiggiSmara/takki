# Takki — Claude Code Guide

Typing tutor for visually impaired children. Audio is the primary interface. See [docs/architecture.md](docs/architecture.md) for all design decisions and rationale.

## Non-negotiable rules

- **Never run `python` directly.** Always `uv run python` or `uv run pytest`. No exceptions.
- **Never `cd` before a command.** All commands run from the repo root. Use absolute or repo-relative paths.
- **All external I/O behind a `typing.Protocol`.** Lesson engine, intent pipeline, and progression logic depend on the Protocol, not the implementation. No direct calls to Piper, pynput, Whisper, `pygame`, etc. from logic code. The Windows-specific platform interfaces below are the most prominent case; the rule applies to every external interface. See ADR-019.
- **Tests use fakes by default.** Each Protocol ships with a fake implementation in `tests/fakes/`. Hardware- and model-dependent tests are gated by pytest markers (`audio`, `model`, `windows_only`, `slow`) and excluded from the default `uv run pytest`. See ADR-019.

## Development environment

- **Package manager:** `uv`. Use `uv add` / `uv run` / `uv sync`. Never use bare `pip install`.
- **Tests:** `uv run pytest`
- **Layout:** `src/` layout. All application source lives under `src/takki/`.
- **Primary dev machine:** Linux (headless box, SSH from Windows laptop).
- **Windows testing:** Spike scripts and platform-specific code are run manually on the Windows laptop. Write scripts here, run there, paste results back. Do not set up a separate Claude Code session on Windows — keep context here.

## Hard architectural constraints

These are decided. Do not introduce code that violates them without opening a discussion first.

- **Offline after install.** No network calls at runtime except the one-time Piper model download (with explicit user confirmation).
- **No elevated privileges.** Nothing that requires admin/UAC on Windows.
- **Audio first.** Every user-facing interaction must work without a visual display. The *visual content* is opt-in per child profile; the window itself is always created as the keyboard-focus anchor (ADR-016/ADR-028) and stays blank in audio-only mode.
- **Language-agnostic lesson engine.** No language-specific logic inside the lesson engine. All language inputs come from the language layer (wordfreq + config).
- **No LLM. Anywhere.** LLM integration is rejected entirely — no intent fallback, no word filtering, no encouragement generation, no lesson content. The intent pipeline is rule-based Layers 1–3 only (ADR-017). The Protocol boundary (ADR-019) is the fork path for anyone who wants one. See ADR-031 (supersedes ADR-004, ADR-018).
- **No backspace in lesson engine.** Wrong keypresses are auto-rejected. Backspace is disabled. See ADR-012.
- **Push-to-talk only.** The microphone is closed by default and opens only when the child presses the configurable talk key (default Right Ctrl). No wake word, no always-listening, no continuous transcription. See ADR-020.
- **YAML for all localisation.** Runtime UI strings, encouragement bank, intent definitions, and voice catalog are all per-language YAML files. No gettext, no `.po`/`.mo` workflow. See ADR-022.

## Platform interfaces

Four functions isolate all Windows-specific code. Implement these first; call them everywhere else.

```
get_system_language()   # Windows locale API → language code
get_layout_positions()  # Windows keyboard scan codes → Layout (keys + graphemes)
get_fallback_tts()      # pyttsx3 → SAPI
detect_screen_reader()  # SPI_GETSCREENREADER + process scan → reader id | None
```

Never call platform APIs directly from application logic. Always go through these interfaces.

## Key technology decisions

| Component | Choice | Notes |
|---|---|---|
| Speech recognition | `faster-whisper` | Local only. `tiny` and `base` both bundled in installer; auto-selected at startup by CPU microbenchmark (matmul < ~2ms → `base`, otherwise → `tiny`). Measured: `tiny` 230–800ms, `base` 400ms–1.5s depending on hardware and power state. `small` not bundled — 1.4s+ even on modern hardware, impractical without CUDA GPU. Triggered by push-to-talk (ADR-020). |
| Voice activity detection | `webrtcvad` | End-of-utterance only (push-to-talk supplies start). Tiny C extension, no ML runtime. See ADR-021. |
| TTS (primary) | Piper TTS | Confirmed on Windows (Python 3.11 MSVC). Load ~2.3s once, synthesis ~0.19s. |
| TTS (fallback) | pyttsx3 / SAPI | Always available on Windows, no install needed. |
| Keyboard capture | `pynput` | No elevated privileges needed on Windows. Push-to-talk key handled via same pipeline. |
| Localisation | YAML per language | UI strings, encouragement, intents, voice catalog — all YAML. No gettext. See ADR-022. |
| Language data | `wordfreq` | ~40 languages, bundled, no network. |
| Persistence | SQLite (`sqlite3`) | Built-in, single file, no server. |
| Audio cues | `pygame.mixer` | Immediate low-latency feedback. Initialised independently of display. |
| Visual display | `pygame.display` | Window always created as the keyboard-focus anchor (ADR-028); visual *content* rendered only if visual display enabled in profile. Headless/CI: `SDL_VIDEODRIVER=dummy`. |
| Distribution | PyInstaller | Must be built on Windows. Unsigned CI-built bundle ships as a GitHub pre-release from Beta; signing/Store distribution at V1 (see docs/research/windows-code-signing.md). |

## Project structure (target)

```
src/
  takki/
    platform/       # Windows-specific interface implementations
    language/       # wordfreq wrapper, word list, frequency data
    lesson/         # Layer controller, drill generator, word selector
    audio/          # TTS wrapper, sound cues, feedback generator
    persistence/    # SQLite schema and access
    display/        # pygame visual display (conditional) + focus source
    input/          # keyboard stream, keypress taxonomy
    voice/          # faster-whisper wrapper
    clock.py        # Clock Protocol + SystemClock — all timing is deadline checks
    config.py       # Global lesson progression thresholds, key bindings, compiled defaults
    focus_model.py  # ACTIVE/PAUSED FSM, focus-gated dispatch
docs/
  architecture.md
intents/            # Per-language intent definitions (lang.yaml)
tests/
CLAUDE.md
CONTRIBUTING.md
README.md
pyproject.toml
```

## Code style

- No comments unless the WHY is non-obvious (hidden constraint, workaround, subtle invariant).
- No docstrings beyond a single short line where genuinely needed.
- No error handling for things that cannot happen. Validate only at system boundaries.
- No premature abstraction. Three similar lines beats a helper that only exists for hypothetical reuse.

## Testing strategy

- Define a `typing.Protocol` for every external interface; concrete impls live in their domain module, fakes live in `tests/fakes/`.
- Default `uv run pytest` runs only fast deterministic tests against fakes. Slow tests opt in via markers.
- GitHub Actions runs the tiered pyramid: unit + integration + Windows platform smoke on every PR; slow integration nightly; PyInstaller on release tags.
- Headless audio/video on CI via `SDL_AUDIODRIVER=dummy` / `SDL_VIDEODRIVER=dummy`.
- Whisper and Piper models are cached in CI via `actions/cache`; integration tests against real models cost seconds after warm-up.
- **Assert exact event sequences and counts, not that something was emitted.** Session 6a shipped a bug — a backup focus poll cancelling real focus events — through a clean review and a full green suite, because the tests asserted an event was present rather than which events, in what order, and how many.
- See ADR-019 for the full pyramid, protocol catalog, and CI strategy.

## Open questions (resolve before implementing affected components)

1. ~~**Piper TTS native Windows support**~~ — **resolved.** Works natively on Windows (Python 3.11 MSVC). Model load ~2.3s (one-time), synthesis ~0.19s per phrase. ADR-003 stands.
2. ~~**`pygame.mixer` headless on Windows**~~ — **resolved.** Confirmed: mixer initialises (22050 Hz stereo) and plays audio with no display window. pygame 2.6.1 / SDL 2.28.4. *Update (2026-06-21, ADR-028): `pygame.display` is now initialised on every run — an always-on window is the keyboard-focus anchor (ADR-016). The window is blank in audio-only mode; headless dev and CI use `SDL_VIDEODRIVER=dummy`, stood in for by the `FocusSource` fake.*
3. ~~**Vocabulary coverage curve**~~ — **resolved.** Silver/Gold are key-count based (≥1/3 and ≥2/3 of language's full key set). Coverage displayed as motivating info only, computed over words ≥ 3 chars (aligns with Layer 2 floor; prevents single-letter articles skewing the number).
4. ~~**Minimum hardware spec**~~ — **resolved.** Requires AVX2; matmul benchmark >~10ms is below minimum for Whisper (Celeron-class hardware). `tiny` and `base` bundled in installer, auto-selected by matmul threshold (~2ms). See ADR-018 and ADR-002.
5. ~~**Model downloads under a child account**~~ — **resolved.** `tiny` + `base` bundled in installer; no runtime HuggingFace downloads for Whisper. English Piper voice always bundled; additional voices distributed as browser downloads via the project website (save to `Documents\Takki\voices\`). No in-app download logic. See ADR-015.
