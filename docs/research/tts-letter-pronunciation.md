# Research note: spoken isolated-letter names (TTS reality)

> **Status:** Research / spike findings. Inputs to an [ADR-003](../adr/0003-text-to-speech.md) amendment and the [ADR-009](../adr/0009-language-configuration.md) letter-name question; closes roadmap **A1**; produces a result for roadmap **C12**.
> **Date:** 2026-06-28
> **Machine:** run on the Windows test laptop (Python 3.11.15, win32). The primary Linux dev box has no audio device, so these are Windows-only results — written up here rather than kept in a session because the listening was done on the laptop.
> **Scope:** how to produce the spoken name of a single isolated letter (the core Alpha loop, ADR-012). *Not* about connected speech (words, encouragement) — Piper remains fine for that.

## The one-line finding

**Isolated letters are not a TTS problem.** They are a closed, fixed, per-language set (en 26, de 30, is ~32) that never changes — the opposite of what runtime TTS exists for. Neural TTS (Piper) is *structurally* bad at them; the rule-based engines (SAPI, espeak-ng) are reliable but each has a coverage limit. The robust answer is to treat letters as **curated audio assets**, not runtime synthesis.

This contradicts [ADR-003](../adr/0003-text-to-speech.md) as written: line 28 assumes "neural TTS engines correctly pronounce letter names," and the Alternatives section rejects pre-recorded audio. Both need revisiting — but narrowly (see *Impact*).

## Spikes run (reproduce on the Windows laptop)

| Script | What it does |
|---|---|
| [`spikes/tts_reality_spike.py`](../../spikes/tts_reality_spike.py) | SAPI + Piper letter WAVs per language + tier; SAPI mid-utterance interrupt test (C12). `uv run --with piper-tts python spikes/tts_reality_spike.py [en\|de]` |
| [`spikes/tts_letter_fix_spike.py`](../../spikes/tts_letter_fix_spike.py) | Piper text-strategy A/B: `bare` / `period` / `comma` / `raw` phonemes. `uv run --with piper-tts python spikes/tts_letter_fix_spike.py` |
| [`spikes/tts_espeak_spike.py`](../../spikes/tts_espeak_spike.py) | espeak-ng as a **direct** audio synth via the bundled DLL (ctypes), en/de/is. `uv run --with espeakng-loader python spikes/tts_espeak_spike.py` |

Generated WAVs land in `spikes/` (gitignored). Voice models and `spikes/tts_letters/` are also gitignored.

## Findings

### 1. SAPI says letters cleanly — but only for installed Windows voices

pyttsx3/SAPI renders every English (David/Zira) and German (Hedda) letter as its correct name, slowed to `rate=120`. The catch is coverage: SAPI can only speak languages with an **installed Windows voice**. This machine has en + de and **no Icelandic** — and Windows ships no Icelandic voice by default. So SAPI is a strong letter engine for major languages and a non-starter for the long multilingual tail.

A pyttsx3 gotcha found and fixed along the way: `pyttsx3.init()` caches one engine in a module-level `WeakValueDict`, and a second `runAndWait()` on that instance **deadlocks** the SAPI5 driver (this is the original "spike hangs" symptom). Fix: construct a fresh `pyttsx3.engine.Engine()` per call. Documented in the spike.

### 2. Piper (neural) is structurally bad at isolated letters

- Fails on many letters at **every quality tier** (low/medium/high) and is inconsistent between tiers — a bigger model does *not* fix it.
- **Spelling the name out** ("ay", "bee") does **not** reliably help and can make it worse.
- **SSML is a dead end**: Piper's espeak bridge does not enable SSML, so `<say-as interpret-as="characters">` is read aloud literally as words.
- Best text strategy is a **trailing period** (`"a."`) — it gives the model sentence-like structure and stabilises most letters — but voice-specific acoustic quirks remain (e.g. German `e` from `de_DE-thorsten` renders like an Icelandic `æ` across low/medium/high).

### 3. Root cause: the phonemes are correct; the failure is acoustic

Inspecting Piper's phonemizer (`piper.phonemize_espeak`, which uses espeak-ng) shows espeak already maps a **bare single character** to the correct letter-name phonemes:

| | input | phonemes Piper receives |
|---|---|---|
| en | `a` / `b` / `w` / `h` | `ˈeɪ` / `bˈiː` / `dˈʌbəljˌuː` / `ˈeɪtʃ` |
| de | `a` / `e` / `w` / `z` | `ˈɑː` / `ˈeː` / `vˈeː` / `tsˈɛt` |

