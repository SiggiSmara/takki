"""What the session loop opens: a prompt and its kind (ADR-024, ADR-027 § Presses that are not attempts).

Its own module because both the drill generator, which makes prompts, and the
attempt counter, which decides where a press on one is kept, read it.
"""

from dataclasses import dataclass
from enum import Enum, auto


class PromptKind(Enum):
    """What a prompt's first press is (ADR-027 § Presses that are not attempts)."""

    # An attempt: a listened press at Choose or Travel, or any prompt in general practice.
    COUNTED = auto()
    # A predictable press at Reach, kept in `reach_presses` and nowhere else.
    REACH = auto()
    # A letter asked again after a miss or a restart: predictable, kept nowhere.
    REASK = auto()
    # The rest cue: answered by the rest keys and never counted.
    REST = auto()


@dataclass(frozen=True)
class Prompt:
    kind: PromptKind
    # The letter asked for; None for a rest cue, which asks by finger.
    grapheme: str | None = None
    # A rest cue: the characters of the rest keys it waits for, one per finger
    # the letter was typed with, in keystroke order.
    owed: tuple[str, ...] = ()
    # A rest cue: the fingers it asks back, ADR-011's `prev_char` after it.
    fingers: str | None = None
