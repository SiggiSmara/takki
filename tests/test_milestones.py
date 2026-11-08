from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

import pytest

from takki import config
from takki.lesson.key_state import KeyStates
from takki.lesson.milestones import (
    FINGERS,
    LADDER,
    REST,
    MilestoneDetector,
    grapheme_thresholds,
    satisfied_rungs,
)
from takki.persistence import Landing, Store, WindowStats
from takki.platform.layout import (
    L_IDX,
    L_MID,
    L_PINK,
    L_RING,
    R_IDX,
    R_MID,
    R_PINK,
    R_RING,
    Layout,
    build_de,
    build_en,
    build_is,
)
from tests.conftest import needs_tzset
from tests.fakes.fake_store import FakeStore


def known(layout: Layout, count: int) -> set[str]:
    return set(sorted(layout.graphemes)[:count])


class TestLadderShape:
    """ADR-027 § Milestone Ladder — six rungs, `rest` first."""

    def test_the_ladder_is_the_six_slugs_in_order(self) -> None:
        assert LADDER == ("rest", "third", "half", "two_thirds", "five_sixths", "alphabet")

    def test_english_thresholds(self) -> None:
        assert grapheme_thresholds(build_en()) == {
            "third": 8,
            "half": 13,
            "two_thirds": 17,
            "five_sixths": 21,
            "alphabet": 26,
        }

    def test_german_thresholds(self) -> None:
        assert grapheme_thresholds(build_de()) == {
            "third": 10,
            "half": 15,
            "two_thirds": 20,
            "five_sixths": 25,
            "alphabet": 30,
        }

    def test_icelandic_thresholds(self) -> None:
        # 36 graphemes: the layout's 30 direct keys plus the six acutes. The
        # dead key itself is keystroke mechanics and is not in the denominator
        # (ADR-027 § Milestone Denominator).
        layout = build_is()
        assert len(layout.graphemes) == 36
        assert "dead-acute" not in layout.graphemes
        assert grapheme_thresholds(layout) == {
            "third": 12,
            "half": 18,
            "two_thirds": 24,
            "five_sixths": 30,
            "alphabet": 36,
        }

    def test_rung_2_clears_the_layer_2_unlock_in_every_layout(self) -> None:
        # ADR-027's claim that reaching `third` means real words are typeable:
        # ADR-010 unlocks Layer 2 at >= 8 keys, and floor(N/3) is >= 8 for
        # every layout in the v1 target set.
        for build in (build_en, build_de, build_is):
            assert grapheme_thresholds(build())["third"] >= 8

    def test_the_rest_rung_is_not_a_grapheme_count(self) -> None:
        # Absent from the counted thresholds on purpose: Known letters are not
        # a rest position, and a milestone fired by mistake is never revoked
        # (ADR-027 § Key States).
        for build in (build_en, build_de, build_is):
            assert REST not in grapheme_thresholds(build())
        assert "anchor" not in LADDER


