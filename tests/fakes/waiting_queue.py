import queue
from collections.abc import Callable

from takki.audio.tts_worker import Command, TTSWorker


class WaitingCommandQueue(queue.Queue[Command]):
    """The worker's command queue, with a hook run while the worker waits in get().

    That is after the previous utterance has finished and before the worker
    receives the next command -- the moment RS-22c measured a stop() landing
    when a keypress beats the finished letter's `SpeechFinished` through the
    loop. A test drives `run_one()` by hand, so without this the test's stop()
    lands before `run_one()` starts, never while it waits.
    """

    def __init__(self) -> None:
        super().__init__()
        self.while_waiting: Callable[[], None] | None = None

    def get(self, block: bool = True, timeout: float | None = None) -> Command:
        hook, self.while_waiting = self.while_waiting, None
        if hook is not None:
            hook()
        return super().get(block, timeout)


def install(worker: TTSWorker) -> WaitingCommandQueue:
    """Swap in before anything is enqueued."""
    commands = WaitingCommandQueue()
    worker._commands = commands  # pyright: ignore[reportPrivateUsage]
    return commands
