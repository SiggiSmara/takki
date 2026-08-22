class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self._now = now

    def monotonic(self) -> float:
        return self._now

    def set(self, now: float) -> None:
        self._now = now

    def advance(self, seconds: float) -> None:
        self._now += seconds
