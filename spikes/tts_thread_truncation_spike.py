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
    uv run python spikes/tts_thread_truncation_spike.py busy
    uv run python spikes/tts_thread_truncation_spike.py sapi 1.5
    uv run python spikes/tts_thread_truncation_spike.py repaired 3
    uv run python spikes/tts_thread_truncation_spike.py onecore

Measured on the test laptop, 2026-09-20 — compare a later run against these:

  pump        stuck at 4.0s; finished 0.06s after the MAIN thread pumped
  truncation  3 x 4.42s of audio completed in 2.66s total (audio is CUT)
  audible     'f' 0.944s; the 15-word line 4.424s
  freshengine 6.61s then 5.36s for the 4.42s line -- full speech, ~1.3-1.9s init each
  stopcost    stop() blocked main 1.03-1.55s and did NOT shorten a 0.94s letter

`stopcost`'s numbers are void until truncation is fixed — every one of them was
taken against a truncated utterance. Re-measure before deciding anything.

------------------------------------------------------------------------------
Alpha session 12a-2 (2026-09-20) closed all of it. Four experiments were added
-- `busy` and `sapi` when the defect was fixed, then `repaired` and `onecore`
when the fix was challenged (see CORRECTIONS at the end of this docstring):

    uv run python spikes/tts_thread_truncation_spike.py busy
    uv run python spikes/tts_thread_truncation_spike.py sapi 1.5
    uv run python spikes/tts_thread_truncation_spike.py repaired 3
    uv run python spikes/tts_thread_truncation_spike.py onecore

`busy` is the root cause the earlier runs only described. pyttsx3 leaves its own
DriverProxy._busy False when the first runAndWait() returns, so from the second
utterance on engine.say() runs driver.say() immediately -- outside the loop --
and runAndWait() then pumps the endLoop command it just queued, straight away,
whose driver.stop() issues Speak("", SPF_PURGEBEFORESPEAK) at the utterance that
has only just started. The engine truncates itself, and it is self-perpetuating:
the purge fires its own EndStream, whose handler leaves _busy False again.

`sapi` is the replacement -- SpVoice driven directly, no pyttsx3, no COM event
sink, no message pump. Re-measured on the same laptop, same day:

  truncation  UNCHANGED, and the returns move between runs: 3 x 4.42s of audio
              in 6.28s (2.06s per line today, 0.92s in the run above), so the
              cutoff is not a fixed ~0.9s -- only reliably short
  freshengine 8.11s then 6.55s for the 4.42s line -- but see the CORRECTION
              below: that figure is cold-start contaminated and much too high
  sapi        every utterance full length, first and later alike:
                driver init (first utterance)      2.05s
                letter 'f', 2nd+ utterance         1.36s
                ADR-023 introduction script        7.42s
                15-word line                       5.88s
              stop(): caller blocked 0.000 ms over 8 samples (pyttsx3: ~1.17s),
              audio stops 0.13-0.36s after the call, consistently ~0.2s.
              Interrupting a letter buys little: a 1.36s letter ends at
              ~1.06-1.17s however early the stop lands.

The letter is 1.36s here against 0.94s everywhere above. That is the rate, not
the engine: pyttsx3's SAPI driver sets Rate=2 for its own 200 wpm default, and
SapiTTS pins Rate=0, which is what ADR-003's mapping gives for the default
length_scale of 1.0. Every duration recorded before this session was taken at
the faster rate.

------------------------------------------------------------------------------
CORRECTIONS, same session, after being asked whether the pyttsx3 threading path
had actually been exhausted. It had not, and two figures above are wrong:

  stop() cost   The ~1.17s (and 1.03-1.55s) on record was measured against a
                TRUNCATED engine, which is exactly what this docstring warned
                about and what nobody then applied to the old engine. Repaired
                (see `repaired`), pyttsx3's stop() blocks the caller 94-156 ms,
                not ~1.17s. The honest SapiTTS comparison is 0.000 ms against
                ~100 ms, not against ~1.17s.
  freshengine   8.11s/6.55s was cold-start contaminated. Warm, in the same
                process, a fresh engine per utterance costs ~4.75s for 4.42s of
                audio -- so "a fresh engine per utterance is too slow" does not
                survive measurement either.

And the path itself works. `repaired` demonstrates it:

  repair 1 only   proxy.setBusy(True) after runAndWait() fixes truncation
                  outright -- 3 x 4.42s of audio in 4.64/4.66/4.63s -- but a
                  cancel then corrupts the NEXT utterance: 2/3 lost
  repairs 1+2     plus a ~250ms message pump before restoring the flag, to
                  absorb the EndStream the purge fires after runAndWait()
                  returns: 0/3 lost, full length, stop() 94-156 ms
  repair 3        `onecore` shows _tokenFromId rejecting a OneCore id; assigning
                  the token onto proxy._driver._tts.Voice directly works

