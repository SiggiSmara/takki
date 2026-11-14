import sqlite3
import sys
from pathlib import Path

import pytest

from takki import progress_dump
from takki.persistence.sqlite_store import SqliteStore
from tests.sessions import session_for


def _seed_db(path: Path) -> int:
    store = SqliteStore(str(path))
    profile = store.create_profile("dev", "en", created_at="2026-09-19T09:00:00+00:00")
    store.upsert_key_stat(profile.id, "f", True, practised_at="2026-09-19T09:01:00+00:00")
    store.upsert_key_stat(profile.id, "f", False, practised_at="2026-09-19T09:02:00+00:00")
    store.append_attempt(
        profile.id,
        session_for(store, profile.id, "2026-09-19T09:01:00+00:00"),
        "f",
        True,
        attempted_at="2026-09-19T09:01:00+00:00",
    )
    store.append_attempt(
        profile.id,
        session_for(store, profile.id, "2026-09-19T09:02:00+00:00"),
        "f",
        False,
        attempted_at="2026-09-19T09:02:00+00:00",
    )
    store.append_attempt(
        profile.id,
        session_for(store, profile.id, "2026-09-20T10:00:00+00:00"),
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
    store.append_attempt(
        profile.id,
        session_for(store, profile.id, day),
        "j",
        False,
        day,
        latency_ms=300,
        after_letter_ms=-900,
    )
    store.append_attempt(
        profile.id,
        session_for(store, profile.id, day),
        "j",
        True,
        day,
        latency_ms=400,
        after_letter_ms=-800,
    )
    store.append_attempt(
        profile.id,
        session_for(store, profile.id, day),
        "j",
        True,
        day,
        latency_ms=1100,
        after_letter_ms=-100,
    )
    store.append_attempt(
        profile.id, session_for(store, profile.id, day), "j", True, day, latency_ms=700
    )
    store.append_attempt(
        profile.id, session_for(store, profile.id, day), "j", True, day, timeouts=2
    )
    store.mark_introduced(profile.id, ["f", "j"], introduced_at="2026-09-19T09:00:00+00:00")
    store.record_milestone(profile.id, "anchor", achieved_at="2026-09-20T11:00:00+00:00")
    ended = store.start_session(profile.id, started_at="2026-09-19T09:00:00+00:00")
    store.begin_level(profile.id, "j", "reach", ended, 0, started_at="2026-09-19T09:00:00+00:00")
    store.complete_level(
        profile.id, "j", "reach", ended, 10, completed_at="2026-09-19T09:05:00+00:00"
    )
    store.begin_level(profile.id, "j", "choose", ended, 0, started_at="2026-09-19T09:06:00+00:00")
    store.record_stable(profile.id, "f", 30, stable_at="2026-09-19T09:10:00+00:00")
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
        # `days` is the count Known reads, from `practice_days` (ADR-011, #12m
        # session 2): `f`'s presses are 25 hours apart, two days in any zone.
        assert (
            "  f           2        1    50.0%     2  2026-09-19T09:02:00+00:00" in out.splitlines()
        )
        assert "key_attempts by local calendar day" in out
        # date(attempted_at, 'localtime') grouping: the window's days, by the child's calendar.
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
        # Introductions and levels: the only place a resumed ramp-up is visible.
        assert "introductions and ramp-up levels" in out
        # Each level run's session, and where it began and was met in the
        # letter's lifetime presses; an open end is a level not yet met. The
        # bar is the lifetime count at which it was met.
        rows = [line for line in lines if line.startswith(("     1 f", "     1 j"))]
        assert [row.split()[:5] for row in rows] == [
            ["1", "f", "0", "(none)", "30"],
            ["1", "j", "1", "reach#3@0-10", "choose#3@0-"],
        ]
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

    def test_a_database_from_before_practice_days_is_still_dumped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The store refuses it (ADR-011, #12m session 2) and says to delete it,
        # so the dump is how the developer sees what it held first.
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TABLE practice_days")
        conn.close()
        _run(monkeypatch, "--db", str(db_path), "--profile", str(profile_id))
        lines = capsys.readouterr().out.splitlines()
        assert "  f           2        1    50.0%     -  2026-09-19T09:02:00+00:00" in lines


def _section(out: str, heading: str) -> list[str]:
    """The lines under `heading` up to the next blank line, heading excluded."""
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading)) + 1
    end = next((i for i in range(start, len(lines)) if lines[i] == ""), len(lines))
    return lines[start:end]


def _dump(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    db_path: Path,
    profile_id: int,
) -> str:
    _run(monkeypatch, "--db", str(db_path), "--profile", str(profile_id))
    return capsys.readouterr().out


