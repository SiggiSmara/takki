"""ADR-033 § The alignment, the rules alone: what is asked, written and passed."""

from collections.abc import Callable

from takki import config
from takki.lesson.alignment import (
    ROUND,
    Alignment,
    Ask,
    Press,
    ask_text,
    key_name,
)
from takki.persistence import RestKey
from takki.platform.layout import (
    L_IDX,
    L_MID,
    L_PINK,
    L_RING,
    R_IDX,
    R_MID,
    R_PINK,
    build_en,
    build_is,
)
from tests.fakes.fake_store import FakeStore

Cell = tuple[int, int]
CONVENTIONAL: dict[str, Cell] = dict(
    zip(ROUND, [(3, c) for c in (4, 7, 1, 10, 3, 8, 2, 9)], strict=True)
)
# a s d f l are strong; j k and `;` are weak (ADR-033 § Introduction order and slots).
SHARES = {"a": 0.08, "s": 0.06, "d": 0.04, "f": 0.03, "l": 0.04, "j": 0.001, "k": 0.007}
STRONG_FINGERS = {L_PINK, L_RING, L_MID, L_IDX, "R-ring"}


def day(n: int) -> str:
    return f"2026-01-{n:02d}T10:00:00+00:00"


class Child:
    """One profile and the sessions it sits, with what its letters' Known set is."""

    def __init__(self) -> None:
        self.store = FakeStore()
        self.profile = self.store.create_profile("kid").id
        self.known: set[str] = set()

    def session(self, n: int) -> Alignment:
        sid = self.store.start_session(self.profile, day(n))
        return Alignment(
            build_en(),
            self.store,
            self.profile,
            sid,
            known=lambda: self.known,
            shares=SHARES,
            now=lambda: day(n),
        )

    def current(self) -> dict[str, RestKey]:
        return {k.finger: k for k in self.store.rest_keys(self.profile) if k.replaced_at is None}


def sit(alignment: Alignment, land: Callable[[Ask, int], Cell] | None = None) -> None:
    """Answer every ask until the alignment is done; then its keys are judged."""

    def conventional(ask: Ask, _: int) -> Cell:
        return CONVENTIONAL[ask.finger]

    pick = land or conventional
    for _ in range(200):
        ask = alignment.ask
        if ask is None:
            alignment.mark_passed()
            return
        alignment.press(pick(ask, alignment.rounds))
    raise AssertionError("the alignment did not end")


class TestRounds:
    def test_a_round_asks_the_index_fingers_then_little_then_middle_and_ring(self) -> None:
        alignment = Child().session(1)
        asked: list[str] = []
        for _ in range(8):
            ask = alignment.ask
            assert ask is not None
            asked.append(ask.finger)
            alignment.press(CONVENTIONAL[ask.finger])
        assert asked == list(ROUND)
        assert alignment.rounds == 2

    def test_a_round_with_no_landing_is_kept_when_abandoned(self) -> None:
        alignment = Child().session(1)
        alignment.take_new_round()
        alignment.abandon_round()
        assert (alignment.rounds, alignment.take_new_round()) == (1, True)
        alignment.press(CONVENTIONAL[L_IDX])
        alignment.abandon_round()
        assert alignment.rounds == 2
        assert alignment.ask == Ask(L_IDX)

    def test_abandoned_rounds_count_toward_the_cap(self) -> None:
        child = Child()
        alignment = child.session(1)
        for _ in range(config.ALIGNMENT_MAX_ROUNDS):
            alignment.press(CONVENTIONAL[L_IDX])
            alignment.abandon_round()
        # Nothing settled: every finger but the index fingers is asked.
        assert alignment.ask == Ask(L_PINK, question=True)

    def test_a_press_outside_the_column_writes_nothing_and_keeps_the_ask(self) -> None:
        child = Child()
        alignment = child.session(1)
        assert alignment.press((3, 5)) is Press.OFF_BUMP
        assert alignment.press((3, 10)) is Press.ELSEWHERE
        assert alignment.press(None) is Press.ELSEWHERE
        assert alignment.ask == Ask(R_IDX)
        assert len(child.store.landings(child.profile)) == 1

    def test_the_first_lesson_is_owed_until_the_child_has_landed(self) -> None:
        child = Child()
        assert child.session(1).cold
        assert child.session(1).cold
        second = child.session(2)
        second.press(CONVENTIONAL[L_IDX])
        assert not second.cold
        assert not child.session(3).cold