class TestSatisfiedRungs:
    """Pure: (layout, Known graphemes) -> the rungs earned. Detection is #10."""

    def test_nothing_known_and_no_rest_earns_nothing(self) -> None:
        assert satisfied_rungs(build_en(), set()) == ()

    def test_the_rest_rung_comes_from_the_landings_not_from_the_known_set(self) -> None:
        layout = build_en()
        assert satisfied_rungs(layout, known(layout, 7)) == ()
        assert satisfied_rungs(layout, set(), rest=True) == (REST,)

    def test_english_rungs_at_each_threshold(self) -> None:
        layout = build_en()
        assert satisfied_rungs(layout, known(layout, 7)) == ()
        assert satisfied_rungs(layout, known(layout, 8)) == ("third",)
        assert satisfied_rungs(layout, known(layout, 12)) == ("third",)
        assert satisfied_rungs(layout, known(layout, 13)) == ("third", "half")
        assert satisfied_rungs(layout, known(layout, 17)) == ("third", "half", "two_thirds")
        assert satisfied_rungs(layout, known(layout, 21)) == (
            "third",
            "half",
            "two_thirds",
            "five_sixths",
        )
        assert satisfied_rungs(layout, known(layout, 25)) == (
            "third",
            "half",
            "two_thirds",
            "five_sixths",
        )
        assert satisfied_rungs(layout, known(layout, 26), rest=True) == LADDER

    def test_the_top_rung_needs_every_grapheme(self) -> None:
        for build in (build_de, build_is):
            layout = build()
            full = set(layout.graphemes)
            assert "alphabet" not in satisfied_rungs(layout, full - {sorted(full)[0]})
            assert "alphabet" in satisfied_rungs(layout, full)

    def test_a_composite_counts_towards_the_rungs_it_is_in_the_denominator_of(self) -> None:
        layout = build_is()
        direct = {c for c, g in layout.graphemes.items() if g.mechanism == "direct"}
        assert satisfied_rungs(layout, direct) == ("third", "half", "two_thirds", "five_sixths")
        assert satisfied_rungs(layout, set(layout.graphemes)) == LADDER[1:]

    def test_a_key_that_is_not_on_this_layout_does_not_count(self) -> None:
        # key_stats survives a profile's language change; the denominator is
        # this layout's graphemes, so the count must be too.
        layout = build_en()
        assert satisfied_rungs(layout, known(layout, 7) | {"ä", "ö", "ü"}) == ()


DAY1 = "2026-01-01T10:00:00+00:00"
DAY2 = "2026-01-02T10:00:00+00:00"
KNOWN = WindowStats(attempt_count=90, correct_count=90, distinct_days=2)
# The order `introduction_sequence` emits for English under home-row fill, with
# no Stage 0 (ADR-033). Spelled out rather than derived, so a change to the
# ordering shows up here as a diff rather than silently redefining the walk.
EN_INTRODUCTION_ORDER = "fjdkslaghentoriwubpcmqyvxz"


class RecordingStore(FakeStore):
    """FakeStore that keeps every `record_milestone` call, duplicates included.

    The store itself is idempotent, so `achieved_milestones()` cannot tell a
    rung written once from one written on every check. The write count is the
    thing under test.
    """

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []
        self.stamps: list[str | None] = []
        # Profile 1, which every test here reads. The rest keys and sessions
        # the `rest` rung reads refuse a profile that does not exist.
        self.create_profile("Ana")

    def record_milestone(self, profile_id: int, level: str, achieved_at: str | None = None) -> None:
        self.writes.append(level)
        self.stamps.append(achieved_at)
        super().record_milestone(profile_id, level, achieved_at)


def practise(store: Store, profile_id: int, char: str, window: WindowStats = KNOWN) -> None:
    """Answer `window` prompts for one key, as AttemptCounter would.

    `attempt_count` prompts, `correct_count` of them right, spread over
    `distinct_days` days. Both writes, because Active is `key_stats` row
    presence and Known is the `key_attempts` window (ADR-027 § Key States) --
    a key with attempts and no row is a state the counter never produces.
    Appends: two calls on one key sum, they do not replace.
    """
    for i in range(window.attempt_count):
        day = DAY1 if window.distinct_days == 1 or i % 2 == 0 else DAY2
        correct = i < window.correct_count
        store.upsert_key_stat(profile_id, char, correct, day)
        store.append_attempt(profile_id, char, correct, day)


def states(store: Store, profile_id: int = 1) -> KeyStates:
    # Read on the second practice day, so nothing has had time to age.
    return KeyStates(store, profile_id, now=lambda: DAY2)


def detector(store: Store, layout: Layout, profile_id: int = 1) -> MilestoneDetector:
    return MilestoneDetector(store, profile_id, layout, states(store, profile_id))


