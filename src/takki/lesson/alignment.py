"""The keyboard alignment (ADR-033 § The alignment): the child placing their hands.

What is asked, what a press means and what the store is told. No speech and no
timing: the session loop speaks the asks and owns every deadline. Nothing here
is timed or counted, and nothing writes `key_attempts` or `key_stats`.
"""

from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from enum import Enum, auto

from takki import config
from takki.lesson.introducer import (
    ANCHOR_COLUMNS,
    FINGER_NAMES,
    HOME_ROW,
    MODIFIER_NAMES,
)
from takki.lesson.milestones import cold_starts, settled
from takki.persistence import RestKey, Store
from takki.platform.layout import (
    COL_TO_FINGER,
    L_IDX,
    L_MID,
    L_PINK,
    L_RING,
    R_IDX,
    R_MID,
    R_PINK,
    R_RING,
    Layout,
    letters_by_position,
)

Cell = tuple[int, int]

# Index fingers on the bumps, then little fingers, then middle and ring: the
# bump and the little finger fix the hand's span (ADR-033).
ROUND: tuple[str, ...] = (L_IDX, R_IDX, L_PINK, R_PINK, L_MID, R_MID, L_RING, R_RING)
BUMPS: dict[str, Cell] = {
    L_IDX: (HOME_ROW, ANCHOR_COLUMNS[0]),
    R_IDX: (HOME_ROW, ANCHOR_COLUMNS[1]),
}


class Press(Enum):
    LANDED = auto()
    # A landing, written unvalidated: the index finger missed its bump.
    OFF_BUMP = auto()
    # Outside the finger's column, or on a key that is no cell. Not a landing.
    ELSEWHERE = auto()
    # The key chosen in answer to the question. Not a landing.
    ANSWERED = auto()


@dataclass(frozen=True)
class Ask:
    finger: str
    # "Which one do you want", with the keys the finger landed on this session.
    question: bool = False
    landed: tuple[Cell, ...] = ()


def _hand(finger: str) -> str:
    return finger[0]