def _seed_slow_corrections(path: Path) -> int:
    """Row 2 has the shape of database A's row 210 (alpha-plan, #12m session (8))."""
    store = SqliteStore(str(path))
    profile = store.create_profile("dev", "en", created_at="2026-11-13T19:00:00+00:00")
    session = store.start_session(profile.id, started_at="2026-11-13T19:20:00+00:00")
    store.mark_introduced(profile.id, ["e"], introduced_at="2026-11-13T19:21:00+00:00")
    store.mark_introduced(profile.id, ["t"], introduced_at="2026-11-13T19:22:00+00:00")
    store.begin_level(profile.id, "t", "choose", session, 0, started_at="2026-11-13T19:23:00+00:00")
    # `t` moves from Choose to Travel two seconds before the first press of row 2.
    store.complete_level(
        profile.id, "t", "choose", session, 30, completed_at="2026-11-13T19:26:55+00:00"
    )
    store.begin_level(
        profile.id, "t", "travel", session, 30, started_at="2026-11-13T19:26:55+00:00"
    )

    def attempt(
        key: str,
        correct: bool,
        at: str,
        latency_ms: int | None,
        prev: str | None,
        session_id: int = session,
        timeouts: int = 0,
    ) -> None:
        store.append_attempt(
            profile.id,
            session_id,
            key,
            correct,
            f"2026-11-13T{at}+00:00",
            latency_ms=latency_ms,
            prev_char=prev,
            timeouts=timeouts,
        )

    attempt("e", True, "19:26:50", 1000, None)
    # Row 2: wrong at 0.9 s, and the right key not before the next letter was
    # sent, 17 s later. Listed.
    attempt("t", False, "19:26:57", 900, "e")
    attempt("e", True, "19:27:15", 1500, "t")
    # Row 4: an ordinary miss, corrected in 5 s. Not listed.
    attempt("t", False, "19:27:20", 800, "e")
    attempt("e", True, "19:27:26", 1200, "t")
    # Row 6: the next prompt is untimed, so the gap cannot be read. Row 7 sat
    # through one re-ask.
    attempt("t", False, "19:27:30", 800, "e")
    attempt("e", True, "19:27:55", None, "t", timeouts=1)
    # Row 8: a rest cue came between, so the next row is not the next prompt.
    attempt("t", False, "19:28:00", 900, "e")
    attempt("n", True, "19:28:40", 900, "R-mid")
    # Row 10: two causes at once, an untimed next row that is also not the
    # next prompt. It is counted as untimed, the first. Row 11 sat through two.
    attempt("t", False, "19:28:45", 900, "e")
    attempt("n", True, "19:28:50", None, "R-mid", timeouts=2)
    # Row 12: the next row is in a later session.
    attempt("e", False, "19:29:00", 900, "n")
    later = store.start_session(profile.id, started_at="2026-11-13T19:40:00+00:00")
    attempt("e", True, "19:40:10", 1000, "e", later)
    # Row 14 is the last row: nothing follows it. A wrong press after a re-ask.
    attempt("t", False, "19:40:30", None, "e", later, timeouts=1)
    store.conn.close()
    return profile.id


