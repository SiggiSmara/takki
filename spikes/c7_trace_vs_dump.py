"""
Spike: C7 -- trace-derived attempt counts against key_attempts, exactly

Alpha session 12b-1 (2026-09-24), for docs/research/windows-validation.md C7.
Reads one section of a pynput_trace_spike.py log and the key_attempts rows
written during it, and checks the engine counted what the keyboard did.

    uv run python spikes/c7_trace_vs_dump.py [trace_log] [--section N] [--db PATH] [--profile ID]

trace_log defaults to spikes/results/pynput_trace.log; --section to the last
one in it (1-based; negative counts from the end). Read-only on the database.

What "derived from the trace" means -- ADR-027 § First-Attempt Counting,
restated as the four rules this script applies, each the one the engine
applies in the file named:

1. An *actuation* is a press of a character key (name None, printable char),
   case-folded with str.lower() -- `classify()` in takki.input.taxonomy.
2. A press of a character already down is an OS auto-repeat and not an
   actuation; a release clears it -- `FocusModel._on_key` / `_on_release`,
   keyed on the folded character.
3. A prompt's *first* actuation is its attempt, correct iff it equals the
   target; later actuations are retries, counted for nothing, until the target
   arrives and the prompt closes -- `AttemptCounter.press`.
4. Escape held to RESTART_HOLD_MS abandons the open prompt without closing
   it; a prompt that had its attempt already keeps it -- `SessionLoop._on_restart`.

The trace does not know what was asked, so targets come from the rows, in
insertion order. That is not circular: each row's target decides only how the
trace is *segmented*; whether a prompt's first actuation was correct, and how
many prompts there were, come from the keyboard. An attempt the engine counted
that the keyboard did not make (a repeat, a retry, a case mismatch) shifts
every later prompt and shows up as a divergence, and the per-attempt time skew
catches an alignment that only matches by coincidence.

What it cannot see, so the run must avoid it: keys typed while Takki is not
the foreground window (dropped by the focus gate) and keys typed while no
prompt is open (an introduction script is speaking; roadmap § D). Both look
like actuations here and like nothing to the engine. Warnings name the
likely cause when the walk diverges.
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from takki import config
from takki.data_dir import database_path
from takki.progress_dump import connect_readonly, first_profile_id

DEFAULT_LOG_PATH = Path(__file__).parent / "results" / "pynput_trace.log"
HEADER = re.compile(r"^=== trace started (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?) ===$")
EVENT = re.compile(r"^\[\s*([\d.]+)s\] (PRESS|RELEASE)\s+char=(.*?)\s+name=(.*)$")
# The engine writes attempted_at at second precision after the frame that
# handled the press; anything outside this is not the press that made the row.
MAX_SKEW_SECONDS = 2.0
NEAR_RESTART_MS = 100


@dataclass(frozen=True)
class Event:
    at: datetime
    pressed: bool
    char: str | None
    name: str | None


@dataclass(frozen=True)
class Actuation:
    at: datetime
    raw: str
    char: str


@dataclass(frozen=True)
class Restart:
    at: datetime


@dataclass(frozen=True)
class Row:
    rowid: int
    key: str
    correct: bool
    at: datetime


@dataclass
class Derived:
    key: str
    correct: bool
    actuation: Actuation


def read_sections(path: Path) -> list[tuple[datetime, list[Event]]]:
    sections: list[tuple[datetime, list[Event]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        header = HEADER.match(line.strip())
        if header:
            sections.append((datetime.fromisoformat(header.group(1)), []))
            continue
        event = EVENT.match(line.strip())
        if event and sections:
            start, events = sections[-1]
            events.append(
                Event(
                    at=start + timedelta(seconds=float(event.group(1))),
                    pressed=event.group(2) == "PRESS",
                    char=ast.literal_eval(event.group(3)),
                    name=ast.literal_eval(event.group(4)),
                )
            )
    return sections


def derive(events: list[Event]) -> tuple[list[Actuation | Restart], dict[str, int], list[str]]:
    """Rules 1, 2 and 4: the timeline of actuations and restarts, plus tallies and warnings."""
    tallies = {
        "press": 0,
        "release": 0,
        "repeat": 0,
        "folded": 0,
        "named": 0,
        "release_mismatch": 0,
    }
    warnings: list[str] = []
    timeline: list[Actuation | Restart] = []
    chars_down: dict[str, str] = {}
    named_down: dict[str, datetime] = {}
    shared = config.REREAD_KEY == config.RESTART_KEY
    hold = timedelta(milliseconds=config.RESTART_HOLD_MS)
    for event in events:
        tallies["press" if event.pressed else "release"] += 1
        if event.name is None:
            if event.char is None or not event.char.isprintable():
                continue
            char = event.char.lower()
            if event.pressed:
                if char in chars_down:
                    tallies["repeat"] += 1
                    continue
                chars_down[char] = event.char
                tallies["folded"] += event.char != char
                timeline.append(Actuation(event.at, event.char, char))
            else:
                pressed_as = chars_down.pop(char, None)
                if pressed_as is not None and pressed_as != event.char:
                    # C2's case: Shift let go first. Folding absorbs it; count it
                    # so the run can say whether it happened at all.
                    tallies["release_mismatch"] += 1
            continue
        tallies["named"] += 1
        name = event.name
        if event.pressed:
            if name in named_down:
                continue
            named_down[name] = event.at
            if name == config.RESTART_KEY and not shared:
                timeline.append(Restart(event.at))
            elif name in ("tab", "cmd", "cmd_l", "cmd_r"):
                warnings.append(
                    f"{event.at:%H:%M:%S.%f} `{name}` pressed -- if focus left Takki, keys typed "
                    "while away were dropped by the focus gate and the walk will not match"
                )
        else:
            down_at = named_down.pop(name, None)
            if down_at is None or name != config.RESTART_KEY or not shared:
                continue
            held = event.at - down_at
            if held >= hold:
                timeline.append(Restart(down_at + hold))
            if abs(held - hold) < timedelta(milliseconds=NEAR_RESTART_MS):
                warnings.append(
                    f"{down_at:%H:%M:%S.%f} Escape held {held.total_seconds() * 1000:.0f} ms, within "
                    f"{NEAR_RESTART_MS} ms of the restart threshold -- read as "
                    f"{'restart' if held >= hold else 're-read'}; the engine may have disagreed"
                )
    end = events[-1].at if events else None
    for name, down_at in named_down.items():
        if name == config.RESTART_KEY and shared and end is not None and end - down_at >= hold:
            timeline.append(Restart(down_at + hold))
    timeline.sort(key=lambda item: item.at)
    return timeline, tallies, warnings


def walk(
    timeline: list[Actuation | Restart], rows: list[Row]
) -> tuple[list[Derived], dict[str, int], list[Actuation]]:
    """Rule 3: segment the actuations into prompts, one target per row."""
    derived: list[Derived] = []
    counts = {"retry": 0, "restart_abandoned": 0, "restart_idle": 0}
    leftover: list[Actuation] = []
    index = 0
    retrying = False
    for item in timeline:
        if isinstance(item, Restart):
            if retrying:
                counts["restart_abandoned"] += 1
                index += 1
                retrying = False
            else:
                counts["restart_idle"] += 1
            continue
        if index >= len(rows):
            leftover.append(item)
            continue
        target = rows[index].key
        if not retrying:
            derived.append(Derived(target, item.char == target, item))
            if item.char == target:
                index += 1
            else:
                retrying = True
        elif item.char == target:
            index += 1
            retrying = False
        else:
            counts["retry"] += 1
    return derived, counts, leftover


def per_key(pairs: list[tuple[str, bool]]) -> dict[str, tuple[int, int]]:
    table: dict[str, tuple[int, int]] = {}
    for key, correct in pairs:
        attempts, right = table.get(key, (0, 0))
        table[key] = (attempts + 1, right + correct)
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description="C7: trace-derived attempt counts vs key_attempts")
    parser.add_argument("trace", type=Path, nargs="?", default=DEFAULT_LOG_PATH)
    parser.add_argument(
        "--section", type=int, default=-1, help="1-based; negative from the end (default -1)"
    )
    parser.add_argument("--db", type=Path, default=None, help="database path (default: main.py's)")
    parser.add_argument("--profile", type=int, default=None, help="profile id (default: first)")
    args = parser.parse_args()

    sections = read_sections(args.trace)
    if not sections:
        print(f"No trace sections in {args.trace}.")
        return 1
    number = args.section if args.section > 0 else len(sections) + args.section + 1
    if not 1 <= number <= len(sections):
        print(f"No section {args.section}; {args.trace} has {len(sections)}.")
        return 1
    start, events = sections[number - 1]
    if not events:
        print(f"Section {number} is empty.")
        return 1
    # Whole seconds either side: attempted_at is truncated to the second.
    window_start = start.replace(microsecond=0)
    window_end = events[-1].at.replace(microsecond=0) + timedelta(seconds=2)

    db_path = args.db if args.db is not None else database_path()
    if not db_path.exists():
        print(f"No database at {db_path}.")
        return 1
    conn = connect_readonly(db_path)
    try:
        profile_id = args.profile if args.profile is not None else first_profile_id(conn)
        if (
            profile_id is None
            or conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone() is None
        ):
            print(f"No profile {profile_id if profile_id is not None else ''} in {db_path}.")
            return 1
        raw_rows = conn.execute(
            """
            SELECT rowid, key_char, correct, attempted_at FROM key_attempts
            WHERE profile_id = ? AND attempted_at >= ?
            ORDER BY rowid
            """,
            (profile_id, window_start.isoformat()),
        ).fetchall()
    finally:
        conn.close()
    rows_all = [Row(r[0], r[1], bool(r[2]), datetime.fromisoformat(r[3])) for r in raw_rows]
    rows = [r for r in rows_all if r.at <= window_end]
    after = len(rows_all) - len(rows)

    timeline, tallies, warnings = derive(events)
    derived, counts, leftover = walk(timeline, rows)
    actuations = [a for a in timeline if isinstance(a, Actuation)]

    print(
        f"Trace: {args.trace} section {number} of {len(sections)}, started {start:%Y-%m-%d %H:%M:%S.%f}"[
            :-3
        ]
    )
    print(
        f"DB:    {db_path} profile {profile_id}; {len(rows)} key_attempts rows in "
        f"[{window_start:%H:%M:%S}, {window_end:%H:%M:%S}]"
        + (f", {after} more after the trace ended (ignored)" if after else "")
    )
    print(
        f"\nTrace: {tallies['press']} presses, {tallies['release']} releases; {tallies['named']} named-key events; "
        f"{tallies['repeat']} held-key repeats removed (rule 2); {len(actuations)} actuations, "
        f"{tallies['folded']} of them upper case (rule 1); {tallies['release_mismatch']} releases reported a different case than their press"
    )
    print(
        f"Walk:  {len(derived)} attempts derived; {counts['retry']} retry presses; "
        f"{counts['restart_abandoned']} restarts abandoning an answered prompt, {counts['restart_idle']} on an unanswered one; "
        f"{len(leftover)} actuations after the last row"
    )

    derived_table = per_key([(d.key, d.correct) for d in derived])
    dump_table = per_key([(r.key, r.correct) for r in rows])
    print(f"\n  {'key':<4} {'trace att':>9} {'trace ok':>9} {'dump att':>9} {'dump ok':>8}")
    for key in sorted(set(derived_table) | set(dump_table)):
        t_att, t_ok = derived_table.get(key, (0, 0))
        d_att, d_ok = dump_table.get(key, (0, 0))
        mark = "" if (t_att, t_ok) == (d_att, d_ok) else "   <-- differs"
        print(f"  {key:<4} {t_att:>9} {t_ok:>9} {d_att:>9} {d_ok:>8}{mark}")
    t_total = (len(derived), sum(d.correct for d in derived))
    d_total = (len(rows), sum(r.correct for r in rows))
    print(f"  {'all':<4} {t_total[0]:>9} {t_total[1]:>9} {d_total[0]:>9} {d_total[1]:>8}")

    divergence = next(
        (i for i, (d, r) in enumerate(zip(derived, rows, strict=False)) if d.correct != r.correct),
        None,
    )
    if divergence is None and len(derived) != len(rows):
        divergence = min(len(derived), len(rows))
    skews = [
        (r.at - d.actuation.at.replace(microsecond=0)).total_seconds()
        for d, r in zip(derived, rows, strict=False)
    ]
    bad_skew = [i for i, s in enumerate(skews) if not -1 <= s <= MAX_SKEW_SECONDS]

    if divergence is not None:
        print(f"\nFirst divergence at prompt {divergence + 1}:")
        for i in range(max(0, divergence - 3), min(max(len(derived), len(rows)), divergence + 4)):
            d = (
                f"{derived[i].actuation.at:%H:%M:%S.%f}"[:-3]
                + f" typed {derived[i].actuation.raw!r} -> {'ok' if derived[i].correct else 'wrong'}"
                if i < len(derived)
                else "(no attempt derived)"
            )
            r = (
                f"row {rows[i].rowid} {rows[i].at:%H:%M:%S} {rows[i].key!r} {'ok' if rows[i].correct else 'wrong'}"
                if i < len(rows)
                else "(no row)"
            )
            print(f"  {'>' if i == divergence else ' '} prompt {i + 1:>3}: trace {d:<40} dump {r}")
    if bad_skew:
        print(
            f"\n{len(bad_skew)} attempts more than {MAX_SKEW_SECONDS:.0f} s from their row, first at prompt {bad_skew[0] + 1} "
            f"({skews[bad_skew[0]]:+.1f} s) -- the alignment matches on flags but not in time"
        )
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  {warning}")

    passed = divergence is None and not bad_skew and len(rows) > 0
    skew_text = (
        f"attempt-to-row skew {min(skews):+.0f}..{max(skews):+.0f} s" if skews else "no rows"
    )
    print(
        f"\nC7: {'PASS' if passed else '**FAIL**'} -- {len(rows)} prompts; trace-derived {t_total[0]} attempts / "
        f"{t_total[1]} correct, dump {d_total[0]} / {d_total[1]}"
        + ("" if divergence is None else f"; diverges at prompt {divergence + 1}")
        + f"; {tallies['repeat']} held repeats, {tallies['folded']} upper-case, {counts['retry']} retries, "
        f"{counts['restart_abandoned'] + counts['restart_idle']} restarts; {skew_text}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
