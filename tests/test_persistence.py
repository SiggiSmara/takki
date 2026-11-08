import os
import sqlite3
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, cast

import pytest

from takki import config
from takki.lesson.key_state import KeyState, KeyStates
from takki.persistence import (
    Attempt,
    ChosenBy,
    Introduction,
    KeyStat,
    Landing,
    Level,
    LevelRecord,
    PhaseRecord,
    ReachPress,
    RestKey,
    Store,
    WindowStats,
    utc_stamp,
)
from takki.persistence.sqlite_store import SqliteStore
from tests.fakes.fake_store import FakeStore


@pytest.fixture()
def store() -> SqliteStore:
    return SqliteStore(":memory:")


@pytest.fixture(params=["sqlite", "fake"])
def any_store(request: pytest.FixtureRequest) -> Store:
    """The real store and its fake, held to the same behaviour (ADR-019)."""
    return SqliteStore(":memory:") if cast(str, request.param) == "sqlite" else FakeStore()


@contextmanager
def failing_on(store: SqliteStore, fragment: str) -> Generator[None]:
    """Every statement through `store.conn` that contains `fragment` raises, as a kill would."""
    real = store.conn

    class Failing:
        def execute(self, sql: str, *args: Any) -> Any:
            if fragment in sql:
                raise RuntimeError("killed")
            return real.execute(sql, *args)

        def __enter__(self) -> Any:
            return real.__enter__()

        def __exit__(self, *exc: Any) -> Any:
            return real.__exit__(*exc)

    store.conn = cast(sqlite3.Connection, Failing())
    try:
        yield
    finally:
        store.conn = real


UTC_STAMP = "2026-01-01T10:00:00+00:00"
# Each is a way a wrong time could reach the store: no offset at all, the
# machine's local offset, a date alone, not a time, nothing -- and two other
# spellings of UTC, refused because stored timestamps are ordered as text.
NOT_UTC = [
    "2026-01-01T10:00:00",
    "2026-01-01T10:00:00+02:00",
    "2026-01-01",
    "yesterday",
    "",
    "2026-01-01T10:00:00Z",
    "2026-01-01T10:00:00.123456+00:00",
]

# Every store method that takes a timestamp, each given one.
WRITES: dict[str, Callable[[Store, int, str], object]] = {
    "create_profile": lambda s, _, at: s.create_profile("Bob", "en", created_at=at),
    "start_session": lambda s, pid, at: s.start_session(pid, started_at=at),
    "end_session": lambda s, pid, at: s.end_session(s.start_session(pid), ended_at=at),
    "upsert_key_stat": lambda s, pid, at: s.upsert_key_stat(pid, "f", True, practised_at=at),
    "bump_key_recency": lambda s, pid, at: s.bump_key_recency(pid, "f", practised_at=at),
    "mark_introduced": lambda s, pid, at: s.mark_introduced(pid, ["f", "j"], at),
    "begin_phase": lambda s, pid, at: s.begin_phase(pid, "f", "A", 0, started_at=at),
    "record_phase": lambda s, pid, at: (
        s.begin_phase(pid, "f", "A", 0),
        s.record_phase(pid, "f", "A", 10, completed_at=at),
    ),
    "append_attempt": lambda s, pid, at: s.append_attempt(pid, "f", True, attempted_at=at),
    "count_attempt": lambda s, pid, at: s.count_attempt(pid, "f", True, attempted_at=at),
    "record_milestone": lambda s, pid, at: s.record_milestone(pid, "anchor", achieved_at=at),
    "append_letter_lengths": lambda s, pid, at: s.append_letter_lengths(
        pid, "voice", 1.0, [("f", 450)], recorded_at=at
    ),
    "record_stable": lambda s, pid, at: (
        s.mark_introduced(pid, ["f"]),
        s.record_stable(pid, "f", 30, stable_at=at),
    ),
    "begin_level": lambda s, pid, at: (
        s.mark_introduced(pid, ["f"]),
        s.begin_level(pid, "f", "choose", s.start_session(pid), 0, started_at=at),
    ),
    "complete_level": lambda s, pid, at: (
        s.mark_introduced(pid, ["f"]),
        sid := s.start_session(pid),
        s.begin_level(pid, "f", "choose", sid, 0),
        s.complete_level(pid, "f", "choose", sid, 10, completed_at=at),
    ),
    "append_reach_press": lambda s, pid, at: (
        s.mark_introduced(pid, ["f"]),
        s.append_reach_press(pid, "f", True, pressed_at=at),
    ),
    "record_landing": lambda s, pid, at: s.record_landing(
        pid, s.start_session(pid), 1, "L-idx", 3, 4, True, landed_at=at
    ),
    "choose_rest_key": lambda s, pid, at: s.choose_rest_key(
        pid, "L-mid", 3, 3, "landings", chosen_at=at
    ),
    "mark_rest_key_ready": lambda s, pid, at: (
        s.choose_rest_key(pid, "L-mid", 3, 3, "landings"),
        s.mark_rest_key_ready(pid, "L-mid", ready_at=at),
    ),
    "mark_rest_key_passed": lambda s, pid, at: (
        s.choose_rest_key(pid, "L-mid", 3, 3, "landings"),
        s.mark_rest_key_passed(pid, "L-mid", passed_at=at),
    ),
}


