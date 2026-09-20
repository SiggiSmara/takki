import time
from typing import Protocol

from takki import config


class Clock(Protocol):
    # Monotonic only: every deadline in the app is a duration from now, and
    # wall-clock time can jump backwards mid-drill (NTP, DST). See
    # concurrency-model.md § Timers -- deadlines are checked each tick, never
    # armed on a timer thread.
    def monotonic(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


class FrameLimiter(Protocol):
    # The `clock.tick(60)` of concurrency-model.md § The loop, kept off `Clock`
    # because the two answer different questions: `Clock` is queried, a limiter
    # is waited on. Tests inject a no-op and drive ticks by hand, which is what
    # keeps the default tier free of real time.
    def wait(self) -> None: ...


class SleepFrameLimiter:
    """Holds the loop at TICK_HZ. The one sanctioned sleep on the main thread.

    concurrency-model.md rule 3 forbids blocking calls there, and this is the
    frame wait its own loop sketch ends on: without it the loop spins a core at
    100% for a 16 ms budget it is nowhere near using. Not pygame's Clock, so
    the core loop needs no pygame import (ADR-019).
    """

    def __init__(self, hz: int = config.TICK_HZ) -> None:
        self._frame = 1.0 / hz
        self._next = time.monotonic()

    def wait(self) -> None:
        self._next += self._frame
        remaining = self._next - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        else:
            # Overran the frame -- do not try to catch up by not sleeping for
            # several frames afterwards; re-base instead.
            self._next = time.monotonic()
