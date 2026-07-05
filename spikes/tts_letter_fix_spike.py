"""
Research spike: making Piper say ISOLATED LETTERS cleanly.

Background (from tts_reality_spike.py): Piper mangles single letters at every
quality tier, and spelling the name out ("ay", "bee") doesn't reliably help.

Root cause found by inspecting Piper's phonemizer (piper.phonemize_espeak):
espeak-ng — which Piper uses for text->phonemes — ALREADY maps a bare single
letter to its correct letter-NAME phonemes:

    en  a -> ˈeɪ   b -> bˈiː   w -> dˈʌbəljˌuː   h -> ˈeɪtʃ
    de  a -> ˈɑː    w -> vˈeː   z -> tsˈɛt

So the phonemes Piper receives are right. The defect is ACOUSTIC: the VITS model
was trained on sentences and renders a 1–3 phoneme utterance with bad prosody /
artifacts / clipping. SSML <say-as> is NOT a fix — Piper's espeak bridge doesn't
enable SSML, so the tags get read literally.

The known workaround for short-utterance VITS instability is to give the model
sentence-like structure (trailing punctuation, or a carrier) instead of a bare
token. This spike renders each strategy so you can pick the one that sounds clean.

Strategies (per letter):
    bare      "a"            baseline — correct phonemes, too short
    period    "a."           add a sentence terminator
    comma     "a,"           softer terminator
    raw       "[[ˈeɪ]]."     feed espeak's own letter-name phonemes + terminator

Run from repo root on the Windows laptop:
    uv run --with piper-tts python spikes/tts_letter_fix_spike.py        # en + de
    uv run --with piper-tts python spikes/tts_letter_fix_spike.py en

Outputs (open and listen), per language <L> and strategy <S>:
    spikes/tts_fix_<L>_<S>_ALL.wav

Report which strategy gives the cleanest, unambiguous letter names.
"""

import string
import sys
import wave
from pathlib import Path

SPIKES_DIR = Path(__file__).resolve().parent
OUT_DIR = SPIKES_DIR / "tts_fix"
PIPER_LENGTH_SCALE = 1.4

LANGS = {
    "en": {
        "voice": "en_US-lessac-medium",
        "espeak": "en-us",
        "letters": list(string.ascii_lowercase),
    },
    "de": {
        "voice": "de_DE-thorsten-medium",
        "espeak": "de",
        "letters": list(string.ascii_lowercase + "äöüß"),
    },
}

_SAFE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def safe(ch: str) -> str:
    return _SAFE.get(ch, ch)


def stitch(paths: list[Path], out_path: Path, silence_ms: int = 500) -> None:
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


def variants(ch: str, raw_phonemes: str) -> dict[str, str]:
    return {
        "bare": ch,
        "period": f"{ch}.",
        "comma": f"{ch},",
        "raw": f"[[{raw_phonemes}]].",
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    requested = [a.lower() for a in sys.argv[1:]] or list(LANGS)
    codes = [c for c in requested if c in LANGS]

    from piper.voice import PiperVoice
    from piper import SynthesisConfig
    from piper.phonemize_espeak import EspeakPhonemizer

    syn = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE)
    espeak = EspeakPhonemizer()
    OUT_DIR.mkdir(exist_ok=True)

    print("Piper letter-fix spike")
    print(f"Languages: {codes}\n")

    for code in codes:
        cfg = LANGS[code]
        voice_path = SPIKES_DIR / f"{cfg['voice']}.onnx"
        if not voice_path.exists():
            print(f"[{code}] SKIP: {voice_path.name} not on disk.")
            continue
        voice = PiperVoice.load(str(voice_path))
        print(f"[{code}] voice {cfg['voice']}")

        # strategy -> list of per-letter wavs
        buckets: dict[str, list[Path]] = {}
        for ch in cfg["letters"]:
            ph = espeak.phonemize(cfg["espeak"], ch)
            raw = "".join("".join(s) for s in ph)
            for strat, text in variants(ch, raw).items():
                out = OUT_DIR / f"{code}_{strat}_{safe(ch)}.wav"
                with wave.open(str(out), "wb") as wf:
                    voice.synthesize_wav(text, wf, syn_config=syn)
                buckets.setdefault(strat, []).append(out)

        for strat, paths in buckets.items():
            allp = SPIKES_DIR / f"tts_fix_{code}_{strat}_ALL.wav"
            stitch(paths, allp)
            print(f"    {strat:8} -> {allp.name}")

    print("\nLISTEN: for each language compare the strategies on the same letters.")
    print("Report which one gives clean, unambiguous letter names (and whether the")
    print("'raw' phoneme path matches 'bare' — if so the defect is purely acoustic).")


if __name__ == "__main__":
    main()
