"""Read-only progress dump (alpha session #12a-0, item 2).

Alpha passes no `celebrant` (ADR-012) -- every milestone rung is silent, so
SQLite is the only place ADR-027's milestone ladder is observable. Opens the
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
from datetime import datetime, timedelta
from pathlib import Path

from takki import config
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
    # `days` is every practice day of the key, which is what Known's days
    # floor reads (ADR-027). The per-day table below shows only the window's.
    # A database from just before `practice_days` (#12m session 2) is refused
    # by the store and still dumped here, so the developer can see what it held
    # before deleting it. One older than #12f still fails on missing columns.
    has_days = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'practice_days'"
        ).fetchone()
        is not None
    )
    days_sql = (
        """(SELECT COUNT(*) FROM practice_days AS d
            WHERE d.profile_id = s.profile_id AND d.key_char = s.key_char)"""
        if has_days
        else "'-'"
    )
    rows = conn.execute(
        f"""
        SELECT key_char, attempt_count, correct_count, {days_sql}, last_practised_at
        FROM key_stats AS s
        WHERE profile_id = ?
        ORDER BY key_char
        """,
        (profile_id,),
    ).fetchall()
    print("\nkey_stats (lifetime)")
    if not rows:
        print("  (none)")
        return
    header = f"  {'key':<4} {'attempts':>8} {'correct':>8} {'accuracy':>9} {'days':>5}"
    print(f"{header}  last_practised_at")
    for key_char, attempts, correct, days, last_practised_at in rows:
        accuracy = correct / attempts if attempts else 0.0
        print(
            f"  {key_char:<4} {attempts:>8} {correct:>8} {accuracy:>8.1%} {days:>5}"
            f"  {last_practised_at}"
        )


def _print_attempts_by_day(conn: sqlite3.Connection, profile_id: int) -> None:
    # date(attempted_at, 'localtime'): the calendar day of each row in the
    # window, converted at read. Stored timestamps are UTC (ADR-011). These are
    # the window's days only: Known counts every practice day of a key, from
    # `practice_days`, which the window cannot evict (#12m session 2, E4). They
    # are calendar days, not practice days: a session left open overnight is
    # one practice day and two rows here. Filed in roadmap § D.
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
    """Introduction steps, the ladder's level runs and the bar (ADR-024, ADR-011).

    The only place a resumed ramp-up is observable. Without it, a session that
    paces wrongly after a restart cannot be told apart from one that paces
    wrongly for any other reason -- which is the position alpha-plan #12d was
    diagnosed from.
    """
    steps = conn.execute(
        """
        SELECT step, key_char, position, introduced_at, stable_attempts FROM introductions
        WHERE profile_id = ?
        ORDER BY step, position
        """,
        (profile_id,),
    ).fetchall()
    print("\nintroductions and ramp-up levels")
    if not steps:
        print("  (none)")
        return
    levels: dict[str, str] = {}
    for key_char, level, session_id, started, completed in conn.execute(
        """
        SELECT key_char, level, session_id, started_presses, completed_presses
        FROM ramp_up_levels WHERE profile_id = ?
        ORDER BY id
        """,
        (profile_id,),
    ).fetchall():
        # The letter's lifetime press count where the level began and where its
        # rule was met, and the session the run was in: Reach starts again in
        # a new session. An open end is a level the letter has not met.
        span = f"{level}#{session_id}@{started}-{'' if completed is None else completed}"
        levels[key_char] = f"{levels.get(key_char, '')}{span} "
    print(
        f"  {'step':>4} {'key':<4} {'pos':>3}  {'levels (session@began-met)':<44} "
        f"{'bar':>4} introduced_at"
    )
    for step, key_char, position, introduced_at, stable in steps:
        bar = "-" if stable is None else str(stable)
        print(
            f"  {step:>4} {key_char:<4} {position:>3}  "
            f"{levels.get(key_char, '(none)'):<44} {bar:>4} {introduced_at}"
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


def _print_accuracy_by_previous_prompt(conn: sqlite3.Connection, profile_id: int) -> None:
    # `prev_char` names the prompt before this one, or the finger ids of a rest
    # cue joined by `+` (ADR-011). The split shows whether a letter is answered
    # less well when the child can predict it (a double) than when it follows
    # another letter.
    rows = conn.execute(
        """
        SELECT CASE
                   WHEN prev_char IS NULL THEN 0
                   WHEN length(prev_char) > 1 AND instr(prev_char, '-') > 0 THEN 1
                   WHEN prev_char = key_char THEN 2
                   ELSE 3
               END AS band, COUNT(*), SUM(correct)
        FROM key_attempts
        WHERE profile_id = ?
        GROUP BY band
        ORDER BY band
        """,
        (profile_id,),
    ).fetchall()
    print("\nfirst-press accuracy by the previous prompt")
    if not rows:
        print("  (none)")
        return
    names = (
        "first prompt of a session",
        "after a rest cue",
        "after the same letter",
        "after another letter",
    )
    print(f"  {'previous prompt':<26} {'attempts':>8} {'correct':>8} {'accuracy':>9}")
    for band, attempts, correct in rows:
        print(f"  {names[band]:<26} {attempts:>8} {correct:>8} {correct / attempts:>9.1%}")


def _level_at(conn: sqlite3.Connection, profile_id: int, key_char: str, at: str) -> str:
    row = conn.execute(
        """
        SELECT level FROM ramp_up_levels
        WHERE profile_id = ? AND key_char = ? AND started_at <= ?
          AND (completed_at IS NULL OR completed_at > ?)
        ORDER BY id DESC LIMIT 1
        """,
        (profile_id, key_char, at, at),
    ).fetchone()
    return row[0] if row else "-"


def _print_slow_corrections(conn: sqlite3.Connection, profile_id: int) -> None:
    # A retry press is not an attempt and writes no row, so the gap is not
    # stored. What is stored: the next row's `attempted_at` less its
    # `latency_ms` is when the next letter was sent, and the right key came no
    # later than that. `timeouts` cannot show it: the row is written at the
    # first press, so it counts only the re-asks before that press and never
    # the one that follows a wrong press. The gap is therefore an
    # upper bound, and it is read only where the next row is the next prompt
    # (its `prev_char` is this letter), is timed, and is in the same session.
    # What it cannot see: a Reach prompt or a re-ask (no row), a pause inside
    # the gap, and seconds below the stamps'.
    attempts = conn.execute(
        """
        SELECT rowid, key_char, attempted_at, correct, latency_ms, prev_char, timeouts
        FROM key_attempts
        WHERE profile_id = ?
        ORDER BY rowid
        """,
        (profile_id,),
    ).fetchall()
    starts = [
        row[0]
        for row in conn.execute(
            "SELECT started_at FROM sessions WHERE profile_id = ?", (profile_id,)
        )
    ]
    slow: list[tuple[int, str, str, float, str, str]] = []
    wrong = 0
    # Why a wrong first press has no readable gap. A press that meets several
    # causes is counted under the first that applies, in this order, so the
    # counts add up to the total: last row, next row untimed, next row not the
    # prompt that followed, a session start in between.
    unreadable = {"last": 0, "untimed": 0, "not next": 0, "session": 0}
    for i, (row_id, key_char, at, correct, _, prev_char, _) in enumerate(attempts):
        if correct:
            continue
        wrong += 1
        following = attempts[i + 1] if i + 1 < len(attempts) else None
        if following is None:
            unreadable["last"] += 1
        elif following[4] is None:
            unreadable["untimed"] += 1
        elif following[5] != key_char:
            unreadable["not next"] += 1
        elif any(at < start <= following[2] for start in starts):
            unreadable["session"] += 1
        else:
            sent = datetime.fromisoformat(following[2]) - timedelta(milliseconds=following[4])
            gap = (sent - datetime.fromisoformat(at)).total_seconds()
            if gap > config.PROMPT_TIMEOUT_SECONDS:
                level = _level_at(conn, profile_id, key_char, at)
                slow.append((row_id, at, key_char, gap, level, prev_char or "-"))
    print(
        f"\nslow corrections (wrong first press, right key after more than {config.PROMPT_TIMEOUT_SECONDS:g} s)"
    )
    if not slow:
        print("  (none)")
    else:
        print(f"  {'row':>5} {'first press':<26} {'key':<4} {'gap s':>6} {'level':<7} prev")
        for row_id, at, key_char, gap, level, prev in slow:
            print(f"  {row_id:>5} {at:<26} {key_char:<4} {gap:>6.1f} {level:<7} {prev}")
    print(
        f"  {wrong} wrong first presses, {sum(unreadable.values())} with no readable gap: "
        f"{unreadable['last']} last press in the database, "
        f"{unreadable['untimed']} next prompt untimed, "
        f"{unreadable['not next']} next recorded prompt not the one that followed, "
        f"{unreadable['session']} session start in between; gap is an upper bound"
    )


def _print_reasked_prompts(conn: sqlite3.Connection, profile_id: int) -> None:
    # A prompt that was asked again and then answered, right or wrong. A child
    # who waits out a prompt that did not sound is stored this way, and so is a
    # child who paused; the rows cannot tell them apart.
    print("\nprompts answered after a re-ask (timeouts > 0)")
    reasked = conn.execute(
        """
        SELECT rowid, key_char, attempted_at, latency_ms, prev_char, timeouts
        FROM key_attempts
        WHERE profile_id = ? AND timeouts > 0
        ORDER BY rowid
        """,
        (profile_id,),
    ).fetchall()
    if not reasked:
        print("  (none)")
        return
    print(
        f"  {'row':>5} {'when':<26} {'key':<4} {'timeouts':>8} {'latency ms':>10} {'level':<7} prev"
    )
    for row_id, key_char, at, latency, prev_char, timeouts in reasked:
        shown = "-" if latency is None else str(latency)
        level = _level_at(conn, profile_id, key_char, at)
        print(
            f"  {row_id:>5} {at:<26} {key_char:<4} {timeouts:>8} {shown:>10} "
            f"{level:<7} {prev_char or '-'}"
        )


def _print_reach_presses(conn: sqlite3.Connection, profile_id: int) -> None:
    rows = conn.execute(
        """
        SELECT key_char, COUNT(*), SUM(correct), MIN(pressed_at), MAX(pressed_at)
        FROM reach_presses
        WHERE profile_id = ?
        GROUP BY key_char
        ORDER BY MIN(id)
        """,
        (profile_id,),
    ).fetchall()
    print("\nreach_presses (never trimmed)")
    if not rows:
        print("  (none)")
        return
    print(f"  {'key':<4} {'presses':>7} {'correct':>8} {'accuracy':>9}  first / last")
    for key_char, presses, correct, first, last in rows:
        print(
            f"  {key_char:<4} {presses:>7} {correct:>8} {correct / presses:>9.1%}  {first} / {last}"
        )


def _print_rest_keys(conn: sqlite3.Connection, profile_id: int) -> None:
    rows = conn.execute(
        """
        SELECT finger, key_row, key_col, chosen_by, chosen_at, ready_at, passed_at, replaced_at
        FROM rest_keys
        WHERE profile_id = ?
        ORDER BY id
        """,
        (profile_id,),
    ).fetchall()
    print("\nrest_keys (replaced ones included)")
    if not rows:
        print("  (none)")
        return
    print(
        f"  {'finger':<7} {'cell':<5} {'chosen_by':<9} {'chosen_at':<26} "
        f"{'ready_at':<26} {'passed_at':<26} replaced_at"
    )
    for finger, row, col, chosen_by, chosen_at, ready_at, passed_at, replaced_at in rows:
        print(
            f"  {finger:<7} {f'{row},{col}':<5} {chosen_by:<9} {chosen_at:<26} "
            f"{ready_at or '-':<26} {passed_at or '-':<26} {replaced_at or '-'}"
        )


def _print_landings(conn: sqlite3.Connection, profile_id: int) -> None:
    rows = conn.execute(
        """
        SELECT session_id, round, finger, key_row, key_col, validated, landed_at
        FROM landings
        WHERE profile_id = ?
        ORDER BY id
        """,
        (profile_id,),
    ).fetchall()
    print("\nlandings (the keyboard alignment)")
    if not rows:
        print("  (none)")
        return
    print(f"  {'session':>7} {'round':>5} {'finger':<7} {'cell':<5} {'valid':<5} landed_at")
    for session_id, round_, finger, row, col, validated, landed_at in rows:
        print(
            f"  {session_id:>7} {round_:>5} {finger:<7} {f'{row},{col}':<5} "
            f"{'yes' if validated else 'no':<5} {landed_at}"
        )


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
        _print_accuracy_by_previous_prompt(conn, profile_id)
        _print_slow_corrections(conn, profile_id)
        _print_reasked_prompts(conn, profile_id)
        _print_ramp_up(conn, profile_id)
        _print_reach_presses(conn, profile_id)
        _print_landings(conn, profile_id)
        _print_rest_keys(conn, profile_id)
        _print_milestones(conn, profile_id)
        _print_sessions(conn, profile_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
