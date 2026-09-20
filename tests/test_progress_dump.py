import sqlite3
import sys
from pathlib import Path

import pytest

from takki import progress_dump
from takki.persistence.sqlite_store import SqliteStore


def _seed_db(path: Path) -> int:
    store = SqliteStore(str(path))
    profile = store.create_profile("dev", "en", created_at="2026-09-19T09:00:00")
    store.upsert_key_stat(profile.id, "f", True, practised_at="2026-09-19T09:01:00")
    store.upsert_key_stat(profile.id, "f", False, practised_at="2026-09-19T09:02:00")
    store.append_attempt(profile.id, "f", True, attempted_at="2026-09-19T09:01:00")
    store.append_attempt(profile.id, "f", False, attempted_at="2026-09-19T09:02:00")
    store.append_attempt(profile.id, "f", True, attempted_at="2026-09-20T10:00:00")
    store.record_milestone(profile.id, "anchor", achieved_at="2026-09-20T11:00:00")
    ended = store.start_session(profile.id, started_at="2026-09-19T09:00:00")
    store.end_session(ended, ended_at="2026-09-19T09:20:00")
    store.start_session(profile.id, started_at="2026-09-20T10:00:00")
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
        assert "key_attempts by calendar day" in out
        # date(attempted_at) grouping — must agree with ADR-027's window_stats().
        assert "2026-09-19" in out
        assert "2026-09-20" in out
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
