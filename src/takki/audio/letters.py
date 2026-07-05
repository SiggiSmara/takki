from typing import Protocol


class LetterAudioSource(Protocol):
    # Isolated letters are a closed, fixed per-language set, not open-ended
    # speech. Neural TTS distorts ultra-short utterances and SAPI only covers
    # installed Windows voices, so letter audio is resolved through a three-layer
    # priority chain behind this seam rather than by general runtime synthesis:
    #   Personal (child's own recording, per profile -- ADR-030)
    #   -> Base (human-recorded per-language clips, bundled or contributed)
    #   -> Synthetic (runtime TTS floor; SAPI or espeak-ng, never empty).
    # Resolution walks down until it finds audio; the floor guarantees a result.
    # See ADR-003 (Letter audio) and docs/research/tts-letter-pronunciation.md.
    def play(self, char: str) -> None: ...

    def stop(self) -> None: ...
