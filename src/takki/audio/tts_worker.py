import itertools
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from takki.audio.tts import TTSEngine


@dataclass(frozen=True)
class Speak:
    text: str
    utterance_id: int


@dataclass(frozen=True)
class Shutdown:
    pass


Command = Speak | Shutdown

SpeechStatus = Literal["completed", "cancelled"]


@dataclass(frozen=True)
class SpeechFinished:
    utterance_id: int
    status: SpeechStatus


class EventSink(Protocol):
    # Not queue.Queue[SpeechFinished]: session 11 passes the core's single
    # inbound queue, which carries every event type, and Queue's parameter is
    # invariant. Structural put() is what the worker actually needs.
    def put(self, item: SpeechFinished, /) -> None: ...


class TTSWorker:
    """Owns a TTSEngine exclusively; commands in, SpeechFinished out (concurrency-model.md § TTS).

    Takes a *factory*, not an engine: "owns" starts at construction, and an
    engine built on another thread and driven from this one does not work at
    all on COM (concurrency-model.md § The engine belongs to the thread that
    creates it). The engine is built as the worker's first act.
    """

    def __init__(self, engine_factory: Callable[[], TTSEngine], outbound: EventSink) -> None:
        self._engine_factory = engine_factory
        self._engine: TTSEngine | None = None
        self._outbound = outbound
        self._commands: queue.Queue[Command] = queue.Queue()
        # Cancellation is a monotonic id threshold, not a flag: everything
        # minted at or before `_cancel_through` is cancelled, and nothing ever
        # clears it. A flag had to be cleared before each utterance, and every
        # place to clear it left a window where a stop() aimed at the command
        # about to be spoken was discarded -- which is how a handed-over
        # utterance played in full despite an interrupt (alpha session 12a-2).
        # `_last_enqueued` is written and read on the main thread only;
        # `_cancel_through` is written there and read by the worker.
        self._last_enqueued = 0
        self._cancel_through = 0
        self._thread: threading.Thread | None = None
        self._built = threading.Event()
        self._build_error: Exception | None = None
        # The single allocator (concurrency-model.md § TTS). Every speaking
        # component used to mint its own ids from 0, so on one worker they
        # collided and the superseded-utterance filter matched the wrong
        # utterance. Minting here leaves no caller able to choose an id.
        # From 1, so 0 is never a live id and "no utterance in flight" can be
        # written as a falsy check without ambiguity.
        self._utterance_ids = itertools.count(1)

    def enqueue_speak(self, text: str) -> int:
        utterance_id = next(self._utterance_ids)
        self._last_enqueued = utterance_id
        self._commands.put(Speak(text, utterance_id))
        return utterance_id

    def enqueue_shutdown(self) -> None:
        self._commands.put(Shutdown())

    def stop(self) -> None:
        """Cancel everything enqueued so far. Main thread."""
        # Raised before the engine is touched, so a worker between the guard in
        # run_one() and its speak() still reports the right status.
        self._cancel_through = self._last_enqueued
        # Read once into a local: the worker assigns it, and None here only
        # means nothing can be sounding yet, which the guard covers on its own.
        engine = self._engine
        if engine is not None:
            engine.stop()

    @property
    def idle(self) -> bool:
        """True when no command is waiting -- for tests that drive run_one() without a thread."""
        return self._commands.empty()

    def build_engine(self) -> TTSEngine:
        """Construct the engine on the calling thread; idempotent.

        `run()` calls it as the worker thread's first act and nothing else
        needs to -- except a test standing in for that thread, which is the
        same reason `run_one()` is public.
        """
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine

    def run_one(self) -> bool:
        """Process one queued command; False on Shutdown. Drivable without a thread, for tests."""
        engine = self.build_engine()
        # Before the blocking get(), never after: from here on every cancel is
        # aimed at the command this call is about to receive, and nothing can
        # clear it out from under that utterance (TTSEngine.clear_cancel()).
        engine.clear_cancel()
        command = self._commands.get()
        if isinstance(command, Shutdown):
            return False
        if command.utterance_id <= self._cancel_through:
            # Cancelled while it sat in the queue: never speak it at all.
            self._outbound.put(SpeechFinished(command.utterance_id, "cancelled"))
            return True
        engine.speak(command.text)
        status: SpeechStatus = (
            "cancelled" if command.utterance_id <= self._cancel_through else "completed"
        )
        self._outbound.put(SpeechFinished(command.utterance_id, status))
        return True

    def run(self) -> None:
        # Builds the engine before the first get() blocks, so construction is
        # this thread's first act even when no command ever arrives.
        try:
            self.build_engine()
        except Exception as error:
            # Handed to start() rather than re-raised here: a dead worker is
            # silent rather than loud -- no SpeechFinished ever arrives, the
            # core's Speaker stays busy forever, and the loop stops issuing
            # prompts, so a blind child gets a running app that says nothing.
            # start() raises it on the thread that can still stop startup.
            self._build_error = error
            self._built.set()
            return
        self._built.set()
        while self.run_one():
            pass

    def start(self) -> None:
        """Start the worker and wait for it to build its engine, re-raising a failure here.

        Blocking is the point: construction has to happen on the worker thread
        (concurrency-model.md § The engine belongs to the thread that creates
        it) but its *failure* has to reach startup, which is where a missing
        voice or a refused COM token can still be reported. Costs the driver
        init -- ~2 s on SAPI -- once, before the loop starts, which is where
        § Startup says one-time work belongs.
        """
        self._thread = threading.Thread(target=self.run, daemon=True, name="tts-worker")
        self._thread.start()
        self._built.wait()
        if self._build_error is not None:
            raise self._build_error

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
