# ADR-003: Text-to-Speech (Audio Feedback)

**Status:** Accepted  
**Date:** 2026-05-17  
**Revised:** 2026-07-05 — isolated letter names moved off runtime neural TTS to a curated `LetterAudioSource` chain (spike: [tts-letter-pronunciation](../research/tts-letter-pronunciation.md)).
**Revised:** 2026-09-20 (alpha session 12a-2) — the *fallback* is still SAPI, but it is no longer reached through pyttsx3 on Windows. See § The Windows fallback drives SAPI directly.

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Piper TTS as default, with Windows SAPI as automatic fallback *(driven directly since 2026-09-20; pyttsx3 remains the Linux dev path only)*.

### Rationale

Audio feedback is the primary output modality. Quality matters — a robotic or mispronouncing voice is demotivating for children.

**Piper TTS** is chosen as the default because:
- High-quality neural voices, substantially better than SAPI
- Runs fully locally, no internet
- Pre-built voice models available for many languages
- Lightweight enough to bundle or download at first run
- Confirmed working natively on Windows (Python 3.11 MSVC): model load ~2.3s once per session, synthesis ~0.19s per phrase (real-time factor ~0.06×)

**SAPI** is retained as fallback because:
- Zero additional installation — uses built-in Windows voices
- Guarantees the app works even if Piper model download fails
- Some users may prefer it for familiarity

*(The binding changed on 2026-09-20 and the choice of engine did not: SAPI is still the fallback, but Takki now talks to `SAPI.SpVoice` itself rather than through pyttsx3. Why, and what it bought, is in § The Windows fallback drives SAPI directly below.)*

**Character and key name pronunciation.** In *connected* speech (words, encouragement, instructions) neural TTS pronounces characters correctly in context (e.g. a German voice reads "ä" correctly inside a word); explicit overrides are added only when testing reveals specific mispronunciations — this list is expected to be very small. *Isolated* letter names are handled separately — see the revision note below.

> **Revised (2026-07-05):** the original claim that "neural TTS engines correctly pronounce letter names" is **false for isolated letters.** The [letter-pronunciation spike](../research/tts-letter-pronunciation.md) found neural TTS (Piper) is *structurally* bad at ultra-short 1–3 phoneme utterances at every quality tier: the phonemes espeak feeds it are correct, but the VITS acoustic model — trained on sentences — distorts them, and no text/SSML/tier trick fixes it. SAPI speaks letters cleanly but only for installed Windows voices (no Icelandic); espeak-ng is reliable and multilingual but robotic. Isolated letters are a **closed, fixed per-language set**, so they are resolved through the `LetterAudioSource` Protocol's three-layer priority chain (below), not by general synthesis. This applies to isolated letters only; Piper remains the default for all connected speech.

### Letter audio: the three-layer model

*(Canonical home for the letter-audio layering. Added with the revision note above, 2026-07-05.)*

Isolated-letter audio resolves through `LetterAudioSource` ([`src/takki/audio/letters.py`](../../src/takki/audio/letters.py)) as three named layers, highest priority first. Resolution **walks down** until it finds audio for the requested letter; a lower layer is consulted only when every layer above it is absent for that letter.

| Priority | Layer | Voice | Scope | Source | Progress-gated |
|---|---|---|---|---|---|
| 1 (wins) | **Personal** | the child's own | per **profile** | recorded in-app — the *reward* workflow ([ADR-030](0030-personal-letter-recordings.md)) | ✅ offered per learned letter |
| 2 | **Base** | a human's | per **language** | bundled curated clips (human-verified, best engine per language), or community-contributed | no |
| 3 (floor) | **Synthetic** | machine | universal | runtime TTS — SAPI where a Windows voice exists, espeak-ng otherwise | no |

**Invariant — Synthetic is the floor and can never be empty.** espeak-ng produces a full, correct (if robotic) letter alphabet for every target language, offline. So resolution always terminates in audio: Personal and Base are quality *upgrades* over the floor, never prerequisites. A missing, muted, or corrupt higher layer degrades exactly one step — never to silence.

**Naming is fixed and internally consistent:** the three *layers* are **Personal / Base / Synthetic**. `reward` names the workflow that populates Personal ([ADR-030](0030-personal-letter-recordings.md)) — it is not a layer. `floor` is informal shorthand for "Synthetic is guaranteed." User-facing copy may use warmer phrasing ("record it in your own voice"), but code, tables, and ADRs use the three layer names.

