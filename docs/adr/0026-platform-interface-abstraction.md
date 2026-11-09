# ADR-026: Platform Interface Abstraction

**Status:** Accepted  
**Date:** 2026-05-23

> Part of the [Takki architecture](../architecture.md).  
> **Amended 2026-11-01 for [ADR-033](0033-rest-keys-and-keyboard-alignment.md) (alpha-plan #12m, session 1):** `get_layout_positions()` returns every cell of the scan-code grid, whatever it carries, and `PhysicalKey` gains a dead-key flag and a scan code. See [§ Every cell of the grid](#every-cell-of-the-grid).

---

**Decision:** Five functions isolate all platform-specific behaviour behind a single `PlatformInterface` Protocol (three from the original cut; `detect_screen_reader()` added 2026-06-21 per ADR-028; `find_voice()` added 2026-09-20, see below). A `select_platform_interface()` factory maps `sys.platform` to the right concrete implementation; new platforms slot in here without touching any other code. A `DevStubInterface` acts as the fallback for platforms that do not yet have a real implementation, so the full codebase runs on any platform during development. The `Layout` / `PhysicalKey` / `Grapheme` data model from the key-introduction spike becomes the canonical return type for `get_layout_positions()` and lives in `src/takki/platform/layout.py`.

### Why These Functions

The boundary is: *the underlying system API is unavoidably platform-specific and cannot be replaced by a pure-Python cross-platform library*.

| Function | Windows | macOS (future) | Linux (future) |
|---|---|---|---|
| `get_system_language()` | Windows NLS locale API | `NSLocale` | `$LANG` / `locale` |
| `get_layout_positions()` | `MapVirtualKeyW` / `VkKeyScanExW` | Carbon / IOKit | xkb |
| `get_fallback_tts(voice_id)` | **SpVoice direct** → SAPI | pyttsx3 → nsss | pyttsx3 → espeak |
| `detect_screen_reader()` | `SPI_GETSCREENREADER` + process scan | `NSWorkspace` / AX API | AT-SPI / process scan |
| `find_voice(language)` | SAPI voice tokens in the registry | `NSSpeechSynthesizer` voices | espeak-ng voice list |

`detect_screen_reader()` was added by ADR-028's 2026-06-21 revision and passes the same test that `get_app_data_dir()` failed: there is no maintained pure-Python cross-platform library that reports whether an assistive screen reader is active, whereas `platformdirs` covers app-data paths across Windows, macOS, and Linux with no platform-specific code (see ADR-025). The boundary admits exactly what the test admits.

### Protocol Definition

```python
class PlatformInterface(Protocol):
    def get_system_language(self) -> str: ...
    def get_layout_positions(self) -> Layout: ...
    def get_fallback_tts(self, voice_id: str) -> Callable[[], TTSEngine]: ...
    def detect_screen_reader(self) -> str | None: ...
    def find_voice(self, language: str) -> str | None: ...
```

`TTSEngine` is the TTS Protocol defined in ADR-003. All five methods on concrete implementations are called once at startup and their results cached by the caller.

**`find_voice()` and why the boundary grew to five** *(added 2026-09-20).* It answers "what can this machine speak", which is a question *about the platform* rather than a request for an object, and it has to answer during startup **before any audio object exists** — because a missing voice for the lesson language is a graceful stop ([ADR-003](0003-text-to-speech.md)), not something to discover mid-lesson. It could not be folded into `get_fallback_tts()`: that function yields an engine, and on Windows the engine can only be constructed on the TTS worker thread ([concurrency-model.md § TTS](../concurrency-model.md)), which is created later and cannot be asked a question synchronously. The Windows implementation reads the SAPI voice tokens out of the registry and touches no COM at all, which is what lets it run on the main thread at startup.

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
    name: str       # the character it produces unshifted, or "dead-acute", "altgr"
    row: int        # 1 = number row, 2 = top alpha, 3 = home, 4 = bottom alpha
    col: int        # 1–13, left to right

    @property
    def dead(self) -> bool: ...       # added 2026-11-01: the name starts "dead-"

    @property
    def scan_code(self) -> int: ...  # added 2026-11-01: SCAN_CODE_GRID, inverted

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

#### Every cell of the grid

*(Amended 2026-11-01, alpha-plan #12m session 1, for [ADR-033](0033-rest-keys-and-keyboard-alignment.md). Marks: **[M]** measured on the Windows test laptop against layouts loaded with `LoadKeyboardLayout` and never activated, and pinned by a `windows_only` test unless said otherwise; **[T]** pinned by a default test against the hand-built tables; **[A]** argued, not measured.)*

**Why.** ADR-033 makes the place a finger rests its own tier of key. A finger may land anywhere in its own column, and the right little finger's conventional place on US QWERTY is `;`. Until this amendment, `Layout.keys` held only letters and dead keys, so a landing on `;` had no key to be matched to.

**What `get_layout_positions()` returns now.** `Layout.keys` holds every cell of `SCAN_CODE_GRID` that produces one character, or is a dead key. That is all 46 cells on the US, UK, German and Icelandic keyboards **[M]**. A cell that carries neither a letter nor a dead key is a **plain cell**. On US QWERTY those are the ten digits, `- = [ ] ; ' \ , . /` **[M, T]**.

- **A plain cell is a key, never a grapheme.** It is never a typing target (ADR-033 § Four tiers of key), so the word pool, the introduction order and the milestone denominators are unchanged. `build_en`, `build_de` and `build_is` still have 26, 30 and 36 graphemes **[T]**. Every engine use of `keys` either looks a key up from a grapheme or keeps only the keys that are graphemes. Stage 0's lookups by position (`anchor_keys`, `home_anchor_keys`) did neither until this amendment's review. They now go through `letters_by_position()`, so a position with no letter still raises, as their comments require **[T]**. A plain cell therefore reaches no lesson code **[A, from reading every use; one existing test changed, because it counted every home-row key as a letter]**.
- **It goes in `keys`, not in a field of its own.** `keys` has always been the physical keys, a dead key included, which no consumer treats as a letter. The engine already reads letters through `graphemes`. A separate field would hold the letters' cells a second time, because a letter's key is a rest key too. Or it would split one keyboard across two dictionaries that the alignment would have to search together. The cost is the rule above: code that wants letters asks `graphemes`, or `letters_by_position()` when it looks a letter up by position. The review of this amendment suggested the separate field; it was weighed and not taken.
- **Its name is the character the key produces unshifted**, as Windows reports it (`;`, `'`, `1`). A dead key keeps its `dead-<diacritic>` name. The name is what ADR-033's spoken key names will be looked up by (ADR-022). Those names are not part of this amendment.
- **`PhysicalKey.dead`** is true for a dead key and only for a dead key **[M, T]**. #13 asked for the flag ([alpha-plan](../alpha-plan.md), "From #13"), because the alignment must disarm a dead key after a landing on it ([ADR-033 § Work](0033-rest-keys-and-keyboard-alignment.md#work-this-adr-requires-before-it-can-be-built)). `describe_mismatch` reads it too (below). **It is derived from the name, not stored.** The reader names every dead key `dead-<diacritic>` (`dead_key_name`), and a plain cell's name is one character. So the flag and the name cannot disagree. A stored flag could, and the review of this amendment found exactly that: a test fixture with a `dead-acute` key that was not flagged.
- **`PhysicalKey.scan_code`** is the cell's set-1 scan code, which is the code the reader asks Windows about. It is **derived from the position, not stored**, so a table, the fake and the reader cannot disagree about it. For every cell of the four keyboards, the code read back through `ToUnicodeEx` gives the cell's own character, or a dead key for a dead cell **[M]**. To make that possible, `SCAN_CODE_GRID` moved from `takki.platform.windows` to `takki.platform.layout`, beside `COL_TO_FINGER`. Like `COL_TO_FINGER`, it is keyboard geometry and not a Windows call. Moving it also lets the default suite check that every key in every hand-built table is a grid cell **[T]**. From #14 a key press is identified by its *SDL* scan code. The table from SDL's codes to set-1 is in `spikes/key_capture_source_spike.py` (`SET1_TO_SDL`); bringing it into product code is the job of #14 or of #12m's session 7 (the alignment), not this amendment.

**What "every cell" covers.**

- **The whole grid, not only the rest columns.** ADR-033 asks for columns 1–3 and 8–13, which are 30 of the grid's 46 cells. The reader already swept the whole grid for letters, and a rule that kept a digit only outside the index columns would have no user. So the four digits `4 5 6 7` are cells too.
- **The number row is in.** ADR-033 rules out no row.
- **0x56, the extra ISO key left of `Z`, stays out.** **[A]** It is not in columns 1–13, so `COL_TO_FINGER` has no finger for it. An ANSI keyboard does not have the key, and Windows reports a character for it either way: `\` on US and UK, `<` on German and Icelandic **[M, from a probe in this session, not a test]**. On US that duplicates 0x2B's `\`, and `keys` is keyed by name. A press on it finds no cell, so the alignment treats it as a press outside the column, which ADR-033 answers with guidance.
- **0x29, left of `1`, stays out.** It is roadmap § C17's question, whether Takki models that key at all. It is a dead key on German, Icelandic and US-International **[M, probe]**.
- **Keys that produce no character stay out**: Tab, Caps Lock, both Shifts, Enter and Backspace. **[A]** They are the same keys on every layout, so there is nothing for the layout to report. Alpha #13 showed the window can still say which of them was pressed, by scan code (ADR-033's dated note). So the rule that a press on such a key is not a landing is now a choice, and this amendment keeps it: such a press finds no cell. Two reasons. Shift is the key a resting little finger would trigger Sticky Keys and Filter Keys from (#13, [M] there). And ADR-033's interim rule already says it. **Whether a landing on one of these keys should count is #12m's session 7's question** (the alignment), and admitting them means amending this section.
- **Column 13 has no cell.** Every key that physically sits there (Backspace, Enter, and on ANSI the `\` key) is either a non-character key or 0x2B, which the grid places at (3, 12). *(Note 2026-11-09, #12m session (5b): on ISO only. On ANSI, 0x2B is placed at (2, 13), the one cell in column 13; see the next point.)*
- **0x2B is placed where ISO keyboards have it, row 3. On an ANSI keyboard the same scan code is the key above Enter, row 2.** **[A]** Windows reports the same scan code for both, so the reader cannot tell. The finger is the right little finger either way. Only the row is wrong on ANSI, which matters to the location rule of #12m's session 5 ("one row up from where your finger rests") for a child whose right little finger rests on `\`.

  *(Note 2026-11-09, alpha-plan #12m session (5b): built as a setting, `config.KEYBOARD_SHAPE`, `"iso"` or `"ansi"`, ISO by default ([ADR-025](0025-configuration-system.md#configpy--compiled-defaults), the dated note). `SCAN_CODE_GRID`, a constant, became `scan_code_grid(shape)`, which reads the setting when it is called without a shape. 0x2B is at (3, 12) on ISO and at (2, 13) on ANSI, above Enter, in the right little finger's column 13. Every other cell is the same on both **[T]**. The reader and the three tables go through it: `read_layout` places the cells by the setting's grid, and `build_en`, `build_de` and `build_is` take an optional shape that defaults to the setting, so a table and the reader agree on either shape **[A: the reader's half is checked here only by pyright's Windows run; `tests/test_windows_layout.py` compares against the default shape and runs on the laptop or CI]**. `PhysicalKey.scan_code` needs no shape: (3, 12) and (2, 13) both name 0x2B **[T]**. The startup check gives every layout the same verdict on both shapes, because 0x2B carries no letter and no dead key in any table **[T]**. **Why a setting and not a reading** (asked by the developer in the session): a Windows layout is a table of characters, and any layout runs on either shape (a US layout on a European ISO keyboard is common), so the active layout says nothing about the shape. The keyboard does not report it either: `GetKeyboardType` gives "enhanced 101/102-key" for both, and a USB keyboard's country field is almost always zero **[A: from the documentation, not measured]**. Apple's Keyboard Setup Assistant asks the user to press the key beside left Shift, for the same reason. A press on 0x56 proves an ISO keyboard, since ANSI has no such key; the absence of one proves nothing, so it cannot replace the setting ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)).)*

**US and UK punctuation.** `build_en()` is US QWERTY, so its cells are US cells. The reader reports the keyboard as it is. Of the grid's 46 cells, UK QWERTY differs from US in one: (3, 12) is `#`, not `\` **[M]**. So a UK child's cell there is named `#`, which is the truth, and that is the layout the engine is handed.

**The startup check compares what it compared before.** **[M, T]** `describe_mismatch` compares `curriculum_positions()`: every key some grapheme needs (letters and modifiers), and every dead key. It does not compare plain cells. So every layout keeps the verdict it had before this amendment:

- US, UK and Icelandic pass.
- German is refused with the same message, `unexpected dead-acute`. That is roadmap § C17, now pinned by a test.
- US-International, Dvorak, French, Russian and Greek are refused, as before.

The reasons:

- A punctuation difference is not a reason to refuse a child's keyboard: it changes only which character a rest key carries, and a rest key without a letter is judged by its position (ADR-033).
- Refusing on it would have stopped UK keyboards, which teach the English curriculum correctly. Nobody decided that.
- Dead keys stay compared, because dropping them would have made German startable, which only C17's fix may do.

**`build_de()` has every cell but one.** It leaves out the dead acute at (1, 12). Declaring that key is C17's fix, which waits on C16. And because dead keys are compared, declaring it would make German startable with a curriculum (30 graphemes, or 36 with the six acutes) that nobody has decided. Real German's keys are exactly `build_de()`'s keys plus that dead acute **[M]**.

**Limits.**
- **A plain character on two cells keeps the first one**, because `keys` is keyed by name, and the reader logs a warning. A letter or a dead-key name on two cells keeps the last one, silently, as it did before this amendment **[A: no layout measured has such a pair, so the warning is untested]**. None of the four keyboards has one: each reads 46 distinct keys **[M]**. Nor do the thirteen English layouts probed in this session, every KLID whose language is `en` among `00000409 00000809 00001009 00011009 00004009 00001809 00011809 00010409 00030409 00040409 00020409 00001409 00000c09` **[M, probe, not a test]**. A layout that had one would lose a cell, and a landing on that cell would be treated as a press outside the column. **[A]**
- **A cell that produces nothing, more than one character, or a control or whitespace character, is not a cell**, because it has no name that could be spoken. None of the four keyboards has one **[M]**. The guard against control and whitespace characters is **[A]**: no layout measured produces one.
- **A modifier that is not a dead key and that no grapheme needs is not compared** by `describe_mismatch`. No table or layout has one. An AltGr key declared before any AltGr letter would be one. **[A]**
- **A key off the grid has no scan code**, and `scan_code` raises for it. No such key exists today. An AltGr key would be one, like its finger, which `COL_TO_FINGER` does not have either.
- **The reader reads each cell unshifted only**, as it always has. A cell's shifted character is not reported.

**Code:** `takki.platform.layout` (`scan_code_grid`, `SCAN_CODE_GRID` until 2026-11-09, `PhysicalKey`, `letters_by_position`, `curriculum_positions`, the three tables) and `read_layout` in `takki.platform.windows`. **Tests:** `tests/test_platform.py` (`TestNonLetterCells`, `TestTheComparisonIgnoresPlainCells`, `TestScanCodeGrid`, `TestKeyboardShape`) and `tests/test_windows_layout.py` (`TestEveryCell` and the per-layout tests).

**`get_fallback_tts(voice_id: str) -> Callable[[], TTSEngine]`**

*(Reshaped 2026-09-20, alpha session 12a-2. It used to read `get_fallback_tts() -> TTSEngine` and return a fully initialised engine.)*

Returns a **factory**, and takes the voice id `find_voice()` has already resolved. Both halves are load-bearing and both were learned by running the thing on Windows:

- **A factory, because the caller must not be able to construct the engine.** `main()` runs on the main thread, and a COM engine built there and then driven by the TTS worker never completes an utterance — Takki ships mute, with no error anywhere ([concurrency-model.md § The engine belongs to the thread that creates it](../concurrency-model.md)). The worker calls the factory as its first act. This reverses a rejection recorded in § Alternatives Considered below; see the note there.
- **The voice id, because verification and application must not be separable.** `find_voice()` establishes that the machine can speak the lesson language and `main()` exits `EXIT_NO_VOICE` if it cannot. A signature that let the engine be built without that id let the check pass and the system default speak anyway, which is worse than not checking ([ADR-003](0003-text-to-speech.md)). There is now no such path.

The engine is still a single instance driven by one thread; ADR-012's interrupt rule still makes concurrent TTS structurally impossible in the lesson engine. What changed is *which* thread may create it, not how many.

**`detect_screen_reader() -> str | None`**

Returns a short identifier for an active screen reader (`"nvda"`, `"jaws"`, `"narrator"`, …) or `None` if none is detected. The Windows implementation combines `SystemParametersInfo(SPI_GETSCREENREADER)` — cheap but unreliable, since not every reader sets the flag (NVDA notably does not by default) — with a process-name scan for the known readers, which is what makes the result dependable. Called once at startup; the result feeds the onboarding self-voicing suggestion (ADR-013) and is otherwise advisory. Takki never reconfigures the reader from its own process.

### Concrete Implementations

**`WindowsPlatformInterface`** — `src/takki/platform/windows.py`  
Real implementations calling Windows APIs. Only imported on `win32`. `detect_screen_reader()` uses `SPI_GETSCREENREADER` plus a process-name scan.

**`DevStubInterface`** — `src/takki/platform/dev_stub.py`  
Fallback for platforms without a real implementation. Logs a startup warning so it is never silently used in production:
- `get_system_language()` → parses `$LANG` / `locale.getlocale()`, falls back to `"en"`
- `get_layout_positions()` → returns the hardcoded US QWERTY `Layout` (the `build_en()` logic from the spike, moved here), with every cell of the grid since 2026-11-01 (§ Every cell of the grid)
- `get_fallback_tts(voice_id)` → the `FallbackTTS` class itself as the factory; pyttsx3 picks its own backend, and `voice_id` is ignored because espeak selects by text language rather than by token id
- `detect_screen_reader()` → returns `None` (no cross-platform detection in the stub)
- `find_voice()` → returns the language code itself; espeak-ng, the Linux pyttsx3 backend, ships every language Takki teaches, so the dev box never hits the graceful stop

The stub produces real output — pyttsx3 speaks, the layout is valid — but cannot reflect the user's actual keyboard layout or system language beyond what `$LANG` reports. Acceptable for development; not acceptable for a shipped product targeting a specific platform.

### Testing (per ADR-019)

**`FakePlatformInterface`** — `tests/fakes/fake_platform.py`  
Configurable fake for unit tests:
- `get_system_language()` → returns a configurable string, default `"en"`
- `get_layout_positions()` → returns a configurable `Layout`, default US QWERTY (`build_en()`, so the same cells as the dev stub)
- `get_fallback_tts(voice_id)` → returns a factory over one shared `FakeTTSEngine`, and records the id it was asked for so a test can assert the verified voice reached the engine
- `detect_screen_reader()` → returns a configurable value, default `None`

All logic code depends on `PlatformInterface`, not on a concrete class. Tests instantiate `FakePlatformInterface` directly — no monkey-patching.

### Naming: `get_layout_positions()` vs `get_home_row_keys()`

The original name in the architecture doc was `get_home_row_keys()`. ADR-023's key introduction protocol requires the full layout — row, column, and finger for every key, plus composite grapheme definitions — not just the home-row characters. The function was extended and renamed to reflect its actual scope before any implementation landed.

### Alternatives Considered

- **Binary Windows / non-Windows dispatch.** Simpler initially but breaks cleanly as soon as a third platform needs a real implementation. The selector function costs nothing and makes the extension path obvious.
- **Three standalone module-level functions instead of a Protocol.** Harder to swap wholesale — callers would import individual functions rather than accepting an interface. A single Protocol is one injection point.
- ~~**Lazy initialisation for `get_fallback_tts()` (return a factory, not an engine).** Avoids the stateful interface but complicates every caller. Rejected because the single-caller constraint already holds by design — the crosstalk risk that motivates lazy/per-call construction does not apply here.~~ **Adopted 2026-09-20 (alpha session 12a-2), and the rejection was wrong for a reason it could not have known.** The argument weighed crosstalk between callers, and crosstalk was never the problem: *which thread runs the constructor* is. A COM engine belongs to its creating thread, so returning a built engine puts it on the caller's thread by construction, and the caller is `main()`. The cost the rejection feared — "complicates every caller" — is one call site. It was invisible until the path ran on Windows, because `FakeTTSEngine` and pyttsx3's espeak driver have no thread affinity at all.
- **`get_app_data_dir()` as an additional platform function.** Rejected — `platformdirs` provides a tested, well-maintained implementation covering all relevant platforms. (Contrast `detect_screen_reader()`, added later, for which no such cross-platform library exists.)
