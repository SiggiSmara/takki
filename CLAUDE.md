# Takki — Claude Code Guide

Typing tutor for visually impaired children. Audio is the primary interface. See [docs/architecture.md](docs/architecture.md) for all design decisions and rationale.

## Non-negotiable rules

- **Never run `python` directly.** Always `uv run python` or `uv run pytest`. No exceptions.
- **Never `cd` before a command.** All commands run from the repo root. Use absolute or repo-relative paths.
- **Commits belong to the developer.** Never commit, push, amend, reset or rebase unless the developer's own message asks for that exact operation. Prepare the changes and report them; the developer reads them first. A "yes" to a question that bundles a commit with something else is not approval to commit.
- **Ask questions in plain chat, one at a time.** Never use the multiple-choice question box (AskUserQuestion). The developer often needs follow-up questions or more context before answering, and a choice box leaves no room for that. Give each question its context: what you found, why it matters, what the answer changes, and your recommendation if you have one. Wait for the answer before asking the next.
- **Code review: propose, then one pass.** At the review step, propose the level and the model with a reason, and wait for the developer's go. `high` is the ceiling, never `max`. Docs-only changes get no `/code-review`. Review agents always run on Sonnet (`CLAUDE_CODE_SUBAGENT_MODEL` in `.claude/settings.json`); never switch it, it is only read when a session starts.
  - **Sonnet review:** `/code-review <level>` in the coding session. One per developer message; a hook enforces it (`.claude/hooks/review_limit.py`).
  - **Opus review:** no subagents. The coding session prints in chat, in full, a prompt for a new Opus session: what changed and why, the ADRs that govern it, how to see the diff (uncommitted changes, untracked files included), and what is out of scope. That session reviews alone: it starts no agents and edits nothing, since it shares the working tree. It ends with a handover the developer pastes back: findings ranked, each with `file:line`, the failing scenario, and its kind — bug, judgment call for the developer, or wording. The coding session makes the fixes, handing a larger one to a subagent only when that helps. When the fixes are more than trivial, it then reviews them with `/code-review` on Sonnet in the same turn, without asking again; never another Opus session.
  - **After either:** fix the bugs, bring judgment calls to the developer, list wording points without acting on them. Then stop and report what was found and fixed, what was left and why, and whether another pass is worth its cost. The developer decides. Done means green tests and one pass, never "clean"; "re-run until clean" in an older prompt means one pass and this report.