class TestUtcStamp:
    """ADR-011 § Timestamps are UTC — the contract itself."""

    def test_a_utc_instant_is_returned_unchanged(self) -> None:
        assert utc_stamp(UTC_STAMP) == UTC_STAMP

    def test_what_the_stores_write_by_default_passes(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.append_attempt(p.id, "f", True)
        assert utc_stamp(p.created_at) == p.created_at
        (attempt,) = any_store.window_attempts(p.id, "f")
        assert utc_stamp(attempt.attempted_at) == attempt.attempted_at

    @pytest.mark.parametrize("stamp", NOT_UTC)
    def test_anything_else_is_refused(self, stamp: str) -> None:
        with pytest.raises(ValueError):
            utc_stamp(stamp)


class TestOnlyUtcIsStored:
    """No timestamp without UTC lands in a store, real or fake."""

    def test_every_timestamp_parameter_on_the_protocol_is_covered(self) -> None:
        # Derived from the Protocol, so a new method that takes a timestamp
        # cannot be added without a row in WRITES.
        takes_a_stamp = {
            name
            for name, member in vars(Store).items()
            if callable(member)
            and any(arg.endswith("_at") for arg in member.__annotations__ if arg != "attempts_at")
        }
        assert takes_a_stamp == set(WRITES)

    @pytest.mark.parametrize("stamp", NOT_UTC)
    @pytest.mark.parametrize("method", sorted(WRITES))
    def test_a_write_refuses_it(self, any_store: Store, method: str, stamp: str) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.upsert_key_stat(p.id, "f", True, practised_at=UTC_STAMP)
        with pytest.raises(ValueError):
            WRITES[method](any_store, p.id, stamp)

    @pytest.mark.parametrize("method", sorted(WRITES))
    def test_a_write_accepts_utc(self, any_store: Store, method: str) -> None:
        p = any_store.create_profile("Alice", "en")
        WRITES[method](any_store, p.id, UTC_STAMP)

    def test_a_refused_attempt_leaves_no_row(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        with pytest.raises(ValueError):
            any_store.append_attempt(p.id, "f", True, attempted_at=NOT_UTC[0])
        assert any_store.window_attempts(p.id, "f") == []
        assert any_store.window_stats(p.id, "f") == WindowStats(0, 0, 0)


class TestOnlyUtcIsReadBack:
    """A row that got in some other way is refused on the way out (real store only)."""

    def bare(self, store: SqliteStore) -> int:
        bare = NOT_UTC[0]
        store.conn.execute(
            "INSERT INTO profiles (name, language, created_at) VALUES ('Old', 'en', ?)", (bare,)
        )
        pid = cast(int, store.conn.execute("SELECT max(id) FROM profiles").fetchone()[0])
        store.conn.execute(
            "INSERT INTO key_stats (profile_id, key_char, attempt_count, correct_count,"
            " last_practised_at) VALUES (?, 'f', 1, 1, ?)",
            (pid, bare),
        )
        store.conn.execute(
            "INSERT INTO key_attempts (profile_id, key_char, correct, attempted_at)"
            " VALUES (?, 'f', 1, ?)",
            (pid, bare),
        )
        store.conn.execute(
            "INSERT INTO introductions (profile_id, key_char, step, position, introduced_at)"
            " VALUES (?, 'f', 1, 0, ?)",
            (pid, bare),
        )
        return pid

    def test_every_read_that_returns_a_timestamp_refuses_it(self, store: SqliteStore) -> None:
        pid = self.bare(store)
        bare = NOT_UTC[0]
        store.conn.execute(
            "INSERT INTO sessions (id, profile_id, started_at) VALUES (7, ?, ?)", (pid, bare)
        )
        store.conn.execute(
            "INSERT INTO ramp_up_levels (profile_id, key_char, level, session_id,"
            " started_presses, started_at) VALUES (?, 'f', 'choose', 7, 0, ?)",
            (pid, bare),
        )
        store.conn.execute(
            "INSERT INTO reach_presses (profile_id, key_char, correct, pressed_at)"
            " VALUES (?, 'f', 1, ?)",
            (pid, bare),
        )
        store.conn.execute(
            "INSERT INTO landings (profile_id, session_id, round, finger, key_row, key_col,"
            " validated, landed_at) VALUES (?, 7, 1, 'L-idx', 3, 4, 1, ?)",
            (pid, bare),
        )
        store.conn.execute(
            "INSERT INTO rest_keys (profile_id, finger, key_row, key_col, chosen_by, chosen_at)"
            " VALUES (?, 'L-mid', 3, 3, 'landings', ?)",
            (pid, bare),
        )
        reads: list[Callable[[], object]] = [
            lambda: store.get_profile(pid),
            store.list_profiles,
            lambda: store.key_stats(pid),
            lambda: store.window_attempts(pid, "f"),
            lambda: store.introductions(pid),
            lambda: store.level_records(pid, "f"),
            lambda: store.reach_presses(pid, "f"),
            lambda: store.landings(pid),
            lambda: store.rest_keys(pid),
        ]
        for read in reads:
            with pytest.raises(ValueError):
                read()

    def test_a_bare_stamp_in_a_later_event_column_is_refused_too(self, store: SqliteStore) -> None:
        # The columns that stay NULL until their event happens are checked
        # when they are filled, not only the ones written with the row.
        pid = store.create_profile("Alice").id
        sid = store.start_session(pid)
        store.mark_introduced(pid, ["f"])
        store.begin_level(pid, "f", "choose", sid, 0)
        store.choose_rest_key(pid, "L-mid", 3, 3, "landings")
        bare = NOT_UTC[0]
        updates = [
            ("UPDATE introductions SET stable_at = ?", lambda: store.introductions(pid)),
            ("UPDATE ramp_up_levels SET completed_at = ?", lambda: store.level_records(pid, "f")),
            ("UPDATE rest_keys SET ready_at = ?", lambda: store.rest_keys(pid)),
            ("UPDATE rest_keys SET ready_at = NULL, passed_at = ?", lambda: store.rest_keys(pid)),
            (
                "UPDATE rest_keys SET passed_at = NULL, replaced_at = ?",
                lambda: store.rest_keys(pid),
            ),
        ]
        for sql, read in updates:
            store.conn.execute(sql, (bare,))
            with pytest.raises(ValueError):
                read()


# POSIX only: Windows has no way to change a running process's timezone.
_tzset: Callable[[], None] | None = getattr(time, "tzset", None)


@pytest.fixture()
def timezone() -> Iterator[Callable[[str], None]]:
    assert _tzset is not None
    apply = _tzset
    before = os.environ.get("TZ")

    def use(name: str) -> None:
        os.environ["TZ"] = name
        apply()

    yield use
    if before is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = before
    apply()


@pytest.mark.skipif(_tzset is None, reason="the process timezone cannot be set here")
class TestPracticeDayIsLocal:
    """ADR-011: stored in UTC, but a practice day is the child's local day."""

    # 09:00 and 17:00 UTC: one day at Greenwich, either side of midnight in
    # Auckland (UTC+13 in January), and one day again in Los Angeles.
    @pytest.mark.parametrize(
        ("zone", "days"), [("UTC", 1), ("Pacific/Auckland", 2), ("America/Los_Angeles", 1)]
    )
    def test_the_same_two_instants_are_counted_by_the_local_calendar(
        self, any_store: Store, timezone: Callable[[str], None], zone: str, days: int
    ) -> None:
        timezone(zone)
        p = any_store.create_profile("Alice", "en")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T09:00:00+00:00")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T17:00:00+00:00")
        assert any_store.window_stats(p.id, "a").distinct_days == days

    def test_a_day_is_the_one_lived_when_the_press_was_written(
        self, any_store: Store, timezone: Callable[[str], None]
    ) -> None:
        # ADR-011, #12m session 2: the day is fixed at the write. Moving the
        # machine to another zone does not split or merge days already lived.
        timezone("UTC")
        p = any_store.create_profile("Alice", "en")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T09:00:00+00:00")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T17:00:00+00:00")
        timezone("Pacific/Auckland")
        assert any_store.window_stats(p.id, "a").distinct_days == 1


class TestPracticeDaysOutlastTheWindow:
    """Review of 2026-10-06, E4: 200 presses in one day must not take a key's earlier days."""

    EARLIER = (
        "2026-01-01T10:00:00+00:00",
        "2026-01-02T10:00:00+00:00",
        "2026-01-03T10:00:00+00:00",
    )
    TODAY = "2026-01-10T10:00:00+00:00"

    def test_the_days_survive_a_full_window_in_one_day(self, any_store: Store) -> None:
        store = any_store
        p = store.create_profile("Alice", "en")
        for stamp in self.EARLIER:
            store.count_attempt(p.id, "f", True, stamp)
        for _ in range(config.ATTEMPT_WINDOW):
            store.count_attempt(p.id, "f", True, self.TODAY)
        # Every row of the window is today's; the three earlier days are evicted
        # from it and still counted. Read over the window, this was 1.
        assert {a.attempted_at for a in store.window_attempts(p.id, "f")} == {self.TODAY}
        assert store.window_stats(p.id, "f") == WindowStats(
            config.ATTEMPT_WINDOW, config.ATTEMPT_WINDOW, 4
        )

    def test_a_known_key_stays_known_through_a_long_day(self, any_store: Store) -> None:
        # The review's repro, through Known itself: `f` has earlier days and
        # is pressed 200 times today. Before the change it lost Known on the
        # 200th press and needed a slot again until tomorrow.
        store = any_store
        p = store.create_profile("Alice", "en")
        states = KeyStates(store, p.id, now=lambda: self.TODAY)
        for stamp in self.EARLIER:
            store.count_attempt(p.id, "f", True, stamp)
        for _ in range(config.ATTEMPT_WINDOW):
            store.count_attempt(p.id, "f", True, self.TODAY)
        assert states.state("f") is KeyState.KNOWN

    def test_presses_that_are_not_attempts_add_no_day(self, any_store: Store) -> None:
        # A Reach press and a landing are not counted (ADR-024, ADR-033), so
        # they are not practice either.
        p = any_store.create_profile("Alice", "en")
        any_store.mark_introduced(p.id, ["f"])
        any_store.append_reach_press(p.id, "f", True, self.TODAY)
        any_store.record_landing(p.id, any_store.start_session(p.id), 1, "L-idx", 3, 4, True)
        assert any_store.window_stats(p.id, "f") == WindowStats(0, 0, 0)
        assert any_store.key_stats(p.id) == {}

    def test_days_belong_to_one_profile_and_one_key(self, any_store: Store) -> None:
        a = any_store.create_profile("Alice", "en")
        b = any_store.create_profile("Bob", "en")
        any_store.append_attempt(a.id, "f", True, self.EARLIER[0])
        any_store.append_attempt(a.id, "f", True, self.EARLIER[1])
        any_store.append_attempt(a.id, "j", True, self.EARLIER[2])
        any_store.append_attempt(b.id, "f", True, self.EARLIER[2])
        assert any_store.window_stats(a.id, "f").distinct_days == 2
        assert any_store.window_stats(a.id, "j").distinct_days == 1
        assert any_store.window_stats(b.id, "f").distinct_days == 1