startLoop(False) + iterate() also speaks in full (4.58/4.59/4.61s). Note what it
does NOT do: cancelling by leaving that loop returns the caller in 0.000 ms but
the AUDIO KEEPS PLAYING -- SAPI's RunningState stayed at 2 for the full 2.8s
measured afterwards. Leaving the loop stops waiting, not speaking, so ADR-012's
interrupt-on-keypress still needs a purge. (endLoop() against a runAndWait()
worker raises RuntimeError: run loop not started.)

**pyttsx3 was therefore rejected on fragility, not capability.** All three
repairs lean on pyttsx3 internals with no stability guarantee, and the failure
they prevent is SILENT -- which is the property that hid this defect for eleven
sessions. See ADR-003 § The pyttsx3 path was made to work first.
"""

import queue
import sys
import threading
import time
import wave
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
LONG = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"
# A voice Windows 11 installs where pyttsx3 does not look. Any OneCore token
# works; this one is present on the test laptop.
ONECORE_VOICE = (
    "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore"
    "\Voices\Tokens\MSTTS_V110_enUS_MarkM"
)


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


def busy() -> None:
    """Why pyttsx3 truncates: it purges its own utterance, every time after the first.

    _busy is left False when the first runAndWait() returns, so the next say()
    runs outside the loop and the endLoop command runAndWait() queues is pumped
    while SAPI is already speaking -- and endLoop calls driver.stop().
    """
    out: queue.Queue[str] = queue.Queue()

    def worker() -> None:
        # Imported here, not at function scope: comtypes initialises COM on the
        # thread that first imports it, so importing on main leaves this thread
        # with no apartment and CreateObject fails with CO_E_NOTINITIALIZED.
        from pyttsx3.drivers import sapi5

        from takki.audio.fallback_tts import FallbackTTS

        lines: list[str] = []
        original = sapi5.SAPI5Driver.stop

        def traced(self):
            lines.append(
                f"    driver.stop(_speaking={self._speaking}) -> "
                + ("Speak('', PURGE)  <== CUTS THE UTTERANCE" if self._speaking else "no-op")
            )
            return original(self)

        sapi5.SAPI5Driver.stop = traced
        engine = FallbackTTS()
        proxy = engine._engine.proxy
        lines.append(f"  after construction:   _busy={proxy.isBusy()}")
        engine.speak("one")
        lines.append(f"  after 1st runAndWait: _busy={proxy.isBusy()}   <- should be True")
        engine.speak("two")
        lines.append(f"  after 2nd runAndWait: _busy={proxy.isBusy()}")
        out.put("\n".join(lines))

    threading.Thread(target=worker, daemon=True).start()
    print(out.get(timeout=180))


def sapi(press_at: float) -> None:
    """The replacement: SpVoice driven directly. Full length, and a free stop()."""
    from takki.audio.sapi_tts import SapiTTS
    from takki.platform.windows import WindowsPlatformInterface

    voice = WindowsPlatformInterface().find_voice("en")
    commands: queue.Queue[str | None] = queue.Queue()
    results: queue.Queue[float] = queue.Queue()
    ready: queue.Queue[float] = queue.Queue()
    handle: list[SapiTTS] = []

    def worker() -> None:
        start = time.monotonic()
        engine = SapiTTS(voice)
        handle.append(engine)
        engine.speak("warm up")
        ready.put(time.monotonic() - start)
        while True:
            item = commands.get()
            if item is None:
                return
            t0 = time.monotonic()
            engine.speak(item)
            results.put(time.monotonic() - t0)

    threading.Thread(target=worker, daemon=True).start()
    print(f"  construction + first utterance (driver init): {ready.get(timeout=120):.3f}s")
    for label, text in (("letter 'f'", "f"), ("15-word line", LONG)):
        commands.put(text)
        print(f"  {label:14s} full length: {results.get(timeout=120):.3f}s")
    commands.put(LONG)
    time.sleep(press_at)
    t0 = time.monotonic()
    handle[0].stop()
    blocked = time.monotonic() - t0
    ended = results.get(timeout=60)
    print(
        f"  stop() at {press_at:.2f}s: caller blocked {blocked * 1000:.3f} ms, "
        f"audio stopped at {ended:.3f}s (latency {ended - press_at:+.3f}s)"
    )
    commands.put(None)


def repaired(rounds: int) -> None:
    """Can pyttsx3 be repaired in place? Yes -- and this is what it costs.

    Alpha session 12a-2 considered keeping pyttsx3 and patching around the
    defect rather than replacing it. It works. This experiment is kept so the
    rejection stays checkable: it was rejected for depending on three pieces of
    pyttsx3 private state, not for being unable to speak.

    Repair 1  proxy.setBusy(True) after each runAndWait() -- restores the
              invariant pyttsx3 breaks, and fixes truncation on its own.
    Repair 2  pump messages before restoring that flag -- a purge fires its own
              EndStream *after* runAndWait() returns, and its handler knocks
              _busy back down, so a cancel corrupts the NEXT utterance. Without
              this, speech is lost after every interrupt.
    Repair 3  (not exercised here, see `onecore`) assigning the voice token onto
              proxy._driver._tts directly, because _tokenFromId rejects OneCore.
    """
    import pythoncom

    from takki.audio.fallback_tts import FallbackTTS

    commands: queue.Queue[tuple[str, bool] | None] = queue.Queue()
    results: queue.Queue[float] = queue.Queue()
    ready: queue.Queue[bool] = queue.Queue()
    handle: list[object] = []

    def worker() -> None:
        engine = FallbackTTS()._engine
        handle.append(engine)

        def say(text: str, drain: bool) -> None:
            engine.say(text)
            engine.runAndWait()
            if drain:
                deadline = time.monotonic() + 0.25
                while time.monotonic() < deadline:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.01)
            engine.proxy.setBusy(True)

        say("warm up", True)
        ready.put(True)
        while True:
            item = commands.get()
            if item is None:
                return
            text, drain = item
            t0 = time.monotonic()
            say(text, drain)
            results.put(time.monotonic() - t0)

    threading.Thread(target=worker, daemon=True).start()
    ready.get(timeout=120)
    engine = handle[0]

    for drain in (False, True):
        label = "repairs 1+2" if drain else "repair 1 only"
        lost = 0
        print(f"  {label}: cancel, then an UNCANCELLED utterance, x{rounds}")
        for index in range(rounds):
            commands.put((LONG, drain))
            time.sleep(1.2)
            t0 = time.monotonic()
            engine.stop()  # type: ignore[attr-defined]
            blocked = time.monotonic() - t0
            cut = results.get(timeout=120)
            commands.put((LONG, drain))  # nobody cancels this one
            following = results.get(timeout=120)
            good = following > 3.5
            lost += 0 if good else 1
            print(
                f"    round {index + 1}: stop blocked {blocked * 1000:6.1f} ms, "
                f"cancelled at {cut:6.3f}s | next {following:6.3f}s "
                f"<-- {'OK' if good else 'SWALLOWED'}"
            )
        print(f"    -> {lost}/{rounds} utterances lost after a cancel\n")
    commands.put(None)


def onecore() -> None:
    """Repair 3: pyttsx3 rejects a OneCore voice id, and says nothing about it.

    Windows 11's Settings > Time & language > Speech > Manage voices -- the
    remedy main.py prints on EXIT_NO_VOICE -- installs into Speech_OneCore.
    pyttsx3's _tokenFromId only searches SpVoice.GetVoices(), which enumerates
    the SAPI5 category alone, so it raises ValueError -- and DriverProxy._pump
    catches every exception into a notify("error", ...) nobody subscribes to,
    leaving the system default voice in place with no sign anything failed.
    """
    from pyttsx3.engine import Engine

    out: queue.Queue[str] = queue.Queue()

    def worker() -> None:
        lines: list[str] = []
        engine = Engine(driverName=None, debug=False)
        errors: list[BaseException] = []
        engine.connect("error", lambda name, exception: errors.append(exception))
        engine.setProperty("voice", ONECORE_VOICE)
        engine.say("hello")
        engine.runAndWait()
        applied = engine.getProperty("voice")
        lines.append(f"  pyttsx3 setProperty('voice', <OneCore id>):")
        lines.append(f"    error hook saw: {errors[0]!r}" if errors else "    error hook saw: nothing")
        lines.append(f"    voice in use:   {applied.rsplit(chr(92), 1)[-1]}")
        lines.append(
            "    -> APPLIED" if applied == ONECORE_VOICE else "    -> NOT APPLIED, silently"
        )

        # Repair 3: go around _tokenFromId, straight at the COM object.
        import comtypes.client

        token = comtypes.client.CreateObject("SAPI.SpObjectToken")
        token.SetId(ONECORE_VOICE)
        engine.proxy._driver._tts.Voice = token
        in_use = engine.proxy._driver._tts.Voice.Id
        lines.append("  assigned onto proxy._driver._tts.Voice instead:")
        lines.append(f"    voice in use:   {in_use.rsplit(chr(92), 1)[-1]}")
        lines.append("    -> APPLIED" if in_use == ONECORE_VOICE else "    -> still not applied")
        out.put("\n".join(lines))

    threading.Thread(target=worker, daemon=True).start()
    print(out.get(timeout=180))


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
    elif name == "sapi":
        sapi(float(sys.argv[2]) if len(sys.argv) > 2 else 1.5)
    elif name == "repaired":
        repaired(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    elif name in {"pump", "truncation", "freshengine", "busy", "onecore"}:
        globals()[name]()
    else:
        print(f"unknown experiment {name!r}")
        print(__doc__)


if __name__ == "__main__":
    main()
