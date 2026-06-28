"""
Spike: TTS reality — isolated letter names + mid-utterance interrupt

Resolves two corner cases logged in docs/roadmap.md:

  A1  Isolated letter-name pronunciation. The entire Alpha loop is "TTS says the
      letter -> child types it" (ADR-012). ADR-009 deleted per-language letter
      names on the assumption that "neural TTS pronounces letter names correctly."
      But Alpha's *default* TTS is pyttsx3/SAPI, not Piper. Does SAPI (and espeak)
      say a bare "a" as the LETTER NAME (/eɪ/) or as the article/schwa (/ə/)?
      If unreliable, Alpha needs a per-language letter-name map — new scope.

  C12 Mid-utterance interrupt. ADR-012 requires TTS to cancel immediately on
      keypress. Piper (we own the buffer) can. pyttsx3/SAPI's stop() is reputedly
      flaky/blocking. Can we actually cut a SAPI utterance at ~300ms?

This spike PRODUCES AUDIO YOU MUST LISTEN TO — pronunciation cannot be judged
from stdout. It writes per-letter WAVs plus one stitched "all letters" WAV per
engine, then runs a timed interrupt test.

Run from repo root on the Windows laptop (SAPI is the Alpha default there):
    uv run --with piper-tts python spikes/tts_reality_spike.py

Without --with piper-tts the Piper section is skipped (pyttsx3/SAPI still runs).
On the headless Linux box the letter WAVs still generate (espeak save-to-file),
but the interrupt test needs an audio device and may be skipped.

Outputs (open and listen):
    spikes/tts_letters/                     per-letter WAVs, both engines
    spikes/tts_letters_pyttsx3_ALL.wav      all 26 letters, SAPI/espeak
    spikes/tts_letters_piper_ALL.wav        all 26 letters, Piper (if available)
    spikes/tts_confusables_pyttsx3.wav      "E" vs "E as in echo" pairs

Then: listen, and report back WHICH letters are spoken wrong (name vs word/schwa),
plus the printed interrupt timing. Paste the full stdout back too.
"""

import string
import sys
import time
import wave
from pathlib import Path

SPIKES_DIR = Path(__file__).resolve().parent
LETTERS_DIR = SPIKES_DIR / "tts_letters"
PIPER_VOICE = "en_US-lessac-low"
PIPER_VOICE_PATH = SPIKES_DIR / f"{PIPER_VOICE}.onnx"

LETTERS = list(string.ascii_lowercase)

# Confusable letters whose bare name is most likely to be misread, with the
# ADR-023 "X as in <word>" disambiguation form to hear as a fallback preview.
CONFUSABLES = {
    "a": "apple", "e": "echo", "i": "igloo", "o": "ocean",
    "u": "umbrella", "m": "mouse", "n": "nose",
}

INTERRUPT_PHRASE = (
    "This is a deliberately long sentence used only to test whether the "
    "text to speech engine can be interrupted cleanly in the middle of "
    "speaking, well before it reaches the final word of the sentence."
)
INTERRUPT_AT_S = 0.30


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
    import pyttsx3
    return pyttsx3.init()


def _say_live(eng, text: str) -> None:
    eng.say(text)
    eng.runAndWait()


