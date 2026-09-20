"""
Spike: the two SAPI defects alpha session 12a-2 has to fix, as runnable proofs.

Written 2026-09-20, during the pre-12a review. Both defects are silent — one
hangs a worker forever, the other truncates speech — and neither is guessable
from the code, so the arguments in docs/concurrency-model.md lean on these
measurements. They are here so that section stays checkable rather than
becoming folklore:

  § The engine belongs to the thread that creates it   -> `pump`
  § SAPI speaks only the first utterance in full       -> `truncation`, `audible`

Windows only, and every experiment needs real SAPI. Run from the repo root:

    uv run python spikes/tts_thread_truncation_spike.py pump
    uv run python spikes/tts_thread_truncation_spike.py truncation
    uv run python spikes/tts_thread_truncation_spike.py audible "some text"
    uv run python spikes/tts_thread_truncation_spike.py freshengine
    uv run python spikes/tts_thread_truncation_spike.py stopcost 0.45

Measured on the test laptop, 2026-09-20 — compare a later run against these:

  pump        stuck at 4.0s; finished 0.06s after the MAIN thread pumped
  truncation  3 x 4.42s of audio completed in 2.66s total (audio is CUT)
  audible     'f' 0.944s; the 15-word line 4.424s
  freshengine 6.61s then 5.36s for the 4.42s line -- full speech, ~1.3-1.9s init each
  stopcost    stop() blocked main 1.03-1.55s and did NOT shorten a 0.94s letter

`stopcost`'s numbers are void until truncation is fixed — every one of them was
taken against a truncated utterance. Re-measure before deciding anything.
"""

import queue
import sys
import threading
import time
import wave
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
LONG = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"


def _require_windows() -> None:
    if sys.platform != "win32":
        print("FAIL: this spike needs real SAPI. Run it on the Windows laptop.")
        sys.exit(1)


def pump() -> None:
    """Prove the hang is message delivery, not blocking.

    An engine built on the main thread and spoken from a worker never finishes,
    because SAPI's completion event is delivered to the *creating* thread's
    message queue while the worker pumps its own. If that is the mechanism,
    the worker completes the moment the MAIN thread starts pumping.
    """
    import pythoncom

    from takki.audio.fallback_tts import FallbackTTS

    engine = FallbackTTS()  # created on the MAIN thread
    done = threading.Event()
    threading.Thread(target=lambda: (engine.speak("hello there"), done.set()), daemon=True).start()

    time.sleep(4)
    print(f"after 4s with no pump on main: finished={done.is_set()}")

    t0 = time.monotonic()
    while not done.is_set() and time.monotonic() - t0 < 15:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.05)
    print(
        f"after main started pumping:    finished={done.is_set()} "
        f"({time.monotonic() - t0:.2f}s of pumping)"
    )


def truncation() -> None:
    """Three long lines on one engine. Sequential audio would take ~13.3s."""
    from takki.audio.fallback_tts import FallbackTTS

    out: queue.Queue[str] = queue.Queue()

    def worker() -> None:
        engine = FallbackTTS()
        engine.speak("warm up")  # make every timed line a 2nd+ utterance
        lines = []
        t_all = time.monotonic()
        for i in range(3):
            t0 = time.monotonic()
            engine.speak(LONG)
            lines.append(f"  line {i + 1}: speak() returned after {time.monotonic() - t0:.3f}s")
        total = time.monotonic() - t_all
        lines.append(f"  TOTAL for 3 x 4.42s of audio: {total:.3f}s")
        lines.append("  -> audio sequential" if total > 10 else "  -> AUDIO IS BEING CUT OFF")
        out.put("\n".join(lines))

    threading.Thread(target=worker, daemon=True).start()
    print(out.get(timeout=180))


def audible(text: str) -> None:
    """Synthesized length of `text`, for comparison against speak()'s return time.

    A fresh Engine per call on purpose: a second runAndWait() on one engine is
    the very defect under investigation, so reusing one here would measure it
    instead of the audio.
    """
    from pyttsx3.engine import Engine

    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "spike_audible.wav"
    engine = Engine(driverName=None, debug=False)
    engine.save_to_file(text, str(path))
    engine.runAndWait()
    with wave.open(str(path)) as handle:
        print(f"{text[:40]!r}: {handle.getnframes() / handle.getframerate():.3f}s audible")


def freshengine() -> None:
    """Does a fresh engine per utterance speak in full? (The obvious workaround.)"""
    from takki.audio.fallback_tts import FallbackTTS

    out: queue.Queue[str] = queue.Queue()

    def worker() -> None:
        lines = []
        for i in range(2):
            t0 = time.monotonic()
            FallbackTTS().speak(LONG)
            lines.append(f"  fresh engine, line {i + 1}: {time.monotonic() - t0:.3f}s (audio 4.42s)")
        out.put("\n".join(lines))

    threading.Thread(target=worker, daemon=True).start()
    print(out.get(timeout=180))


def stopcost(press_at: float) -> None:
    """Production shape: one worker builds AND speaks; main only calls stop()."""
    from takki.audio.fallback_tts import FallbackTTS

    commands: queue.Queue[str] = queue.Queue()
    results: queue.Queue[float] = queue.Queue()
    ready = threading.Event()
    handle: list[FallbackTTS] = []

    def worker() -> None:
        engine = FallbackTTS()
        handle.append(engine)
        engine.speak("warm up")
        ready.set()
        while True:
            item = commands.get()
            if item == "quit":
                return
            t0 = time.monotonic()
            engine.speak(item)
            results.put(time.monotonic() - t0)

    threading.Thread(target=worker, daemon=True).start()
    ready.wait(60)
    commands.put("f")
    time.sleep(press_at)
    t0 = time.monotonic()
    handle[0].stop()
    blocked = time.monotonic() - t0
    print(
        f"press_at={press_at:.2f}s  stop() blocked main {blocked:.3f}s  "
        f"utterance ended at {results.get(timeout=30):.3f}s"
    )
    commands.put("quit")


def main() -> None:
    _require_windows()
    if len(sys.argv) < 2:
        print(__doc__)
        return
    name = sys.argv[1]
    if name == "audible":
        audible(sys.argv[2] if len(sys.argv) > 2 else LONG)
    elif name == "stopcost":
        stopcost(float(sys.argv[2]) if len(sys.argv) > 2 else 0.45)
    elif name in {"pump", "truncation", "freshengine"}:
        globals()[name]()
    else:
        print(f"unknown experiment {name!r}")
        print(__doc__)


if __name__ == "__main__":
    main()