def make_known(store: Store, profile_id: int, layout: Layout, count: int) -> None:
    """Bring the first `count` graphemes of the layout to the Known bar."""
    for char in sorted(layout.graphemes)[:count]:
        if store.window_stats(profile_id, char).attempt_count == 0:
            practise(store, profile_id, char)


class TestFiringOnce:
    """The rolling query is not once; the `milestones` rows are what make it so."""

    def test_a_rung_fires_on_the_check_that_crosses_it_and_never_again(self) -> None:
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        make_known(store, 1, layout, 7)
        assert found.check() == ()
        make_known(store, 1, layout, 8)
        assert found.check() == ("third",)
        assert found.check() == ()
        assert found.check() == ()
        assert store.writes == ["third"]
        assert store.achieved_milestones(1) == ["third"]

    def test_a_rung_is_stamped_by_the_clock_the_detector_was_given(self) -> None:
        store, layout = RecordingStore(), build_en()
        stamp = "2026-03-04T05:06:07+00:00"
        found = MilestoneDetector(store, 1, layout, states(store), lambda: stamp)
        make_known(store, 1, layout, 8)
        assert found.check() == ("third",)
        assert store.stamps == [stamp]

    def test_a_key_only_speed_keeps_from_known_does_not_count_towards_a_rung(self) -> None:
        # alpha-plan #12f: the rungs count Known, and Known has a speed term.
        store, layout = RecordingStore(), build_en()
        eight = sorted(layout.graphemes)[:8]
        for char in eight:
            ms = 2500 if char == eight[0] else 1000
            for i in range(config.KNOWN_MIN_ATTEMPTS):
                day = DAY1 if i % 2 == 0 else DAY2
                store.upsert_key_stat(1, char, True, day)
                store.append_attempt(1, char, True, day, ms)
        found = detector(store, layout)
        assert states(store).slow_keys() == {eight[0]}
        assert found.check() == ()
        for _ in range(config.SPEED_SAMPLE):
            store.append_attempt(1, eight[0], True, DAY2, 1000)
        assert found.check() == ("third",)

    def test_the_rung_sequence_of_a_full_english_walk(self) -> None:
        """Zero to the full alphabet, in the order the introducer emits keys.

        Each rung fires on the check that crosses it, once, and the writes are
        rungs 2 to 6 in order. `rest` never fires: nothing writes landings or
        rest keys until the alignment (alpha-plan #12m session 7).
        """
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        fired: list[tuple[str, tuple[str, ...]]] = []

        assert sorted(EN_INTRODUCTION_ORDER) == sorted(layout.graphemes)
        assert found.check() == ()

        for position, char in enumerate(EN_INTRODUCTION_ORDER, start=1):
            practise(store, 1, char)
            crossed = found.check()
            if crossed:
                fired.append((f"{position} graphemes Known", crossed))

        assert fired == [
            ("8 graphemes Known", ("third",)),
            ("13 graphemes Known", ("half",)),
            ("17 graphemes Known", ("two_thirds",)),
            ("21 graphemes Known", ("five_sixths",)),
            ("26 graphemes Known", ("alphabet",)),
        ]
        assert tuple(store.writes) == LADDER[1:]

    def test_a_fresh_detector_does_not_re_fire_what_the_store_already_holds(self) -> None:
        # The reason the persisted set is the authority: the detector is
        # session-local, the milestone is not. An in-memory record would
        # congratulate the child on a third of the alphabet every session.
        store, layout = RecordingStore(), build_en()
        make_known(store, 1, layout, 13)
        assert detector(store, layout).check() == ("third", "half")
        assert detector(store, layout).check() == ()
        assert store.writes == ["third", "half"]

    def test_two_detectors_on_one_profile_do_not_double_fire(self) -> None:
        store, layout = RecordingStore(), build_en()
        first, second = detector(store, layout), detector(store, layout)
        make_known(store, 1, layout, 8)
        assert first.check() == ("third",)
        assert second.check() == ()
        assert store.writes == ["third"]

    def test_two_profiles_earn_their_rungs_independently(self) -> None:
        store, layout = RecordingStore(), build_en()
        make_known(store, 1, layout, 8)
        assert detector(store, layout, 1).check() == ("third",)
        assert detector(store, layout, 2).check() == ()
        assert store.achieved_milestones(2) == []


