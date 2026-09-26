"""
Spike: why does a prompt's letter sometimes go unspoken?

Alpha session 12b-2 (2026-09-26). During the hands-on run the letter for a
new prompt was sometimes never heard: silence until the 10 s re-prompt (B9)
or a re-read tap. It happened with deliberately slow typing, and seemed more
frequent once more keys were in play. A race that needs a keypress in the
last tick of a letter is known (alpha-plan #12c), but slow typing should not
reach it, so something else may be dropping letters.

Runs the real Takki (real SAPI voice, real window, real mixer, real pynput
hook) on a *copy* of the current database, so it starts with the key set the
developer has reached. A bot thread answers every prompt correctly, and only
once its letter has finished speaking, no utterance is in progress, and a
random pause has passed: no keypress ever overlaps speech. Everything the
speech path does is logged with monotonic timestamps, and each prompt's
letter is classified at the end:

    AUDIBLE    SAPI spent a normal letter's time speaking it
    FLAG       SapiTTS.speak() found the cancel flag set on entry and returned
    SHORT      SAPI returned in under MIN_AUDIBLE_S with no flag set
    CUT        the cancel flag was raised while it was speaking
    MISSING    the worker never called speak() for it (cancelled in the queue)

What it cannot see: a letter SAPI renders for its full length that still
never reaches the ear (an output device dropping audio). Listen during the
run; a silence the report calls AUDIBLE points at the output side.

    uv run python spikes/silent_prompt_spike.py [--minutes 15] [--out PATH]

**Do not touch the keyboard or mouse while it runs.** The bot types only
while Takki is the foreground window and the target letter is on the same
key as US; if focus leaves Takki, it waits. Close with the window's X or
Ctrl+C to end early; the report is still written.

The layout is pinned to US inside this process only (as in
listener_coexistence_spike.py); nothing activates a layout. The database is
copied with SQLite's backup API, which reads through the WAL, so the real one
is never opened for writing.
"""

import argparse
import os
import random
import sqlite3
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).parent))

import listener_coexistence_spike as kit

MIN_AUDIBLE_S = 0.5
MARGIN_S = (0.4, 1.2)
LETTER_WAIT_S = 3.0


@dataclass
class Speak:
    text: str
    entered: float
    flag_on_entry: bool
    left: float | None = None
    flag_on_exit: bool = False

    @property
    def duration(self) -> float:
        return (self.left or self.entered) - self.entered


@dataclass
class Log:
    lock: threading.Lock = field(default_factory=threading.Lock)
    speaks: list[Speak] = field(default_factory=list)
    lines: list[tuple[float, str]] = field(default_factory=list)
    prompts: list[tuple[float, str, str, frozenset[str]]] = field(default_factory=list)
    in_speak: Speak | None = None

    def line(self, text: str) -> None:
        with self.lock:
            self.lines.append((time.monotonic(), text))


LOG = Log()
LOOP: list[object] = []


