"""
Spike: TTS reality — isolated letter names + mid-utterance interrupt

Resolves two corner cases logged in docs/roadmap.md:

  A1  Isolated letter-name pronunciation. The entire Alpha loop is "TTS says the
      letter -> child types it" (ADR-012). ADR-009 deleted per-language letter
      names on the assumption that "neural TTS pronounces letter names correctly."
      Reality so far (English): SAPI says letters well; Piper (neural) struggles
      even when fed the spelled-out name. This run adds German to check whether
      that holds across languages — i.e. whether the deleted per-language
      letter-name map needs to come back, and whether letters want the SAPI
      engine even where Piper is the default for connected speech.

  C12 Mid-utterance interrupt. ADR-012 requires TTS to cancel immediately on
      keypress. Piper (we own the buffer) can. pyttsx3/SAPI's stop() is reputedly
      flaky/blocking. Can we actually cut a SAPI utterance at ~300ms?

This spike PRODUCES AUDIO YOU MUST LISTEN TO — pronunciation cannot be judged
from stdout. Per language it writes per-letter WAVs plus stitched "all letters"
WAVs per engine, then runs one timed interrupt test (language-independent).

Run from repo root on the Windows laptop (both SAPI voices must be installed):
    uv run --with piper-tts python spikes/tts_reality_spike.py          # en + de
    uv run --with piper-tts python spikes/tts_reality_spike.py en       # one lang
    uv run --with piper-tts python spikes/tts_reality_spike.py de

Without --with piper-tts the Piper sections are skipped (SAPI still runs).
German needs the "Microsoft Hedda" SAPI voice and spikes/de_DE-thorsten-low.onnx
(download: uv run --with piper-tts python -m piper.download_voices
 --download-dir spikes de_DE-thorsten-low).

Outputs per language <L> (open and listen):
    spikes/tts_letters/                          per-letter WAVs, both engines
    spikes/tts_letters_pyttsx3_<L>_ALL.wav       all letters, SAPI
    spikes/tts_letters_piper_<L>_ALL.wav         all letters, Piper bare char
    spikes/tts_letters_piper_<L>_NAMES_ALL.wav   all letters, Piper spelled name
    spikes/tts_confusables_pyttsx3_<L>.wav       "X" vs "X as in word" (en only)

Then: listen, report which letters are wrong per language/engine, plus the
interrupt timing. Paste the full stdout back too.
"""

import string
import sys
import time
import wave
from pathlib import Path

SPIKES_DIR = Path(__file__).resolve().parent
LETTERS_DIR = SPIKES_DIR / "tts_letters"

# Slow the speech for single letters — the default rate clips them together.
SAPI_RATE = 120          # SAPI words/min; default ~200. Lower = slower.
PIPER_LENGTH_SCALE = 1.6  # Piper duration multiplier; >1.0 = slower.

# Letter-NAME spellings. The A1 fallback: if an engine can't say a bare
# character as its letter name, feed it the name spelled phonetically instead.
# This is the per-language map ADR-009 deleted — testing whether Piper needs it.
EN_NAMES = {
    "a": "ay", "b": "bee", "c": "see", "d": "dee", "e": "ee", "f": "eff",
    "g": "jee", "h": "aitch", "i": "eye", "j": "jay", "k": "kay", "l": "el",
    "m": "em", "n": "en", "o": "oh", "p": "pee", "q": "cue", "r": "ar",
    "s": "ess", "t": "tee", "u": "you", "v": "vee", "w": "double-you",
    "x": "ex", "y": "why", "z": "zee",
}

DE_NAMES = {
    "a": "ah", "b": "beh", "c": "tseh", "d": "deh", "e": "eh", "f": "eff",
    "g": "geh", "h": "hah", "i": "ih", "j": "jott", "k": "kah", "l": "ell",
    "m": "emm", "n": "enn", "o": "oh", "p": "peh", "q": "kuh", "r": "err",
    "s": "ess", "t": "teh", "u": "uh", "v": "fau", "w": "weh", "x": "iks",
    "y": "üpsilon", "z": "tsett",
    "ä": "ä", "ö": "ö", "ü": "ü", "ß": "eszett",
}

LANGS = {
    "en": {
        "label": "English",
        "letters": list(string.ascii_lowercase),
        "names": EN_NAMES,
        # low/medium/high tiers — only those present on disk are rendered.
        "piper_voices": [
            "en_US-lessac-low", "en_US-lessac-medium", "en_US-lessac-high",
        ],
        "sapi_match": None,  # default voice (David)
        "confusables": {
            "a": "apple", "e": "echo", "i": "igloo", "o": "ocean",
            "u": "umbrella", "m": "mouse", "n": "nose",
        },
    },
    "de": {
        "label": "German",
        "letters": list("abcdefghijklmnopqrstuvwxyzäöüß"),
        "names": DE_NAMES,
        "piper_voices": [
            "de_DE-thorsten-low", "de_DE-thorsten-medium", "de_DE-thorsten-high",
        ],
        "sapi_match": "DE-DE",  # Microsoft Hedda
        "confusables": None,
    },
}