class TestChosenAndReady:
    def test_rounds_in_a_row_are_counted_across_sessions(self) -> None:
        # One round on the first day, cut short by a quit, and two the next.
        child = Child()
        first = child.session(1)
        for finger in ROUND:
            first.press(CONVENTIONAL[finger])
        assert all(key.ready_at is None for key in child.current().values())
        second = child.session(2)
        for _ in range(2 * len(ROUND)):
            ask = second.ask
            assert ask is not None
            second.press(CONVENTIONAL[ask.finger])
        assert second.done
        assert all(key.ready_at == day(2) for key in child.current().values())
        assert child.current()[L_MID].chosen_at == day(2)

    def test_a_round_whose_bump_missed_neither_counts_nor_breaks_the_run(self) -> None:
        child = Child()
        alignment = child.session(1)

        def land(ask: Ask, round: int) -> Cell:
            if ask.finger == L_IDX and round == 2:
                return (3, 5)
            return CONVENTIONAL[ask.finger]

        sit(alignment, land)
        current = child.current()
        # The left index finger missed once, so it needs three more rounds in
        # a row; its hand's other fingers skip round 2 and are ready at 4.
        assert alignment.rounds == 5
        assert current[L_IDX].ready_at is not None
        assert current[L_MID].ready_at is not None

    def test_a_ready_finger_that_moves_three_rounds_in_a_row_is_asked_again(self) -> None:
        child = Child()
        sit(child.session(1))
        moved = child.session(2)
        assert moved.ask == Ask(L_IDX)

        def land(ask: Ask, round: int) -> Cell:
            if ask.question:
                return (2, 3)
            return (2, 3) if ask.finger == L_MID else CONVENTIONAL[ask.finger]

        for _ in range(8):
            ask = moved.ask
            assert ask is not None
            moved.press(land(ask, moved.rounds))
        # One round, and the finger is ready: not asked yet.
        assert moved.done
        later = child.session(3)
        for _ in range(8):
            ask = later.ask
            assert ask is not None
            later.press(land(ask, later.rounds))
        assert later.done
        third = child.session(4)
        for _ in range(8):
            ask = third.ask
            assert ask is not None
            third.press(land(ask, third.rounds))
        assert third.ask == Ask(L_MID, question=True, landed=((2, 3),))
        third.press((2, 3))
        assert third.done
        current = child.current()[L_MID]
        assert (current.row, current.col, current.chosen_by) == (2, 3, "answer")
        # Its last three landings were on the key it chose, so it is ready.
        assert current.ready_at == day(4)


class TestPassed:
    def test_weak_keys_pass_on_five_days_and_strong_ones_by_their_letter(self) -> None:
        child = Child()
        for n in range(1, 5):
            sit(child.session(n))
        assert not any(key.passed_at for key in child.current().values())
        sit(child.session(5))
        passed = {finger for finger, key in child.current().items() if key.passed_at}
        assert passed == set(ROUND) - STRONG_FINGERS
        child.known = {"a", "s", "d", "f", "l"}
        sit(child.session(6))
        assert all(key.passed_at for key in child.current().values())
        assert child.session(7).full is False

    def test_five_restarts_in_one_day_are_one_start(self) -> None:
        child = Child()
        for _ in range(5):
            sit(child.session(1))
        sit(child.session(2))
        assert not any(key.passed_at for key in child.current().values())

    def test_a_strong_key_whose_finger_is_not_ready_does_not_pass(self) -> None:
        # Passed only once ready (decided 2026-11-13, #12m session (7)).
        child = Child()
        child.known = {"s"}

        def land(ask: Ask, round: int) -> Cell:
            if ask.question:
                return (3, 2)
            if ask.finger == L_RING:
                return (3, 2) if round % 2 else (2, 2)
            return CONVENTIONAL[ask.finger]

        sit(child.session(1), land)
        ring = child.current()[L_RING]
        assert (ring.row, ring.col, ring.chosen_by) == (3, 2, "answer")
        assert ring.ready_at is None and ring.passed_at is None

    def test_a_retired_full_round_opens_with_the_two_bumps_and_judges_nothing(self) -> None:
        child = Child()
        child.known = set(SHARES)
        for n in range(1, 6):
            sit(child.session(n))
        bumps = child.session(6)
        assert bumps.full is False
        asked: list[str] = []
        while bumps.ask is not None:
            asked.append(bumps.ask.finger)
            bumps.press(CONVENTIONAL[bumps.ask.finger])
        assert asked == [L_IDX, R_IDX]
        bumps.mark_passed()
        landings = [one for one in child.store.landings(child.profile) if one.session_id == 6]
        assert [(one.finger, one.round, one.validated) for one in landings] == [
            (L_IDX, 1, True),
            (R_IDX, 1, True),
        ]

    def test_a_retired_full_round_at_the_cap_asks_no_question(self) -> None:
        # Bumps only judges no other key, even one whose landings have moved.
        child = Child()
        child.known = set(SHARES)
        for n in range(1, 6):
            sit(child.session(n))
        for _ in range(config.REST_CHANGE_ROUNDS):
            child.store.record_landing(child.profile, 5, 9, L_MID, 2, 3, True, day(5))
        bumps = child.session(6)
        assert bumps.full is False
        for _ in range(config.ALIGNMENT_MAX_ROUNDS):
            bumps.press(CONVENTIONAL[L_IDX])
            bumps.abandon_round()
        assert (bumps.done, bumps.ask) == (True, None)


class TestWords:
    def test_the_asks_use_the_rest_letters_terms(self) -> None:
        layout = build_en()
        assert ask_text(layout, Ask(R_IDX)) == (
            "Find the bump with your right index finger. Press it and let go."
        )
        assert ask_text(layout, Ask(R_MID)) == (
            "Put your right middle finger down where it rests. Press and let go."
        )
        assert ask_text(layout, Ask(R_PINK, question=True)) == (
            "Where should your right little finger rest? Press the key you want, and let go."
        )
        assert ask_text(layout, Ask(R_PINK, True, ((3, 10), (3, 11), (2, 11)))) == (
            "Where should your right little finger rest? "
            "It landed on semicolon, apostrophe and left bracket. "
            "Press the key you want, and let go."
        )

    def test_a_dead_key_and_a_letter_are_named(self) -> None:
        assert key_name(build_is(), (3, 11)) == "the accent key"
        assert key_name(build_is(), (3, 10)) == "Æ"
