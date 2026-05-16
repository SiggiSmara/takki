# Takki — Claude Code Guide

Typing tutor for visually impaired children. Audio is the primary interface. See [docs/typing_tutor_architecture.md](docs/typing_tutor_architecture.md) for all design decisions and rationale.

## Non-negotiable rules

- **Never run `python` directly.** Always `uv run python` or `uv run pytest`. No exceptions.
- **Never `cd` before a command.** All commands run from the repo root. Use absolute or repo-relative paths.

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
- **Audio first.** Every user-facing interaction must work without a visual display. The visual display (pygame window) is opt-in per child profile.
- **Language-agnostic lesson engine.** No language-specific logic inside the lesson engine. All language inputs come from the language layer (wordfreq + config).
- **No LLM for word filtering.** Explicitly decided against. See ADR-008.
- **No backspace in lesson engine.** Wrong keypresses are auto-rejected. Backspace is disabled. See ADR-012.

## Platform interfaces

Three functions isolate all Windows-specific code. Implement these first; call them everywhere else.

```
get_system_language()   # Windows locale API → language code
get_home_row_keys()     # Windows keyboard scan codes → list of characters
get_fallback_tts()      # pyttsx3 → SAPI
```

Never call platform APIs directly from application logic. Always go through these interfaces.

## Key technology decisions

| Component | Choice | Notes |
|---|---|---|
| Speech recognition | `faster-whisper` | Local only. `base` model default. CPU viable (~500–800ms). |
| TTS (primary) | Piper TTS | Native Windows support TBD — spike required before finalising. |
| TTS (fallback) | pyttsx3 / SAPI | Always available on Windows, no install needed. |
| Keyboard capture | `pynput` | No elevated privileges needed on Windows. |
| Language data | `wordfreq` | ~40 languages, bundled, no network. |
| Persistence | SQLite (`sqlite3`) | Built-in, single file, no server. |
| Audio cues | `pygame.mixer` | Immediate low-latency feedback. Initialised independently of display. |
| Visual display | `pygame.display` | Conditional — only initialised if visual display enabled in profile. |
| Distribution | PyInstaller | Must be built on Windows. |

## Project structure (target)

```
src/
  takki/
    platform/       # Windows-specific interface implementations
    language/       # wordfreq wrapper, word list, frequency data
    lesson/         # Layer controller, drill generator, word selector
    audio/          # TTS wrapper, sound cues, feedback generator
    persistence/    # SQLite schema and access
    display/        # pygame visual display (conditional)
    voice/          # faster-whisper wrapper
    config.py       # Global lesson progression thresholds
docs/
  typing_tutor_architecture.md
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

## Open questions (resolve before implementing affected components)

1. ~~**Piper TTS native Windows support**~~ — **resolved.** Works natively on Windows (Python 3.11 MSVC). Model load ~2.3s (one-time), synthesis ~0.19s per phrase. ADR-003 stands.
2. ~~**`pygame.mixer` headless on Windows**~~ — **resolved.** Confirmed: mixer initialises (22050 Hz stereo) and plays audio with no display window. `pygame.display` never touched. pygame 2.6.1 / SDL 2.28.4.
3. ~~**Vocabulary coverage curve**~~ — **resolved.** Silver/Gold are key-count based (≥1/3 and ≥2/3 of language's full key set). Coverage displayed as motivating info only, computed over words ≥ 3 chars (aligns with Layer 2 floor; prevents single-letter articles skewing the number).
4. **Minimum hardware spec** — affects default Whisper model recommendation.
