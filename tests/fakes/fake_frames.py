class FakeFrameLimiter:
    """No-op frame wait. Default-tier tests drive ticks by hand and never sleep."""

    def __init__(self) -> None:
        self.waits = 0

    def wait(self) -> None:
        self.waits += 1