class Alignment:
    """One session's alignment, from the first round to the last question."""

    def __init__(
        self,
        layout: Layout,
        store: Store,
        profile_id: int,
        session_id: int,
        *,
        known: Callable[[], AbstractSet[str]],
        shares: Mapping[str, float],
        now: Callable[[], str] | None = None,
    ) -> None:
        self._layout = layout
        self._store = store
        self._profile_id = profile_id
        self._session_id = session_id
        self._known = known
        self._shares = shares
        self._now = now
        current = self._current()
        # The first lesson is owed until the child has landed once: a session
        # quit before any press has written the bump rows and nothing else.
        self.cold = not store.landings(profile_id)
        for finger, (row, col) in BUMPS.items():
            # The one rest key the child does not choose, and only on its cell.
            if finger not in current:
                store.choose_rest_key(profile_id, finger, row, col, "bump", self._stamp())
        # The full round retires when every key has passed its own test, and
        # never while a finger is not ready (ADR-033; #12m session (5)). Then
        # the opening is the two bumps.
        current = self._current()
        self.full = not all(
            (key := current.get(finger)) is not None
            and key.ready_at is not None
            and key.passed_at is not None
            for finger in ROUND
        )
        self.rounds = 0
        self.done = False
        self._left: list[str] = []
        self._bump_ok: dict[str, bool] = {}
        self._questions: list[Ask] = []
        self._new_round = False
        self._start_round()

    @property
    def ask(self) -> Ask | None:
        """What is asked now, or None once the alignment is done."""
        if self._questions:
            return self._questions[0]
        if self._left:
            return Ask(self._left[0])
        return None

    def take_new_round(self) -> bool:
        """True once per round started since the last call: the hands come off first."""
        new, self._new_round = self._new_round, False
        return new

    def press(self, cell: Cell | None) -> Press:
        """A press in answer to `ask`; `cell` is None for a key that is no cell."""
        ask = self.ask
        assert ask is not None
        if cell is None or COL_TO_FINGER.get(cell[1]) != ask.finger:
            return Press.ELSEWHERE
        if ask.question:
            return self._answer(ask.finger, cell)
        finger = self._left.pop(0)
        if finger in BUMPS:
            validated = self._bump_ok[_hand(finger)] = cell == BUMPS[finger]
        else:
            # A hand whose bump press missed has its other presses not counted.
            validated = self._bump_ok.get(_hand(finger), False)
        self._store.record_landing(
            self._profile_id,
            self._session_id,
            self.rounds,
            finger,
            *cell,
            validated,
            self._stamp(),
        )
        self.cold = False
        if not self._left:
            self._end_of_round()
        return Press.OFF_BUMP if finger in BUMPS and not validated else Press.LANDED

    def abandon_round(self) -> None:
        """The hands left the keys mid-round (a pause, the restart key): start a new one.

        A round with no landing yet is kept. Its landings so far stay written,
        and it counts toward the cap. A question is asked again as it was.
        """
        if self.done:
            return
        if self._questions or len(self._left) == len(self._order()):
            self._new_round = True
            return
        self._start_round()

    # ---- rounds --------------------------------------------------------

    def _order(self) -> tuple[str, ...]:
        return ROUND if self.full else tuple(BUMPS)

    def _start_round(self) -> None:
        if self.rounds >= config.ALIGNMENT_MAX_ROUNDS:
            # Bumps only asks nothing: the retired round's keys are not judged.
            if self.full:
                self._end_rounds()
            else:
                self._finish()
            return
        self.rounds += 1
        self._left = list(self._order())
        self._bump_ok = {}
        self._new_round = True

    def _end_of_round(self) -> None:
        if not self.full:
            self._finish()
            return
        self._update()
        current = self._current()
        if all((key := current.get(f)) is not None and key.ready_at for f in ROUND):
            self._end_rounds()
        else:
            self._start_round()

    def _update(self) -> None:
        """Chosen and ready, from the landings in a row (ADR-033's table)."""
        history = self._history()
        for finger in ROUND:
            key = self._current().get(finger)
            if key is None:
                last = history[finger][-config.REST_CHOSEN_ROUNDS :]
                if len(last) == config.REST_CHOSEN_ROUNDS and len(set(last)) == 1:
                    self._store.choose_rest_key(
                        self._profile_id, finger, *last[0], "landings", self._stamp()
                    )
            self._mark_ready(finger, history)

    def _mark_ready(self, finger: str, history: Mapping[str, list[Cell]]) -> None:
        key = self._current().get(finger)
        if key is None or key.ready_at is not None:
            return
        last = history[finger][-config.REST_READY_ROUNDS :]
        if len(last) == config.REST_READY_ROUNDS and set(last) == {(key.row, key.col)}:
            self._store.mark_rest_key_ready(self._profile_id, finger, self._stamp())

    def _end_rounds(self) -> None:
        """At the cap, every finger not ready is asked; so is a ready one that has moved."""
        self._left = []
        history = self._history()
        current = self._current()
        today = self._history(session=self._session_id)
        for finger in ROUND:
            if finger in BUMPS:
                # An index finger is never asked: its key is the bump.
                continue
            key = current.get(finger)
            moved = history[finger][-config.REST_CHANGE_ROUNDS :]
            if (
                key is None
                or key.ready_at is None
                or (
                    len(moved) == config.REST_CHANGE_ROUNDS
                    and len(set(moved)) == 1
                    and moved[0] != (key.row, key.col)
                )
            ):
                landed = tuple(dict.fromkeys(today[finger]))
                self._questions.append(Ask(finger, question=True, landed=landed))
        if not self._questions:
            self._finish()

    def _answer(self, finger: str, cell: Cell) -> Press:
        self._store.choose_rest_key(self._profile_id, finger, *cell, "answer", self._stamp())
        self._mark_ready(finger, self._history())
        self._questions.pop(0)
        if not self._questions:
            self._finish()
        return Press.ANSWERED

    def _finish(self) -> None:
        self._left = []
        self.done = True

    def mark_passed(self) -> None:
        """Each ready key that passes its own test is marked passed (ADR-033).

        Called once the alignment is done, by the caller, which may hold the
        key states' window reads for it and the block boundary after.
        """
        assert self.done
        if not self.full:
            return
        current = self._current()
        letters = letters_by_position(self._layout)
        # Read only for a strong key waiting to pass: Known is a window read
        # per Active key, which the block boundary after this reads anyway.
        known: AbstractSet[str] | None = None
        starts = cold_starts(
            self._store.first_round_landings(self._profile_id),
            self._store.practice_days_by_session(self._profile_id),
            config.REST_SETTLED_SESSION_STARTS,
        )
        for finger in ROUND:
            key = current.get(finger)
            if key is None or key.ready_at is None or key.passed_at is not None:
                continue
            letter = letters.get((key.row, key.col))
            if letter is not None and self._shares.get(letter, 0.0) >= config.REST_LETTER_MIN_SHARE:
                # A strong rest key passes by its letter being Known.
                if known is None:
                    known = self._known()
                passed = letter in known
            else:
                # Any other by landing, on the rung's count of one start a day.
                passed = len(starts) == config.REST_SETTLED_SESSION_STARTS and all(
                    settled([one for one in start if one.finger == finger], current)
                    for start in starts
                )
            if passed:
                self._store.mark_rest_key_passed(self._profile_id, finger, self._stamp())

    # ---- reads ---------------------------------------------------------

    def _current(self) -> dict[str, RestKey]:
        return {
            key.finger: key
            for key in self._store.rest_keys(self._profile_id)
            if key.replaced_at is None
        }

    def _history(self, session: int | None = None) -> dict[str, list[Cell]]:
        """Each finger's landings that count, oldest first.

        An index finger's every landing counts, so a miss breaks its run. Any
        other finger's landing on a hand whose bump press missed is not counted.
        """
        history: dict[str, list[Cell]] = {finger: [] for finger in ROUND}
        for landing in self._store.landings(self._profile_id):
            if session is not None and landing.session_id != session:
                continue
            if landing.finger in BUMPS or landing.validated:
                history[landing.finger].append((landing.row, landing.col))
        return history

    def _stamp(self) -> str | None:
        return self._now() if self._now is not None else None


