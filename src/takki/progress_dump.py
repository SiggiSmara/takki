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
    # date(attempted_at) -- the same grouping ADR-027's window_stats() uses
    # for distinct_days, so this dump agrees with what the engine counts.
    rows = conn.execute(
        """
        SELECT key_char, date(attempted_at) AS day, COUNT(*), SUM(correct)
        FROM key_attempts
        WHERE profile_id = ?
        GROUP BY key_char, day
        ORDER BY key_char, day
        """,
        (profile_id,),
    ).fetchall()
    print("\nkey_attempts by calendar day")
    if not rows:
        print("  (none)")
        return
    print(f"  {'key':<4} {'day':<10} {'attempts':>8} {'correct':>8} {'accuracy':>9}")
    for key_char, day, attempts, correct in rows:
        accuracy = correct / attempts if attempts else 0.0
        print(f"  {key_char:<4} {day:<10} {attempts:>8} {correct:>8} {accuracy:>8.1%}")


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
        _print_milestones(conn, profile_id)
        _print_sessions(conn, profile_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
