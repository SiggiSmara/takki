"""
Spike: map the keypress window that silences the next letter (alpha-plan #12c (1))

Alpha session 12b-2 (2026-09-27). RS-22b found every unheard letter was a
FLAG: SapiTTS.speak() entered with the cancel flag already set, after a
keypress whose stop() landed once the previous letter had ended. Reading the
code predicts the window exactly:

    TTSWorker.run_one(): speak() returns at R -> put(finished) -> clear_cancel()
                         -> blocks in get()
    SessionLoop.tick():  every 1/TICK_HZ, drains the inbound queue in order.
                         Until `finished` is dispatched, Speaker.interrupt()
                         still calls stop(), which sets the flag.

A key that reaches the queue *before* R but is drained *after* R is dispatched
ahead of `finished`, after the flag was cleared, so its stop() sets a flag
nothing will clear. The next letter enters speak() with it set and is
silent. Prediction, with t the time the key reaches the queue:

    t < last drain before R        the stop cuts the letter: clean
    last drain before R < t < R    SILENT
    t > R                          `finished` is ahead of the key: clean

so a window 0..1/TICK_HZ (~16.7 ms) wide ending at R, its width set by where
R falls in the tick. Measured against the SendInput time the window moves
earlier by the hook latency.

A bot presses the prompted letter at a chosen offset from each letter's
predicted end: R is predicted from the median speak() duration of that
letter so far, which SAPI keeps to a few ms. Offsets are drawn uniformly from
[--lo, --hi] ms, with 10% controls at -400 ms (mid-letter) and +150 ms (well
after). Each trial records the send time, when the loop dispatched the key and
the letter's `finished`, whether the letter was cut, and whether the next
speak() entered with the flag set. When the stop landed after R the letter
was not cut and its real end is known, so those offsets are exact; for cut
letters the offset is against the prediction.

    uv run python spikes/flag_race_sweep.py [--minutes 15] [--lo -60] [--hi 30] [--out PATH]

Real Takki on a copy of the database, as silent_prompt_spike.py; hands off
the machine. Once #12c (1) is fixed, the same run must show no SILENT at any
offset.
"""

import argparse
import csv
import statistics
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import listener_coexistence_spike as kit
import silent_prompt_spike as sp

LEARN_SAMPLES = 3
RECOVER_AFTER_S = 1.5
OUTCOME_WAIT_S = 3.0


@dataclass
class Trial:
    target: str
    kind: str  # sweep | inside | after
    intended_ms: float
    speak: sp.Speak
    predicted_end: float
    sent: float
    key_dispatched: float | None = None
    finished_dispatched: float | None = None
    outcome: str = "none"  # SILENT | spoken | none


TRIAL: list[Trial] = []  # the one armed trial, if any
TRIALS: list[Trial] = []


def _instrument() -> None:
    from takki import session, speech

    original_character = session.SessionLoop._on_character

    def on_character(self, typed) -> None:  # type: ignore[no-untyped-def]
        now = time.perf_counter()
        if TRIAL and TRIAL[0].key_dispatched is None and typed.char == TRIAL[0].target:
            TRIAL[0].key_dispatched = now
        original_character(self, typed)

    session.SessionLoop._on_character = on_character  # type: ignore[method-assign]

    original_finished = speech.Speaker.on_finished

    def on_finished(self, event) -> bool:  # type: ignore[no-untyped-def]
        now = time.perf_counter()
        # The first finished dispatched after the send is the armed letter's:
        # it had been speaking ~1 s, so anything earlier was drained long ago,
        # and the worker is FIFO, so the next letter's comes after it.
        if TRIAL and TRIAL[0].finished_dispatched is None and now >= TRIAL[0].sent:
            TRIAL[0].finished_dispatched = now
        return original_finished(self, event)

    speech.Speaker.on_finished = on_finished  # type: ignore[method-assign]


def _press(user32, us: int, char: str) -> float:  # type: ignore[no-untyped-def]
    vk = kit._vk(user32, us, char)
    sent = time.perf_counter()
    kit._send(user32, vk, True)
    time.sleep(0.03)
    kit._send(user32, vk, False)
    return sent


def _wait_until(deadline: float) -> None:
    # time.sleep is high-resolution on Windows from Python 3.11; spin the last
    # 2 ms, yielding, so the send lands within a fraction of a millisecond.
    remaining = deadline - time.perf_counter()
    if remaining > 0.002:
        time.sleep(remaining - 0.002)
    while time.perf_counter() < deadline:
        time.sleep(0)