- **ADRs state the current design.** A session implements from an ADR, so it must read as what holds now, not as a history.
  - **An amendment replaces the text it changes.** Never append a dated note beside the old text, and never leave text marked superseded, retired or withdrawn.
  - **History goes in one place:** a change list at the end of the ADR, one line per change with the date, the session and what changed. The reasoning goes in the commit message.
  - **A rejected alternative is kept, once,** with its reason, so that a later session does not propose it again.
  - **A change of direction is a new ADR** that supersedes the old one, not a restatement inside it.
  - Older ADRs still carry dated notes. Do not rewrite them in passing; that is a session of its own for each ADR, after the Windows re-validation run (alpha-plan #12h).
- **All external I/O behind a `typing.Protocol`.** Lesson engine, intent pipeline, and progression logic depend on the Protocol, not the implementation. No direct calls to Piper, Whisper, `pygame`, SAPI, etc. from logic code. The Windows-specific platform interfaces below are the most prominent case; the rule applies to every external interface. See ADR-019.
- **Tests use fakes by default.** Each Protocol ships with a fake implementation in `tests/fakes/`. Hardware- and model-dependent tests are gated by pytest markers (`audio`, `model`, `windows_only`, `slow`, `no_audio_output`) and excluded from the default `uv run pytest`. `no_audio_output` runs only on the `windows-latest` runner, which has a voice and no audio device, and fails on a machine that can play sound. See ADR-019.

## Development environment

- **Package manager:** `uv`. Use `uv add` / `uv run` / `uv sync`. Never use bare `pip install`.
- **Tests:** `uv run pytest`
- **Layout:** `src/` layout. All application source lives under `src/takki/`.
- **Primary dev machine:** Linux (headless box, SSH from Windows laptop) — for everything that is not OS-specific.
- **Where a chunk is developed follows what it touches.** The OS-specific code is deliberately confined behind Protocols so the other ~90% of the codebase is portable and stays here (see *Platform interfaces* below, ADR-019, ADR-026). But **implementing those platform stubs, and anything whose behaviour only exists on the target OS, is developed on that OS** — you cannot write `ctypes.windll` scan-code mapping, SAPI/COM threading, real focus transitions, or the window's live key events against a machine that can run none of them. Writing blind and pasting results back is for *spikes* — a script, one question, one answer. It is not a way to build a module.
- **Moving the session is fine; splitting it is not.** Move the whole working session to the machine that can run the code, and move back when the chunk is done. What must not happen is two Claude Code sessions on two machines for one chunk — that fragments context, which is the thing this rule has always been protecting. Alpha #12a/#12b are developed on the Windows laptop for this reason; Beta's engine work returns here.
- **Spike scripts** still follow the old loop where they genuinely are spikes: write here, run on the laptop, paste results back into a `docs/research/` note.

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

Six functions isolate all Windows-specific code. Implement these first; call them everywhere else.

```
get_system_language()   # Windows locale API → language code
get_layout_positions()  # Windows keyboard scan codes → Layout (keys + graphemes)
find_voice(language)    # SAPI5 + OneCore voice tokens → voice id | None  (registry only, no COM)
get_fallback_tts(voice) # voice id → a factory the TTS worker calls on its own thread
detect_screen_reader()  # SPI_GETSCREENREADER + process scan → reader id | None
disarm_dead_key()       # ToUnicodeEx(Space) on the window's thread: clears an armed dead key
```

`get_fallback_tts` returns a *factory*, not an engine, and that is not a style choice: a COM
engine belongs to the thread that created it, so anything built on the main thread and driven
from the TTS worker never finishes an utterance and Takki ships mute (ADR-026,
[concurrency-model.md](docs/concurrency-model.md)).

Never call platform APIs directly from application logic. Always go through these interfaces.

## Key technology decisions

| Component | Choice | Notes |
|---|---|---|
| Speech recognition | `faster-whisper` | Local only. `tiny` and `base` both bundled in installer; auto-selected at startup by CPU microbenchmark (matmul < ~2ms → `base`, otherwise → `tiny`). Measured: `tiny` 230–800ms, `base` 400ms–1.5s depending on hardware and power state. `small` not bundled — 1.4s+ even on modern hardware, impractical without CUDA GPU. Triggered by push-to-talk (ADR-020). |
| Voice activity detection | `webrtcvad` | End-of-utterance only (push-to-talk supplies start). Tiny C extension, no ML runtime. See ADR-021. |
| TTS (primary) | Piper TTS | Confirmed on Windows (Python 3.11 MSVC). Load ~2.3s once, synthesis ~0.19s. |
| TTS (fallback) | Windows SAPI, driven directly (`SAPI.SpVoice` via comtypes) | Always available on Windows, no install needed. **Not pyttsx3** — it truncates every utterance after the first and rejects OneCore voice ids (ADR-003, alpha session 12a-2). pyttsx3 remains the Linux dev path only. |
| Keyboard capture | Takki's own window (SDL via pygame) | `TEXTINPUT` gives the character Windows composed, dead keys included; `KEYDOWN`/`KEYUP` give the physical key by scan code. Read from `PygameFocusSource.poll()`'s one drain on the main thread: no hook, no extra thread, no elevated privileges. Keys arrive only while Takki has focus; Alt+Tab is the way back. **Not pynput** — its hook never composes a dead key and mixes layouts after a switch (alpha #13); it is a dev dependency for old spikes only. |
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
    input/          # window key reader, keypress taxonomy
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
- **pyright runs once per target platform, never on the inferred host** (`--pythonplatform Linux` and `--pythonplatform Windows`, both in pre-commit). pyright drops `if sys.platform == "win32":` branches as unreachable before checking them, so a host-inferred run silently skips half the codebase — the half you are usually not sitting on. Do not replace the two runs with a `pythonPlatform` pin in `pyproject.toml`; that just moves the blind spot.
- Whisper and Piper models are cached in CI via `actions/cache`; integration tests against real models cost seconds after warm-up.
- **Assert exact event sequences and counts, not that something was emitted.** Session 6a shipped a bug — a backup focus poll cancelling real focus events — through a clean review and a full green suite, because the tests asserted an event was present rather than which events, in what order, and how many.
- See ADR-019 for the full pyramid, protocol catalog, and CI strategy.

## Open questions (resolve before implementing affected components)

1. ~~**Piper TTS native Windows support**~~ — **resolved.** Works natively on Windows (Python 3.11 MSVC). Model load ~2.3s (one-time), synthesis ~0.19s per phrase. ADR-003 stands.
2. ~~**`pygame.mixer` headless on Windows**~~ — **resolved.** Confirmed: mixer initialises (22050 Hz stereo) and plays audio with no display window. pygame 2.6.1 / SDL 2.28.4. *Update (2026-06-21, ADR-028): `pygame.display` is now initialised on every run — an always-on window is the keyboard-focus anchor (ADR-016). The window is blank in audio-only mode; headless dev and CI use `SDL_VIDEODRIVER=dummy`, stood in for by the `FocusSource` fake.*
3. ~~**Vocabulary coverage curve**~~ — **resolved.** Silver/Gold are key-count based (≥1/3 and ≥2/3 of language's full key set). Coverage displayed as motivating info only, computed over words ≥ 3 chars (aligns with Layer 2 floor; prevents single-letter articles skewing the number).
4. ~~**Minimum hardware spec**~~ — **resolved.** Requires AVX2; matmul benchmark >~10ms is below minimum for Whisper (Celeron-class hardware). `tiny` and `base` bundled in installer, auto-selected by matmul threshold (~2ms). See ADR-018 and ADR-002.
5. ~~**Model downloads under a child account**~~ — **resolved.** `tiny` + `base` bundled in installer; no runtime HuggingFace downloads for Whisper. English Piper voice always bundled; additional voices distributed as browser downloads via the project website (save to `Documents\Takki\voices\`). No in-app download logic. See ADR-015.
