# ADR-026: Platform Interface Abstraction

**Status:** Accepted  
**Date:** 2026-05-23

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Five functions isolate all platform-specific behaviour behind a single `PlatformInterface` Protocol (three from the original cut; `detect_screen_reader()` added 2026-06-21 per ADR-028; `find_voice()` added 2026-09-20, see below). A `select_platform_interface()` factory maps `sys.platform` to the right concrete implementation; new platforms slot in here without touching any other code. A `DevStubInterface` acts as the fallback for platforms that do not yet have a real implementation, so the full codebase runs on any platform during development. The `Layout` / `PhysicalKey` / `Grapheme` data model from the key-introduction spike becomes the canonical return type for `get_layout_positions()` and lives in `src/takki/platform/layout.py`.

### Why These Functions

The boundary is: *the underlying system API is unavoidably platform-specific and cannot be replaced by a pure-Python cross-platform library*.

| Function | Windows | macOS (future) | Linux (future) |
|---|---|---|---|
| `get_system_language()` | Windows NLS locale API | `NSLocale` | `$LANG` / `locale` |
| `get_layout_positions()` | `MapVirtualKeyW` / `VkKeyScanExW` | Carbon / IOKit | xkb |
| `get_fallback_tts()` | pyttsx3 → SAPI | pyttsx3 → nsss | pyttsx3 → espeak |
| `detect_screen_reader()` | `SPI_GETSCREENREADER` + process scan | `NSWorkspace` / AX API | AT-SPI / process scan |
| `find_voice(language)` | SAPI voice tokens in the registry | `NSSpeechSynthesizer` voices | espeak-ng voice list |

`detect_screen_reader()` was added by ADR-028's 2026-06-21 revision and passes the same test that `get_app_data_dir()` failed: there is no maintained pure-Python cross-platform library that reports whether an assistive screen reader is active, whereas `platformdirs` covers app-data paths across Windows, macOS, and Linux with no platform-specific code (see ADR-025). The boundary admits exactly what the test admits.

### Protocol Definition

```python
class PlatformInterface(Protocol):
    def get_system_language(self) -> str: ...
    def get_layout_positions(self) -> Layout: ...
    def get_fallback_tts(self) -> TTSEngine: ...
    def detect_screen_reader(self) -> str | None: ...
    def find_voice(self, language: str) -> str | None: ...
```

`TTSEngine` is the TTS Protocol defined in ADR-003. All five methods on concrete implementations are called once at startup and their results cached by the caller.

**`find_voice()` and why the boundary grew to five** *(added 2026-09-20).* It answers "what can this machine speak", which is a question *about the platform* rather than a request for an object, and it has to answer during startup **before any audio object exists** — because a missing voice for the lesson language is a graceful stop ([ADR-003](0003-text-to-speech.md)), not something to discover mid-lesson. It could not be folded into `get_fallback_tts()`: that function returns an engine, and on Windows the pyttsx3 engine can only be constructed on the TTS worker thread ([concurrency-model.md § TTS](../concurrency-model.md)), which is created later and cannot be asked a question synchronously. The Windows implementation reads the SAPI voice tokens out of the registry and touches no COM at all, which is what lets it run on the main thread at startup.

This is the second instance of a pattern worth naming, the first being [ADR-025 § Language and layout must agree](0025-configuration-system.md): **a startup precondition that cannot be degraded.** Both ask the platform a question, compare the answer against the configured curriculum, and stop the app when they disagree, because continuing would mean teaching against a keyboard the child does not have or a voice they cannot understand. A third would be worth looking for before it becomes a third ad-hoc check in `main()`.

### Platform Selection

```python
def select_platform_interface() -> PlatformInterface:
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface
        return WindowsPlatformInterface()
    # darwin, linux, etc. — real implementations added here as platforms mature
    return DevStubInterface()
```

Adding a real macOS or Linux implementation means: write a new concrete class, add an `elif sys.platform == ...` branch, done. No other code changes.

### Return Types

**`get_system_language() -> str`**

Returns a BCP 47 language tag normalised to the primary subtag: `"en"`, `"de"`, `"fi"`, etc. Territory and script subtags are stripped (`"en_GB.UTF-8"` → `"en"`). The caller looks this up in `LANGUAGE_CONFIGS` (ADR-009); if no match, falls back to `"en"`.

**`get_layout_positions() -> Layout`**

Returns a `Layout` describing every typeable position on the active keyboard. The `Layout`, `PhysicalKey`, and `Grapheme` data classes are defined in `src/takki/platform/layout.py` — they are the production version of the data model developed in `spikes/key_introduction_order_spike.py`.