German `e` → `ˈeː` is the *correct* letter name. So the defect is not spelling or phonemes — it is the **VITS acoustic model distorting ultra-short (1–3 phoneme) utterances**, because it was trained on sentences. No text/phoneme/tier trick fixes an acoustic-model limitation. This is why the `raw` `[[ˈeː]]` strategy can't help either — same phonemes, same acoustic output.

### 4. espeak-ng as a direct synth: reliable + multilingual, robotic timbre

Driving the espeak-ng **shared library** directly via ctypes (DLL + data from the `espeakng-loader` pip package, ~9 MB, no admin, no `espeak-ng.exe`, offline after install) produced full alphabets for **en, de, and Icelandic** at 22050 Hz. Because espeak-ng is rule-based with built-in letter-name dictionaries, isolated letters are deterministic and it covers 100+ languages — including the ones SAPI can't. The open question is purely **timbre**: is the robotic formant voice acceptable as a child's letter cue? *(Pending human listen verdict — see below.)*

### 5. C12 (interrupt) — SAPI `stop()` works

The roadmap flagged that SAPI's `stop()` is reputedly too flaky to honour ADR-012's "cancel TTS on keypress." Measured: full utterance ~12s; `stop()` called at 0.30s returned at ~2.2s and cut the audio. **SAPI interruption works** on this machine — C12's worst case did not materialise. (Confirm by ear on the target hardware before relying on it.)

## By-ear verdicts so far (from the laptop)

- **period** is the most stable Piper strategy, but not clean — "funny" letters remain (German `e` ≈ Icelandic `æ`).
- Piper **tiers are all bad, inconsistently** so — quality tier is not the lever.
- SAPI letters: clean (en/de).
- **Pending:** espeak-ng timbre verdict (en/de/is), and whether espeak Icelandic letters are usable where SAPI cannot run.

## The reframe → recommended architecture

Reserve runtime TTS for **open-ended** content (words, encouragement, instructions). For the **closed** letter set, resolve audio through a `LetterAudioSource` Protocol (fits the ADR-019 I/O-isolation rule) with a priority chain:

1. **Per-profile recorded clip** (parent/educator voice) — opt-in. A familiar voice naming letters is potentially a *feature* for a VI child, and the contribution path for new languages.
2. **Bundled curated clip** for the language — pre-rendered at build time with the **best engine per language** (SAPI for en/de; espeak-ng or human recording where neural/SAPI fail), **each clip human-verified** before shipping. This is where the German `e` is fixed once, permanently.
3. **Runtime TTS fallback** — only if neither exists; never blocks.

Benefits: determinism for the core Alpha loop; letter quality decoupled from whichever runtime engine is chosen; a clean per-language contribution surface (~30 clips); multilingual survival (Icelandic works with no SAPI voice).

### Engine option summary

| Option | Letters | Languages | Timbre | Notes |
|---|---|---|---|---|
| SAPI only | clean | installed Windows voices only (no is) | good | kills small languages |
| Piper only | **bad** | 40+ bundled | neural/warm | structural short-utterance failure |
| espeak-ng direct | clean | 100+ incl. is | **robotic** | bundled DLL, no admin; timbre TBD |
| Pre-rendered curated clips | clean (verified) | any (per-language assets) | best-per-language | small asset pipeline; **recommended** |
| Human recordings | best | any (contributed) | natural | cold-start; use as override, not prerequisite |

## Impact on existing decisions

- **[ADR-003](../adr/0003-text-to-speech.md) line 28** ("neural TTS engines correctly pronounce letter names") is **false for isolated letters** — amend.
- **[ADR-003](../adr/0003-text-to-speech.md) Alternatives** rejected pre-recorded audio, but for the *entire corpus* ("every letter, word, and phrase"). The proposal here is **letters only** (a tiny closed set), leaving TTS for open-ended speech — this narrow use was not the rejected case.
- **[ADR-009](../adr/0009-language-configuration.md)** deleted the per-language letter-name map assuming TTS handles names. With curated letter assets the map is largely moot; if any runtime-TTS fallback path survives, the map may still be needed there.
- **Roadmap A1**: spiked and answered — letters need curated assets, not the Alpha SAPI path alone.
- **Roadmap C12**: SAPI interrupt works; the relax-the-rule fallback is likely unnecessary.

## Open decision (for the Linux dev session)

Primary near-term languages are **en + de**, where SAPI already sounds good — so the minimum viable move is *letters → SAPI, keep Piper for connected speech*. The larger call is whether to invest now in the `LetterAudioSource` chain + build-time curated-clip pipeline (which future-proofs Icelandic and the multilingual tail) or defer it. That decision is pending the espeak-ng timbre verdict and a choice on how far to build ahead of need.