INTERRUPT_PHRASE = (
    "This is a deliberately long sentence used only to test whether the "
    "text to speech engine can be interrupted cleanly in the middle of "
    "speaking, well before it reaches the final word of the sentence."
)
INTERRUPT_AT_S = 0.30

_SAFE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def safe(ch: str) -> str:
    return _SAFE.get(ch, ch)


def section(title: str) -> None:
    print(f"\n{'=' * 64}\n  {title}\n{'=' * 64}")


def stitch_wavs(paths: list[Path], out_path: Path, silence_ms: int = 450) -> None:
    """Concatenate same-format WAVs with inserted silence. Assumes all clips
    share the params of the first clip (true within one engine + settings)."""
    paths = [p for p in paths if p.exists()]
    if not paths:
        return
    with wave.open(str(paths[0]), "rb") as w0:
        params = w0.getparams()
    silence = b"\x00" * (
        params.sampwidth * params.nchannels * int(params.framerate * silence_ms / 1000)
    )
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for p in paths:
            with wave.open(str(p), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            out.writeframes(silence)


# --------------------------------------------------------------- pyttsx3 --

def pyttsx3_engine():
    # NOT pyttsx3.init(): it caches one engine in a module-level WeakValueDict,
    # so a second runAndWait() on the same instance deadlocks the SAPI5 driver
    # (the loop hang this spike originally hit). A fresh Engine() per call has
    # its own driver and runs cleanly. See spikes notes / pyttsx3 #257.
    import pyttsx3
    from pyttsx3.engine import Engine
    return Engine(driverName=None, debug=False)


def _say_live(eng, text: str) -> None:
    eng.say(text)
    eng.runAndWait()


def _say_live(eng, text: str) -> None:
    eng.say(text)
    eng.runAndWait()


def resolve_sapi_voice(match: str | None) -> str | None:
    """Return the SAPI voice id whose id contains `match`, or None. None match
    means 'use the engine default'; a match that finds nothing returns None and
    the caller should skip rather than render with the wrong-language voice."""
    if not match:
        return None
    eng = pyttsx3_engine()
    for v in eng.getProperty("voices"):
        if match.lower() in v.id.lower():
            return v.id
    return None


def sapi_save(text: str, path: Path, voice_id: str | None) -> None:
    eng = pyttsx3_engine()
    if voice_id:
        eng.setProperty("voice", voice_id)
    eng.setProperty("rate", SAPI_RATE)
    eng.save_to_file(text, str(path))
    eng.runAndWait()


def pyttsx3_letters(code: str, cfg: dict) -> None:
    section(f"SAPI letters — {cfg['label']}")
    if cfg["sapi_match"]:
        voice_id = resolve_sapi_voice(cfg["sapi_match"])
        if not voice_id:
            print(f"  SKIP: no SAPI voice matching '{cfg['sapi_match']}' installed.")
            print("  (Install the language's Microsoft voice via Windows Settings ->")
            print("   Time & language -> Speech, then re-run.)")
            return
    else:
        voice_id = None
    print(f"  voice id: {voice_id or '(engine default)'}")

    # SAPI's save_to_file + runAndWait hangs on many Windows setups (the
    # file-stream 'done' event never fires). Play letters LIVE instead — the
    # whole point is to hear them. espeak/Linux saves fine, keep files there.
    if sys.platform == "win32":
        print("  win32: playing letters LIVE (SAPI save_to_file hangs).")
        print("  LISTEN: each should be the letter NAME (a=/eɪ/, e=/iː/), not a word/schwa.")
        for i, ch in enumerate(LETTERS, 1):
            print(f"    {i:02d} {ch}", flush=True)
            _say_live(eng, ch)
        print("  confusables — bare letter, then 'X as in <word>':")
        for ch, word in CONFUSABLES.items():
            print(f"    {ch}  /  {ch} as in {word}", flush=True)
            _say_live(eng, ch)
            _say_live(eng, f"{ch}, as in {word}")
        return True

    LETTERS_DIR.mkdir(exist_ok=True)

    per_letter: list[Path] = []
    for i, ch in enumerate(cfg["letters"], 1):
        out = LETTERS_DIR / f"pyttsx3_{code}_{i:02d}_{safe(ch)}.wav"
        sapi_save(ch, out, voice_id)
        per_letter.append(out)
    all_path = SPIKES_DIR / f"tts_letters_pyttsx3_{code}_ALL.wav"
    stitch_wavs(per_letter, all_path)
    print(f"  wrote {len(per_letter)} letters; stitched -> {all_path.name}")

    if cfg["confusables"]:
        conf_paths: list[Path] = []
        for ch, word in cfg["confusables"].items():
            p1 = LETTERS_DIR / f"pyttsx3_{code}_conf_{ch}_bare.wav"
            p2 = LETTERS_DIR / f"pyttsx3_{code}_conf_{ch}_asin.wav"
            sapi_save(ch, p1, voice_id)
            sapi_save(f"{ch}, as in {word}", p2, voice_id)
            conf_paths.extend([p1, p2])
        conf_all = SPIKES_DIR / f"tts_confusables_pyttsx3_{code}.wav"
        stitch_wavs(conf_paths, conf_all, silence_ms=300)
        print(f"  stitched confusable pairs -> {conf_all.name}")


# ----------------------------------------------------------------- Piper --

def piper_letters(code: str, cfg: dict) -> None:
    section(f"Piper letters — {cfg['label']} (low/medium/high tiers)")
    try:
        from piper.voice import PiperVoice
        from piper import SynthesisConfig
    except ImportError:
        print("  SKIP: piper not installed. Re-run with --with piper-tts.")
        return

    syn = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE)
    LETTERS_DIR.mkdir(exist_ok=True)
    rendered = 0
    for voice_name in cfg["piper_voices"]:
        tier = voice_name.rsplit("-", 1)[-1]
        voice_path = SPIKES_DIR / f"{voice_name}.onnx"
        if not voice_path.exists():
            print(f"  [{tier:6}] SKIP: {voice_path.name} not on disk.")
            continue
        voice = PiperVoice.load(str(voice_path))

        bare: list[Path] = []
        named: list[Path] = []
        for i, ch in enumerate(cfg["letters"], 1):
            b = LETTERS_DIR / f"piper_{code}_{tier}_{i:02d}_{safe(ch)}.wav"
            n = LETTERS_DIR / f"piper_{code}_{tier}_name_{i:02d}_{safe(ch)}.wav"
            with wave.open(str(b), "wb") as wf:
                voice.synthesize_wav(ch, wf, syn_config=syn)
            with wave.open(str(n), "wb") as wf:
                voice.synthesize_wav(cfg["names"][ch], wf, syn_config=syn)
            bare.append(b)
            named.append(n)
        bare_path = SPIKES_DIR / f"tts_letters_piper_{code}_{tier}_ALL.wav"
        names_path = SPIKES_DIR / f"tts_letters_piper_{code}_{tier}_NAMES_ALL.wav"
        stitch_wavs(bare, bare_path)
        stitch_wavs(named, names_path)
        print(f"  [{tier:6}] -> {bare_path.name}  +  {names_path.name}")
        rendered += 1

    if rendered == 0:
        print("  (No tiers on disk. Download e.g.: uv run --with piper-tts python")
        print(f"   -m piper.download_voices --download-dir spikes {cfg['piper_voices'][1]})")


