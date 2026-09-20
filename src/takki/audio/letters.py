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
    # Returns the utterance id when this source speaks through the shared TTS
    # worker, and None when it plays its own audio (a clip player, Beta). The
    # core needs the id to know whether a letter is still outstanding: without
    # it a second letter stacks behind the first and plays over the cue and the
    # next prompt, and a stop() cannot be aimed (alpha session 11).
    def play(self, char: str) -> int | None: ...

    def stop(self) -> None: ...