class TestNeverRevoked:
    def test_a_rung_stays_fired_when_the_known_count_falls_back_below_it(self) -> None:
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        make_known(store, 1, layout, 13)
        assert found.check() == ("third", "half")
        # 'a' loses its accuracy: 90 correct then 20 wrong is 110 attempts at
        # 81.8%, under the Known floor. The Known count drops to 12, one under
        # `half` -- ADR-027 § Key States: milestones are never reverted.
        for _ in range(20):
            store.append_attempt(1, "a", False, DAY2)
        assert satisfied_rungs(layout, states(store).known_keys()) == ("third",)
        assert found.check() == ()
        assert store.achieved_milestones(1) == ["third", "half"]
        assert store.writes == ["third", "half"]


class TestSeveralRungsAtOnce:
    def test_a_jump_past_two_rungs_writes_both_in_ladder_order(self) -> None:
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        make_known(store, 1, layout, 7)
        assert found.check() == ()
        make_known(store, 1, layout, 13)
        assert found.check() == ("third", "half")
        assert store.writes == ["third", "half"]

    def test_the_whole_ladder_can_land_on_one_check(self) -> None:
        # A profile restored from a backup, or one nothing ever checked: five
        # settled days and every letter Known. `rest` comes first, as the
        # ladder puts it, however late it was earned.
        store, layout = RecordingStore(), build_en()
        seat(store, 1)
        for day in range(1, 6):
            first_round(store, 1, day)
        make_known(store, 1, layout, 26)
        assert detector(store, layout).check() == LADDER
        assert tuple(store.writes) == LADDER


# The conventional rest position on QWERTY, by (row, col), and the order a round
# asks for the fingers (ADR-033: index, little, then middle and ring).
REST_POSITION: dict[str, tuple[int, int]] = {
    L_IDX: (3, 4),
    R_IDX: (3, 7),
    L_PINK: (3, 1),
    R_PINK: (3, 10),
    L_MID: (3, 3),
    R_MID: (3, 8),
    L_RING: (3, 2),
    R_RING: (3, 9),
}


def noon(day: int, minutes: int = 0) -> str:
    # Midday UTC: in any fixed zone, consecutive days stay distinct local days,
    # and two stamps minutes apart stay on one.
    return (datetime(2026, 2, 1, 12, minutes) + timedelta(days=day - 1)).isoformat() + "+00:00"


def seat(
    store: Store, profile_id: int, keys: Mapping[str, tuple[int, int]] = REST_POSITION
) -> None:
    """Give every finger its current rest key, as the alignment would (session 7)."""
    for finger, (row, col) in keys.items():
        chosen_by = "bump" if finger in (L_IDX, R_IDX) else "landings"
        store.choose_rest_key(profile_id, finger, row, col, chosen_by, noon(1))


def first_round(
    store: Store,
    profile_id: int,
    day: int,
    *,
    minutes: int = 0,
    landed: Mapping[str, tuple[int, int]] = REST_POSITION,
    validated: bool = True,
    fingers: int = 8,
    round: int = 1,
) -> int:
    """One session whose round `round` lands each finger on `landed`, at `day`'s noon."""
    stamp = noon(day, minutes)
    session = store.start_session(profile_id, stamp)
    for finger, (row, col) in list(landed.items())[:fingers]:
        store.record_landing(profile_id, session, round, finger, row, col, validated, stamp)
    return session


class ReadCountingStore(RecordingStore):
    """Counts the two reads the `rest` rung makes."""

    def __init__(self) -> None:
        super().__init__()
        self.rest_reads = 0

    def first_round_landings(self, profile_id: int) -> list[Landing]:
        self.rest_reads += 1
        return super().first_round_landings(profile_id)


