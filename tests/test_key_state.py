from takki import config
from takki.lesson.key_state import KeyState, KeyStates, KnownCriterion, is_known
from takki.persistence import Store, WindowStats
from tests.fakes.fake_store import FakeStore

DAY1 = "2026-01-01T10:00:00"
DAY2 = "2026-01-02T10:00:00"


def stocked(store: Store, profile_id: int, key_char: str, *, correct: int, wrong: int) -> None:
    """Practise a key over two calendar days, correct attempts first."""
    for i in range(correct):
        store.append_attempt(profile_id, key_char, True, DAY1 if i % 2 == 0 else DAY2)
    for i in range(wrong):
        store.append_attempt(profile_id, key_char, False, DAY1 if i % 2 == 0 else DAY2)


def window(attempts: int, correct: int, days: int) -> WindowStats:
    return WindowStats(attempt_count=attempts, correct_count=correct, distinct_days=days)


class TestKnownCriterion:
    def test_compiled_defaults_are_adr_027s_floors(self) -> None:
        criterion = KnownCriterion()
        assert criterion.min_attempts == config.KNOWN_MIN_ATTEMPTS == 90
        assert criterion.min_accuracy == config.KNOWN_MIN_ACCURACY == 0.90
        assert criterion.min_distinct_days == config.KNOWN_MIN_DISTINCT_DAYS == 2

    def test_all_three_conditions_met(self) -> None:
        assert is_known(window(90, 81, 2))

    def test_attempts_below_floor_alone(self) -> None:
        assert not is_known(window(89, 89, 2))

    def test_attempts_exactly_at_floor(self) -> None:
        assert is_known(window(89, 89, 2)) is False
        assert is_known(window(90, 90, 2)) is True

    def test_accuracy_below_floor_alone(self) -> None:
        assert not is_known(window(100, 89, 2))

    def test_accuracy_exactly_at_floor(self) -> None:
        assert is_known(window(100, 89, 2)) is False
        assert is_known(window(100, 90, 2)) is True

    def test_accuracy_just_below_floor_at_the_window_cap(self) -> None:
        assert is_known(window(200, 179, 2)) is False  # 0.895
        assert is_known(window(200, 180, 2)) is True  # 0.900

    def test_distinct_days_below_floor_alone(self) -> None:
        assert not is_known(window(100, 100, 1))

    def test_distinct_days_exactly_at_floor(self) -> None:
        assert is_known(window(100, 100, 1)) is False
        assert is_known(window(100, 100, 2)) is True

    def test_no_attempts_is_not_known(self) -> None:
        assert not is_known(window(0, 0, 0))

    def test_criterion_is_overridable(self) -> None:
        lenient = KnownCriterion(min_attempts=2, min_accuracy=0.5, min_distinct_days=1)
        assert is_known(window(2, 1, 1), lenient)


class TestKeyStateDerivation:
    def test_unseen_key_has_no_row(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        assert KeyStates(store, p.id).state("a") is KeyState.UNSEEN

    def test_a_practised_key_is_active(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        store.append_attempt(p.id, "a", True, DAY1)
        assert KeyStates(store, p.id).state("a") is KeyState.ACTIVE

    def test_active_becomes_known_when_the_criterion_is_met(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        states = KeyStates(store, p.id)
        stocked(store, p.id, "a", correct=89, wrong=0)
        assert states.state("a") is KeyState.ACTIVE
        store.append_attempt(p.id, "a", True, DAY2)
        assert states.state("a") is KeyState.KNOWN

    def test_known_is_recomputed_not_latched(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        states = KeyStates(store, p.id)
        stocked(store, p.id, "a", correct=90, wrong=0)
        assert states.state("a") is KeyState.KNOWN
        # 10 wrong on top: 90/100 is still exactly the floor, 90/101 is not.
        stocked(store, p.id, "a", correct=0, wrong=10)
        assert states.state("a") is KeyState.KNOWN
        store.append_attempt(p.id, "a", False, DAY2)
        assert states.state("a") is KeyState.ACTIVE

    def test_a_row_with_no_window_rows_is_active_not_known(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        assert KeyStates(store, p.id).state("a") is KeyState.ACTIVE

    def test_states_are_per_profile(self) -> None:
        store = FakeStore()
        alice = store.create_profile("Alice")
        bob = store.create_profile("Bob")
        store.upsert_key_stat(alice.id, "a", True, DAY1)
        stocked(store, alice.id, "a", correct=90, wrong=0)
        assert KeyStates(store, alice.id).state("a") is KeyState.KNOWN
        assert KeyStates(store, bob.id).state("a") is KeyState.UNSEEN


class TestRollingWindow:
    def test_the_cap_discards_oldest_attempts(self) -> None:
        store = FakeStore(window_cap=100)
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", False, DAY1)
        for _ in range(20):
            store.append_attempt(p.id, "a", False, DAY1)
        for _ in range(90):
            store.append_attempt(p.id, "a", True, DAY2)
        stats = store.window_stats(p.id, "a")
        assert stats == WindowStats(attempt_count=100, correct_count=90, distinct_days=2)

    def test_the_cap_can_carry_a_key_into_known(self) -> None:
        # At the cap, one clean press does two things: it adds a correct row
        # and it evicts the oldest failure. 89/100 -> 90/100 crosses the floor
        # by two counts, not one.
        store = FakeStore(window_cap=100)
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", False, DAY1)
        states = KeyStates(store, p.id)
        for _ in range(11):
            store.append_attempt(p.id, "a", False, DAY1)
        for _ in range(89):
            store.append_attempt(p.id, "a", True, DAY2)
        assert store.window_stats(p.id, "a") == WindowStats(100, 89, 2)
        assert states.state("a") is KeyState.ACTIVE
        store.append_attempt(p.id, "a", True, DAY2)
        assert store.window_stats(p.id, "a") == WindowStats(100, 90, 2)
        assert states.state("a") is KeyState.KNOWN

    def test_default_cap_is_the_configured_window(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        for _ in range(config.ATTEMPT_WINDOW + 5):
            store.append_attempt(p.id, "a", True, DAY1)
        assert store.window_stats(p.id, "a").attempt_count == config.ATTEMPT_WINDOW


class TestKeyEnumeration:
    def test_no_active_keys_on_a_fresh_profile(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        assert KeyStates(store, p.id).active_keys() == set()
        assert KeyStates(store, p.id).known_keys() == set()

    def test_active_keys_are_every_key_with_a_row(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        for char in "fjdk":
            store.upsert_key_stat(p.id, char, True, DAY1)
        assert KeyStates(store, p.id).active_keys() == {"f", "j", "d", "k"}

    def test_known_keys_are_the_subset_meeting_the_criterion(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        for char in "fjd":
            store.upsert_key_stat(p.id, char, True, DAY1)
        stocked(store, p.id, "f", correct=90, wrong=0)
        stocked(store, p.id, "j", correct=90, wrong=10)  # 0.9 exactly
        stocked(store, p.id, "d", correct=89, wrong=11)  # 0.89
        states = KeyStates(store, p.id)
        assert states.known_keys() == {"f", "j"}
        assert states.active_keys() == {"f", "j", "d"}

    def test_enumeration_is_per_profile(self) -> None:
        store = FakeStore()
        alice = store.create_profile("Alice")
        bob = store.create_profile("Bob")
        store.upsert_key_stat(alice.id, "f", True, DAY1)
        store.upsert_key_stat(bob.id, "j", True, DAY1)
        assert KeyStates(store, alice.id).active_keys() == {"f"}
        assert KeyStates(store, bob.id).active_keys() == {"j"}