```python
@dataclass(frozen=True)
class PhysicalKey:
    name: str       # character it produces, or modifier name ("altgr", "dead-acute")
    row: int        # 1 = number row, 2 = top alpha, 3 = home, 4 = bottom alpha
    col: int        # 1–13, left to right

@dataclass(frozen=True)
class Grapheme:
    char: str
    mechanism: str              # "direct" | "dead-key" | "altgr-chord"
    prereq_keys: tuple[str, ...]
    keystrokes: int = 1
    base: str | None = None
    dead_key: str | None = None

@dataclass
class Layout:
    lang: str
    keys: dict[str, PhysicalKey]     # name → PhysicalKey
    graphemes: dict[str, Grapheme]   # char → Grapheme
```

Finger assignment is derived from `col` via a universal `COL_TO_FINGER` mapping (also in `layout.py`) — this is keyboard geometry, not platform-specific. The Windows implementation populates `keys` and direct `graphemes` from scan-code queries; composite graphemes (dead-key, AltGr) are built from the same scan-code data.

**`get_fallback_tts() -> TTSEngine`**

Returns a fully initialised pyttsx3 engine with the appropriate backend for the platform. Pre-initialised because pyttsx3 has real startup cost and is not designed for repeated construction. The engine is a single shared instance; callers must not use it concurrently. This assumption is safe because ADR-012's TTS interrupt rule makes concurrent TTS structurally impossible in the lesson engine — any future contributor who adds a background audio path must revisit this.

**`detect_screen_reader() -> str | None`**

Returns a short identifier for an active screen reader (`"nvda"`, `"jaws"`, `"narrator"`, …) or `None` if none is detected. The Windows implementation combines `SystemParametersInfo(SPI_GETSCREENREADER)` — cheap but unreliable, since not every reader sets the flag (NVDA notably does not by default) — with a process-name scan for the known readers, which is what makes the result dependable. Called once at startup; the result feeds the onboarding self-voicing suggestion (ADR-013) and is otherwise advisory. Takki never reconfigures the reader from its own process.

### Concrete Implementations

**`WindowsPlatformInterface`** — `src/takki/platform/windows.py`  
Real implementations calling Windows APIs. Only imported on `win32`. `detect_screen_reader()` uses `SPI_GETSCREENREADER` plus a process-name scan.

**`DevStubInterface`** — `src/takki/platform/dev_stub.py`  
Fallback for platforms without a real implementation. Logs a startup warning so it is never silently used in production:
- `get_system_language()` → parses `$LANG` / `locale.getlocale()`, falls back to `"en"`
- `get_layout_positions()` → returns the hardcoded US QWERTY `Layout` (the `build_en()` logic from the spike, moved here)
- `get_fallback_tts()` → pyttsx3 with whatever backend pyttsx3 finds on the current platform
- `detect_screen_reader()` → returns `None` (no cross-platform detection in the stub)
- `find_voice()` → returns the language code itself; espeak-ng, the Linux pyttsx3 backend, ships every language Takki teaches, so the dev box never hits the graceful stop

The stub produces real output — pyttsx3 speaks, the layout is valid — but cannot reflect the user's actual keyboard layout or system language beyond what `$LANG` reports. Acceptable for development; not acceptable for a shipped product targeting a specific platform.

### Testing (per ADR-019)

**`FakePlatformInterface`** — `tests/fakes/fake_platform.py`  
Configurable fake for unit tests:
- `get_system_language()` → returns a configurable string, default `"en"`
- `get_layout_positions()` → returns a configurable `Layout`, default US QWERTY
- `get_fallback_tts()` → returns a `FakeTTSEngine` (already defined in `tests/fakes/`)
- `detect_screen_reader()` → returns a configurable value, default `None`

All logic code depends on `PlatformInterface`, not on a concrete class. Tests instantiate `FakePlatformInterface` directly — no monkey-patching.

### Naming: `get_layout_positions()` vs `get_home_row_keys()`

The original name in the architecture doc was `get_home_row_keys()`. ADR-023's key introduction protocol requires the full layout — row, column, and finger for every key, plus composite grapheme definitions — not just the home-row characters. The function was extended and renamed to reflect its actual scope before any implementation landed.

### Alternatives Considered

- **Binary Windows / non-Windows dispatch.** Simpler initially but breaks cleanly as soon as a third platform needs a real implementation. The selector function costs nothing and makes the extension path obvious.
- **Three standalone module-level functions instead of a Protocol.** Harder to swap wholesale — callers would import individual functions rather than accepting an interface. A single Protocol is one injection point.
- **Lazy initialisation for `get_fallback_tts()` (return a factory, not an engine).** Avoids the stateful interface but complicates every caller. Rejected because the single-caller constraint already holds by design — the crosstalk risk that motivates lazy/per-call construction does not apply here.
- **`get_app_data_dir()` as an additional platform function.** Rejected — `platformdirs` provides a tested, well-maintained implementation covering all relevant platforms. (Contrast `detect_screen_reader()`, added later, for which no such cross-platform library exists.)