def _ready(user32, us: int, char: str) -> bool:  # type: ignore[no-untyped-def]
    from takki import config

    return kit._foreground_title(user32) == config.WINDOW_TITLE and kit._types_like_us(
        user32, kit._foreground_hkl(user32), us, {char}
    )


def _sweep(minutes: float, lo: float, hi: float, seed: int | None) -> None:
    import random

    from takki import config

    rng = random.Random(seed)
    user32 = kit._user32()
    us = kit._us_hkl(user32)
    if not kit._wait_for_foreground(user32, config.WINDOW_TITLE, 30):
        sp.LOG.line("sweep: Takki never came to the foreground; giving up")
        return
    durations: dict[str, list[float]] = {}
    seen: set[int] = set()
    deadline = time.perf_counter() + minutes * 60
    last_activity = time.perf_counter()
    while time.perf_counter() < deadline:
        time.sleep(0.005)
        loop = sp.LOOP[0] if sp.LOOP else None
        target = getattr(loop, "_prompt", None)
        with sp.LOG.lock:
            record = sp.LOG.in_speak
            last = sp.LOG.speaks[-1] if sp.LOG.speaks else None
        if record is not None:
            last_activity = time.perf_counter()
        if target is None or len(target) != 1:
            continue
        if record is None:
            # A prompt open with nothing speaking -- after a SILENT letter, or
            # a letter this loop skipped. Answer it so the lesson moves on.
            quiet_since = (last.p_left or 0) if last else 0
            if time.perf_counter() - max(quiet_since, last_activity) > RECOVER_AFTER_S and _ready(
                user32, us, target
            ):
                _press(user32, us, target)
                last_activity = time.perf_counter()
            continue
        if record.text != target or id(record) in seen:
            continue
        seen.add(id(record))
        history = durations.setdefault(target, [])
        if len(history) < LEARN_SAMPLES:
            # Learn this letter's length: let it end, then answer late.
            while record.p_left is None and time.perf_counter() - record.p_entered < OUTCOME_WAIT_S:
                time.sleep(0.005)
            if record.p_left is not None and not record.flag_on_exit and not record.flag_on_entry:
                history.append(record.p_left - record.p_entered)
            time.sleep(0.3)
            if getattr(loop, "_prompt", None) == target and _ready(user32, us, target):
                _press(user32, us, target)
            continue
        roll = rng.random()
        kind, offset_ms = (
            ("inside", -400.0)
            if roll < 0.1
            else ("after", 150.0)
            if roll < 0.2
            else ("sweep", rng.uniform(lo, hi))
        )
        predicted_end = record.p_entered + statistics.median(history[-7:])
        fire_at = predicted_end + offset_ms / 1000
        if fire_at < time.perf_counter() + 0.003 or not _ready(user32, us, target):
            continue
        trial = Trial(target, kind, offset_ms, record, predicted_end, sent=fire_at)
        TRIAL[:] = [trial]
        _wait_until(fire_at)
        trial.sent = _press(user32, us, target)
        # Outcome: the next speak() to start after the send.
        until = trial.sent + OUTCOME_WAIT_S
        while time.perf_counter() < until:
            with sp.LOG.lock:
                later = [s for s in sp.LOG.speaks if s.p_entered > trial.sent]
            if later:
                trial.outcome = "SILENT" if later[0].flag_on_entry else "spoken"
                break
            time.sleep(0.005)
        if record.p_left is not None and not record.flag_on_exit:
            history.append(record.p_left - record.p_entered)
        TRIAL[:] = []
        TRIALS.append(trial)
        last_activity = time.perf_counter()
    sp.LOG.line(f"sweep: {minutes:g} minutes up, {len(TRIALS)} trials; stopping Takki")
    if sp.LOOP:
        sp.LOOP[0].stop()  # type: ignore[attr-defined]