class TestRestRung:
    """ADR-027 § The `rest` rung, on the fake store and a fixed clock.

    Nothing writes landings or rest keys before alpha-plan #12m session (7), so
    every store here is seeded by hand: the rung cannot fire in a real session yet.
    """

    def found(self, store: Store) -> Callable[[], tuple[str, ...]]:
        stamp = "2026-03-01T09:00:00+00:00"
        return MilestoneDetector(store, 1, build_en(), states(store), lambda: stamp).check

    def test_not_on_the_fourth_day_and_on_the_fifth(self) -> None:
        store = RecordingStore()
        seat(store, 1)
        check = self.found(store)
        for day in range(1, 5):
            first_round(store, 1, day)
            assert check() == ()
        first_round(store, 1, 5)
        assert check() == (REST,)
        assert store.writes == [REST]
        assert store.stamps == ["2026-03-01T09:00:00+00:00"]
        assert states(store).known_keys() == set()

    def test_two_sessions_on_one_day_count_once(self) -> None:
        # Five session starts over four days: a restart minutes later is not a
        # cold start, so this is four days.
        store = RecordingStore()
        seat(store, 1)
        check = self.found(store)
        for day in range(1, 5):
            first_round(store, 1, day)
        first_round(store, 1, 4, minutes=10)
        assert check() == ()
        first_round(store, 1, 5)
        assert check() == (REST,)

    def test_only_the_first_complete_round_of_a_day_is_read(self) -> None:
        # The day's first session landed well; a restart that day landed a
        # finger elsewhere. The day is judged by the first, and passes.
        store = RecordingStore()
        seat(store, 1)
        for day in range(1, 6):
            first_round(store, 1, day)
        first_round(store, 1, 5, minutes=10, landed=REST_POSITION | {L_MID: (2, 3)})
        assert self.found(store)() == (REST,)

    def test_a_cut_short_round_is_passed_over_and_a_later_one_that_day_counts(self) -> None:
        # Day 5's first session stopped after seven landings; its second
        # session that day is the day's first complete round.
        store = RecordingStore()
        seat(store, 1)
        check = self.found(store)
        for day in range(1, 5):
            first_round(store, 1, day)
        first_round(store, 1, 5, fingers=7)
        assert check() == ()
        first_round(store, 1, 5, minutes=10)
        assert check() == (REST,)

    def test_days_away_neither_count_for_nor_against(self) -> None:
        store = RecordingStore()
        seat(store, 1)
        for day in (1, 2, 9, 30, 31):
            first_round(store, 1, day)
        assert self.found(store)() == (REST,)

    def test_a_wrong_landing_restarts_the_count(self) -> None:
        # Day 3's left middle finger landed one row up. Days 1 to 5 hold it,
        # and so do the last five days until day 8 pushes it out.
        store = RecordingStore()
        seat(store, 1)
        check = self.found(store)
        fired_on = []
        for day in range(1, 9):
            wrong = REST_POSITION | {L_MID: (2, 3)} if day == 3 else REST_POSITION
            first_round(store, 1, day, landed=wrong)
            if check():
                fired_on.append(day)
        assert fired_on == [8]
        assert store.writes == [REST]

    def test_an_unvalidated_round_fails_its_day(self) -> None:
        # A hand whose bump press missed has its landings not counted (ADR-033),
        # so the round, landed where it should be, still fails.
        store = RecordingStore()
        seat(store, 1)
        for day in range(1, 6):
            first_round(store, 1, day, validated=day != 2)
        assert self.found(store)() == ()

    def test_a_finger_with_no_current_rest_key_fails(self) -> None:
        store = RecordingStore()
        seat(store, 1, {finger: cell for finger, cell in REST_POSITION.items() if finger != R_RING})
        for day in range(1, 6):
            first_round(store, 1, day)
        assert self.found(store)() == ()

    def test_landings_outside_round_1_are_not_read(self) -> None:
        store = RecordingStore()
        seat(store, 1)
        for day in range(1, 6):
            first_round(store, 1, day, round=2)
        assert self.found(store)() == ()

    def test_a_changed_rest_key_restarts_the_count(self) -> None:
        # Five days on (3,3) for the left middle finger, then it changes to
        # (2,3): every day so far landed on the old key, so none of them
        # counts, and five days on the new key are needed.
        store = RecordingStore()
        seat(store, 1)
        for day in range(1, 5):
            first_round(store, 1, day)
        store.choose_rest_key(1, L_MID, 2, 3, "answer", noon(5))
        check = self.found(store)
        moved = REST_POSITION | {L_MID: (2, 3)}
        fired_on = []
        for day in range(5, 11):
            first_round(store, 1, day, landed=moved)
            if check():
                fired_on.append(day)
        assert fired_on == [9]

    def test_the_first_day_counts_when_it_landed_where_the_finger_settled(self) -> None:
        # No finger has a key at round 1 of the first session; a key is chosen
        # after round 2. The rung judges against the key the finger has now.
        store = RecordingStore()
        for day in range(1, 6):
            first_round(store, 1, day)
            if day == 1:
                seat(store, 1)
        assert self.found(store)() == (REST,)

    def test_the_full_round_retired_fires_it_with_no_landings_at_all(self) -> None:
        store = RecordingStore()
        seat(store, 1)
        check = self.found(store)
        for finger in sorted(FINGERS)[:-1]:
            store.mark_rest_key_passed(1, finger, noon(2))
            assert check() == ()
        store.mark_rest_key_passed(1, sorted(FINGERS)[-1], noon(2))
        assert check() == (REST,)
        assert store.writes == [REST]

    def test_a_replaced_key_that_had_passed_does_not_count_as_passed(self) -> None:
        store = RecordingStore()
        seat(store, 1)
        for finger in FINGERS:
            store.mark_rest_key_passed(1, finger, noon(2))
        store_two = RecordingStore()
        seat(store_two, 1)
        for finger in FINGERS:
            store_two.mark_rest_key_passed(1, finger, noon(2))
        store_two.choose_rest_key(1, L_MID, 2, 3, "answer", noon(3))
        assert self.found(store)() == (REST,)
        assert self.found(store_two)() == ()

    def test_it_is_not_evaluated_again_once_it_has_fired(self) -> None:
        store = ReadCountingStore()
        seat(store, 1)
        for day in range(1, 6):
            first_round(store, 1, day)
        check = self.found(store)
        assert check() == (REST,)
        assert store.rest_reads == 1
        first_round(store, 1, 6, landed=REST_POSITION | {L_MID: (2, 3)})
        assert check() == ()
        assert check() == ()
        assert store.rest_reads == 1
        assert store.writes == [REST]

    def test_it_is_never_revoked(self) -> None:
        # A later day landing elsewhere would fail the criterion now; the rung
        # stays, because it is not re-read (above) and the row is the milestone.
        store = RecordingStore()
        seat(store, 1)
        for day in range(1, 6):
            first_round(store, 1, day)
        assert self.found(store)() == (REST,)
        for day in range(6, 11):
            first_round(store, 1, day, landed=REST_POSITION | {L_MID: (2, 3)})
        assert self.found(store)() == ()
        assert store.achieved_milestones(1) == [REST]

    def test_it_fires_late_and_after_third(self) -> None:
        # ADR-027: `third` can come before the fifth day. Ladder order is not
        # a precondition, and the writes are in the order earned.
        store, layout = RecordingStore(), build_en()
        seat(store, 1)
        check = self.found(store)
        make_known(store, 1, layout, 8)
        for day in range(1, 5):
            first_round(store, 1, day)
        assert check() == ("third",)
        first_round(store, 1, 5)
        assert check() == (REST,)
        assert store.writes == ["third", REST]

    def test_two_profiles_are_judged_apart(self) -> None:
        store = RecordingStore()
        alice, bob = store.create_profile("Alice").id, store.create_profile("Bob").id
        seat(store, alice)
        seat(store, bob)
        for day in range(1, 6):
            first_round(store, alice, day)
        for day in range(1, 5):
            first_round(store, bob, day)
        stamp = "2026-03-01T09:00:00+00:00"
        layout = build_en()
        assert MilestoneDetector(
            store, alice, layout, states(store, alice), lambda: stamp
        ).check() == (REST,)
        assert (
            MilestoneDetector(store, bob, layout, states(store, bob), lambda: stamp).check() == ()
        )


