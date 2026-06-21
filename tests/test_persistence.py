import pytest

from takki.persistence.sqlite_store import SqliteStore


@pytest.fixture()
def store() -> SqliteStore:
    return SqliteStore(":memory:")


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
        p = store.create_profile("Alice", "en", created_at="2026-01-01T09:00:00")
        assert p.created_at == "2026-01-01T09:00:00"
        assert store.get_profile(p.id).created_at == "2026-01-01T09:00:00"  # type: ignore[union-attr]


class TestSessions:
    def test_start_returns_id(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        sid = store.start_session(p.id, started_at="2026-01-01T10:00:00")
        assert isinstance(sid, int)

    def test_start_ended_at_null(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        sid = store.start_session(p.id, started_at="2026-01-01T10:00:00")
        row = store.conn.execute("SELECT ended_at FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row[0] is None

    def test_end_sets_ended_at(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        sid = store.start_session(p.id, started_at="2026-01-01T10:00:00")
        store.end_session(sid, ended_at="2026-01-01T10:30:00")
        row = store.conn.execute("SELECT ended_at FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row[0] == "2026-01-01T10:30:00"

    def test_sequential_ids(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        s1 = store.start_session(p.id)
        s2 = store.start_session(p.id)
        assert s2 == s1 + 1


class TestKeyStats:
    def test_upsert_creates_row_on_first_call(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:00:00")
        row = store.conn.execute(
            "SELECT attempt_count, correct_count, last_practised_at FROM key_stats"
            " WHERE profile_id = ? AND key_char = ?",
            (p.id, "a"),
        ).fetchone()
        assert row == (1, 1, "2026-01-01T10:00:00")

    def test_upsert_accumulates(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:00:00")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:01:00")
        store.upsert_key_stat(p.id, "a", False, practised_at="2026-01-01T10:02:00")
        row = store.conn.execute(
            "SELECT attempt_count, correct_count, last_practised_at FROM key_stats"
            " WHERE profile_id = ? AND key_char = ?",
            (p.id, "a"),
        ).fetchone()
        assert row == (3, 2, "2026-01-01T10:02:00")

    def test_bump_recency_updates_timestamp(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.upsert_key_stat(p.id, "a", True, practised_at="2026-01-01T10:00:00")
        store.bump_key_recency(p.id, "a", practised_at="2026-01-01T10:05:00")
        row = store.conn.execute(
            "SELECT attempt_count, correct_count, last_practised_at FROM key_stats"
            " WHERE profile_id = ? AND key_char = ?",
            (p.id, "a"),
        ).fetchone()
        assert row == (1, 1, "2026-01-01T10:05:00")

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
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 1
        assert stats.correct_count == 1

    def test_rolling_cap_count_stays_at_cap(self) -> None:
        store = SqliteStore(":memory:", window_cap=5)
        p = store.create_profile("Alice", "en")
        for i in range(7):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-01T{i:02d}:00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 5

    def test_rolling_cap_oldest_dropped(self) -> None:
        store = SqliteStore(":memory:", window_cap=5)
        p = store.create_profile("Alice", "en")
        # First row (to be evicted): wrong
        store.append_attempt(p.id, "a", False, attempted_at="2026-01-01T00:00:00")
        # Next 5 rows (all correct): these become the window
        for i in range(1, 6):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-01T{i:02d}:00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 5
        assert stats.correct_count == 5  # wrong row was evicted

    def test_rolling_cap_newest_kept(self) -> None:
        store = SqliteStore(":memory:", window_cap=3)
        p = store.create_profile("Alice", "en")
        for i in range(5):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-0{i + 1}T10:00:00")
        rows = store.conn.execute(
            "SELECT attempted_at FROM key_attempts WHERE profile_id = ? AND key_char = ? ORDER BY attempted_at",
            (p.id, "a"),
        ).fetchall()
        dates = [r[0] for r in rows]
        assert dates == ["2026-01-03T10:00:00", "2026-01-04T10:00:00", "2026-01-05T10:00:00"]

    def test_cap_independent_per_char(self) -> None:
        store = SqliteStore(":memory:", window_cap=3)
        p = store.create_profile("Alice", "en")
        for i in range(4):
            store.append_attempt(p.id, "a", True, attempted_at=f"2026-01-0{i + 1}T10:00:00")
            store.append_attempt(p.id, "b", True, attempted_at=f"2026-01-0{i + 1}T11:00:00")
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
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:00:00")
        store.append_attempt(p.id, "a", False, attempted_at="2026-01-01T10:01:00")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:02:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 3
        assert stats.correct_count == 2

    def test_distinct_days_same_day(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T09:00:00")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T17:00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.distinct_days == 1

    def test_distinct_days_across_calendar_days(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T10:00:00")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-01T11:00:00")
        store.append_attempt(p.id, "a", False, attempted_at="2026-01-02T10:00:00")
        store.append_attempt(p.id, "a", True, attempted_at="2026-01-03T10:00:00")
        stats = store.window_stats(p.id, "a")
        assert stats.attempt_count == 4
        assert stats.correct_count == 3
        assert stats.distinct_days == 3

    def test_stats_isolated_per_profile(self, store: SqliteStore) -> None:
        a = store.create_profile("Alice", "en")
        b = store.create_profile("Bob", "en")
        store.append_attempt(a.id, "a", True, attempted_at="2026-01-01T10:00:00")
        store.append_attempt(a.id, "a", True, attempted_at="2026-01-01T10:01:00")
        store.append_attempt(b.id, "a", False, attempted_at="2026-01-01T10:00:00")
        assert store.window_stats(a.id, "a").attempt_count == 2
        assert store.window_stats(b.id, "a").attempt_count == 1
        assert store.window_stats(b.id, "a").correct_count == 0


class TestMilestones:
    def test_record_and_query(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-01T10:00:00")
        assert store.achieved_milestones(p.id) == ["bronze"]

    def test_record_idempotent(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-01T10:00:00")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-02T10:00:00")
        assert store.achieved_milestones(p.id) == ["bronze"]

    def test_query_empty(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        assert store.achieved_milestones(p.id) == []

    def test_multiple_milestones_ordered_by_achieved_at(self, store: SqliteStore) -> None:
        p = store.create_profile("Alice", "en")
        store.record_milestone(p.id, "silver", achieved_at="2026-02-01T10:00:00")
        store.record_milestone(p.id, "bronze", achieved_at="2026-01-01T10:00:00")
        store.record_milestone(p.id, "gold", achieved_at="2026-03-01T10:00:00")
        assert store.achieved_milestones(p.id) == ["bronze", "silver", "gold"]

    def test_milestones_isolated_per_profile(self, store: SqliteStore) -> None:
        a = store.create_profile("Alice", "en")
        b = store.create_profile("Bob", "en")
        store.record_milestone(a.id, "bronze", achieved_at="2026-01-01T10:00:00")
        store.record_milestone(b.id, "silver", achieved_at="2026-01-01T10:00:00")
        assert store.achieved_milestones(a.id) == ["bronze"]
        assert store.achieved_milestones(b.id) == ["silver"]