def _report(out: Path, lo: float, hi: float) -> None:
    rows = []
    for t in TRIALS:
        cut = t.speak.flag_on_exit
        end = t.predicted_end if cut or t.speak.p_left is None else t.speak.p_left
        rows.append(
            {
                "target": t.target,
                "kind": t.kind,
                "intended_ms": round(t.intended_ms, 2),
                "offset_ms": round((t.sent - end) * 1000, 2),
                "offset_basis": "predicted" if cut or t.speak.p_left is None else "actual",
                "prediction_error_ms": ""
                if t.speak.p_left is None or cut
                else round((t.speak.p_left - t.predicted_end) * 1000, 2),
                "letter_cut": cut,
                "key_after_send_ms": ""
                if t.key_dispatched is None
                else round((t.key_dispatched - t.sent) * 1000, 2),
                "key_before_finished": ""
                if t.key_dispatched is None or t.finished_dispatched is None
                else t.key_dispatched < t.finished_dispatched,
                "outcome": t.outcome,
            }
        )
    csv_path = out.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["target"])
        writer.writeheader()
        writer.writerows(rows)

    lines = ["# flag_race_sweep report", ""]
    lines.append(f"trials: {len(rows)}  SILENT: {sum(r['outcome'] == 'SILENT' for r in rows)}")
    for kind in ("inside", "after"):
        group = [r for r in rows if r["kind"] == kind]
        silent = sum(r["outcome"] == "SILENT" for r in group)
        lines.append(f"control {kind:6}: {len(group)} trials, {silent} SILENT")
    errors = [r["prediction_error_ms"] for r in rows if r["prediction_error_ms"] != ""]
    if len(errors) > 1:
        lines.append(
            f"end-of-letter prediction error: median {statistics.median(errors):+.1f} ms, "
            f"sd {statistics.stdev(errors):.1f} ms, n={len(errors)}"
        )
    latency = [r["key_after_send_ms"] for r in rows if r["key_after_send_ms"] != ""]
    if latency:
        lines.append(
            f"send -> key dispatched: median {statistics.median(latency):.1f} ms, "
            f"max {max(latency):.1f} ms (hook latency + wait for the tick)"
        )
    order = [r for r in rows if r["key_before_finished"] != ""]
    rule = sum(
        (r["outcome"] == "SILENT") == (r["key_before_finished"] is True and not r["letter_cut"])
        for r in order
    )
    lines.append(
        f"rule 'SILENT iff key dispatched before finished and the letter was not cut': "
        f"holds on {rule} of {len(order)}"
    )
    # After the #12c (1) fix the rule above stops holding, so a clean run needs
    # its own evidence that the race actually occurred.
    race = [r for r in order if r["key_before_finished"] is True and not r["letter_cut"]]
    lines.append(
        f"race hit (key dispatched before finished, letter not cut): {len(race)}, "
        f"SILENT: {sum(r['outcome'] == 'SILENT' for r in race)}"
    )
    lines += ["", "offset from the letter's end (send time), 2 ms bins, sweep trials:", ""]
    lines.append("   bin (ms)      n  SILENT  cut  basis")
    sweep = [r for r in rows if r["kind"] == "sweep"]
    edge = lo
    while edge < hi:
        group = [r for r in sweep if edge <= r["offset_ms"] < edge + 2]
        if group:
            silent = sum(r["outcome"] == "SILENT" for r in group)
            cut = sum(bool(r["letter_cut"]) for r in group)
            actual = sum(r["offset_basis"] == "actual" for r in group)
            bar = "#" * silent
            lines.append(
                f"  [{edge:+5.0f},{edge + 2:+5.0f})  {len(group):4d}  {silent:6d}  {cut:3d}  "
                f"{actual}/{len(group)} actual  {bar}"
            )
        edge += 2
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"report: {out}\ntrials: {csv_path}")


def main() -> int:
    if sys.platform != "win32":
        print("FAIL: Windows only (real SAPI, real window, real pynput).")
        return 1
    parser = argparse.ArgumentParser(
        description="Map the keypress window that silences the next letter"
    )
    parser.add_argument("--minutes", type=float, default=15.0)
    parser.add_argument(
        "--lo", type=float, default=-60.0, help="earliest offset, ms from the letter's end"
    )
    parser.add_argument(
        "--hi", type=float, default=30.0, help="latest offset, ms from the letter's end"
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("spikes/results/flag_race_sweep.txt"))
    args = parser.parse_args()

    from takki.data_dir import database_path

    real = database_path()
    tmp = Path(tempfile.mkdtemp(prefix="takki-sweep-"))
    db = tmp / "takki.sqlite"
    if real.exists():
        sp._copy_db(real, db)
        print(f"copied {real} -> {db}")

    import takki.main as takki_main
    import takki.platform.windows as windows_platform
    from takki import config

    us = kit._us_hkl(kit._user32())
    takki_main.database_path = lambda: db  # type: ignore[assignment]
    config.LANGUAGE = "en"
    windows_platform.WindowsPlatformInterface.get_layout_positions = (  # type: ignore[method-assign]
        lambda self: windows_platform.read_layout(us)
    )
    sp._instrument()
    _instrument()

    threading.Thread(
        target=_sweep, args=(args.minutes, args.lo, args.hi, args.seed), daemon=True, name="sweep"
    ).start()
    code = 0
    try:
        code = takki_main.main()
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        _report(args.out, args.lo, args.hi)
    print(f"takki exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
