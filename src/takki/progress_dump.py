"""Read-only progress dump (alpha session #12a-0, item 2).

Alpha passes no `celebrant` (ADR-012) -- every milestone rung is silent, so
SQLite is the only place ADR-027's anchor gate is observable. Opens the
database with sqlite3's `mode=ro` URI, which refuses writes at the file
level: this tool cannot corrupt what it reads.

    uv run python -m takki.progress_dump [--db PATH] [--profile ID]

--db defaults to the same path main.py writes to -- the OS's per-user data
directory via platformdirs, `%LOCALAPPDATA%\\Takki\\` on Windows (ADR-025).
--profile defaults to the first profile by id, matching main.py's own
single-profile Alpha behaviour -- but never creates one.
"""

import argparse
import sqlite3
from pathlib import Path

from takki.data_dir import database_path


def connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def first_profile_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM profiles ORDER BY id LIMIT 1").fetchone()
    return row[0] if row is not None else None


def _print_profile(conn: sqlite3.Connection, profile_id: int) -> bool:
    row = conn.execute(
        "SELECT name, language, created_at FROM profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    if row is None:
        print(f"No profile with id={profile_id}.")
        return False
    name, language, created_at = row
    print(f"Profile: {name} (id={profile_id}, language={language}, created {created_at})")
    return True


def _print_key_stats(conn: sqlite3.Connection, profile_id: int) -> None:
    rows = conn.execute(
        """
        SELECT key_char, attempt_count, correct_count, last_practised_at
        FROM key_stats
        WHERE profile_id = ?
        ORDER BY key_char
        """,
        (profile_id,),
    ).fetchall()
    print("\nkey_stats (lifetime)")
    if not rows:
        print("  (none)")
        return
    print(f"  {'key':<4} {'attempts':>8} {'correct':>8} {'accuracy':>9}  last_practised_at")
    for key_char, attempts, correct, last_practised_at in rows:
        accuracy = correct / attempts if attempts else 0.0
        print(f"  {key_char:<4} {attempts:>8} {correct:>8} {accuracy:>8.1%}  {last_practised_at}")


def _print_attempts_by_day(conn: sqlite3.Connection, profile_id: int) -> None:
    # date(attempted_at, 'localtime') -- the same grouping window_stats() uses
    # for distinct_days, so this dump agrees with what the engine counts. Stored
    # timestamps are UTC (ADR-011) and a practice day is the child's own day.
    # `mean ms` is the time from the letter being sent, which is what the speed
    # term reads (ADR-011).
    rows = conn.execute(
        """
        SELECT key_char, date(attempted_at, 'localtime') AS day, COUNT(*), SUM(correct),
               AVG(latency_ms), COUNT(latency_ms), SUM(timeouts > 0)
        FROM key_attempts
        WHERE profile_id = ?
        GROUP BY key_char, day
        ORDER BY key_char, day
        """,
        (profile_id,),
    ).fetchall()
    print("\nkey_attempts by local calendar day")
    if not rows:
        print("  (none)")
        return
    header = f"  {'key':<4} {'day':<10} {'attempts':>8} {'correct':>8} {'accuracy':>9}"
    print(f"{header} {'mean ms':>8} {'timed':>6} {'timed out':>9}")
    for key_char, day, attempts, correct, mean_ms, timed, timed_out in rows:
        accuracy = correct / attempts if attempts else 0.0
        latency = f"{mean_ms:>8.0f}" if mean_ms is not None else f"{'-':>8}"
        print(
            f"  {key_char:<4} {day:<10} {attempts:>8} {correct:>8} {accuracy:>8.1%}"
            f" {latency} {timed:>6} {timed_out:>9}"
        )


def _print_accuracy_by_timing(conn: sqlite3.Connection, profile_id: int) -> None:
    # ADR-027 keeps every press from HEARD_MIN_MS on, however early, and leaves
    # it to correctness to show whether the early ones were heard or guessed.
    # This is where that shows: a first band well under the others is a child
    # following a pattern, and the drill content is what has failed.
    rows = conn.execute(
        """
        SELECT CASE
                   WHEN latency_ms IS NULL THEN 4
                   WHEN after_letter_ms IS NULL THEN 3
                   WHEN 2 * latency_ms < latency_ms - after_letter_ms THEN 0
                   WHEN after_letter_ms < 0 THEN 1
                   ELSE 2
               END AS band, COUNT(*), SUM(correct)
        FROM key_attempts
        WHERE profile_id = ?
        GROUP BY band
        ORDER BY band
        """,
        (profile_id,),
    ).fetchall()
    print("\nfirst-press accuracy by when the answer came")
    if not rows:
        print("  (none)")
        return
    names = (
        "in the letter's first half",
        "in the letter's second half",
        "after the letter",
        "letter length not known",
        "not timed",
    )
    print(f"  {'answer':<28} {'attempts':>8} {'correct':>8} {'accuracy':>9}")
    for band, attempts, correct in rows:
        print(f"  {names[band]:<28} {attempts:>8} {correct:>8} {correct / attempts:>9.1%}")


def _print_ramp_up(conn: sqlite3.Connection, profile_id: int) -> None:
    """Introduction steps and the phases each member has passed (ADR-024).

    The only place a resumed ramp-up is observable. Without it, a session that
    paces wrongly after a restart cannot be told apart from one that paces
    wrongly for any other reason -- which is the position alpha-plan #12d was
    diagnosed from.
    """
    steps = conn.execute(
        """
        SELECT step, key_char, position, introduced_at FROM introductions
        WHERE profile_id = ?
        ORDER BY step, position
        """,
        (profile_id,),
    ).fetchall()
    print("\nintroductions and ramp-up phases")
    if not steps:
        print("  (none)")
        return
    phases: dict[str, str] = {}
    for key_char, phase, started, completed in conn.execute(
        """
        SELECT key_char, phase, started_attempts, completed_attempts FROM ramp_up_phases
        WHERE profile_id = ?
        ORDER BY key_char, phase
        """,
        (profile_id,),
    ).fetchall():
        # The key's lifetime attempt count where the phase began and where it
        # was passed; an open end is the phase the key is in.
        span = f"{phase}@{started}-{'' if completed is None else completed}"
        phases[key_char] = f"{phases.get(key_char, '')}{span} "
    print(f"  {'step':>4} {'key':<4} {'pos':>3}  {'phases (began-passed)':<30} introduced_at")
    for step, key_char, position, introduced_at in steps:
        print(
            f"  {step:>4} {key_char:<4} {position:>3}  "
            f"{phases.get(key_char, '(none)'):<30} {introduced_at}"
        )


def _print_milestones(conn: sqlite3.Connection, profile_id: int) -> None:
    rows = conn.execute(
        "SELECT level, achieved_at FROM milestones WHERE profile_id = ? ORDER BY achieved_at",
        (profile_id,),
    ).fetchall()
    print("\nmilestones")
    if not rows:
        print("  (none)")
        return
    for level, achieved_at in rows:
        print(f"  {level:<10} {achieved_at}")


def _print_sessions(conn: sqlite3.Connection, profile_id: int) -> None:
    rows = conn.execute(
        "SELECT id, started_at, ended_at FROM sessions WHERE profile_id = ? ORDER BY started_at",
        (profile_id,),
    ).fetchall()
    print("\nsessions")
    if not rows:
        print("  (none)")
        return
    print(f"  {'id':>4}  {'started_at':<20} ended_at")
    for session_id, started_at, ended_at in rows:
        print(f"  {session_id:>4}  {started_at:<20} {ended_at or '(in progress)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None, help="database path (default: main.py's)")
    parser.add_argument("--profile", type=int, default=None, help="profile id (default: first)")
    args = parser.parse_args()

    db_path = args.db if args.db is not None else database_path()
    if not db_path.exists():
        print(f"No database at {db_path}.")
        return

    conn = connect_readonly(db_path)
    try:
        profile_id = args.profile if args.profile is not None else first_profile_id(conn)
        if profile_id is None:
            print(f"No profiles in {db_path}.")
            return
        if not _print_profile(conn, profile_id):
            return
        _print_key_stats(conn, profile_id)
        _print_attempts_by_day(conn, profile_id)
        _print_accuracy_by_timing(conn, profile_id)
        _print_ramp_up(conn, profile_id)
        _print_milestones(conn, profile_id)
        _print_sessions(conn, profile_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