@needs_tzset
class TestRestRungDayIsLocal:
    """Decided 2026-11-08: a round's day is its UTC stamp's local day, read when checked."""

    # Three days at noon UTC, then two sessions at 10:30 and 11:30 UTC: one day
    # at Greenwich, either side of midnight in Auckland (UTC+13 in February).
    @pytest.mark.parametrize(("zone", "fired"), [("UTC", ()), ("Pacific/Auckland", (REST,))])
    def test_two_sessions_are_one_day_or_two_by_the_local_calendar(
        self, timezone: Callable[[str], None], zone: str, fired: tuple[str, ...]
    ) -> None:
        timezone(zone)
        store = RecordingStore()
        seat(store, 1)
        for day in range(1, 4):
            first_round(store, 1, day)
        for stamp in ("2026-02-10T10:30:00+00:00", "2026-02-10T11:30:00+00:00"):
            session = store.start_session(1, stamp)
            for finger, (row, col) in REST_POSITION.items():
                store.record_landing(1, session, 1, finger, row, col, True, stamp)
        assert detector(store, build_en()).check() == fired

    def test_a_round_1_that_crosses_midnight_is_the_day_it_began(
        self, timezone: Callable[[str], None]
    ) -> None:
        # ADR-027, "Built: how a day is read": a session's day is that of its
        # round 1's first landing. Four days at noon, then a restart on day 4
        # at 23:59:58 whose round ends on day 5. Read by its first landing it
        # is a second session on day 4 and adds nothing; read by its last it
        # would be day 5 and fire the rung.
        timezone("UTC")
        store = RecordingStore()
        seat(store, 1)
        check = self.found_check(store)
        for day in range(1, 5):
            first_round(store, 1, day)
        start = datetime(2026, 2, 4, 23, 59, 58)
        session = store.start_session(1, start.isoformat() + "+00:00")
        for index, (finger, (row, col)) in enumerate(REST_POSITION.items()):
            stamp = (start + timedelta(seconds=index)).isoformat() + "+00:00"
            store.record_landing(1, session, 1, finger, row, col, True, stamp)
        assert check() == ()
        first_round(store, 1, 5)
        assert check() == (REST,)

    def found_check(self, store: Store) -> Callable[[], tuple[str, ...]]:
        return detector(store, build_en()).check


class TestOtherLayouts:
    def test_icelandics_denominator_is_the_layouts_36_graphemes(self) -> None:
        # roadmap D records 32 vs 36 as contested; the ladder is built on the
        # layout reading and the detector inherits it unchanged. `third` fires
        # at 12, not at 10 (which is floor(32/3)).
        store, layout = RecordingStore(), build_is()
        found = detector(store, layout)
        make_known(store, 1, layout, 11)
        assert found.check() == ()
        make_known(store, 1, layout, 12)
        assert found.check() == ("third",)

    def test_a_german_walk_fires_at_the_german_thresholds(self) -> None:
        store, layout = RecordingStore(), build_de()
        found = detector(store, layout)
        make_known(store, 1, layout, 9)
        assert found.check() == ()
        make_known(store, 1, layout, 15)
        assert found.check() == ("third", "half")
