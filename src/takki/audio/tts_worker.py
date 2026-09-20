import itertools
import queue
import threading
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
    """Owns a TTSEngine exclusively; commands in, SpeechFinished out (concurrency-model.md § TTS)."""

    def __init__(self, engine: TTSEngine, outbound: EventSink) -> None:
        self._engine = engine
        self._outbound = outbound
        self._commands: queue.Queue[Command] = queue.Queue()
        self._cancel_requested = threading.Event()
        self._thread: threading.Thread | None = None
        # The single allocator (concurrency-model.md § TTS). Every speaking
        # component used to mint its own ids from 0, so on one worker they
        # collided and the superseded-utterance filter matched the wrong
        # utterance. Minting here leaves no caller able to choose an id.
        # From 1, so 0 is never a live id and "no utterance in flight" can be
        # written as a falsy check without ambiguity.
        self._utterance_ids = itertools.count(1)

    def enqueue_speak(self, text: str) -> int:
        utterance_id = next(self._utterance_ids)
        self._commands.put(Speak(text, utterance_id))
        return utterance_id

    def enqueue_shutdown(self) -> None:
        self._commands.put(Shutdown())

    def stop(self) -> None:
        # The one sanctioned cross-thread call (concurrency-model.md rule 4).
        self._cancel_requested.set()
        self._engine.stop()

    @property
    def idle(self) -> bool:
        """True when no command is waiting -- for tests that drive run_one() without a thread."""
        return self._commands.empty()

    def run_one(self) -> bool:
        """Process one queued command; False on Shutdown. Drivable without a thread, for tests."""
        command = self._commands.get()
        if isinstance(command, Shutdown):
            return False
        self._cancel_requested.clear()
        self._engine.speak(command.text)
        status: SpeechStatus = "cancelled" if self._cancel_requested.is_set() else "completed"
        self._outbound.put(SpeechFinished(command.utterance_id, status))
        return True

    def run(self) -> None:
        while self.run_one():
            pass

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, daemon=True, name="tts-worker")
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