def _instrument() -> None:
    from takki import session, speech
    from takki.audio import pygame_cues, sapi_tts, tts_worker

    original_speak = sapi_tts.SapiTTS.speak

    def speak(self, text: str) -> None:  # type: ignore[no-untyped-def]
        record = Speak(text, time.monotonic(), self._cancel.is_set())
        with LOG.lock:
            LOG.speaks.append(record)
            LOG.in_speak = record
        try:
            original_speak(self, text)
        finally:
            record.left = time.monotonic()
            record.flag_on_exit = self._cancel.is_set()
            with LOG.lock:
                LOG.in_speak = None

    sapi_tts.SapiTTS.speak = speak  # type: ignore[method-assign]

    original_stop = tts_worker.TTSWorker.stop

    def stop(self) -> None:  # type: ignore[no-untyped-def]
        busy = LOG.in_speak is not None
        LOG.line(
            f"worker.stop  last_enqueued={self._last_enqueued} "
            f"cancel_through={self._cancel_through}->{self._last_enqueued} "
            f"worker_speaking={busy}"
        )
        original_stop(self)

    tts_worker.TTSWorker.stop = stop  # type: ignore[method-assign]

    original_enqueue = tts_worker.TTSWorker.enqueue_speak

    def enqueue(self, text: str) -> int:  # type: ignore[no-untyped-def]
        utterance_id = original_enqueue(self, text)
        LOG.line(f"enqueue      id={utterance_id} {text[:40]!r}")
        return utterance_id

    tts_worker.TTSWorker.enqueue_speak = enqueue  # type: ignore[method-assign]

    original_finished = speech.Speaker.on_finished

    def on_finished(self, event) -> bool:  # type: ignore[no-untyped-def]
        LOG.line(f"finished     id={event.utterance_id} {event.status}")
        return original_finished(self, event)

    speech.Speaker.on_finished = on_finished  # type: ignore[method-assign]

    original_init = session.SessionLoop.__init__

    def init(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        original_init(self, *args, **kwargs)
        LOOP.append(self)

    session.SessionLoop.__init__ = init  # type: ignore[method-assign]

    # Every letter a prompt speaks goes through _speak_prompt, the first ask
    # included (_start_prompt calls it), so that is the one place a prompt is
    # recorded; _start_prompt only marks the next one as a first ask.
    starting = threading.local()
    original_start = session.SessionLoop._start_prompt
    original_speak_prompt = session.SessionLoop._speak_prompt

    def start_prompt(self) -> None:  # type: ignore[no-untyped-def]
        starting.value = True
        try:
            original_start(self)
        finally:
            starting.value = False

    def speak_prompt(self) -> None:  # type: ignore[no-untyped-def]
        label = "ask" if getattr(starting, "value", False) else "re-ask"
        keys = frozenset(self._block.prompts)
        with LOG.lock:
            LOG.prompts.append((time.monotonic(), label, self._prompt, keys))
        LOG.line(f"{label:12} {self._prompt!r} block_keys={''.join(sorted(keys))}")
        original_speak_prompt(self)

    session.SessionLoop._start_prompt = start_prompt  # type: ignore[method-assign]
    session.SessionLoop._speak_prompt = speak_prompt  # type: ignore[method-assign]

    def wrap(name: str, label: str) -> None:
        original = getattr(session.SessionLoop, name)

        def wrapped(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            LOG.line(label)
            return original(self, *args, **kwargs)

        setattr(session.SessionLoop, name, wrapped)

    wrap("_on_timeout", "timeout (B9)")
    wrap("_on_restart", "restart")
    wrap("_begin_block", "block boundary")

    original_play = pygame_cues.PygameMixerCues.play

    def play(self, cue: str) -> None:  # type: ignore[no-untyped-def]
        LOG.line(f"cue          {cue}")
        original_play(self, cue)

    pygame_cues.PygameMixerCues.play = play  # type: ignore[method-assign]


def _heard_since(target: str, since: float) -> Speak | None:
    with LOG.lock:
        for record in LOG.speaks:
            if (
                record.text == target
                and record.entered >= since
                and record.left is not None
                and record.duration >= MIN_AUDIBLE_S
                and not record.flag_on_exit
            ):
                return record
    return None


def _bot(minutes: float, rng: random.Random) -> None:
    from takki import config

    user32 = kit._user32()
    us = kit._us_hkl(user32)
    if not kit._wait_for_foreground(user32, config.WINDOW_TITLE, 30):
        LOG.line("bot: Takki never came to the foreground; giving up")
        return
    deadline = time.monotonic() + minutes * 60
    answered = 0
    while time.monotonic() < deadline:
        time.sleep(0.05)
        loop = LOOP[0] if LOOP else None
        target = getattr(loop, "_prompt", None)
        if target is None:
            continue
        with LOG.lock:
            asked = [p for p in LOG.prompts if p[2] == target]
        if not asked:
            continue
        heard = _heard_since(target, asked[-1][0])
        if heard is None or LOG.in_speak is not None:
            continue
        if time.monotonic() < (heard.left or 0) + rng.uniform(*MARGIN_S):
            continue
        if LOG.in_speak is not None or getattr(loop, "_prompt", None) != target:
            continue
        if kit._foreground_title(user32) != config.WINDOW_TITLE:
            continue
        if not kit._types_like_us(user32, kit._foreground_hkl(user32), us, {target}):
            LOG.line(f"bot: foreground layout does not type {target!r} like US; waiting")
            time.sleep(1)
            continue
        vk = kit._vk(user32, us, target)
        LOG.line(f"bot key      {target!r}")
        kit._send(user32, vk, True)
        time.sleep(0.06)
        kit._send(user32, vk, False)
        answered += 1
        time.sleep(0.2)
    LOG.line(f"bot: {minutes:g} minutes up, {answered} answers; stopping Takki")
    if LOOP:
        LOOP[0].stop()  # type: ignore[attr-defined]


def _classify(start: float, target: str, until: float) -> tuple[str, Speak | None]:
    with LOG.lock:
        candidates = [s for s in LOG.speaks if s.text == target and start <= s.entered < until]
    if not candidates:
        return "MISSING", None
    first = candidates[0]
    if first.flag_on_entry:
        return "FLAG", first
    if first.flag_on_exit:
        return "CUT", first
    if first.duration < MIN_AUDIBLE_S:
        return "SHORT", first
    return "AUDIBLE", first


def _report(out: Path, t0: float) -> None:
    with LOG.lock:
        prompts = list(LOG.prompts)
        lines = list(LOG.lines)
    rows = []
    counts: dict[str, int] = {}
    for i, (at, label, target, keys) in enumerate(prompts):
        until = prompts[i + 1][0] if i + 1 < len(prompts) else float("inf")
        verdict, record = _classify(at, target, min(until, at + LETTER_WAIT_S))
        counts[verdict] = counts.get(verdict, 0) + 1
        rows.append((at, label, target, keys, verdict, record))

    with out.open("w", encoding="utf-8") as f:
        f.write("# silent_prompt_spike report\n\n")
        f.write(f"prompts spoken (first asks + re-speaks): {len(rows)}\n")
        for verdict in ("AUDIBLE", "FLAG", "SHORT", "CUT", "MISSING"):
            f.write(f"  {verdict:8} {counts.get(verdict, 0)}\n")
        f.write("\n## Every letter that was not AUDIBLE, with the 3 s of log before it\n")
        for at, label, target, keys, verdict, record in rows:
            if verdict == "AUDIBLE":
                continue
            detail = f" speak {record.duration * 1000:.0f} ms" if record else ""
            f.write(
                f"\n[{at - t0:8.3f}s] {verdict} {label} {target!r}"
                f" block_keys={''.join(sorted(keys))}{detail}\n"
            )
            for when, text in lines:
                if at - 3.0 <= when <= at + LETTER_WAIT_S:
                    f.write(f"    {when - t0:8.3f}s  {text}\n")
        f.write("\n## Full log\n")
        for when, text in lines:
            f.write(f"{when - t0:8.3f}s  {text}\n")
        f.write("\n## Every speak() call\n")
        with LOG.lock:
            for s in LOG.speaks:
                f.write(
                    f"{s.entered - t0:8.3f}s  {s.duration * 1000:6.0f} ms  "
                    f"flag_in={s.flag_on_entry!s:5} flag_out={s.flag_on_exit!s:5} {s.text[:50]!r}\n"
                )
    summary = "  ".join(
        f"{k}={counts.get(k, 0)}" for k in ("AUDIBLE", "FLAG", "SHORT", "CUT", "MISSING")
    )
    print(f"silent_prompt: {len(rows)} prompts spoken; {summary}")
    print(f"report: {out}")


def _copy_db(source: Path, target: Path) -> None:
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


def main() -> int:
    if sys.platform != "win32":
        print("FAIL: Windows only (real SAPI, real window, real pynput).")
        return 1
    parser = argparse.ArgumentParser(description="Find where unspoken prompt letters are lost")
    parser.add_argument("--minutes", type=float, default=15.0)
    parser.add_argument("--out", type=Path, default=Path("spikes/results/silent_prompt.log"))
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    from takki.data_dir import database_path

    real = database_path()
    tmp = Path(tempfile.mkdtemp(prefix="takki-silent-"))
    db = tmp / "takki.sqlite"
    if real.exists():
        _copy_db(real, db)
        print(f"copied {real} -> {db}")
    else:
        print(f"no database at {real}; starting from a cold profile at {db}")

    import takki.main as takki_main
    import takki.platform.windows as windows_platform
    from takki import config

    us = kit._us_hkl(kit._user32())
    takki_main.database_path = lambda: db  # type: ignore[assignment]
    config.LANGUAGE = "en"
    windows_platform.WindowsPlatformInterface.get_layout_positions = (  # type: ignore[method-assign]
        lambda self: windows_platform.read_layout(us)
    )
    _instrument()

    t0 = time.monotonic()
    rng = random.Random(args.seed)
    threading.Thread(target=_bot, args=(args.minutes, rng), daemon=True, name="bot").start()
    code = 0
    try:
        code = takki_main.main()
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        _report(args.out, t0)
    print(f"takki exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
