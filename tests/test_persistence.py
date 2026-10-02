import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest

from takki.persistence import KeyStat, Store, WindowStats, utc_stamp
from takki.persistence.sqlite_store import SqliteStore
from tests.fakes.fake_store import FakeStore


@pytest.fixture()
def store() -> SqliteStore:
    return SqliteStore(":memory:")


@pytest.fixture(params=["sqlite", "fake"])
def any_store(request: pytest.FixtureRequest) -> Store:
    """The real store and its fake, held to the same behaviour (ADR-019)."""
    return SqliteStore(":memory:") if cast(str, request.param) == "sqlite" else FakeStore()


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
    "record_phase": lambda s, pid, at: s.record_phase(pid, "f", "A", 10, completed_at=at),
    "append_attempt": lambda s, pid, at: s.append_attempt(pid, "f", True, attempted_at=at),
    "record_milestone": lambda s, pid, at: s.record_milestone(pid, "anchor", achieved_at=at),
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
        reads: list[Callable[[], object]] = [
            lambda: store.get_profile(pid),
            store.list_profiles,
            lambda: store.key_stats(pid),
            lambda: store.window_attempts(pid, "f"),
            lambda: store.introductions(pid),
        ]
        for read in reads:
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


class TestMigration:
    def test_a_database_written_before_the_new_columns_still_opens(self, tmp_path: Path) -> None:
        # ADR-011, 2026-09-29: two nullable additions, so an existing profile
        # keeps every row and simply has no latency or predecessor history for
        # what it already recorded.
        path = str(tmp_path / "takki.sqlite")
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE profiles (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL,
                tts_voice TEXT, tts_rate REAL, talk_key TEXT, reread_key TEXT,
                restart_key TEXT, ptt_mode TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE key_attempts (
                profile_id INTEGER NOT NULL, key_char TEXT NOT NULL,
                attempted_at TEXT NOT NULL, correct INTEGER NOT NULL
            );
            INSERT INTO profiles (name, language, created_at)
                VALUES ('Alice', 'en', '2026-09-01T10:00:00+00:00');
            INSERT INTO key_attempts VALUES (1, 'f', '2026-09-01T10:00:00+00:00', 1);
        """)
        old.commit()
        old.close()

        store = SqliteStore(path)
        rows = store.window_attempts(1, "f")
        assert [(r.correct, r.latency_ms, r.prev_char) for r in rows] == [(True, None, None)]
        # And the new writes work on the migrated table.
        store.append_attempt(1, "f", True, "2026-09-29T10:00:00+00:00", 300, "j")
        assert store.window_attempts(1, "f")[-1].latency_ms == 300
        store.mark_introduced(1, ["f"])
        assert [i.key_char for i in store.introductions(1)] == ["f"]