class TestSlowCorrections:
    def test_only_a_slow_correction_is_listed_and_the_rest_are_counted_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_slow_corrections(db_path)
        out = _dump(capsys, monkeypatch, db_path, profile_id)

        assert _section(out, "slow corrections") == [
            "    row first press                key   gap s level   prev",
            "      2 2026-11-13T19:26:57+00:00  t      16.5 travel  e",
            "  7 wrong first presses, 5 with no readable gap: 1 last press in the database, "
            "2 next prompt untimed, 1 next recorded prompt not the one that followed, "
            "1 session start in between; gap is an upper bound",
        ]

    def test_prompts_answered_after_a_re_ask_are_listed_whatever_the_press(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_slow_corrections(db_path)
        out = _dump(capsys, monkeypatch, db_path, profile_id)

        assert _section(out, "prompts answered after a re-ask") == [
            "    row when                       key  timeouts latency ms level   prev",
            "      7 2026-11-13T19:27:55+00:00  e           1          - -       t",
            "     11 2026-11-13T19:28:50+00:00  n           2          - -       R-mid",
            "     14 2026-11-13T19:40:30+00:00  t           1          - travel  e",
        ]

    def test_a_database_with_no_slow_correction_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_db(db_path)
        out = _dump(capsys, monkeypatch, db_path, profile_id)

        assert _section(out, "slow corrections")[0] == "  (none)"
        # `j`'s one answer that sat through two timeouts, with the Choose run
        # that was open at the time.
        assert _section(out, "prompts answered after a re-ask") == [
            "    row when                       key  timeouts latency ms level   prev",
            "      8 2026-09-20T10:01:00+00:00  j           2          - choose  -",
        ]

    def test_a_database_with_no_re_ask_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_alignment_and_ladder(db_path)
        out = _dump(capsys, monkeypatch, db_path, profile_id)

        assert _section(out, "prompts answered after a re-ask") == ["  (none)"]


def _seed_alignment_and_ladder(path: Path) -> int:
    store = SqliteStore(str(path))
    profile = store.create_profile("dev", "en", created_at="2026-11-13T09:00:00+00:00")
    session = store.start_session(profile.id, started_at="2026-11-13T09:00:00+00:00")
    store.record_landing(profile.id, session, 1, "L-index", 3, 4, True, "2026-11-13T09:00:05+00:00")
    store.record_landing(profile.id, session, 1, "L-pink", 3, 1, False, "2026-11-13T09:00:12+00:00")
    store.choose_rest_key(profile.id, "L-index", 3, 4, "bump", "2026-11-13T09:00:05+00:00")
    store.choose_rest_key(profile.id, "L-pink", 3, 1, "landings", "2026-11-13T09:01:00+00:00")
    store.choose_rest_key(profile.id, "L-pink", 3, 2, "answer", "2026-11-13T09:02:00+00:00")
    store.mark_rest_key_ready(profile.id, "L-index", "2026-11-13T09:00:30+00:00")
    store.mark_rest_key_passed(profile.id, "L-index", "2026-11-13T09:03:00+00:00")
    store.record_milestone(profile.id, "rest", "2026-11-13T09:04:00+00:00")
    store.mark_introduced(profile.id, ["e", "n"], introduced_at="2026-11-13T09:04:30+00:00")
    store.append_reach_press(profile.id, "e", True, "2026-11-13T09:05:00+00:00")
    store.append_reach_press(profile.id, "e", False, "2026-11-13T09:05:30+00:00")
    store.append_reach_press(profile.id, "e", True, "2026-11-13T09:06:00+00:00")
    store.append_reach_press(profile.id, "n", True, "2026-11-13T09:07:00+00:00")
    # One attempt after each kind of previous prompt.
    for key, correct, prev in (
        ("f", True, None),
        ("e", True, "R-mid"),
        ("e", False, "R-mid+L-pink"),
        ("n", True, "n"),
        ("n", False, "e"),
        ("n", True, "e"),
    ):
        store.append_attempt(
            profile.id, session, key, correct, "2026-11-13T09:10:00+00:00", prev_char=prev
        )
    store.conn.close()
    return profile.id


class TestAlignmentAndLadderRecords:
    def test_landings_rest_keys_reach_presses_and_the_rest_rung_are_printed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_alignment_and_ladder(db_path)
        out = _dump(capsys, monkeypatch, db_path, profile_id)

        assert _section(out, "landings") == [
            "  session round finger  cell  valid landed_at",
            "        1     1 L-index 3,4   yes   2026-11-13T09:00:05+00:00",
            "        1     1 L-pink  3,1   no    2026-11-13T09:00:12+00:00",
        ]
        # A replaced key is kept, with when it was replaced.
        rest_keys = _section(out, "rest_keys")
        assert [line.split() for line in rest_keys] == [
            "finger cell chosen_by chosen_at ready_at passed_at replaced_at".split(),
            [
                "L-index", "3,4", "bump", "2026-11-13T09:00:05+00:00",
                "2026-11-13T09:00:30+00:00", "2026-11-13T09:03:00+00:00", "-",
            ],
            [
                "L-pink", "3,1", "landings", "2026-11-13T09:01:00+00:00",
                "-", "-", "2026-11-13T09:02:00+00:00",
            ],
            ["L-pink", "3,2", "answer", "2026-11-13T09:02:00+00:00", "-", "-", "-"],
        ]  # fmt: skip
        assert _section(out, "reach_presses") == [
            "  key  presses  correct  accuracy  first / last",
            "  e          3        2     66.7%  2026-11-13T09:05:00+00:00 / 2026-11-13T09:06:00+00:00",
            "  n          1        1    100.0%  2026-11-13T09:07:00+00:00 / 2026-11-13T09:07:00+00:00",
        ]
        assert _section(out, "milestones") == ["  rest       2026-11-13T09:04:00+00:00"]

    def test_accuracy_is_split_by_the_previous_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "takki.sqlite"
        profile_id = _seed_alignment_and_ladder(db_path)
        out = _dump(capsys, monkeypatch, db_path, profile_id)

        assert _section(out, "first-press accuracy by the previous prompt") == [
            "  previous prompt            attempts  correct  accuracy",
            "  first prompt of a session         1        1    100.0%",
            "  after a rest cue                  2        1     50.0%",
            "  after the same letter             1        1    100.0%",
            "  after another letter              2        1     50.0%",
        ]
