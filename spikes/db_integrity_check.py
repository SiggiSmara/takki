"""
Spike: post-kill database check for docs/research/windows-validation.md D3

Alpha session 12b-1 (2026-09-24). Run it after killing Takki mid-write and
*before* relaunching it, so it reads the file exactly as the kill left it --
the next launch replays the WAL and the evidence is gone. Read-only
(sqlite3 `mode=ro`), then prints the progress dump.

    uv run python spikes/db_integrity_check.py [--db PATH] [--profile ID]

Three checks, one paste-ready line:
1. PRAGMA integrity_check and foreign_key_check -- the file is sound.
2. key_stats agrees with key_attempts. Each counted attempt is two separate
   commits (SqliteStore.upsert_key_stat, then append_attempt), so a kill
   between them leaves the lifetime counter one ahead of the rolling window
   with no corruption at all. Below the ATTEMPT_WINDOW cap the two must be
   equal; at the cap the counter may only be ahead.
3. Exactly one session is left unended -- the one that was killed. A clean
   close ends its session row (SessionLoop.shutdown), so any others are
   earlier unclean exits worth knowing about.
"""

import argparse
import sys
from pathlib import Path

from takki import config
from takki.data_dir import database_path
from takki.progress_dump import connect_readonly, first_profile_id
from takki.progress_dump import main as dump_main


def main() -> int:
    parser = argparse.ArgumentParser(description="D3: post-kill integrity check, read-only")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--profile", type=int, default=None)
    args = parser.parse_args()

    db_path = args.db if args.db is not None else database_path()
    if not db_path.exists():
        print(f"No database at {db_path}.")
        return 1
    wal = db_path.with_name(db_path.name + "-wal")
    wal_text = f"-wal {wal.stat().st_size} bytes" if wal.exists() else "no -wal"

    conn = connect_readonly(db_path)
    try:
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check").fetchall()]
        foreign = conn.execute("PRAGMA foreign_key_check").fetchall()
        profile_id = args.profile if args.profile is not None else first_profile_id(conn)
        has_profile = (
            profile_id is not None
            and conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
            is not None
        )
        if not has_profile:
            # Every check below would match nothing and report "consistent for 0
            # keys" -- a pass that compared nothing.
            print(f"integrity_check: {'; '.join(integrity)}")
            which = profile_id if profile_id is not None else "at all"
            print(f"\nD3: **FAIL** -- no profile {which} in {db_path}; nothing to compare")
            return 1
        rows = conn.execute(
            """
            SELECT s.key_char, s.attempt_count, s.correct_count,
                   COUNT(a.rowid), COALESCE(SUM(a.correct), 0)
            FROM key_stats s
            LEFT JOIN key_attempts a
                ON a.profile_id = s.profile_id AND a.key_char = s.key_char
            WHERE s.profile_id = ?
            GROUP BY s.key_char
            ORDER BY s.key_char
            """,
            (profile_id,),
        ).fetchall()
        orphans = conn.execute(
            """
            SELECT DISTINCT key_char FROM key_attempts
            WHERE profile_id = ? AND key_char NOT IN
                (SELECT key_char FROM key_stats WHERE profile_id = ?)
            """,
            (profile_id, profile_id),
        ).fetchall()
        open_sessions = conn.execute(
            "SELECT id, started_at FROM sessions WHERE profile_id = ? AND ended_at IS NULL ORDER BY id",
            (profile_id,),
        ).fetchall()
    finally:
        conn.close()

    torn: list[str] = []
    for key, attempts, correct, window, window_correct in rows:
        if window < config.ATTEMPT_WINDOW:
            if (attempts, correct) != (window, window_correct):
                torn.append(
                    f"{key}: key_stats {attempts}/{correct} vs key_attempts {window}/{window_correct}"
                )
        elif attempts < window:
            torn.append(f"{key}: key_stats {attempts} behind a full window of {window}")
    torn.extend(f"{key}: key_attempts rows with no key_stats row" for (key,) in orphans)

    sound = integrity == ["ok"] and not foreign
    print(f"Database: {db_path} ({wal_text} at check time)")
    print(f"integrity_check: {'; '.join(integrity)}; foreign_key_check: {len(foreign)} violations")
    print(
        f"key_stats vs key_attempts: {'consistent for ' + str(len(rows)) + ' keys' if not torn else 'TORN -- ' + '; '.join(torn)}"
    )
    print(
        f"unended sessions: {', '.join(f'{sid} (started {started})' for sid, started in open_sessions) or 'none'}"
    )
    print()
    sys.argv = [sys.argv[0], "--db", str(db_path)] + (
        ["--profile", str(args.profile)] if args.profile is not None else []
    )
    dump_main()

    passed = sound and not torn
    print(
        f"\nD3: {'PASS' if passed else '**FAIL**'} -- integrity_check {'ok' if integrity == ['ok'] else 'FAILED'}, "
        f"{len(foreign)} FK violations, key_stats/key_attempts {'consistent' if not torn else 'torn (' + str(len(torn)) + ' keys)'}, "
        f"{len(open_sessions)} unended session(s) (expect 1: the killed one); {wal_text} before relaunch"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
