from collections import deque
from statistics import median

from takki import config
from takki.persistence import Store


class LetterLengths:
    """How long each letter takes to say under one voice and rate (ADR-011 § letter_lengths)."""

    def __init__(
        self,
        store: Store,
        profile_id: int,
        voice: str,
        rate: float,
        sample: int = config.LETTER_LENGTH_SAMPLE,
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        # A length belongs to a voice and a rate, so only the lengths measured
        # under the pair in use are read, and a new pair starts with none.
        self._voice = voice
        self._rate = rate
        self._sample = sample
        self._lengths: dict[str, deque[int]] = {}
        self._unwritten: list[tuple[str, int]] = []

    def usual(self, letter: str) -> int | None:
        """The median over the letter's latest full playbacks, or None when it has none."""
        lengths = self._of(letter)
        return round(median(lengths)) if lengths else None

    def record(self, letter: str, length_ms: int) -> None:
        """One playback that ran to its end, in an introduction or a prompt."""
        self._of(letter).append(length_ms)
        self._unwritten.append((letter, length_ms))

    def flush(self) -> None:
        # Written at a block boundary and not as each letter ends: a letter
        # often ends just before the child's press, and a write there is delay
        # ahead of the cue.
        if self._unwritten:
            self._store.append_letter_lengths(
                self._profile_id, self._voice, self._rate, self._unwritten
            )
            self._unwritten = []

    def _of(self, letter: str) -> deque[int]:
        if letter not in self._lengths:
            self._lengths[letter] = deque(
                self._store.letter_lengths(self._profile_id, letter, self._voice, self._rate),
                maxlen=self._sample,
            )
        return self._lengths[letter]