# -------------------------------------------------------------- interrupt --

def pyttsx3_interrupt() -> None:
    section("Interrupt — SAPI mid-utterance (C12, language-independent)")
    import threading
    try:
        eng = pyttsx3_engine()
        t0 = time.perf_counter()
        eng.say(INTERRUPT_PHRASE)
        eng.runAndWait()
        full = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        print(f"  SKIP: playback failed (no audio device?): {e}")
        return
    print(f"  full utterance duration:        {full:6.2f}s")

    eng2 = pyttsx3_engine()

    def stopper() -> None:
        time.sleep(INTERRUPT_AT_S)
        eng2.stop()

    th = threading.Thread(target=stopper)
    eng2.say(INTERRUPT_PHRASE)
    th.start()
    t0 = time.perf_counter()
    eng2.runAndWait()
    interrupted = time.perf_counter() - t0
    th.join()
    print(f"  stop() called at {INTERRUPT_AT_S:.2f}s, returned at: {interrupted:6.2f}s")

    if interrupted < full * 0.6:
        verdict = "INTERRUPT WORKS — stop() cut the utterance early."
    else:
        verdict = "INTERRUPT FAILED — utterance ran (nearly) to completion despite stop()."
    print(f"  VERDICT: {verdict}")


def main() -> None:
    # The summary prints IPA (/eɪ/ etc.) and umlauts; the default Windows console
    # is cp1252 and would crash on encode. UTF-8 with replace is harmless.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    requested = [a.lower() for a in sys.argv[1:]] or list(LANGS)
    codes = [c for c in requested if c in LANGS]
    if not codes:
        print(f"Unknown language(s) {requested}. Available: {list(LANGS)}")
        return

    print("TTS Reality Spike")
    print(f"Python: {sys.version.split()[0]}  Platform: {sys.platform}")
    print(f"Languages: {codes}")

    for code in codes:
        cfg = LANGS[code]
        pyttsx3_letters(code, cfg)
        piper_letters(code, cfg)

    pyttsx3_interrupt()

    section("DONE — now LISTEN")
    print("  Per language, the SAPI baseline plus every Piper tier on disk:")
    for code in codes:
        print(f"    {code}: tts_letters_pyttsx3_{code}_ALL.wav                 (SAPI baseline)")
        print(f"        tts_letters_piper_{code}_<tier>_ALL.wav           (Piper bare char)")
        print(f"        tts_letters_piper_{code}_<tier>_NAMES_ALL.wav     (Piper spelled name)")
    print("  Compare tiers (low vs medium vs high): does a bigger model say")
    print("  isolated letters better, or is it a structural neural-TTS limit?")
    print("  For each letter note: LETTER NAME vs word/schwa/garbled. List which")
    print("  letters fail per engine/tier/language. Then report the interrupt")
    print("  VERDICT above. Paste stdout + by-ear findings back to Claude.")


if __name__ == "__main__":
    main()
