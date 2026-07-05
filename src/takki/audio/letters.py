from typing import Protocol


class LetterAudioSource(Protocol):
    # Isolated letters are a closed, fixed per-language set, not open-ended
    # speech. Neural TTS distorts ultra-short utterances and SAPI only covers
    # installed Windows voices, so letter audio is resolved through a priority
    # chain (per-profile recording -> curated clip -> TTS fallback) behind this
    # seam rather than by general runtime synthesis.
    # See docs/research/tts-letter-pronunciation.md.
    def play(self, char: str) -> None: ...

    def stop(self) -> None: ...
