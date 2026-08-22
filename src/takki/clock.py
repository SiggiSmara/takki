import time
from typing import Protocol


class Clock(Protocol):
    # Monotonic only: every deadline in the app is a duration from now, and
    # wall-clock time can jump backwards mid-drill (NTP, DST). See
    # concurrency-model.md § Timers -- deadlines are checked each tick, never
    # armed on a timer thread.
    def monotonic(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()