- **Base subsumes shipped *and* contributed clips** — same layer, same per-language scope. A parent/teacher-recorded alphabet is the community-contribution surface and is curatable into a later shipped bundle. The *contribution* recording workflow (a human supplies a language Base) is **deferred**: with the Synthetic floor there is no silent-language failure to rescue, so it is a post-Alpha feature and gets its own ADR when built.
- **Personal is per-profile** and lives in the profile database ([ADR-011](0011-persistence-and-state.md), [ADR-030](0030-personal-letter-recordings.md)); Base clips are read-only per-language assets, not per-profile.
- This model covers **isolated letters only**. Connected speech (words, encouragement, instructions) is unchanged — Piper per the main decision above.

**Per-student voice settings** are stored in the child profile (see ADR-011):

- `tts_rate` — Piper `length_scale` float. Default 1.0. Range 0.6–2.0 in 0.2 steps. Higher = slower. Adjusted via spoken "faster" / "slower" commands; each command moves one step. Speech rate is highly individual — a change of 0.2 is perceptible and meaningful. The range covers the full practical spectrum from fast-but-intelligible (0.6) to very deliberate (2.0).
- `tts_voice` — Piper voice model key, e.g. `en_US-amy-low`. Null means use the language default. Gender and accent are baked into the model; there is no separate gender field. The parent selects a voice from the curated `voice_catalog.yaml` (see ADR-015) before the model is downloaded — the chosen key is then stored here.
- `language` — BCP-47 language code override. Null means inherit the globally detected system language. Used when a child's instruction language differs from the OS locale (e.g. an English OS in a Welsh-medium school).

**SAPI fallback rate mapping:** SAPI rate runs −10 (slowest) to +10 (fastest), opposite direction to `length_scale`. Mapping: `sapi_rate = round((1.0 − length_scale) × 10)`, clamped to [−10, 10].

**A missing voice is a graceful stop** *(decided 2026-09-20).* If no installed voice matches the lesson language, Takki reports why and exits rather than starting. This is the same startup-precondition shape as [ADR-025 § Language and layout must agree](0025-configuration-system.md), and for the same reason: Alpha's entire loop is *"hear a letter, type it"* ([ADR-012](0012-audio-feedback-design.md)), so a curriculum Takki cannot pronounce is exactly as unusable as one it cannot type. Falling back to the system default voice would not degrade the experience, it would produce prompts the child cannot resolve to a letter — the A1 failure, reached without ever touching A1's code path.

The check is a **registry read, not an engine query**: `WindowsPlatformInterface.find_voice()` enumerates the voice-token keys directly. **It reads four of them, not one** *(corrected 2026-09-20, alpha session 12a-2)*: `Speech\Voices\Tokens` and `Speech_OneCore\Voices\Tokens`, under both `HKLM` and `HKCU`. Reading only the first is what made this check's own remedy useless — Windows 11's *Settings → Time & language → Speech → Manage voices*, which is verbatim what `main.py` prints on `EXIT_NO_VOICE`, installs into **Speech_OneCore**, so a parent who followed the instruction exactly got the same refusal with nothing further to try. Measured on the test laptop: 3 SAPI5 tokens against 6 OneCore. That matters because the pyttsx3 engine can only be constructed on the TTS worker thread ([concurrency-model.md § TTS](../concurrency-model.md)), and this must answer during startup before any thread or audio object exists. A token's `Language` attribute is a hex LCID whose low 10 bits are the primary language, so every regional variant collapses onto one curriculum language — `0x409` en-US and `0x809` en-GB are both `en`, which is right, because the curriculum is per-language and not per-region. The ids it returns are exactly the strings `SpObjectToken.SetId` expects.

**A voice that cannot sound is a graceful stop too** *(decided 2026-09-24, alpha session 12a-2)*. The registry read above cannot see the output device, and a GitHub runner showed the gap is real: David resolves, COM initialises, the token applies, and only `SpVoice.Speak` fails (`COMError 0x8004503A`). So `SapiTTS` proves output as it is built — one letter at volume 0 and maximum rate, through a second `SpVoice` so the real one is never left silent — and raises `SpeechOutputError` on a `COMError` or a 10 s non-completion. `main()` exits `EXIT_NO_AUDIO` (4) with the remedy on stderr, the third startup precondition beside layout and voice. 0.58 s once on the laptop. Losing the device *after* startup is not refused but survived: the TTS worker reports the utterance `failed` and carries on ([concurrency-model.md § TTS](../concurrency-model.md)). Test strategy in [ADR-019 § Headless audio/video](0019-testing-strategy-and-io-isolation.md).

