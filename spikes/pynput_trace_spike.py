"""
Spike: pynput event trace — timestamp, pressed/released, char, name

Split off the front of alpha session #12a (2026-09-20) so #12a's Windows
carry-forward decisions -- letter case above all -- can be read against a
real event log instead of argued from memory. Also feeds
docs/research/windows-validation.md tier C directly (12b): the two ADR-027
input assumptions (auto-repeat emits no release; press/release report the
same char) are read from this trace, not by ear.

Starts a REAL PynputKeyStream -- the production translation path
(takki.input.pynput_stream.translate()), not raw pynput -- so what this
logs is exactly what the engine would see. No lesson engine, no focus
gating, nothing else.

Run from repo root on the Windows laptop:
    uv run python spikes/pynput_trace_spike.py [output_path]

Defaults to spikes/results/pynput_trace.log (appended, not overwritten --
each run adds to the same file so a session's trace isn't lost by re-running
it). Type freely; Ctrl+C in this console to stop.

For C3 (Caps Lock) and C6 (dead-key composition) switch the relevant state
or layout *before* typing the letters you want traced, per
windows-validation.md's tier C instructions.
"""

import queue
import sys
import time
from pathlib import Path

from takki.input import KeyEvent

DEFAULT_LOG_PATH = Path(__file__).parent / "results" / "pynput_trace.log"


def _format_event(t0: float, event: KeyEvent) -> str:
    elapsed = time.perf_counter() - t0
    state = "PRESS  " if event.pressed else "RELEASE"
    return f"[{elapsed:9.3f}s] {state}  char={event.char!r:8s} name={event.name!r}"


def main() -> None:
    if sys.platform != "win32":
        print("FAIL: this spike is Windows-only (PynputKeyStream requires win32).")
        print("Run it on the laptop: uv run python spikes/pynput_trace_spike.py")
        sys.exit(1)

    from takki.input.pynput_stream import PynputKeyStream

    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    inbound: queue.Queue[KeyEvent] = queue.Queue()
    stream = PynputKeyStream(inbound)
    stream.start()

    t0 = time.perf_counter()
    print(f"Logging to {log_path}. Type freely; Ctrl+C here to stop.\n")
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n=== trace started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.flush()
            while True:
                try:
                    event = inbound.get(timeout=0.5)
                except queue.Empty:
                    continue
                line = _format_event(t0, event)
                print(line)
                f.write(line + "\n")
                f.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        stream.join(2.0)
        print(f"\nStopped. Trace appended to {log_path}")


if __name__ == "__main__":
    main()
