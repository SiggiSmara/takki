"""
Spike: espeak-ng as a DIRECT audio synthesizer for isolated letters.

Why: Piper (neural) renders isolated letters unreliably at every tier/voice —
the phonemes espeak hands it are correct, but the VITS acoustic model distorts
1–3 phoneme utterances (see tts_reality_spike.py / tts_letter_fix_spike.py).
SAPI says letters cleanly but only for languages with an installed Windows voice
(en, de here — NOT Icelandic). espeak-ng is rule-based, so isolated letters are
deterministic and it covers 100+ languages incl. Icelandic. The open question is
purely TIMBRE: is the robotic formant voice acceptable for a child's letter cue?

This spike drives the espeak-ng SHARED LIBRARY directly via ctypes — no system
install, no admin, no espeak-ng.exe. The DLL + data come from the pip package
`espeakng-loader` (bundleable, offline after install), which is the same
distribution shape the product would use.

Run from repo root on the Windows laptop:
    uv run --with espeakng-loader python spikes/tts_espeak_spike.py        # en de is
    uv run --with espeakng-loader python spikes/tts_espeak_spike.py en

Outputs (open and listen), per language <L>:
    spikes/tts_espeak_<L>_ALL.wav     full alphabet, one robotic letter each

Report: is the espeak voice intelligible/acceptable for letter cues? Compare to
the SAPI files from tts_reality_spike.py. Does Icelandic work where SAPI can't?
"""

import ctypes
import string
import sys
import wave
from pathlib import Path

SPIKES_DIR = Path(__file__).resolve().parent

# espeak-ng C API constants
AUDIO_OUTPUT_SYNCHRONOUS = 0x02
POS_CHARACTER = 1
espeakCHARS_UTF8 = 0x01

LANGS = {
    "en": {"voice": "en-us", "letters": list(string.ascii_lowercase)},
    "de": {"voice": "de", "letters": list(string.ascii_lowercase + "äöüß")},
    # Icelandic alphabet (no c q w z natively; adds á é í ó ú ý þ æ ö ð).
    "is": {"voice": "is", "letters": list("aábdðeéfghiíjklmnoóprstuúvxyýþæö")},
}

SPEED_WPM = 130  # slower = clearer single letters

_SAFE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "á": "a1", "é": "e1",
         "í": "i1", "ó": "o1", "ú": "u1", "ý": "y1", "þ": "th", "æ": "ae2",
         "ð": "dh"}


def safe(ch: str) -> str:
    return _SAFE.get(ch, ch)


def stitch(paths, out_path, silence_ms=500):
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


# Synchronous synth callback collects 16-bit mono samples into a bytearray.
SYNTH_CB = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_short),
    ctypes.c_int,
    ctypes.c_void_p,
)


class Espeak:
    def __init__(self, lib_path: str, data_parent: str):
        import os
        os.add_dll_directory(os.path.dirname(lib_path))
        self.lib = ctypes.CDLL(lib_path)
        self.lib.espeak_Synth.restype = ctypes.c_int
        self.samplerate = self.lib.espeak_Initialize(
            AUDIO_OUTPUT_SYNCHRONOUS, 0, data_parent.encode("utf-8"), 0
        )
        if self.samplerate <= 0:
            raise RuntimeError(f"espeak_Initialize failed: {self.samplerate}")
        self._buf = bytearray()

        def _cb(wav, numsamples, events):
            if numsamples > 0:
                self._buf += ctypes.string_at(wav, numsamples * 2)
            return 0

        self._cb = SYNTH_CB(_cb)
        self.lib.espeak_SetSynthCallback(self._cb)

    def set_voice(self, name: str):
        rc = self.lib.espeak_SetVoiceByName(name.encode("utf-8"))
        if rc != 0:
            raise RuntimeError(f"no espeak voice '{name}' (rc={rc})")

    def set_speed(self, wpm: int):
        # espeakRATE = 1
        self.lib.espeak_SetParameter(1, wpm, 0)

    def synth_to_wav(self, text: str, path: Path):
        self._buf = bytearray()
        data = text.encode("utf-8")
        self.lib.espeak_Synth(
            data, len(data) + 1, 0, POS_CHARACTER, 0,
            espeakCHARS_UTF8, None, None,
        )
        self.lib.espeak_Synchronize()
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.samplerate)
            wf.writeframes(bytes(self._buf))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    requested = [a.lower() for a in sys.argv[1:]] or list(LANGS)
    codes = [c for c in requested if c in LANGS]

    import espeakng_loader
    lib = espeakng_loader.get_library_path()
    data_dir = Path(espeakng_loader.get_data_path())
    data_parent = str(data_dir.parent)  # API wants the dir CONTAINING espeak-ng-data

    print("espeak-ng letter spike")
    print(f"lib:  {lib}")
    print(f"data: {data_dir}")
    eng = Espeak(lib, data_parent)
    eng.set_speed(SPEED_WPM)
    print(f"samplerate: {eng.samplerate} Hz   languages: {codes}\n")

    for code in codes:
        cfg = LANGS[code]
        try:
            eng.set_voice(cfg["voice"])
        except RuntimeError as e:
            print(f"[{code}] SKIP: {e}")
            continue
        letter_dir = SPIKES_DIR / "tts_letters"
        letter_dir.mkdir(exist_ok=True)
        paths = []
        for i, ch in enumerate(cfg["letters"], 1):
            out = letter_dir / f"espeak_{code}_{i:02d}_{safe(ch)}.wav"
            eng.synth_to_wav(ch, out)
            paths.append(out)
        allp = SPIKES_DIR / f"tts_espeak_{code}_ALL.wav"
        stitch(paths, allp)
        print(f"[{code}] voice {cfg['voice']}: {len(paths)} letters -> {allp.name}")

    print("\nLISTEN: is the espeak voice acceptable for letter cues? Compare to")
    print("the SAPI tts_letters_pyttsx3_*_ALL.wav files. Note Icelandic — SAPI")
    print("cannot do it, espeak can. Report intelligibility + any wrong letters.")


if __name__ == "__main__":
    main()