~~Two measured facts for whoever implements the engine side~~ — **both are now moot, and one of them was a trap** *(2026-09-20, alpha session 12a-2)*. They described pyttsx3: that a registry-derived id applies and persists, but that `getProperty("voice")` straight after `setProperty` reports the *old* voice because pyttsx3 queues property changes until the next `runAndWait()`. The sharper finding is that **pyttsx3 rejects a OneCore id outright and swallows the `ValueError`** — `setProperty` is pushed onto its command queue and `DriverProxy._pump` catches every exception into a `notify("error", …)` nobody subscribes to, so the engine silently keeps the system default. A voice verified in the registry and then silently not applied is exactly the failure this section exists to prevent. Driving SAPI directly removes both problems: `SpObjectToken.SetId(voice_id)` accepts either category's path, and `SpVoice.Voice` reflects it immediately.

**SAPI fallback voice selection** *(amendment 2026-09-20, pre-alpha-session-12a review).* This ADR maps the fallback's *rate* and says nothing about its *voice*, and `tts_voice` above is a Piper model key with no SAPI counterpart — so `FallbackTTS` sets no voice at all and speaks in whatever the machine's SAPI default happens to be. On the Windows test laptop the default is `TTS_MS_EN-US_DAVID_11.0` and English letters come out in English, which is why the gap was invisible; the same machine also has `TTS_MS_DE-DE_HEDDA_11.0` installed, and on a machine defaulting to that, every English letter is read with German phonology. That is the A1 failure — a prompt the child cannot resolve to a letter — reached by a route A1 never considered, and it lands on Alpha's *default* TTS path rather than a fallback nobody exercises. **The fallback must select a voice whose language matches the profile language**, chosen inside `get_fallback_tts()`, which is the platform function that already knows the language ([ADR-026](0026-platform-interface-abstraction.md)). Two sub-cases need deciding with it, both reachable on the test laptop today: more than one installed voice matches (David and Zira are both `en-US` — pick the first deterministically and let the parent tier override later), and **none** matches (no Icelandic voice is installed, and the [letter-pronunciation research](../research/tts-letter-pronunciation.md) records that no Windows one exists) — speaking the wrong language is worse than a clear spoken failure, so that branch should not fall through to the default voice in silence. Alpha session 12a-2 owns the implementation; the per-profile SAPI voice override is Beta's, alongside the rest of the config tier.

### The Windows fallback drives SAPI directly

*(Added 2026-09-20, alpha session 12a-2, after implementing the fallback path for the first time on Windows.)*

**pyttsx3 is off the Windows path.** The engine choice is unchanged — SAPI is still the fallback — but Takki now creates `SAPI.SpVoice` through comtypes and drives it itself (`src/takki/audio/sapi_tts.py`). pyttsx3 remains the Linux dev path, where its espeak driver is fine and no COM is involved.

**Why.** pyttsx3's SAPI driver leaves its own `DriverProxy._busy` False when the first `runAndWait()` returns, so every later utterance is started outside its loop and then immediately purged by the `endLoop` command the same `runAndWait()` queued. **Every utterance after the first was cut to ~0.9–2.1 s.** That is not a corner case for Takki: [ADR-023](0023-key-introduction-protocol.md)'s introduction script is the longest thing the curriculum says and the one utterance that teaches rather than tests, and a child heard *"New letter F. Use your…"* and then silence. It survived eleven sessions because Alpha's commonest utterance is a single letter and a letter is shorter than the cutoff. Full mechanism and the runnable proof: [concurrency-model.md § SAPI speaks only the first utterance in full](../concurrency-model.md), `spikes/tts_thread_truncation_spike.py busy`.

**What the change bought, measured on the test laptop the same day:**

| | pyttsx3, as shipped | pyttsx3, repaired | SpVoice direct |
|---|---|---|---|
| Utterance after the first | truncated to ~0.9–2.1 s | full length | full length |
| Utterance after a *cancel* | — | full length **only with repair 2** | full length |
| `stop()` cost on the calling thread | — | 94–156 ms | 0.000 ms |
| Audio-stop latency | — | ~0.4 s | ~0.2 s |
| OneCore voice id | rejected, `ValueError` swallowed | applies **via repair 3** | applies |
| COM event sink and message pump | required | required | none |
| pyttsx3 internals depended on | — | three | none |

The middle column is the one that decides this, and it is why the next section exists rather than this table standing alone.

#### The pyttsx3 path was made to work first

*(Added 2026-09-20, after the first draft of this section presented replacement as forced. It was not, and saying so was wrong. The experiments are `spikes/tts_thread_truncation_spike.py repaired` and `onecore`.)*

**pyttsx3 can be repaired in place, and it speaks correctly when it is.** Three repairs, each restoring an invariant the library breaks:

1. **`engine.proxy.setBusy(True)` after every `runAndWait()`.** Restores the flag pyttsx3 leaves False, which fixes truncation on its own — three 4.42 s lines in a row return in 4.64/4.66/4.63 s.
2. **Pump messages (~250 ms) before restoring that flag.** A purge fires its *own* `EndStream` **after** `runAndWait()` has returned, and the sink's handler knocks `_busy` down again — so with repair 1 alone a cancel corrupts the **next** utterance: measured 2 of 3 lost. With both, 0 of 3 lost.
3. **Assign the voice token onto `proxy._driver._tts.Voice`.** Goes around `_tokenFromId`, which searches the SAPI5 category only and so rejects every OneCore id.

`startLoop(False)` + `iterate()` also speaks in full (4.58/4.59/4.61 s), and is worth recording for what it does *not* fix. Cancelling by leaving that loop returns the caller in 0.000 ms, **but the audio keeps playing** — SAPI's own `RunningState` stayed at "speaking" for the full 2.8 s measured afterwards. Leaving the loop stops *waiting*, not speaking, and [ADR-012](0012-audio-feedback-design.md)'s interrupt-on-keypress needs the letter to stop sounding. So a purge is still required, and the purge is what needs repair 2.

**Two figures that had been used to argue for replacement were wrong, and both are corrected above.** `stop()`'s ~1.17 s was measured against a *truncated* engine — repaired, it blocks the caller 94–156 ms, so the real gap is 0.000 ms against ~100 ms, not against a second. And "a fresh engine per utterance costs 1.3–3.7 s" was cold-start contamination; warm, in one process, it is ~4.75 s for 4.42 s of audio, i.e. almost free.

**So the decision rests on fragility, not capability, and it is worth being explicit about that.** All three repairs depend on pyttsx3 internals with no stability guarantee — `proxy.setBusy`, the timing of an event the library does not document, and two private attributes. The failure they prevent is **silent**: a version bump that re-broke any of them would not raise, it would quietly cut the child off mid-sentence, which is precisely the property that hid this defect for eleven green sessions and through a clean review. Ninety lines of `SpVoice` with no private access is the cheaper thing to own. A library is normally worth depending on through documented repairs; it is not worth it when the repair is undocumented internals and the regression is inaudible to CI.

**This probably ends pyttsx3 in Takki rather than only on Windows** *(noted 2026-09-20)*. It remains the macOS and Linux row of [ADR-026](0026-platform-interface-abstraction.md)'s table and the dev-box path, which is fine while Windows is the only target and the other platforms are not shipped. The same argument would apply to them the moment they are: a real three-OS release wants one TTS seam whose failures are loud, and `TTSEngine` is already that seam — `SapiTTS` shows what a per-platform implementation behind it costs. Decide it in the phase that first ships a second OS, not now. See [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr).

**Speaking rate: `Rate = 0`, and it is slower than every figure previously recorded.** `SapiTTS` pins the rate from the mapping above with the default `length_scale` of 1.0, which gives 0. pyttsx3 had been setting `Rate = 2` — its own 200 wpm default, unrelated to this ADR — so every SAPI duration on record anywhere in the repo was taken ~30% fast. Re-measured at `Rate = 0`: a letter is **1.36 s** (recorded as 0.94 s), ADR-023's introduction script **7.42 s** (recorded as ~4.2 s), driver init ~2.0 s. Nothing in the engine is wrong; the curriculum simply speaks at the rate this ADR specifies for the first time. **Whether 1.0 is the right default `length_scale` for a child is now an open tuning question and not an engine question** — it was never chosen against measured SAPI audio, and Alpha has no per-profile rate tier to move it with.

**Voice selection is applied, not merely verified.** `get_fallback_tts(voice_id)` takes the id `find_voice()` resolved and the engine sets it before speaking; the signature has no path that skips it. A check that reads as a guarantee and is not applied is worse than no check, which is what the `TODO` this section replaces had left in `main.py`.

### Alternatives Considered

- **Pre-recorded audio for the *entire* corpus:** Rejected. Recording every letter, word, and phrase in every supported language eliminates multilingual flexibility and creates an enormous maintenance burden. *(Revised 2026-07-05: this rejection stands for the open-ended corpus only. Curated audio for the **closed isolated-letter set** — on the order of ~30 clips per language — is a distinct, accepted case, resolved behind the `LetterAudioSource` Protocol; see the revision note above and [ADR-009](0009-language-configuration.md). It keeps runtime TTS for open-ended speech while giving deterministic, human-verified letter audio.)*
- **Cloud TTS only:** Rejected. Breaks fully-offline principle.
- **SAPI only:** Rejected. Voice quality is insufficient for a primary audio interface, especially for children.
