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
    # Returns the id its finish will be reported under, as a SpeechFinished on
    # the core's inbound queue. The core needs it to know whether a letter is
    # still outstanding: without it a second letter stacks behind the first and
    # plays over the cue and the next prompt, and a stop() cannot be aimed
    # (alpha session 11). It also times the letter by it and holds the rest of
    # an introduction on it (ADR-012 § A letter inside a sequence), so a source
    # that plays its own audio (a clip player, Beta) must report its finish too
    # (ADR-030).
    def play(self, char: str) -> int: ...

    def stop(self) -> None: ...
