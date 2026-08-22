from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class KeyEvent:
    pressed: bool
    char: str | None
    name: str | None


class EventSink(Protocol):
    # Structural put(), not queue.Queue[KeyEvent] -- session 11 passes the
    # core's single inbound queue, which carries every event type, and
    # Queue's parameter is invariant.
    def put(self, item: KeyEvent, /) -> None: ...


class KeyEventStream(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...
