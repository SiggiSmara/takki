import sqlite3
import sys
from pathlib import Path

import pytest

from takki import progress_dump
from takki.persistence.sqlite_store import SqliteStore


def _seed_db(path: Path) -> int:
    store = SqliteStore(str(path))
    profile = store.create_profile("dev", "en", created_at="2026-09-19T09:00:00+00:00")
    store.upsert_key_stat(profile.id, "f", True, practised_at="2026-09-19T09:01:00+00:00")
    store.upsert_key_stat(profile.id, "f", False, practised_at="2026-09-19T09:02:00+00:00")
    store.append_attempt(profile.id, "f", True, attempted_at="2026-09-19T09:01:00+00:00")
    store.append_attempt(profile.id, "f", False, attempted_at="2026-09-19T09:02:00+00:00")
    store.append_attempt(
        profile.id,
        "f",
        True,
        attempted_at="2026-09-20T10:00:00+00:00",
        latency_ms=1620,
        prev_char="j",
        after_letter_ms=420,
    )
    # ADR-011, alpha-plan #12f. Against a 1200 ms letter: two answers in its
    # first half (300 and 400 ms after it was sent), one in its second half,
    # and one that sat through two timeouts and so was not timed.
    day = "2026-09-20T10:01:00+00:00"
    store.append_attempt(profile.id, "j", False, day, latency_ms=300, after_letter_ms=-900)
    store.append_attempt(profile.id, "j", True, day, latency_ms=400, after_letter_ms=-800)
    store.append_attempt(profile.id, "j", True, day, latency_ms=1100, after_letter_ms=-100)
    store.append_attempt(profile.id, "j", True, day, latency_ms=700)
    store.append_attempt(profile.id, "j", True, day, timeouts=2)
    store.mark_introduced(profile.id, ["f", "j"], introduced_at="2026-09-19T09:00:00+00:00")
    store.begin_phase(profile.id, "f", "A", 0, started_at="2026-09-19T09:00:00+00:00")
    store.record_phase(profile.id, "f", "A", 10, completed_at="2026-09-19T09:05:00+00:00")
    store.begin_phase(profile.id, "f", "B", 14, started_at="2026-09-19T09:06:00+00:00")
    store.record_milestone(profile.id, "anchor", achieved_at="2026-09-20T11:00:00+00:00")
    ended = store.start_session(profile.id, started_at="2026-09-19T09:00:00+00:00")
    store.end_session(ended, ended_at="2026-09-19T09:20:00+00:00")
    store.start_session(profile.id, started_at="2026-09-20T10:00:00+00:00")
    store.conn.close()
    return profile.id


def _run(monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["progress_dump", *args])
    progress_dump.main()


class TestConnectReadonly:
    def test_cannot_write(self, tmp_path: Path) -> None:
        db_path = tmp_path / "takki.sqlite"
        _seed_db(db_path)
        conn = progress_dump.connect_readonly(db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO sessions (profile_id, started_at) VALUES (1, 'x')")
        finally:
            conn.close()

    def test_reads_fine(self, tmp_path: Path) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_db(db_path)
        conn = progress_dump.connect_readonly(db_path)
        try:
            assert progress_dump.first_profile_id(conn) == profile_id
        finally:
            conn.close()


class TestMain:
    def test_no_db_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        missing = tmp_path / "nope.sqlite"
        _run(monkeypatch, "--db", str(missing))
        assert "No database" in capsys.readouterr().out

    def test_no_profiles(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        store = SqliteStore(str(db_path))
        store.conn.close()
        _run(monkeypatch, "--db", str(db_path))
        assert "No profiles" in capsys.readouterr().out

    def test_default_profile_is_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        _seed_db(db_path)
        _run(monkeypatch, "--db", str(db_path))
        assert "Profile: dev" in capsys.readouterr().out

    def test_dump_all_sections(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_db(db_path)
        _run(monkeypatch, "--db", str(db_path), "--profile", str(profile_id))
        out = capsys.readouterr().out

        assert "Profile: dev" in out
        assert "key_stats (lifetime)" in out
        assert "key_attempts by local calendar day" in out
        # date(attempted_at, 'localtime') grouping — must agree with window_stats().
        assert "2026-09-19" in out
        assert "2026-09-20" in out
        # The mean time from the letter being sent, how many answers were
        # timed, and how many sat through a timeout: `f`'s one timed attempt
        # at 420 ms after a 1200 ms letter, and `j`'s three at 300, 400 and 1100.
        lines = out.splitlines()
        assert "  f    2026-09-20        1        1   100.0%     1620      1         0" in lines
        assert "  j    2026-09-20        5        4    80.0%      625      4         1" in lines
        # ADR-027: every press from the floor on is kept, so whether the early
        # ones were heard or guessed has to be readable somewhere.
        table = lines[lines.index("first-press accuracy by when the answer came") + 2 :][:5]
        assert table == [
            "  in the letter's first half          2        1     50.0%",
            "  in the letter's second half         1        1    100.0%",
            "  after the letter                    1        1    100.0%",
            "  letter length not known             1        1    100.0%",
            "  not timed                           3        2     66.7%",
        ]
        # Introductions and phases: the only place a resumed ramp-up is visible.
        assert "introductions and ramp-up phases" in out
        # Where each phase began and was passed, in the key's lifetime attempts;
        # the open end is the phase the key is in.
        assert "A@0-10 B@14- " in out
        assert "milestones" in out
        assert "anchor" in out
        assert "sessions" in out
        assert "(in progress)" in out

    def test_unknown_profile_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        _seed_db(db_path)
        _run(monkeypatch, "--db", str(db_path), "--profile", "999")
        assert "No profile with id=999" in capsys.readouterr().out