def pyttsx3_letters() -> bool:
    section("1. pyttsx3 / SAPI — isolated letter names")
    try:
        eng = pyttsx3_engine()
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: could not init pyttsx3: {e}")
        return False

    driver = eng.getProperty("voice")
    print(f"  engine up. active voice id: {driver}")

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
    for i, ch in enumerate(LETTERS, 1):
        out = LETTERS_DIR / f"pyttsx3_{i:02d}_{ch}.wav"
        eng.save_to_file(ch, str(out))
        eng.runAndWait()
        per_letter.append(out)
    print(f"  wrote {len(per_letter)} per-letter WAVs to {LETTERS_DIR}/")

    all_path = SPIKES_DIR / "tts_letters_pyttsx3_ALL.wav"
    stitch_wavs(per_letter, all_path)
    print(f"  stitched -> {all_path.name}  (listen: a,b,c,... — letter NAMES?)")

    # Confusables: "X" then "X as in <word>"
    conf_paths: list[Path] = []
    for ch, word in CONFUSABLES.items():
        p1 = LETTERS_DIR / f"pyttsx3_conf_{ch}_bare.wav"
        p2 = LETTERS_DIR / f"pyttsx3_conf_{ch}_asin.wav"
        eng.save_to_file(ch, str(p1)); eng.runAndWait()
        eng.save_to_file(f"{ch}, as in {word}", str(p2)); eng.runAndWait()
        conf_paths.extend([p1, p2])
    conf_all = SPIKES_DIR / "tts_confusables_pyttsx3.wav"
    stitch_wavs(conf_paths, conf_all, silence_ms=300)
    print(f"  stitched confusable pairs -> {conf_all.name}")
    print(f"  (bare letter then the 'X as in {list(CONFUSABLES.values())[0]}' fallback, per letter)")
    return True


def pyttsx3_interrupt() -> None:
    section("2. pyttsx3 / SAPI — mid-utterance interrupt (C12)")
    import threading
    try:
        eng = pyttsx3_engine()
    except Exception as e:  # noqa: BLE001
        print(f"  SKIP: could not init pyttsx3: {e}")
        return

    # Baseline: full utterance.
    try:
        t0 = time.perf_counter()
        eng.say(INTERRUPT_PHRASE)
        eng.runAndWait()
        full = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        print(f"  SKIP: playback failed (no audio device?): {e}")
        return
    print(f"  full utterance duration:        {full:6.2f}s")

    # Interrupted: stop() from another thread after INTERRUPT_AT_S.
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
    print("  (Confirm by ear: did the second clip cut off mid-sentence?)")


# ----------------------------------------------------------------- Piper --

def piper_letters() -> None:
    section("3. Piper — isolated letter names (optional)")
    if not PIPER_VOICE_PATH.exists():
        print(f"  SKIP: {PIPER_VOICE_PATH.name} not found in spikes/.")
        print("  (Run piper_tts_spike.py first to download it, or ignore — Piper is the")
        print("   Beta default; the A1 risk is specifically the Alpha SAPI path above.)")
        return
    try:
        from piper.voice import PiperVoice
    except ImportError:
        print("  SKIP: piper not installed. Re-run with --with piper-tts to include Piper.")
        return

    voice = PiperVoice.load(str(PIPER_VOICE_PATH))
    LETTERS_DIR.mkdir(exist_ok=True)
    per_letter: list[Path] = []
    for i, ch in enumerate(LETTERS, 1):
        out = LETTERS_DIR / f"piper_{i:02d}_{ch}.wav"
        with wave.open(str(out), "wb") as wf:
            voice.synthesize_wav(ch, wf)
        per_letter.append(out)
    all_path = SPIKES_DIR / "tts_letters_piper_ALL.wav"
    stitch_wavs(per_letter, all_path)
    print(f"  wrote {len(per_letter)} per-letter WAVs; stitched -> {all_path.name}")
    print("  (Compare Piper's letter names against SAPI's — does neural TTS do better?)")


def main() -> None:
    print("TTS Reality Spike")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")

    ok = pyttsx3_letters()
    if ok:
        pyttsx3_interrupt()
    piper_letters()

    section("DONE — now LISTEN")
    print("  1. Play tts_letters_pyttsx3_ALL.wav. For each letter, note whether you")
    print("     heard the LETTER NAME (a=/eɪ/, e=/iː/) or a word/schwa (a=/ə/).")
    print("     List every letter that is wrong — those need an explicit name map.")
    print("  2. Play tts_confusables_pyttsx3.wav to hear the 'X as in <word>' fallback.")
    print("  3. If Piper ran, compare tts_letters_piper_ALL.wav.")
    print("  4. Report the interrupt VERDICT printed above.")
    print("\n  Paste the stdout plus your by-ear letter findings back to Claude.")


if __name__ == "__main__":
    main()