class TestProfiles:
    def test_create_returns_profile_with_id(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        assert p.id == 1
        assert p.name == "Alice"
        assert p.language == "en"

    def test_get_by_id(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        fetched = store.get_profile(p.id)
        assert fetched == p

    def test_get_missing_returns_none(self, store: SqliteStore) -> None:
        assert store.get_profile(999) is None

    def test_list_profiles_empty(self, store: SqliteStore) -> None:
        assert store.list_profiles() == []

    def test_list_profiles_multiple(self, store: SqliteStore) -> None:
        a = store.create_profile("Alice", "en")
        b = store.create_profile("Bob", "is")
        assert store.list_profiles() == [a, b]

    def test_nullable_columns_round_trip_none(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        fetched = store.get_profile(p.id)
        assert fetched is not None
        assert fetched.tts_voice is None
        assert fetched.tts_rate is None
        assert fetched.talk_key is None
        assert fetched.reread_key is None
        assert fetched.restart_key is None
        assert fetched.ptt_mode is None

    def test_nullable_columns_round_trip_values(self, store: SqliteStore) -> None:
        p = store.create_profile(
            "Bob",
            "is",
            tts_voice="en-us",
            tts_rate=1.2,
            talk_key="ctrl_r",
            reread_key="ctrl_r2",
            restart_key="ctrl_r3",
            ptt_mode="hold",
        )
        fetched = store.get_profile(p.id)
        assert fetched is not None
        assert fetched.tts_voice == "en-us"
        assert fetched.tts_rate == pytest.approx(1.2)
        assert fetched.talk_key == "ctrl_r"
        assert fetched.reread_key == "ctrl_r2"
        assert fetched.restart_key == "ctrl_r3"
        assert fetched.ptt_mode == "hold"

    def test_created_at_injected(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en", created_at="2026-01-01T09:00:00+00:00")
        assert p.created_at == "2026-01-01T09:00:00+00:00"
        assert store.get_profile(p.id).created_at == "2026-01-01T09:00:00+00:00"  # type: ignore[union-attr]


class TestSessions:
    def test_start_returns_id(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        sid = store.start_session(p.id, started_at="2026-01-01T10:00:00+00:00")
        assert isinstance(sid, int)

    def test_start_ended_at_null(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        sid = store.start_session(p.id, started_at="2026-01-01T10:00:00+00:00")
        row = store.conn.execute("SELECT ended_at FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row[0] is None

    def test_end_sets_ended_at(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        sid = store.start_session(p.id, started_at="2026-01-01T10:00:00+00:00")
        store.end_session(sid, ended_at="2026-01-01T10:30:00+00:00")
        row = store.conn.execute("SELECT ended_at FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row[0] == "2026-01-01T10:30:00+00:00"

    def test_sequential_ids(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        s1 = store.start_session(p.id)
        s2 = store.start_session(p.id)
        assert s2 == s1 + 1


class TestKeyStats:
    def test_upsert_creates_row_on_first_call(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:00:00+00:00")
        row = store.conn.execute(
            "SELECT attempt_count, correct_count, last_practised_at FROM key_stats"
            " WHERE profile_id = ? AND key_char = ?",
            (p.id, "a"),
        ).fetchone()
        assert row == (1, 1, "2026-01-01T10:00:00+00:00")

    def test_upsert_accumulates(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:00:00+00:00")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:01:00+00:00")
        store.upsert_key_stat(p.id, "a", False, practised_at="2026-01-01T10:02:00+00:00")
        row = store.conn.execute(
            "SELECT attempt_count, correct_count, last_practised_at FROM key_stats"
            " WHERE profile_id = ? AND key_char = ?",
            (p.id, "a"),
        ).fetchone()
        assert row == (3, 2, "2026-01-01T10:02:00+00:00")

    def test_bump_recency_updates_timestamp(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:00:00+00:00")
        store.bump_key_recency(p.id, "a", practised_at="2026-01-01T10:05:00+00:00")
        row = store.conn.execute(
            "SELECT attempt_count, correct_count, last_practised_at FROM key_stats"
            " WHERE profile_id = ? AND key_char = ?",
            (p.id, "a"),
        ).fetchone()
        assert row == (1, 1, "2026-01-01T10:05:00+00:00")

    def test_upsert_independent_per_key(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.upsert_key_stat(p.id, "a", True)
        store.upsert_key_stat(p.id, "b", False)
        a_row = store.conn.execute(
            "SELECT attempt_count, correct_count FROM key_stats WHERE profile_id = ? AND key_char = ?",
            (p.id, "a"),
        ).fetchone()
        b_row = store.conn.execute(
            "SELECT attempt_count, correct_count FROM key_stats WHERE profile_id = ? AND key_char = ?",
            (p.id, "b"),
        ).fetchone()
        assert a_row == (1, 1)
        assert b_row == (1, 0)


class TestKeyAttempts:
    def test_append_single(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:00:00+00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 1
        assert stats.correct_count == 1

    def test_rolling_cap_count_stays_at_cap(self) -> None:
        store = SqliteStore(":memory:", window_cap=5)
        p = store.create_profile("Alice", "en")
        for i in range(7):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-01T{i:02d}:00:00+00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 5

    def test_rolling_cap_oldest_dropped(self) -> None:
        store = SqliteStore(":memory:", window_cap=5)
        p = store.create_profile("Alice", "en")
        # First row (to be evicted): wrong
        store.append_attempt(p.id, "a", False, attempted_at="2026-01-01T00:00:00+00:00")
        # Next 5 rows (all correct): these become the window
        for i in range(1, 6):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-01T{i:02d}:00:00+00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 5
        assert stats.correct_count == 5  # wrong row was evicted

    def test_rolling_cap_newest_kept(self) -> None:
        store = SqliteStore(":memory:", window_cap=3)
        p = store.create_profile("Alice", "en")
        for i in range(5):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-0{i + 1}T10:00:00+00:00")
        rows = store.conn.execute(
            "SELECT attempted_at FROM key_attempts WHERE profile_id = ? AND key_char = ? ORDER BY attempted_at",
            (p.id, "a"),
        ).fetchall()
        dates = [r[0] for r in rows]
        assert dates == [
            "2026-01-03T10:00:00+00:00",
            "2026-01-04T10:00:00+00:00",
            "2026-01-05T10:00:00+00:00",
        ]

    def test_cap_independent_per_char(self) -> None:
        store = SqliteStore(":memory:", window_cap=3)
        p = store.create_profile("Alice", "en")
        for i in range(4):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-0{i + 1}T10:00:00+00:00")
            store.append_attempt(p.id, "b", True, attempted_at=f"2026-01-0{i + 1}T11:00:00+00:00")
        assert store.window_stats(p.id, "a").attempt_count == 3
        assert store.window_stats(p.id, "b").attempt_count == 3


class TestWindowStats:
    def test_empty_stats(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 0
        assert stats.correct_count == 0
        assert stats.distinct_days == 0

    def test_attempt_and_correct_counts(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:00:00+00:00")
        store.append_attempt(p.id, "a", False, attempted_at="2026-01-01T10:01:00+00:00")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:02:00+00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 3
        assert stats.correct_count == 2

    # The instants are chosen so the answer is the same in every timezone: a
    # minute apart is one local day, 24 hours apart is two. What "local day"
    # means is pinned separately, in TestPracticeDayIsLocal.
    def test_distinct_days_same_day(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:00:00+00:00")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:01:00+00:00")
        assert any_store.window_stats(p.id, "a").distinct_days == 1

    def test_distinct_days_across_calendar_days(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:00:00+00:00")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:01:00+00:00")
        any_store.append_attempt(p.id, "a", False, attempted_at="2026-01-02T10:00:00+00:00")
        any_store.append_attempt(p.id, "a", True, attempted_at="2026-01-03T10:00:00+00:00")
        stats = any_store.window_stats(p.id, "a")
        assert stats.attempt_count == 4
        assert stats.correct_count == 3
        assert stats.distinct_days == 3

    def test_stats_isolated_per_profile(self, store: SqliteStore) -> None:
        a = store.create_profile("Alice", "en")
        b = store.create_profile("Bob", "en")
        store.append_attempt(a.id, "a", True, attempted_at="2026-01-01T10:00:00+00:00")
        store.append_attempt(a.id, "a", True, attempted_at="2026-01-01T10:01:00+00:00")
        store.append_attempt(b.id, "a", False, attempted_at="2026-01-01T10:00:00+00:00")
        assert store.window_stats(a.id, "a").attempt_count == 2
        assert store.window_stats(b.id, "a").attempt_count == 1
        assert store.window_stats(b.id, "a").correct_count == 0


class TestMilestones:
    def test_record_and_query(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-01T10:00:00+00:00")
        assert store.achieved_milestones(p.id) == ["bronze"]

    def test_record_idempotent(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-01T10:00:00+00:00")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-02T10:00:00+00:00")
        assert store.achieved_milestones(p.id) == ["bronze"]

    def test_query_empty(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        assert store.achieved_milestones(p.id) == []

    def test_multiple_milestones_ordered_by_achieved_at(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.record_milestone(p.id, "silver", achieved_at="2026-02-01T10:00:00+00:00")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-01T10:00:00+00:00")
        store.record_milestone(p.id, "gold", achieved_at="2026-03-01T10:00:00+00:00")
        assert store.achieved_milestones(p.id) == ["bronze", "silver", "gold"]

    def test_milestones_isolated_per_profile(self, store: SqliteStore) -> None:
        a = store.create_profile("Alice", "en")
        b = store.create_profile("Bob", "en")
        store.record_milestone(a.id, "bronze", achieved_at="2026-01-01T10:00:00+00:00")
        store.record_milestone(b.id, "silver", achieved_at="2026-01-01T10:00:00+00:00")
        assert store.achieved_milestones(a.id) == ["bronze"]
        assert store.achieved_milestones(b.id) == ["silver"]


class TestKeyStatsRead:
    def test_empty_on_a_fresh_profile(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        assert any_store.key_stats(p.id) == {}

    def test_one_row_per_practised_key(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.upsert_key_stat(p.id, "f", True, practised_at="2026-01-01T10:00:00+00:00")
        any_store.upsert_key_stat(p.id, "f", False, practised_at="2026-01-01T10:01:00+00:00")
        any_store.upsert_key_stat(p.id, "j", True, practised_at="2026-01-01T10:02:00+00:00")
        assert any_store.key_stats(p.id) == {
            "f": KeyStat(2, 1, "2026-01-01T10:01:00+00:00"),
            "j": KeyStat(1, 1, "2026-01-01T10:02:00+00:00"),
        }

    def test_a_recency_bump_shows_without_moving_the_counters(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.upsert_key_stat(p.id, "f", True, practised_at="2026-01-01T10:00:00+00:00")
        any_store.bump_key_recency(p.id, "f", practised_at="2026-01-01T10:05:00+00:00")
        assert any_store.key_stats(p.id) == {"f": KeyStat(1, 1, "2026-01-01T10:05:00+00:00")}

    def test_a_bump_on_an_unseen_key_creates_nothing(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.bump_key_recency(p.id, "f", practised_at="2026-01-01T10:00:00+00:00")
        assert any_store.key_stats(p.id) == {}

    def test_window_rows_alone_do_not_make_a_key_active(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.append_attempt(p.id, "f", True, attempted_at="2026-01-01T10:00:00+00:00")
        assert any_store.key_stats(p.id) == {}

    def test_isolated_per_profile(self, any_store: Store) -> None:
        a = any_store.create_profile("Alice", "en")
        b = any_store.create_profile("Bob", "en")
        any_store.upsert_key_stat(a.id, "f", True, practised_at="2026-01-01T10:00:00+00:00")
        any_store.upsert_key_stat(b.id, "j", True, practised_at="2026-01-01T10:00:00+00:00")
        assert set(any_store.key_stats(a.id)) == {"f"}
        assert set(any_store.key_stats(b.id)) == {"j"}


class TestEvictionParity:
    def test_out_of_order_timestamps_still_aggregate(self, any_store: Store) -> None:
        # Out-of-order arrival is not hypothetical. Timestamps are UTC now, which
        # has no fall-back hour, but the system clock they come from is not
        # monotonic: an NTP correction or a manual fix steps it back.
        store = any_store
        p = store.create_profile("Alice", "en")
        store.append_attempt(p.id, "f", False, attempted_at="2026-01-01T02:30:00+00:00")
        store.append_attempt(p.id, "f", True, attempted_at="2026-01-01T01:30:00+00:00")
        store.append_attempt(p.id, "f", True, attempted_at="2026-01-01T03:00:00+00:00")
        assert store.window_stats(p.id, "f") == WindowStats(3, 2, 1)

    def test_eviction_drops_the_first_to_arrive_not_the_oldest_stamp(self) -> None:
        """ADR-011: the window forgets in arrival order, both stores alike.

        Distinguishing the two rules takes a row whose *outcome* differs from the
        one a timestamp rule would drop -- the version of this test that only
        varied the stamps could not tell them apart, because both rules left two
        rows with one correct between them. Arrival order is what the derived
        ramp-up means by "the child's answers", and evicting by stamp let a clock
        that had run ahead delete the row just written, freezing the window.
        """
        stores: list[Store] = [SqliteStore(":memory:", window_cap=2), FakeStore(window_cap=2)]
        for store in stores:
            p = store.create_profile("Alice", "en")
            store.append_attempt(p.id, "f", True, attempted_at="2026-01-01T02:00:00+00:00")
            store.append_attempt(p.id, "f", False, attempted_at="2026-01-01T01:00:00+00:00")
            store.append_attempt(p.id, "f", True, attempted_at="2026-01-01T03:00:00+00:00")
            # The 02:00 row arrived first and goes, though 01:00 is the older stamp.
            assert [row.correct for row in store.window_attempts(p.id, "f")] == [False, True]


class TestIntroductions:
    """ADR-011's `introductions` — which step is current, after a restart."""

    def profile(self, any_store: Store) -> int:
        return any_store.create_profile("Alice").id

    def test_a_step_is_one_ordinal_and_keeps_its_member_order(self, any_store: Store) -> None:
        # The ordinal groups the step and the position preserves ADR-023's
        # left-hand-member-first order, which `members[0]` is read as.
        pid = self.profile(any_store)
        assert any_store.mark_introduced(pid, ["f", "j"]) == 1
        introduced = any_store.introductions(pid)
        assert [(i.key_char, i.step, i.position) for i in introduced] == [
            ("f", 1, 0),
            ("j", 1, 1),
        ]

    def test_steps_are_ordered_by_ordinal_not_by_clock(self, any_store: Store) -> None:
        # The second step's *timestamp* is older here, as an NTP correction or a
        # manual clock fix can make it even in UTC -- the system clock is not
        # monotonic. The ordinal is what says which came later.
        pid = self.profile(any_store)
        any_store.mark_introduced(pid, ["f", "j"], "2026-09-29T02:30:00+00:00")
        any_store.mark_introduced(pid, ["r", "u"], "2026-09-29T01:30:00+00:00")
        introduced = any_store.introductions(pid)
        assert [i.key_char for i in introduced] == ["f", "j", "r", "u"]
        assert {i.step for i in introduced if i.key_char in "fj"} == {1}
        assert {i.step for i in introduced if i.key_char in "ru"} == {2}

    def test_the_first_introduction_wins(self, any_store: Store) -> None:
        # A step introduced again -- the child never answered it -- keeps the
        # step identity it had, instead of moving under a resumed ramp-up.
        pid = self.profile(any_store)
        any_store.mark_introduced(pid, ["f"], "2026-09-01T10:00:00+00:00")
        any_store.mark_introduced(pid, ["f"], "2026-09-29T10:00:00+00:00")
        introduced = any_store.introductions(pid)
        assert [(i.key_char, i.step, i.introduced_at) for i in introduced] == [
            ("f", 1, "2026-09-01T10:00:00+00:00")
        ]

    def test_an_introduction_alone_does_not_make_a_key_active(self, any_store: Store) -> None:
        # Active is row presence in `key_stats` (ADR-027 § Key States). Writing
        # one here would consume the introduction of a step the child never
        # answered, which ADR-023 says is owed its script again.
        pid = self.profile(any_store)
        any_store.mark_introduced(pid, ["f", "j"])
        assert any_store.key_stats(pid) == {}

    def test_a_profile_with_no_introductions_is_empty(self, any_store: Store) -> None:
        assert any_store.introductions(self.profile(any_store)) == []


class TestWindowAttempts:
    """The ordered window read ADR-024's derived bars need."""

    def test_rows_come_back_oldest_first_with_their_columns(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.append_attempt(pid, "f", True, "2026-09-29T10:00:00+00:00", 120, None)
        any_store.append_attempt(pid, "f", False, "2026-09-29T10:00:01+00:00", None, "j")
        rows = any_store.window_attempts(pid, "f")
        assert [(r.correct, r.latency_ms, r.prev_char) for r in rows] == [
            (True, 120, None),
            (False, None, "j"),
        ]

    def test_a_signed_latency_its_letter_length_and_the_timeouts_come_back(
        self, any_store: Store
    ) -> None:
        # ADR-011, alpha-plan #12f: a press before the letter's usual end is a
        # negative latency, beside the length it was timed against.
        pid = any_store.create_profile("Alice").id
        stamp = "2026-10-04T10:00:00+00:00"
        any_store.append_attempt(pid, "f", True, stamp, 1020, "j", after_letter_ms=-180)
        any_store.append_attempt(pid, "f", True, stamp, 400)
        any_store.append_attempt(pid, "f", True, stamp, timeouts=2)
        any_store.append_attempt(pid, "f", False, stamp)
        rows = any_store.window_attempts(pid, "f")
        assert [(r.latency_ms, r.after_letter_ms, r.timeouts) for r in rows] == [
            (1020, -180, 0),
            (400, None, 0),
            (None, None, 2),
            (None, None, 0),
        ]

    def test_equal_timestamps_keep_insertion_order(self, any_store: Store) -> None:
        # A drill puts several attempts inside one second, and a streak read in
        # the wrong order is a different streak.
        pid = any_store.create_profile("Alice").id
        for correct in (True, False, True, True):
            any_store.append_attempt(pid, "f", correct, "2026-09-29T10:00:00+00:00")
        assert [r.correct for r in any_store.window_attempts(pid, "f")] == [
            True,
            False,
            True,
            True,
        ]

    def test_an_untouched_key_has_no_rows(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        assert any_store.window_attempts(pid, "f") == []

    def test_a_limit_keeps_the_latest_rows_and_zero_keeps_none(self, any_store: Store) -> None:
        # How a ramp-up phase reads its evidence: the rows since it began
        # (ADR-024 § Ramp-up variability), and none of the ones before.
        pid = any_store.create_profile("Alice").id
        for correct in (True, True, False, True, False):
            any_store.append_attempt(pid, "f", correct, "2026-09-29T10:00:00+00:00")
        assert [r.correct for r in any_store.window_attempts(pid, "f", limit=2)] == [True, False]
        assert len(any_store.window_attempts(pid, "f", limit=9)) == 5
        assert any_store.window_attempts(pid, "f", limit=0) == []


class TestCountedAttempt:
    """ADR-011: a counted attempt is one lifetime count and one window row, written together."""

    STAMP = "2026-10-07T10:00:00+00:00"

    def test_it_writes_the_count_and_the_row_with_one_stamp(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.count_attempt(pid, "f", True, self.STAMP, 400, "j", after_letter_ms=-50)
        any_store.count_attempt(pid, "f", False, self.STAMP, timeouts=1)
        assert any_store.key_stats(pid) == {"f": KeyStat(2, 1, self.STAMP)}
        rows = any_store.window_attempts(pid, "f")
        assert rows == [
            Attempt(True, self.STAMP, latency_ms=400, prev_char="j", after_letter_ms=-50),
            Attempt(False, self.STAMP, timeouts=1),
        ]

    def test_a_refused_stamp_leaves_neither(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        with pytest.raises(ValueError):
            any_store.count_attempt(pid, "f", True, "2026-10-07T10:00:00")
        assert any_store.key_stats(pid) == {}
        assert any_store.window_attempts(pid, "f") == []

    def test_a_failure_between_the_two_writes_leaves_neither(self) -> None:
        # What a kill between two separate commits used to leave: the count
        # one ahead of the rows for good (alpha-plan #12k, R1).
        class Killed(SqliteStore):
            def _append_attempt(self, *args: Any, **kwargs: Any) -> None:
                raise RuntimeError("killed")

        store = Killed(":memory:")
        pid = store.create_profile("Alice").id
        with pytest.raises(RuntimeError, match="killed"):
            store.count_attempt(pid, "f", True, self.STAMP)
        assert store.key_stats(pid) == {}
        assert store.window_attempts(pid, "f") == []

    def test_a_failure_at_the_practice_day_leaves_nothing(self) -> None:
        # ADR-011, #12m session 2: the day is written with the row, in the
        # same transaction, so neither can stand without the other.
        store = SqliteStore(":memory:")
        pid = store.create_profile("Alice").id
        with failing_on(store, "INTO practice_days"), pytest.raises(RuntimeError, match="killed"):
            store.count_attempt(pid, "f", True, self.STAMP)
        with failing_on(store, "INTO practice_days"), pytest.raises(RuntimeError, match="killed"):
            store.append_attempt(pid, "f", True, self.STAMP)
        assert store.key_stats(pid) == {}
        assert store.window_attempts(pid, "f") == []
        assert store.window_stats(pid, "f") == WindowStats(0, 0, 0)


class TestPhaseRecords:
    """ADR-011's `ramp_up_phases`: one record per key per phase, with both ends."""

    def test_a_phase_is_begun_and_then_completed(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice")
        any_store.begin_phase(p.id, "f", "A", 0)
        assert any_store.phase_records(p.id, "f") == {"A": PhaseRecord(0)}
        any_store.record_phase(p.id, "f", "A", 10)
        any_store.begin_phase(p.id, "f", "B", 14)
        assert any_store.phase_records(p.id, "f") == {
            "A": PhaseRecord(0, 10),
            "B": PhaseRecord(14),
        }

    def test_both_ends_are_written_once(self, any_store: Store) -> None:
        # The start bounds the phase's evidence and the completion is a fact
        # about the child: neither moves once written.
        p = any_store.create_profile("Alice")
        any_store.begin_phase(p.id, "f", "A", 0)
        any_store.begin_phase(p.id, "f", "A", 5)
        any_store.record_phase(p.id, "f", "A", 10)
        any_store.record_phase(p.id, "f", "A", 25)
        any_store.begin_phase(p.id, "f", "A", 30)
        assert any_store.phase_records(p.id, "f") == {"A": PhaseRecord(0, 10)}

    def test_a_completion_without_a_start_is_refused(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice")
        with pytest.raises(ValueError, match="never begun"):
            any_store.record_phase(p.id, "f", "A", 10)
        assert any_store.phase_records(p.id, "f") == {}

    def test_records_belong_to_one_profile_and_one_key(self, any_store: Store) -> None:
        alice = any_store.create_profile("Alice")
        bob = any_store.create_profile("Bob")
        any_store.begin_phase(alice.id, "f", "A", 0)
        any_store.begin_phase(alice.id, "j", "A", 3)
        any_store.begin_phase(bob.id, "f", "A", 7)
        assert any_store.phase_records(alice.id, "f") == {"A": PhaseRecord(0)}
        assert any_store.phase_records(alice.id, "j") == {"A": PhaseRecord(3)}
        assert any_store.phase_records(bob.id, "f") == {"A": PhaseRecord(7)}

    def test_the_stored_stamps_are_utc(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice")
        store.begin_phase(p.id, "f", "A", 0)
        store.record_phase(p.id, "f", "A", 10)
        (started_at, completed_at) = store.conn.execute(
            "SELECT started_at, completed_at FROM ramp_up_phases"
        ).fetchone()
        assert utc_stamp(started_at) == started_at
        assert utc_stamp(completed_at) == completed_at


T1 = "2026-11-01T10:00:00+00:00"
T2 = "2026-11-01T10:05:00+00:00"
T3 = "2026-11-02T10:00:00+00:00"
T4 = "2026-11-03T10:00:00+00:00"


class TestTheBar:
    """ADR-011, #12m session 2: ADR-024's one bar, met once, on the letter's introduction."""

    def test_the_bar_is_recorded_on_the_introduction(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.mark_introduced(pid, ["f", "j"], T1)
        any_store.record_stable(pid, "j", 31, T2)
        assert any_store.introductions(pid) == [
            Introduction("f", 1, 0, T1),
            Introduction("j", 1, 1, T1, stable_attempts=31, stable_at=T2),
        ]

    def test_it_is_written_once(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.mark_introduced(pid, ["f"], T1)
        any_store.record_stable(pid, "f", 30, T2)
        any_store.record_stable(pid, "f", 60, T3)
        assert any_store.introductions(pid) == [Introduction("f", 1, 0, T1, 30, T2)]

    def test_a_letter_never_introduced_is_refused(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        with pytest.raises(ValueError, match="never introduced"):
            any_store.record_stable(pid, "f", 30, T2)
        assert any_store.introductions(pid) == []

    def test_it_belongs_to_one_profile(self, any_store: Store) -> None:
        alice = any_store.create_profile("Alice").id
        bob = any_store.create_profile("Bob").id
        any_store.mark_introduced(alice, ["f"], T1)
        any_store.mark_introduced(bob, ["f"], T1)
        any_store.record_stable(alice, "f", 30, T2)
        assert any_store.introductions(bob) == [Introduction("f", 1, 0, T1)]


class TestLevelRecords:
    """ADR-011 `ramp_up_levels`: each run of each level, by name, with both ends."""

    def profile(self, store: Store, name: str = "Alice") -> int:
        # A level run is for a letter of a step, so the letters are introduced.
        pid = store.create_profile(name).id
        store.mark_introduced(pid, ["d", "k"])
        return pid

    def test_a_letter_never_introduced_is_refused(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        sid = any_store.start_session(pid)
        with pytest.raises(ValueError, match="never introduced"):
            any_store.begin_level(pid, "q", "reach", sid, 0, T1)
        assert any_store.level_records(pid, "q") == []

    def test_levels_are_begun_and_completed_in_order(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        sid = any_store.start_session(pid)
        any_store.begin_level(pid, "d", "reach", sid, 0, T1)
        any_store.complete_level(pid, "d", "reach", sid, 12, T2)
        any_store.begin_level(pid, "d", "choose", sid, 0, T2)
        assert any_store.level_records(pid, "d") == [
            LevelRecord("reach", sid, 0, T1, 12, T2),
            LevelRecord("choose", sid, 0, T2),
        ]

    def test_both_ends_are_written_once_within_a_session(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        sid = any_store.start_session(pid)
        any_store.begin_level(pid, "d", "choose", sid, 4, T1)
        any_store.begin_level(pid, "d", "choose", sid, 9, T2)
        any_store.complete_level(pid, "d", "choose", sid, 14, T2)
        any_store.complete_level(pid, "d", "choose", sid, 20, T3)
        assert any_store.level_records(pid, "d") == [LevelRecord("choose", sid, 4, T1, 14, T2)]

    def test_reach_started_again_after_a_restart_is_a_new_run(self, any_store: Store) -> None:
        # ADR-024: a step not yet at Choose starts Reach from nothing after a
        # restart, also a member that had met Reach's rule. The earlier run
        # stays, as history, and each completion names its own run.
        pid = self.profile(any_store)
        first = any_store.start_session(pid)
        any_store.begin_level(pid, "d", "reach", first, 0, T1)
        any_store.complete_level(pid, "d", "reach", first, 10, T2)
        second = any_store.start_session(pid)
        any_store.begin_level(pid, "d", "reach", second, 14, T3)
        any_store.complete_level(pid, "d", "reach", second, 24, T4)
        assert any_store.level_records(pid, "d") == [
            LevelRecord("reach", first, 0, T1, 10, T2),
            LevelRecord("reach", second, 14, T3, 24, T4),
        ]

    def test_a_run_begun_in_an_earlier_session_is_completed_by_naming_it(
        self, any_store: Store
    ) -> None:
        # Choose survives a restart (ADR-024), so its run can end sessions later.
        pid = self.profile(any_store)
        first = any_store.start_session(pid)
        any_store.begin_level(pid, "d", "choose", first, 20, T1)
        second = any_store.start_session(pid)
        with pytest.raises(ValueError, match="never begun in that session"):
            any_store.complete_level(pid, "d", "choose", second, 30, T3)
        any_store.complete_level(pid, "d", "choose", first, 30, T3)
        assert any_store.level_records(pid, "d") == [LevelRecord("choose", first, 20, T1, 30, T3)]

    def test_a_completion_without_a_start_is_refused(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        sid = any_store.start_session(pid)
        any_store.begin_level(pid, "d", "reach", sid, 0, T1)
        with pytest.raises(ValueError, match="never begun"):
            any_store.complete_level(pid, "d", "choose", sid, 10, T2)
        assert any_store.level_records(pid, "d") == [LevelRecord("reach", sid, 0, T1)]

    def test_records_belong_to_one_profile_and_one_letter(self, any_store: Store) -> None:
        alice = self.profile(any_store, "Alice")
        bob = self.profile(any_store, "Bob")
        a_sid = any_store.start_session(alice)
        b_sid = any_store.start_session(bob)
        any_store.begin_level(alice, "d", "choose", a_sid, 1, T1)
        any_store.begin_level(alice, "k", "choose", a_sid, 2, T1)
        any_store.begin_level(bob, "d", "choose", b_sid, 3, T1)
        any_store.complete_level(alice, "k", "choose", a_sid, 12, T2)
        assert any_store.level_records(alice, "d") == [LevelRecord("choose", a_sid, 1, T1)]
        assert any_store.level_records(alice, "k") == [LevelRecord("choose", a_sid, 2, T1, 12, T2)]
        assert any_store.level_records(bob, "d") == [LevelRecord("choose", b_sid, 3, T1)]

    def test_the_order_is_the_order_begun_not_the_clock(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        sid = any_store.start_session(pid)
        any_store.begin_level(pid, "d", "travel", sid, 0, T3)
        any_store.begin_level(pid, "d", "choose", sid, 0, T1)
        assert [r.level for r in any_store.level_records(pid, "d")] == ["travel", "choose"]


class TestReachPresses:
    """ADR-011 `reach_presses`: kept apart from `key_attempts`, and never trimmed."""

    def profile(self, store: Store, name: str = "Alice") -> int:
        # A Reach press is for a letter of a step, so the letters are introduced.
        pid = store.create_profile(name).id
        store.mark_introduced(pid, ["d", "k"])
        return pid

    def test_a_letter_never_introduced_is_refused(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        with pytest.raises(ValueError, match="never introduced"):
            any_store.append_reach_press(pid, "q", True, T1)
        assert any_store.reach_presses(pid, "q") == []

    def test_presses_come_back_in_the_order_pressed(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        any_store.append_reach_press(pid, "d", True, T2)
        any_store.append_reach_press(pid, "d", False, T1)
        any_store.append_reach_press(pid, "k", True, T1)
        assert any_store.reach_presses(pid, "d") == [ReachPress(True, T2), ReachPress(False, T1)]
        assert any_store.reach_presses(pid, "k") == [ReachPress(True, T1)]

    def test_they_are_not_attempts_and_make_no_key_active(self, any_store: Store) -> None:
        pid = self.profile(any_store)
        any_store.append_reach_press(pid, "d", True, T1)
        assert any_store.window_attempts(pid, "d") == []
        assert any_store.key_stats(pid) == {}

    @pytest.mark.parametrize("kind", ["sqlite", "fake"])
    def test_the_attempt_window_does_not_trim_them(self, kind: str) -> None:
        store: Store = (
            SqliteStore(":memory:", window_cap=2) if kind == "sqlite" else FakeStore(window_cap=2)
        )
        pid = self.profile(store)
        for correct in (False, True, True, False, True):
            store.append_reach_press(pid, "d", correct, T1)
        assert [p.correct for p in store.reach_presses(pid, "d")] == [
            False,
            True,
            True,
            False,
            True,
        ]

    def test_they_belong_to_one_profile(self, any_store: Store) -> None:
        alice = self.profile(any_store, "Alice")
        bob = self.profile(any_store, "Bob")
        any_store.append_reach_press(alice, "d", True, T1)
        assert any_store.reach_presses(bob, "d") == []


class TestLandings:
    """ADR-011 `landings`: one row per alignment press, by finger and cell (ADR-033)."""

    def test_landings_come_back_exactly_in_the_order_pressed(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        sid = any_store.start_session(pid)
        # A round's opening: both bumps, the left one missed, then the little
        # fingers, the left one judged against a bump press that was not the bump.
        any_store.record_landing(pid, sid, 1, "L-idx", 3, 5, False, T2)
        any_store.record_landing(pid, sid, 1, "R-idx", 3, 7, True, T2)
        any_store.record_landing(pid, sid, 1, "L-pink", 3, 1, False, T1)
        any_store.record_landing(pid, sid, 1, "R-pink", 3, 10, True, T1)
        any_store.record_landing(pid, sid, 2, "L-idx", 3, 4, True, T3)
        assert any_store.landings(pid) == [
            Landing(sid, 1, "L-idx", 3, 5, False, T2),
            Landing(sid, 1, "R-idx", 3, 7, True, T2),
            Landing(sid, 1, "L-pink", 3, 1, False, T1),
            Landing(sid, 1, "R-pink", 3, 10, True, T1),
            Landing(sid, 2, "L-idx", 3, 4, True, T3),
        ]

    def test_a_landing_writes_nothing_else(self, any_store: Store) -> None:
        # ADR-033: no alignment press writes to `key_attempts` or `key_stats`
        # or makes a key Active, whatever letter its cell carries.
        pid = any_store.create_profile("Alice").id
        any_store.record_landing(pid, any_store.start_session(pid), 1, "L-idx", 3, 4, True, T1)
        assert any_store.key_stats(pid) == {}
        assert any_store.window_attempts(pid, "f") == []

    def test_landings_belong_to_one_profile(self, any_store: Store) -> None:
        alice = any_store.create_profile("Alice").id
        bob = any_store.create_profile("Bob").id
        any_store.record_landing(alice, any_store.start_session(alice), 1, "L-idx", 3, 4, True, T1)
        assert any_store.landings(bob) == []

    def test_the_sessions_are_kept_apart(self, any_store: Store) -> None:
        # The `rest` rung reads the first round of each of the last five
        # sessions (ADR-033), so a round number alone is not enough.
        pid = any_store.create_profile("Alice").id
        first = any_store.start_session(pid)
        second = any_store.start_session(pid)
        any_store.record_landing(pid, first, 1, "R-pink", 2, 11, True, T1)
        any_store.record_landing(pid, second, 1, "R-pink", 3, 10, True, T3)
        assert [(x.session_id, x.round, x.row, x.col) for x in any_store.landings(pid)] == [
            (first, 1, 2, 11),
            (second, 1, 3, 10),
        ]


class TestRestKeys:
    """ADR-011 `rest_keys`: each finger's rest key and its events, replaced keys kept."""

    def test_a_key_is_chosen_becomes_ready_and_passes(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.choose_rest_key(pid, "L-mid", 2, 3, "landings", T1)
        any_store.mark_rest_key_ready(pid, "L-mid", T2)
        any_store.mark_rest_key_passed(pid, "L-mid", T3)
        assert any_store.rest_keys(pid) == [RestKey("L-mid", 2, 3, "landings", T1, T2, T3)]

    def test_each_event_is_written_once(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.choose_rest_key(pid, "L-mid", 2, 3, "landings", T1)
        any_store.mark_rest_key_ready(pid, "L-mid", T2)
        any_store.mark_rest_key_ready(pid, "L-mid", T3)
        any_store.mark_rest_key_passed(pid, "L-mid", T3)
        any_store.mark_rest_key_passed(pid, "L-mid", T4)
        assert any_store.rest_keys(pid) == [RestKey("L-mid", 2, 3, "landings", T1, T2, T3)]

    def test_the_same_key_chosen_again_changes_nothing(self, any_store: Store) -> None:
        # A ready finger asked the question again (ADR-033) may answer with the
        # key it already has: it keeps its events and how it was first chosen.
        pid = any_store.create_profile("Alice").id
        any_store.choose_rest_key(pid, "R-ring", 3, 9, "landings", T1)
        any_store.mark_rest_key_ready(pid, "R-ring", T2)
        any_store.choose_rest_key(pid, "R-ring", 3, 9, "answer", T3)
        assert any_store.rest_keys(pid) == [RestKey("R-ring", 3, 9, "landings", T1, T2)]

    def test_a_changed_key_keeps_the_old_one_with_when_it_was_replaced(
        self, any_store: Store
    ) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.choose_rest_key(pid, "R-pink", 3, 10, "landings", T1)
        any_store.mark_rest_key_ready(pid, "R-pink", T2)
        any_store.choose_rest_key(pid, "R-pink", 2, 11, "answer", T3)
        any_store.mark_rest_key_ready(pid, "R-pink", T4)
        assert any_store.rest_keys(pid) == [
            RestKey("R-pink", 3, 10, "landings", T1, ready_at=T2, replaced_at=T3),
            RestKey("R-pink", 2, 11, "answer", T3, ready_at=T4),
        ]

    def test_a_mark_without_a_key_is_refused(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.choose_rest_key(pid, "L-mid", 2, 3, "landings", T1)
        with pytest.raises(ValueError, match="no rest key"):
            any_store.mark_rest_key_ready(pid, "R-mid", T2)
        with pytest.raises(ValueError, match="no rest key"):
            any_store.mark_rest_key_passed(pid, "R-mid", T2)
        assert any_store.rest_keys(pid) == [RestKey("L-mid", 2, 3, "landings", T1)]

    def test_fingers_and_profiles_are_kept_apart(self, any_store: Store) -> None:
        # An index finger's key is the bump, which the child does not choose.
        alice = any_store.create_profile("Alice").id
        bob = any_store.create_profile("Bob").id
        any_store.choose_rest_key(alice, "L-idx", 3, 4, "bump", T1)
        any_store.choose_rest_key(alice, "L-mid", 3, 3, "landings", T1)
        any_store.choose_rest_key(bob, "L-mid", 2, 3, "answer", T1)
        any_store.mark_rest_key_ready(alice, "L-idx", T2)
        assert any_store.rest_keys(alice) == [
            RestKey("L-idx", 3, 4, "bump", T1, ready_at=T2),
            RestKey("L-mid", 3, 3, "landings", T1),
        ]
        assert any_store.rest_keys(bob) == [RestKey("L-mid", 2, 3, "answer", T1)]

    def test_the_schema_allows_one_current_key_per_finger(self) -> None:
        store = SqliteStore(":memory:")
        pid = store.create_profile("Alice").id
        store.choose_rest_key(pid, "R-pink", 3, 10, "landings", T1)
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            store.conn.execute(
                "INSERT INTO rest_keys (profile_id, finger, key_row, key_col, chosen_by, chosen_at)"
                " VALUES (?, 'R-pink', 2, 11, 'answer', ?)",
                (pid, T2),
            )

    def test_a_failed_change_leaves_the_old_key_current(self) -> None:
        # The replacement and the new key are one transaction: a finger never
        # has two current keys, or none between them.
        store = SqliteStore(":memory:")
        pid = store.create_profile("Alice").id
        store.choose_rest_key(pid, "R-pink", 3, 10, "landings", T1)
        with (
            failing_on(store, "INSERT INTO rest_keys"),
            pytest.raises(RuntimeError, match="killed"),
        ):
            store.choose_rest_key(pid, "R-pink", 2, 11, "answer", T2)
        assert store.rest_keys(pid) == [RestKey("R-pink", 3, 10, "landings", T1)]


class TestRefusalsLeaveNoTransactionOpen:
    """A refused write rolls back what it ran, so no lock outlives it (SQLite)."""

    def test_each_refusal_leaves_the_connection_idle(self) -> None:
        store = SqliteStore(":memory:")
        pid = store.create_profile("Alice").id
        sid = store.start_session(pid)
        store.mark_introduced(pid, ["d"])
        refusals: list[tuple[type[Exception], Callable[[], object]]] = [
            (ValueError, lambda: store.record_phase(pid, "f", "A", 10)),
            (ValueError, lambda: store.record_stable(pid, "f", 30)),
            (ValueError, lambda: store.complete_level(pid, "f", "choose", sid, 10)),
            (ValueError, lambda: store.mark_rest_key_ready(pid, "L-mid")),
            (ValueError, lambda: store.mark_rest_key_passed(pid, "L-mid")),
            # Refused by SQLite itself, partway through an INSERT.
            (sqlite3.IntegrityError, lambda: store.begin_level(pid, "d", cast(Level, "x"), sid, 0)),
            (ValueError, lambda: store.append_reach_press(pid, "q", True)),
            (
                sqlite3.IntegrityError,
                lambda: store.choose_rest_key(99, "L-mid", 3, 3, "landings"),
            ),
        ]
        for error, refusal in refusals:
            with pytest.raises(error):
                refusal()
            assert not store.conn.in_transaction


class TestOnlyTheNamedValuesAreStored:
    """A level or a way of choosing outside the Protocol's names is refused by both stores."""

    def test_a_level_by_another_name_is_refused(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.mark_introduced(pid, ["d"])
        sid = any_store.start_session(pid)
        with pytest.raises(sqlite3.IntegrityError):
            any_store.begin_level(pid, "d", cast(Level, "Reach"), sid, 0, T1)
        assert any_store.level_records(pid, "d") == []

    def test_a_rest_key_chosen_another_way_is_refused(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        with pytest.raises(sqlite3.IntegrityError):
            any_store.choose_rest_key(pid, "L-mid", 3, 3, cast(ChosenBy, "answered"), T1)
        assert any_store.rest_keys(pid) == []


class TestTheRestRung:
    """ADR-033's first rung is recorded as any rung is: a `milestones` row (ADR-011)."""

    def test_it_is_stored_and_read_back_in_the_order_earned(self, any_store: Store) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.record_milestone(pid, "third", T1)
        any_store.record_milestone(pid, "rest", T2)
        any_store.record_milestone(pid, "rest", T3)
        assert any_store.achieved_milestones(pid) == ["third", "rest"]


class TestLetterLengths:
    """ADR-011 § letter_lengths: full playbacks, kept per letter, voice and rate."""

    def test_lengths_come_back_oldest_first(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        any_store.append_letter_lengths(p.id, "voice", 1.0, [("f", 450), ("j", 500)])
        any_store.append_letter_lengths(p.id, "voice", 1.0, [("f", 470), ("f", 430)])
        assert any_store.letter_lengths(p.id, "f", "voice", 1.0) == [450, 470, 430]
        assert any_store.letter_lengths(p.id, "j", "voice", 1.0) == [500]

    def test_a_letter_never_measured_has_none(self, any_store: Store) -> None:
        p = any_store.create_profile("Alice", "en")
        assert any_store.letter_lengths(p.id, "f", "voice", 1.0) == []

    def test_a_length_belongs_to_one_voice_one_rate_and_one_profile(self, any_store: Store) -> None:
        a = any_store.create_profile("Alice", "en")
        b = any_store.create_profile("Bob", "en")
        any_store.append_letter_lengths(a.id, "voice", 1.0, [("f", 450)])
        assert any_store.letter_lengths(a.id, "f", "other", 1.0) == []
        assert any_store.letter_lengths(a.id, "f", "voice", 1.2) == []
        assert any_store.letter_lengths(b.id, "f", "voice", 1.0) == []

    @pytest.mark.parametrize("kind", ["sqlite", "fake"])
    def test_only_the_newest_are_kept_per_letter_voice_and_rate(self, kind: str) -> None:
        store: Store = (
            SqliteStore(":memory:", length_cap=3) if kind == "sqlite" else FakeStore(length_cap=3)
        )
        p = store.create_profile("Alice", "en")
        store.append_letter_lengths(p.id, "other", 1.0, [("f", 900)])
        store.append_letter_lengths(p.id, "voice", 1.2, [("f", 800)])
        store.append_letter_lengths(p.id, "voice", 1.0, [("j", 700)])
        store.append_letter_lengths(p.id, "voice", 1.0, [("f", ms) for ms in (1, 2, 3, 4)])
        store.append_letter_lengths(p.id, "voice", 1.0, [("f", 5)])
        assert store.letter_lengths(p.id, "f", "voice", 1.0) == [3, 4, 5]
        # A voice the child may come back to keeps what was measured under it.
        assert store.letter_lengths(p.id, "f", "other", 1.0) == [900]
        assert store.letter_lengths(p.id, "f", "voice", 1.2) == [800]
        assert store.letter_lengths(p.id, "j", "voice", 1.0) == [700]


class TestOrderOfResults:
    # Review of 2026-10-06, F6. No caller reads these three in order today,
    # and one that starts to must not pass on the fake alone.

    def test_key_stats_come_back_by_key(self, any_store: Store) -> None:
        profile = any_store.create_profile("kid")
        for name in "jfad":
            any_store.upsert_key_stat(profile.id, name, True)
        assert list(any_store.key_stats(profile.id)) == ["a", "d", "f", "j"]

    def test_phase_records_come_back_by_phase(self, any_store: Store) -> None:
        profile = any_store.create_profile("kid")
        for phase in ("C", "A", "B"):
            any_store.begin_phase(profile.id, "f", phase, 0)
        assert list(any_store.phase_records(profile.id, "f")) == ["A", "B", "C"]

    def test_milestones_with_one_stamp_come_back_in_the_order_earned(
        self, any_store: Store
    ) -> None:
        # Rungs fired at one block boundary share a stamp.
        profile = any_store.create_profile("kid")
        any_store.record_milestone(profile.id, "bronze", achieved_at="2026-01-02T10:00:00+00:00")
        for level in ("third", "anchor", "silver"):
            any_store.record_milestone(profile.id, level, achieved_at=UTC_STAMP)
        assert any_store.achieved_milestones(profile.id) == [
            "third",
            "anchor",
            "silver",
            "bronze",
        ]


class TestMigration:
    def test_a_missing_table_at_the_current_version_is_created(self, tmp_path: Path) -> None:
        # alpha-plan #12l added `letter_lengths` with no refusal, and a table
        # missing from a database is still created when it is opened. A
        # database from before #12l is now refused by its version (#12m
        # session 2), so this is what is left of that rule.
        path = str(tmp_path / "takki.sqlite")
        SqliteStore(path).conn.close()
        old = sqlite3.connect(path)
        old.executescript("DROP TABLE letter_lengths;")
        old.commit()
        old.close()
        store = SqliteStore(path)
        p = store.create_profile("Alice", "en")
        store.append_letter_lengths(p.id, "voice", 1.0, [("f", 450)])
        assert store.letter_lengths(p.id, "f", "voice", 1.0) == [450]

    def test_a_database_with_the_old_phase_table_is_refused_at_open(self, tmp_path: Path) -> None:
        # ADR-011, 2026-10-04: `ramp_up_phases` changed shape with no migration.
        # Refused when opened, in words, and not at the first phase read.
        path = str(tmp_path / "takki.sqlite")
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE ramp_up_phases (
                profile_id INTEGER NOT NULL, key_char TEXT NOT NULL, phase TEXT NOT NULL,
                attempts_at INTEGER NOT NULL, completed_at TEXT NOT NULL,
                PRIMARY KEY (profile_id, key_char, phase)
            );
        """)
        old.commit()
        old.close()
        with pytest.raises(RuntimeError, match=r"schema version 0, older.*delete it"):
            SqliteStore(path)
        # Refused before anything is written: not even switched to WAL.
        with closing(sqlite3.connect(path)) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert not Path(path + "-wal").exists()

    def test_a_database_from_before_practice_days_is_refused_at_open(self, tmp_path: Path) -> None:
        # ADR-011, #12m session 2: practice days are kept outside the window.
        # An older database has them only in the window, so its keys would read
        # back with fewer days than they had, and no migration is written.
        path = str(tmp_path / "takki.sqlite")
        SqliteStore(path).conn.close()
        old = sqlite3.connect(path)
        old.executescript("PRAGMA user_version = 0; DROP TABLE practice_days;")
        old.commit()
        old.close()
        with pytest.raises(RuntimeError, match=r"schema version 0, older.*delete it"):
            SqliteStore(path)
        # Refused before anything is written to it.
        with closing(sqlite3.connect(path)) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        assert "practice_days" not in tables

    def test_a_database_from_a_newer_takki_is_refused_and_not_restamped(
        self, tmp_path: Path
    ) -> None:
        path = str(tmp_path / "takki.sqlite")
        SqliteStore(path).conn.close()
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("PRAGMA user_version = 2")
        with pytest.raises(RuntimeError, match="schema version 2, newer"):
            SqliteStore(path)
        with closing(sqlite3.connect(path)) as conn:
            assert conn.execute("PRAGMA user_version").fetchone() == (2,)

    def test_a_file_that_is_not_a_database_is_not_held_open(self, tmp_path: Path) -> None:
        # A file the error says to delete must be deletable while Takki runs.
        path = tmp_path / "takki.sqlite"
        path.write_bytes(b"not a database, and longer than a header" * 4)
        with pytest.raises(sqlite3.DatabaseError):
            SqliteStore(str(path))
        path.unlink()

    def test_a_current_database_opens_while_another_connection_writes(self, tmp_path: Path) -> None:
        path = str(tmp_path / "takki.sqlite")
        SqliteStore(path).conn.close()
        with closing(sqlite3.connect(path, isolation_level=None)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            SqliteStore(path).conn.close()
            writer.execute("ROLLBACK")

    def test_a_new_database_is_stamped_with_its_schema_and_opens_again(
        self, tmp_path: Path
    ) -> None:
        path = str(tmp_path / "takki.sqlite")
        SqliteStore(path).conn.close()
        store = SqliteStore(path)
        assert store.conn.execute("PRAGMA user_version").fetchone() == (1,)
        store.conn.close()

    def test_a_first_open_that_fails_leaves_no_tables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The schema is one transaction. Created table by table, a first
        # launch killed half-way left some tables and not `practice_days`, and
        # the next launch refused a new database as an old one.
        import takki.persistence.sqlite_store as sqlite_store

        path = str(tmp_path / "takki.sqlite")
        broken = sqlite_store._SCHEMA.replace(  # pyright: ignore[reportPrivateUsage]
            "CREATE TABLE IF NOT EXISTS practice_days", "THIS IS NOT SQL; CREATE TABLE x"
        )
        monkeypatch.setattr(sqlite_store, "_SCHEMA", broken)
        with pytest.raises(sqlite3.OperationalError):
            SqliteStore(path)
        monkeypatch.undo()
        with closing(sqlite3.connect(path)) as conn:
            assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []
        SqliteStore(path).conn.close()


class TestSessionsAndProfilesMustExist:
    """Both stores refuse a new record for a session that is not the profile's, or for no profile."""

    @pytest.mark.parametrize("session", ["none", "another child's"])
    def test_a_landing_needs_the_profiles_own_session(self, any_store: Store, session: str) -> None:
        pid = any_store.create_profile("Alice").id
        other = any_store.start_session(any_store.create_profile("Bob").id)
        sid = 99 if session == "none" else other
        with pytest.raises(ValueError, match="is not profile"):
            any_store.record_landing(pid, sid, 1, "L-idx", 3, 4, True, T1)
        assert any_store.landings(pid) == []

    @pytest.mark.parametrize("session", ["none", "another child's"])
    def test_a_level_run_needs_the_profiles_own_session(
        self, any_store: Store, session: str
    ) -> None:
        pid = any_store.create_profile("Alice").id
        any_store.mark_introduced(pid, ["d"])
        other = any_store.start_session(any_store.create_profile("Bob").id)
        sid = 99 if session == "none" else other
        with pytest.raises(ValueError, match="is not profile"):
            any_store.begin_level(pid, "d", "reach", sid, 0, T1)
        assert any_store.level_records(pid, "d") == []

    def test_a_rest_key_needs_a_profile(self, any_store: Store) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            any_store.choose_rest_key(99, "L-mid", 3, 3, "landings", T1)
        assert any_store.rest_keys(99) == []