# Placeholder English, as the introduction script's (ADR-022's per-language
# YAML tier does not exist yet). The terms are the rest letter's script's:
# "the bump" and "where that finger rests" (ADR-023, #12m session (5b)).
FIRST_LESSON = (
    "Before we type, we find where your fingers rest. "
    "Two keys have a small bump, and your index fingers rest on them."
)
HANDS_OFF = "Take your hands off the keyboard."
OFF_BUMP = "That was not the key with the bump."
ELSEWHERE = "That key is for another finger."
LET_GO = "Let go of the key."
CLOSING = (
    "Well done. Finding the bumps takes practice. That is all for today. "
    "Next time we will start with the bumps again."
)

KEY_NAMES: dict[str, str] = {
    ";": "semicolon",
    "'": "apostrophe",
    ",": "comma",
    ".": "full stop",
    "/": "slash",
    "\\": "backslash",
    "[": "left bracket",
    "]": "right bracket",
    "-": "minus",
    "=": "equals",
    "+": "plus",
    "#": "hash",
}


def ask_text(layout: Layout, ask: Ask) -> str:
    finger = FINGER_NAMES[ask.finger]
    if ask.question:
        landed = [key_name(layout, cell) for cell in ask.landed]
        where = f" It landed on {_listed(landed)}." if landed else ""
        return f"Where should your {finger} rest?{where} Press the key you want, and let go."
    if ask.finger in BUMPS:
        return f"Find the bump with your {finger}. Press it and let go."
    return f"Put your {finger} down where it rests. Press and let go."


def key_name(layout: Layout, cell: Cell) -> str:
    """A key's spoken name, for the question: a letter, a modifier, or a named sign."""
    name = next(name for name, key in layout.keys.items() if (key.row, key.col) == cell)
    if name in layout.graphemes:
        upper = name.upper()
        return upper if len(upper) == 1 else name
    return MODIFIER_NAMES.get(name) or KEY_NAMES.get(name, name)


def _listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
